import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
from pathlib import Path
from functools import wraps
from urllib.parse import urlparse

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

import razorpay
from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth
from flask import Flask, g, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from itsdangerous import BadSignature, URLSafeSerializer
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from ai_parser import normalize_phone
from chatbot_flow import ChatbotFlow
from delivery_config import AVAILABLE_CITIES, CITIES, COMING_SOON_PRODUCTS, ORDER_STATUSES, PRODUCTS, city_by_choice, get_delivery_schedule
from email_service import build_order_confirmation, send_resend_email
from order_manager import OrderManager
from usage_monitor import usage_health_report


load_dotenv()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


def clean_env(name, default=""):
    value = os.getenv(name, default)
    if value is None:
        return default
    return str(value).strip().lstrip("\ufeff").replace("\r", "").replace("\n", "").strip()


def clean_int_env(name, default):
    try:
        return int(clean_env(name, str(default)) or default)
    except (TypeError, ValueError):
        return default


configured_secret_key = clean_env("SECRET_KEY")
SESSION_SECRET_CONFIGURED = bool(configured_secret_key)
if not configured_secret_key:
    configured_secret_key = secrets.token_urlsafe(48)
    app.logger.warning("SECRET_KEY is not configured; using an ephemeral local key")
app.config["SECRET_KEY"] = configured_secret_key
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = bool(os.getenv("VERCEL"))
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["MAX_CONTENT_LENGTH"] = clean_int_env("MAX_REQUEST_BYTES", 262144)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 31536000

STATIC_CACHE_CONTROL = "public, max-age=31536000, s-maxage=31536000, immutable"
NO_CACHE_CONTROL = "no-cache, no-store, must-revalidate"
SLOW_REQUEST_MS = clean_int_env("SLOW_REQUEST_MS", 1200)
DYNAMIC_LOG_PREFIXES = ("/api/", "/admin", "/auth/", "/webhook", "/send-order")


def wants_json_response():
    return request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json"


def log_checkout(event, **details):
    payload = {
        "event": event,
        "path": request.path if request else "",
        "method": request.method if request else "",
        **details,
    }
    try:
        app.logger.info(json.dumps(payload, default=str, ensure_ascii=True))
    except Exception:
        app.logger.info(f"{event} {details}")


def log_json(level, **payload):
    try:
        message = json.dumps(payload, default=str, ensure_ascii=True)
    except Exception:
        message = str(payload)
    getattr(app.logger, level)(message)


@app.before_request
def mark_request_start():
    g.request_started_at = time.perf_counter()


@app.after_request
def finalize_response(response):
    if request.path.startswith("/static/") or request.path in {"/favicon.ico", "/apple-touch-icon.png"}:
        response.headers["Cache-Control"] = STATIC_CACHE_CONTROL
    elif should_disable_cache(response):
        response.headers["Cache-Control"] = NO_CACHE_CONTROL
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["Vary"] = "Cookie"
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.is_secure:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    log_request_summary(response)
    return response


def should_disable_cache(response):
    if any(request.path.startswith(prefix) for prefix in DYNAMIC_LOG_PREFIXES):
        return True
    return bool(response.content_type and response.content_type.startswith("text/html"))


def should_log_request():
    if request.path.startswith("/static/") or request.path in {"/favicon.ico", "/apple-touch-icon.png"}:
        return False
    return any(request.path.startswith(prefix) for prefix in DYNAMIC_LOG_PREFIXES) or request.path == "/"


def log_request_summary(response):
    if not should_log_request():
        return
    started_at = getattr(g, "request_started_at", None)
    duration_ms = int(round((time.perf_counter() - started_at) * 1000)) if started_at else None
    payload = {
        "event": "request_complete",
        "method": request.method,
        "path": request.path,
        "status": response.status_code,
        "duration_ms": duration_ms,
        "request_id": request.headers.get("x-vercel-id") or request.headers.get("x-request-id", ""),
        "content_length": response.calculate_content_length(),
    }
    if response.status_code >= 500:
        level = "error"
    elif duration_ms is not None and duration_ms >= SLOW_REQUEST_MS:
        level = "warning"
        payload["slow_request_ms"] = SLOW_REQUEST_MS
    else:
        level = "info"
    log_json(level, **payload)


@app.errorhandler(HTTPException)
def handle_http_error(error):
    if wants_json_response():
        return jsonify({"ok": False, "error": error.description or error.name}), error.code
    return error


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    if wants_json_response():
        if "order_manager" in globals() and order_manager.sheets.is_rate_limit_error(error):
            app.logger.exception("Google Sheets rate limit reached")
            return jsonify({"ok": False, "error": "Orders are briefly busy right now. Please try again in a minute."}), 503
        app.logger.exception("Unhandled API error")
        return jsonify({"ok": False, "error": "Something went wrong. Please refresh and try again."}), 500
    raise error

order_manager = OrderManager()
chatbot = ChatbotFlow(order_manager=order_manager)
oauth = OAuth(app)

if clean_env("GOOGLE_OAUTH_CLIENT_ID") and clean_env("GOOGLE_OAUTH_CLIENT_SECRET"):
    oauth.register(
        name="google",
        client_id=clean_env("GOOGLE_OAUTH_CLIENT_ID"),
        client_secret=clean_env("GOOGLE_OAUTH_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


def google_oauth_enabled():
    return SESSION_SECRET_CONFIGURED and "google" in oauth._clients


def customer_login_required():
    return True


def offline_order_admin_email():
    return clean_env("OFFLINE_ORDER_ADMIN_EMAIL", "pulpsandleaves@gmail.com").lower()


def is_offline_order_admin(customer):
    identity = customer_payload(customer)
    email = str((identity or {}).get("email", "")).strip().lower()
    return bool(email and hmac.compare_digest(email, offline_order_admin_email()))


def prepare_order_payload(payload, customer):
    offline_order_admin = is_offline_order_admin(customer)
    if offline_order_admin:
        payload["city"] = "bangalore"
        payload["address"] = ""
    return offline_order_admin


def razorpay_config():
    return {
        "key_id": clean_env("RAZORPAY_KEY_ID"),
        "key_secret": clean_env("RAZORPAY_KEY_SECRET"),
        "enabled": clean_env("RAZORPAY_ENABLED", "false").lower() in {"1", "true", "yes", "on"},
    }


def razorpay_enabled():
    config = razorpay_config()
    return bool(SESSION_SECRET_CONFIGURED and config["enabled"] and config["key_id"] and config["key_secret"])


def razorpay_client():
    config = razorpay_config()
    client = razorpay.Client(auth=(config["key_id"], config["key_secret"]))
    client.set_app_details({"title": "Pulps & Leaves", "version": "1.0"})
    return client


def support_phone():
    return clean_env("SUPPORT_PHONE", "+91 98354 96666")


def support_email():
    return clean_env("SUPPORT_EMAIL", "pulpsandleaves@gmail.com")


def send_order_confirmation_email(order):
    if str(order.get("Source", "")).strip() != "Website":
        return False

    to_email = str(order.get("Customer Email", "")).strip()
    if not to_email:
        return False

    api_key = clean_env("RESEND_API_KEY")
    from_email = clean_env("ORDER_CONFIRMATION_FROM_EMAIL")
    reply_to = clean_env("ORDER_CONFIRMATION_REPLY_TO")
    if not api_key or not from_email:
        app.logger.info("Order confirmation email skipped because Resend is not configured")
        return False

    message = build_order_confirmation(order, support_phone(), support_email())
    send_resend_email(
        api_key=api_key,
        from_email=from_email,
        to_email=to_email,
        subject=message["subject"],
        html=message["html"],
        text=message["text"],
        reply_to=reply_to or None,
        timeout=max(1, clean_int_env("ORDER_CONFIRMATION_TIMEOUT_SECONDS", 3)),
    )
    return True


def public_customer_order(order):
    return {
        "order_id": order.get("Order ID", ""),
        "timestamp": order.get("Timestamp", ""),
        "product": order.get("Product", ""),
        "quantity": order.get("Quantity", ""),
        "total_amount": order.get("Total Amount", ""),
        "payment_mode": order.get("Payment Mode", ""),
        "payment_status": order.get("Payment Status", ""),
        "order_status": order.get("Order Status", ""),
        "city": order.get("City", ""),
        "address": order.get("Address", ""),
    }


def public_order_receipt(order):
    return {
        "Order ID": order.get("Order ID", ""),
        "Timestamp": order.get("Timestamp", ""),
        "Product": order.get("Product", ""),
        "Quantity": order.get("Quantity", ""),
        "Total Amount": order.get("Total Amount", ""),
        "Payment Mode": order.get("Payment Mode", ""),
        "Payment Status": order.get("Payment Status", ""),
        "Order Status": order.get("Order Status", ""),
        "City": order.get("City", ""),
        "Address": order.get("Address", ""),
    }


def order_belongs_to_customer(order, customer):
    identity = customer_payload(customer)
    if not order or not identity:
        return False
    google_subject = str(identity.get("google_subject", "")).strip()
    email = str(identity.get("email", "")).strip().lower()
    order_subject = str(order.get("Google Subject", "")).strip()
    order_email = str(order.get("Customer Email", "")).strip().lower()
    return bool(
        (google_subject and order_subject and hmac.compare_digest(order_subject, google_subject))
        or (email and order_email and hmac.compare_digest(order_email, email))
    )


def customer_order_or_none(order_id, customer):
    order, error = order_manager.validate_order_id(order_id)
    if error or not order_belongs_to_customer(order, customer):
        return None
    return order


def verify_razorpay_signature(order_id, payment_id, signature):
    secret = razorpay_config()["key_secret"]
    message = f"{order_id}|{payment_id}".encode()
    digest = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, str(signature or ""))


def razorpay_state_serializer():
    return URLSafeSerializer(app.config["SECRET_KEY"], salt="razorpay-pending-order")


def build_razorpay_verification_token(order_id, payload, amount):
    return razorpay_state_serializer().dumps(
        {
            "order_id": order_id,
            "payload": payload,
            "amount": amount,
            "created_at": int(time.time()),
        }
    )


def parse_razorpay_verification_token(token, expected_order_id):
    if not token:
        return None
    try:
        data = razorpay_state_serializer().loads(token)
    except BadSignature:
        return None
    if str(data.get("order_id", "")).strip() != str(expected_order_id or "").strip():
        return None
    created_at = int(data.get("created_at", 0) or 0)
    if not created_at or (time.time() - created_at) > 3600:
        return None
    return data


def current_customer():
    customer = session.get("customer")
    if not customer:
        return None
    if not isinstance(customer, dict):
        session.pop("customer", None)
        return None

    try:
        return customer_payload(customer)
    except Exception:
        session.pop("customer", None)
        return None


def remember_completed_order(order):
    # Remove legacy cookie payloads. Orders now live only in persistent storage.
    session.pop("completed_checkout_orders", None)
    session.pop("pending_razorpay_orders", None)
    session.pop("order_history_cache", None)


def find_completed_order_by_checkout_token(checkout_token):
    if not checkout_token:
        return None
    return order_manager.find_order_by_checkout_token(checkout_token)


def find_completed_order_by_payment_id(payment_id):
    if not payment_id:
        return None
    return order_manager.find_order_by_payment_id(payment_id)


def customer_payload(customer):
    if not customer:
        return None
    return {
        "google_subject": customer.get("Google Subject") or customer.get("google_subject", ""),
        "email": customer.get("Email") or customer.get("email", ""),
        "name": customer.get("Name") or customer.get("name", ""),
        "picture": customer.get("Picture") or customer.get("picture", ""),
        "phone": customer.get("Phone") or customer.get("phone", ""),
        "city": customer.get("Default City") or customer.get("city", ""),
        "address": customer.get("Default Address") or customer.get("address", ""),
        "created_at": customer.get("Created At") or customer.get("created_at", ""),
        "updated_at": customer.get("Updated At") or customer.get("updated_at", ""),
    }


def remember_customer_checkout_details(phone="", city="", address=""):
    customer = session.get("customer")
    if not isinstance(customer, dict):
        return
    normalized = customer_payload(customer) or {}
    if phone:
        normalized["phone"] = phone
    if city:
        normalized["city"] = city
    if address:
        normalized["address"] = address
    session["customer"] = normalized


def safe_next_url(raw_next):
    if not raw_next:
        return url_for("index")
    parsed = urlparse(raw_next)
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return url_for("index")
    if parsed.netloc:
        next_host = parsed.netloc.split("@")[-1].split(":")[0].lower()
        request_host = request.host.split(":")[0].lower()
        allowed_hosts = {request_host, request_host.removeprefix("www.")}
        if not request_host.startswith("www."):
            allowed_hosts.add(f"www.{request_host}")
        if next_host not in allowed_hosts:
            return url_for("index")
        path = parsed.path or url_for("index")
        query = f"?{parsed.query}" if parsed.query else ""
        fragment = f"#{parsed.fragment}" if parsed.fragment else ""
        return f"{path}{query}{fragment}"
    if not str(raw_next).startswith("/"):
        return url_for("index")
    return raw_next


def google_callback_url():
    current_url = url_for("google_callback", _external=True)
    configured_url = clean_env("GOOGLE_OAUTH_REDIRECT_URI")
    if not configured_url:
        return current_url

    current_host = urlparse(current_url).netloc.lower()
    configured_host = urlparse(configured_url).netloc.lower()
    if current_host == configured_host:
        return configured_url
    if current_host.split(":")[0] in {"pulpsandleaves.com", "www.pulpsandleaves.com"}:
        return current_url
    return configured_url


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        username = clean_env("ADMIN_USERNAME")
        password = clean_env("ADMIN_PASSWORD")
        if not username or not password:
            return "Admin access is not configured", 503
        auth_header = request.headers.get("Authorization", "")
        expected = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
        if not hmac.compare_digest(auth_header, expected):
            return (
                "Admin login required",
                401,
                {"WWW-Authenticate": 'Basic realm="Pulps & Leaves Admin"'},
            )
        return view(*args, **kwargs)

    return wrapper


def outbound_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        token = clean_env("OUTBOUND_CONFIRMATION_SECRET")
        auth_header = request.headers.get("Authorization", "")
        webhook_header = request.headers.get("X-Webhook-Secret", "")
        expected = f"Bearer {token}" if token else ""
        username = clean_env("ADMIN_USERNAME")
        password = clean_env("ADMIN_PASSWORD")
        admin_expected = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode() if username and password else ""
        bearer_ok = bool(token and hmac.compare_digest(auth_header, expected))
        webhook_ok = bool(token and hmac.compare_digest(webhook_header, token))
        admin_ok = bool(admin_expected and hmac.compare_digest(auth_header, admin_expected))
        if not token and not admin_expected:
            return jsonify({"ok": False, "error": "Service authentication is not configured."}), 503
        if not (bearer_ok or webhook_ok or admin_ok):
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        return view(*args, **kwargs)

    return wrapper


def meta_webhook_signature_valid():
    app_secret = clean_env("META_APP_SECRET")
    supplied = request.headers.get("X-Hub-Signature-256", "")
    if not app_secret or not supplied.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(app_secret.encode(), request.get_data(cache=True), hashlib.sha256).hexdigest()
    return hmac.compare_digest(supplied, expected)


def ordering_unavailable_response():
    return jsonify({"ok": False, "error": "Online payment is not available for pre-order inquiries right now."}), 503


@app.get("/")
def index():
    customer = customer_payload(current_customer())
    customer_authenticated = bool(customer and (customer.get("google_subject") or customer.get("email")))
    return render_template(
        "index.html",
        cities=AVAILABLE_CITIES,
        products=PRODUCTS,
        coming_soon_products=COMING_SOON_PRODUCTS,
        schedules={key: get_delivery_schedule(key) for key in AVAILABLE_CITIES},
        storage_backend=order_manager.sheets.backend_name,
        customer=customer,
        customer_authenticated=customer_authenticated,
        offline_order_admin=is_offline_order_admin(customer),
        customer_login_required=customer_login_required(),
        google_login_enabled=google_oauth_enabled(),
        razorpay_enabled=razorpay_enabled(),
        razorpay_key_id=razorpay_config()["key_id"] if razorpay_enabled() else "",
        coupon_offers=OrderManager.coupon_offers(),
    )


@app.get("/profile")
def profile():
    customer = customer_payload(current_customer())
    if not customer:
        if google_oauth_enabled():
            return redirect(url_for("google_login", next=url_for("profile")))
        return redirect(url_for("index", account_error="sign_in_required"))
    return render_template(
        "profile.html",
        customer=customer,
        cities=AVAILABLE_CITIES,
    )


@app.get("/favicon.ico")
def favicon():
    return send_from_directory(app.static_folder, "img/logo-favicon.png", mimetype="image/png")


@app.get("/apple-touch-icon.png")
def apple_touch_icon():
    return send_from_directory(app.static_folder, "img/apple-touch-icon.png", mimetype="image/png")


@app.get("/robots.txt")
def robots_txt():
    return app.response_class("User-agent: *\nAllow: /\n", mimetype="text/plain")


@app.post("/api/coupons/preview")
def coupon_preview():
    payload = request.get_json(silent=True) or {}
    preview = OrderManager.coupon_preview(payload.get("code", ""))
    if not preview:
        return jsonify({"ok": False, "error": "Coupon code is not valid."}), 404
    return jsonify({"ok": True, "coupon": preview})


@app.post("/api/admin/sync-atharv")
@outbound_required
def sync_atharv_sheet():
    result = order_manager.sheets.sync_atharv_orders()
    return jsonify(result), 200 if result.get("ok") else 400


@app.post("/api/orders")
def create_order():
    payload = request.get_json(silent=True) or request.form.to_dict()
    customer = current_customer()
    offline_order_admin = prepare_order_payload(payload, customer)
    source = "Website"
    payload["source"] = source
    checkout_token = str(payload.get("checkout_token", "")).strip()
    log_checkout(
        "order_request_received",
        source=source,
        payment_mode=str(payload.get("payment_mode", "")).strip() or "COD",
        checkout_token=checkout_token,
        authenticated=bool(customer),
    )
    if customer_login_required() and not customer:
        log_checkout("order_request_auth_required", checkout_token=checkout_token)
        return jsonify({"ok": False, "auth_required": True, "error": "Please create your account with Google before placing the order."}), 401
    if customer and source == "Website":
        payload["customer_email"] = customer_payload(customer)["email"]
        payload["google_subject"] = customer_payload(customer)["google_subject"]
    submitted_payment_mode = str(payload.get("payment_mode") or payload.get("payment_method") or "").strip().lower()
    if submitted_payment_mode in {"razorpay", "online", "paid", "prepaid"}:
        log_checkout("order_request_invalid_mode", checkout_token=checkout_token)
        return jsonify({"ok": False, "error": "Please complete Razorpay payment verification before placing this order."}), 400

    if checkout_token:
        existing_order = find_completed_order_by_checkout_token(checkout_token)
        if existing_order:
            if not order_belongs_to_customer(existing_order, customer):
                return jsonify({"ok": False, "error": "This checkout reference is already in use."}), 409
            log_checkout(
                "order_request_idempotent_hit",
                checkout_token=checkout_token,
                order_id=existing_order.get("Order ID", ""),
            )
            return jsonify({"ok": True, "duplicate": True, "order": public_order_receipt(existing_order)}), 200

    clean_data, errors = order_manager.validate_new_order(payload, address_required=not offline_order_admin)
    log_checkout(
        "order_request_validated",
        checkout_token=checkout_token,
        has_errors=bool(errors),
        item_count=clean_data.get("quantity", 0),
        total_amount=clean_data.get("total_amount", 0),
    )
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400
    result = order_manager.create_order(payload, source=source, address_required=not offline_order_admin)
    log_checkout(
        "order_request_saved",
        checkout_token=checkout_token,
        ok=result["ok"],
        duplicate=result.get("duplicate", False),
        order_id=result.get("order", {}).get("Order ID", "") if result.get("order") else "",
    )
    if result["ok"]:
        remember_completed_order(result["order"])
    if result["ok"] and customer and source == "Website" and not offline_order_admin:
        remember_customer_checkout_details(
            phone=payload.get("phone", ""),
            city=payload.get("city", ""),
            address=payload.get("address", ""),
        )
        log_checkout("customer_profile_sync_deferred", checkout_token=checkout_token)
    if result["ok"]:
        try:
            send_order_confirmation_email(result["order"])
        except Exception:
            app.logger.exception("Order confirmation email failed after COD order placement")
    status = 200 if result["ok"] else 400
    log_checkout("order_request_response", checkout_token=checkout_token, status=status)
    response_result = dict(result)
    if response_result.get("order"):
        response_result["order"] = public_order_receipt(response_result["order"])
    return jsonify(response_result), status


@app.post("/send-order-status-updates")
@outbound_required
def send_order_status_updates():
    status_map = {
        "confirmed": "Confirmed",
        "packed": "Packed",
        "delivered": "Delivered",
        "cancelled": "Cancelled",
    }
    order_id = str(request.args.get("order_id", "")).strip().upper()
    status = status_map.get(str(request.args.get("status", "")).strip().lower())

    if not order_id or not status:
        return jsonify({"ok": False, "error": "Missing or invalid order_id/status."}), 400

    result = order_manager.update_status(order_id, status)
    if not result["ok"]:
        return jsonify(result), 404

    return jsonify(
        {
            "ok": True,
            "order_id": order_id,
            "status": status,
            "worksheet": request.args.get("worksheet", ""),
            "message": "Order status updated. Connect WhatsApp provider send here when outbound messaging is enabled.",
        }
    )


@app.post("/send-order-confirmations")
@outbound_required
def send_order_confirmations():
    order_id = str(request.args.get("order_id", "")).strip().upper()
    if not order_id:
        return jsonify({"ok": False, "error": "Missing order_id."}), 400

    order, error = order_manager.validate_order_id(order_id)
    if error:
        return jsonify({"ok": False, "error": error}), 404

    return jsonify(
        {
            "ok": True,
            "order_id": order_id,
            "phone": order.get("Phone", ""),
            "message": "Order confirmation accepted. Connect WhatsApp provider send here when outbound messaging is enabled.",
        }
    )


@app.post("/api/create-order")
@app.post("/api/payments/razorpay/order")
def create_razorpay_order():
    if not razorpay_enabled():
        return jsonify({"ok": False, "error": "Razorpay test payments are not configured."}), 503

    payload = request.get_json(silent=True) or {}
    customer = current_customer()
    offline_order_admin = prepare_order_payload(payload, customer)
    checkout_token = str(payload.get("checkout_token", "")).strip()
    log_checkout(
        "payment_initialize_received",
        checkout_token=checkout_token,
        authenticated=bool(customer),
    )
    if customer_login_required() and not customer:
        log_checkout("payment_initialize_auth_required", checkout_token=checkout_token)
        return jsonify({"ok": False, "auth_required": True, "error": "Please create your account with Google before paying."}), 401
    if customer:
        payload["customer_email"] = customer_payload(customer)["email"]
        payload["google_subject"] = customer_payload(customer)["google_subject"]
    payload["payment_mode"] = "Razorpay"
    payload["source"] = "Website"

    if checkout_token:
        existing_order = find_completed_order_by_checkout_token(checkout_token)
        if existing_order:
            if not order_belongs_to_customer(existing_order, customer):
                return jsonify({"ok": False, "error": "This checkout reference is already in use."}), 409
            log_checkout(
                "payment_initialize_existing_order",
                checkout_token=checkout_token,
                order_id=existing_order.get("Order ID", ""),
            )
            return jsonify({"ok": True, "duplicate": True, "order": public_order_receipt(existing_order)}), 200

    clean_data, errors = order_manager.validate_new_order(payload, address_required=not offline_order_admin)
    log_checkout(
        "payment_initialize_validated",
        checkout_token=checkout_token,
        has_errors=bool(errors),
        item_count=clean_data.get("quantity", 0),
        total_amount=clean_data.get("total_amount", 0),
    )
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    amount_paise = int(clean_data["total_amount"]) * 100
    if amount_paise < 100:
        return jsonify({"ok": False, "error": "Minimum Razorpay order amount is 100 paise."}), 400
    receipt = f"pl_{secrets.token_hex(8)}"
    try:
        razorpay_order = razorpay_client().order.create(
            data={
                "amount": amount_paise,
                "currency": "INR",
                "receipt": receipt,
                "payment_capture": 1,
                "notes": {
                    "customer_name": clean_data["name"],
                    "phone": clean_data["phone"],
                    "source": "Pulps and Leaves website",
                },
            }
        )
    except Exception as error:
        log_checkout("payment_initialize_failed", checkout_token=checkout_token, error=str(error))
        status_code = getattr(error, "status_code", None)
        if status_code in {401, 403}:
            return jsonify({"ok": False, "error": "Razorpay authentication failed. Please check the API keys."}), 401
        return jsonify({"ok": False, "error": f"Razorpay order could not be created: {error}"}), 500

    checkout_customer = {
        "name": clean_data["name"],
        "email": clean_data.get("customer_email", ""),
        "contact": clean_data["phone"],
    }
    log_checkout(
        "payment_initialized",
        checkout_token=checkout_token,
        razorpay_order_id=razorpay_order["id"],
        amount_paise=amount_paise,
    )

    return jsonify(
        {
            "ok": True,
            "key_id": razorpay_config()["key_id"],
            "order_id": razorpay_order["id"],
            "amount": amount_paise,
            "currency": "INR",
            "verification_token": build_razorpay_verification_token(razorpay_order["id"], payload, amount_paise),
            "customer": checkout_customer,
        }
    )


@app.post("/api/verify-payment")
@app.post("/api/payments/razorpay/verify")
def verify_razorpay_payment():
    payload = request.get_json(silent=True) or {}
    customer = current_customer()
    offline_order_admin = is_offline_order_admin(customer)
    razorpay_order_id = str(payload.get("razorpay_order_id", "")).strip()
    razorpay_payment_id = str(payload.get("razorpay_payment_id", "")).strip()
    razorpay_signature = str(payload.get("razorpay_signature", "")).strip()
    verification_token = str(payload.get("verification_token", "")).strip()
    log_checkout(
        "payment_verify_received",
        razorpay_order_id=razorpay_order_id,
        razorpay_payment_id=razorpay_payment_id,
        authenticated=bool(customer),
    )
    if customer_login_required() and not customer:
        log_checkout("payment_verify_auth_required", razorpay_order_id=razorpay_order_id)
        return jsonify({"ok": False, "auth_required": True, "error": "Please create your account with Google before completing payment."}), 401
    if not razorpay_order_id or not razorpay_payment_id or not razorpay_signature:
        log_checkout("payment_verify_missing_fields", razorpay_order_id=razorpay_order_id)
        return jsonify({"ok": False, "error": "Missing payment verification fields."}), 400
    duplicate_order = find_completed_order_by_payment_id(razorpay_payment_id)
    if duplicate_order:
        if not order_belongs_to_customer(duplicate_order, customer):
            return jsonify({"ok": False, "error": "This payment is already linked to another order."}), 409
        log_checkout(
            "payment_verify_duplicate_hit",
            razorpay_order_id=razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
            order_id=duplicate_order.get("Order ID", ""),
        )
        return jsonify({"ok": True, "duplicate": True, "order": public_order_receipt(duplicate_order)}), 200

    token_state = parse_razorpay_verification_token(verification_token, razorpay_order_id)
    pending = None
    if token_state:
        pending = {
            "payload": token_state.get("payload", {}),
            "amount": token_state.get("amount", 0),
        }

    if not pending:
        log_checkout("payment_verify_missing_pending", razorpay_order_id=razorpay_order_id)
        return jsonify({"ok": False, "error": "Payment session expired. Please try again."}), 400
    token_customer = customer_payload(customer)
    token_payload = pending.get("payload", {})
    token_subject = str(token_payload.get("google_subject", "")).strip()
    token_email = str(token_payload.get("customer_email", "")).strip().lower()
    if not (
        token_customer
        and token_subject
        and hmac.compare_digest(token_subject, str(token_customer.get("google_subject", "")).strip())
        and token_email
        and hmac.compare_digest(token_email, str(token_customer.get("email", "")).strip().lower())
    ):
        return jsonify({"ok": False, "error": "Payment session does not belong to this account."}), 403
    if not verify_razorpay_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
        log_checkout("payment_verify_signature_failed", razorpay_order_id=razorpay_order_id, razorpay_payment_id=razorpay_payment_id)
        return jsonify({"ok": False, "error": "Razorpay payment verification failed."}), 400

    order_payload = dict(pending["payload"])
    prepare_order_payload(order_payload, customer)
    if customer:
        order_payload["customer_email"] = customer_payload(customer)["email"]
        order_payload["google_subject"] = customer_payload(customer)["google_subject"]
    order_payload.update(
        {
            "payment_mode": "Razorpay",
            "payment_status": "Paid",
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
        }
    )

    clean_data, errors = order_manager.validate_new_order(order_payload, address_required=not offline_order_admin)
    log_checkout(
        "payment_verify_validated",
        checkout_token=str(order_payload.get("checkout_token", "")).strip(),
        has_errors=bool(errors),
        total_amount=clean_data.get("total_amount", 0),
    )
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400
    if int(clean_data["total_amount"]) * 100 != int(pending["amount"]):
        log_checkout("payment_verify_amount_mismatch", razorpay_order_id=razorpay_order_id)
        return jsonify({"ok": False, "error": "Order amount changed after payment. Please try again."}), 400

    result = order_manager.create_order(
        order_payload,
        source=order_payload.get("source", "Website"),
        address_required=not offline_order_admin,
    )
    log_checkout(
        "payment_verify_saved",
        checkout_token=str(order_payload.get("checkout_token", "")).strip(),
        ok=result["ok"],
        duplicate=result.get("duplicate", False),
        order_id=result.get("order", {}).get("Order ID", "") if result.get("order") else "",
    )
    if result["ok"]:
        remember_completed_order(result["order"])
        if customer and not offline_order_admin:
            remember_customer_checkout_details(
                phone=order_payload.get("phone", ""),
                city=order_payload.get("city", ""),
                address=order_payload.get("address", ""),
            )
            log_checkout("customer_profile_sync_deferred", checkout_token=str(order_payload.get("checkout_token", "")).strip())
        try:
            send_order_confirmation_email(result["order"])
        except Exception:
            app.logger.exception("Order confirmation email failed after Razorpay order placement")
    log_checkout(
        "payment_verify_response",
        razorpay_order_id=razorpay_order_id,
        status=200 if result["ok"] else 400,
    )
    response_result = dict(result)
    if response_result.get("order"):
        response_result["order"] = public_order_receipt(response_result["order"])
    return jsonify(response_result), 200 if result["ok"] else 400


@app.get("/api/me")
def me():
    customer = current_customer()
    return jsonify({"ok": True, "authenticated": bool(customer), "customer": customer_payload(customer)})


@app.post("/api/me")
def update_me():
    customer = current_customer()
    if not customer:
        return jsonify({"ok": False, "auth_required": True, "error": "Please sign in first."}), 401
    payload = request.get_json(silent=True) or request.form.to_dict()
    phone_raw = str(payload.get("phone", "")).strip()
    city_raw = str(payload.get("city", "")).strip()
    address = str(payload.get("address", "")).strip()
    phone = normalize_phone(phone_raw)
    city = city_by_choice(city_raw)
    errors = {}
    if not phone:
        errors["phone"] = "Please enter a valid 10-digit Indian mobile number."
    if not city:
        errors["city"] = "Please select a supported delivery city."
    if len(address) < 8 or len(address) > 300:
        errors["address"] = "Please enter a complete delivery address of up to 300 characters."
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    remember_customer_checkout_details(
        phone=phone,
        city=city,
        address=address,
    )
    try:
        updated = order_manager.sheets.update_customer_profile(
            customer_payload(customer)["google_subject"],
            {
                "phone": phone,
                "city": city,
                "address": address,
            },
        )
    except Exception as error:
        log_checkout("customer_profile_sync_failed", error=str(error))
        updated = None
    if not updated:
        try:
            profile = customer_payload(current_customer() or customer)
            profile.update(
                {
                    "phone": phone,
                    "city": city,
                    "address": address,
                }
            )
            updated = order_manager.sheets.upsert_customer(profile)
        except Exception as error:
            log_checkout("customer_profile_upsert_failed", error=str(error))
    return jsonify({"ok": True, "customer": customer_payload(updated or current_customer() or customer), "synced": bool(updated)})


@app.get("/api/me/orders")
def my_orders():
    customer = current_customer()
    if not customer:
        return jsonify({"ok": False, "auth_required": True, "error": "Please sign in to view your order history."}), 401

    identity = customer_payload(customer)
    matching_orders = []

    try:
        orders = order_manager.sheets.get_all_orders()
    except Exception as error:
        log_checkout("order_history_load_failed", error=str(error))
        return jsonify(
            {
                "ok": False,
                "error": "Your order history could not be loaded right now. Please try again.",
            }
        ), 503

    seen_order_ids = set()
    for order in orders:
        order_id = str(order.get("Order ID", "")).strip()
        if order_id and order_id in seen_order_ids:
            continue
        if order_belongs_to_customer(order, identity):
            if order_id:
                seen_order_ids.add(order_id)
            matching_orders.append(public_customer_order(order))

    response_orders = list(reversed(matching_orders))
    return jsonify({"ok": True, "orders": response_orders})


@app.get("/auth/google")
def google_login():
    if not google_oauth_enabled():
        return redirect(url_for("index", account_error="google_not_configured"))
    session["auth_next"] = safe_next_url(request.args.get("next") or url_for("index"))
    redirect_uri = google_callback_url()
    return oauth.google.authorize_redirect(redirect_uri)


@app.get("/auth/google/callback")
def google_callback():
    if not google_oauth_enabled():
        return redirect(url_for("index", account_error="google_not_configured"))
    if request.args.get("error"):
        return redirect(url_for("index", account_error=request.args.get("error")))
    try:
        token = oauth.google.authorize_access_token()
    except Exception:
        return redirect(url_for("index", account_error="google_auth_failed"))
    profile = token.get("userinfo") or oauth.google.userinfo()
    customer_profile = {
        "google_subject": profile.get("sub", ""),
        "email": profile.get("email", ""),
        "name": profile.get("name", ""),
        "picture": profile.get("picture", ""),
    }
    try:
        customer = order_manager.sheets.upsert_customer(customer_profile)
    except Exception:
        customer = None
    if customer:
        session["customer"] = customer_payload(customer)
    else:
        session["customer"] = customer_profile
    next_url = session.pop("auth_next", url_for("index"))
    return redirect(safe_next_url(next_url))


@app.post("/auth/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/orders/<order_id>")
def get_order(order_id):
    customer = current_customer()
    if not customer:
        return jsonify({"ok": False, "auth_required": True, "error": "Please sign in to view this order."}), 401
    order = customer_order_or_none(order_id, customer)
    if not order:
        return jsonify({"ok": False, "error": "Order not found."}), 404
    return jsonify({"ok": True, "order": public_customer_order(order)})


@app.post("/api/orders/<order_id>/edit")
def edit_order(order_id):
    customer = current_customer()
    if not customer:
        return jsonify({"ok": False, "auth_required": True, "error": "Please sign in to edit this order."}), 401
    payload = request.get_json(silent=True) or request.form.to_dict()
    order = customer_order_or_none(order_id, customer)
    if not order:
        return jsonify({"ok": False, "error": "Order not found."}), 404
    if payload.get("phone") and not normalize_phone(payload.get("phone")):
        return jsonify({"ok": False, "error": "Please enter a valid 10-digit Indian mobile number."}), 400
    responses = []
    if payload.get("address"):
        responses.append(order_manager.update_address(order_id, payload["address"]))
    if payload.get("phone"):
        responses.append(order_manager.update_phone(order_id, payload["phone"]))

    if not responses:
        return jsonify({"ok": False, "error": "Please provide a new address or mobile number."}), 400

    failures = [response for response in responses if not response["ok"]]
    if failures:
        return jsonify(failures[0]), 400
    return jsonify({"ok": True, "order_id": order_id.upper(), "updates": [r["updates"] for r in responses]})


@app.get("/api/delivery/<city>")
def delivery(city):
    schedule = get_delivery_schedule(city)
    if not schedule:
        return jsonify({"ok": False, "error": "Unsupported city."}), 404
    return jsonify({"ok": True, "schedule": schedule})


@app.post("/api/chatbot/message")
@outbound_required
def chatbot_message():
    payload = request.get_json(force=True)
    user_id = payload.get("user_id") or payload.get("from") or "website-user"
    message = payload.get("message", "")
    return jsonify(chatbot.handle_message(user_id, message))


@app.route("/webhook", methods=["GET", "POST"], strict_slashes=False)
def meta_webhook():
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        verify_token = clean_env("META_VERIFY_TOKEN") or clean_env("WHATSAPP_VERIFY_TOKEN")

        if mode == "subscribe" and challenge:
            if not verify_token:
                return "Webhook verification is not configured", 503
            if not hmac.compare_digest(str(token or ""), verify_token):
                return "Invalid verify token", 403
            return app.response_class(challenge, mimetype="text/plain")

        return "Webhook endpoint is ready", 200

    if not clean_env("META_APP_SECRET"):
        return jsonify({"ok": False, "error": "Meta webhook signing is not configured."}), 503
    if not meta_webhook_signature_valid():
        return jsonify({"ok": False, "error": "Invalid webhook signature."}), 401
    return handle_whatsapp_payload()


@app.post("/webhook/whatsapp")
@outbound_required
def whatsapp_webhook():
    """Webhook-ready endpoint for Meta, Twilio, WATI, or Interakt adapters.

    Today it returns the generated reply as JSON. In production the provider
    adapter can take this same reply and send it through the provider API.
    """
    return handle_whatsapp_payload()


def handle_whatsapp_payload():
    payload = request.get_json(silent=True) or {}
    user_id, message = extract_webhook_message(payload)
    if not message:
        return jsonify({"ok": False, "error": "No message found in webhook payload."}), 400
    response = chatbot.handle_message(user_id, message)
    return jsonify({"ok": True, "to": user_id, **response})


@app.get("/admin")
@admin_required
def admin_dashboard():
    city = request.args.get("city", "")
    status = request.args.get("status", "")
    query = request.args.get("q", "")
    orders = order_manager.list_orders(city=city, status=status, query=query)
    return render_template(
        "admin.html",
        orders=orders,
        cities=CITIES,
        statuses=ORDER_STATUSES,
        filters={"city": city, "status": status, "q": query},
        storage_backend=order_manager.sheets.backend_name,
        usage_report=usage_health_report(),
    )


@app.get("/api/admin/usage-health")
@admin_required
def admin_usage_health():
    return jsonify(usage_health_report())


@app.post("/admin/orders/<order_id>/status")
@admin_required
def admin_update_status(order_id):
    status = request.form.get("status", "")
    result = order_manager.update_status(order_id, status)
    if request.headers.get("Accept") == "application/json":
        return jsonify(result), 200 if result["ok"] else 400
    return redirect(url_for("admin_dashboard"))


def extract_webhook_message(payload):
    if payload.get("from") and payload.get("message"):
        return payload["from"], payload["message"]

    try:
        message = payload["entry"][0]["changes"][0]["value"]["messages"][0]
        user_id = message["from"]
        text = message.get("text", {}).get("body", "")
        return user_id, text
    except (KeyError, IndexError, TypeError):
        pass

    try:
        user_id = payload["waId"] or payload["phone"]
        text = payload.get("text") or payload.get("body") or payload.get("message")
        return user_id, text
    except KeyError:
        return "unknown-user", ""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5001")), debug=True)

# Force Vercel rebuild 2
