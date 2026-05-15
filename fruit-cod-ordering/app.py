import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from functools import wraps
from urllib.parse import urlparse

import requests
import razorpay
from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth
from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from itsdangerous import BadSignature, URLSafeSerializer
from werkzeug.exceptions import HTTPException

from ai_parser import normalize_phone
from chatbot_flow import ChatbotFlow
from delivery_config import AVAILABLE_CITIES, CITIES, COMING_SOON_PRODUCTS, ORDER_STATUSES, PRODUCTS, city_by_choice, get_delivery_schedule
from email_service import build_order_confirmation, send_resend_email
from order_manager import OrderManager


load_dotenv()

app = Flask(__name__)


def clean_env(name, default=""):
    value = os.getenv(name, default)
    if value is None:
        return default
    return str(value).strip().lstrip("\ufeff").replace("\r", "").replace("\n", "").strip()


app.config["SECRET_KEY"] = clean_env("SECRET_KEY", "dev-secret-change-me")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = bool(os.getenv("VERCEL"))


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
    return "google" in oauth._clients


def customer_login_required():
    return clean_env("REQUIRE_CUSTOMER_LOGIN", "false").lower() in {"1", "true", "yes", "on"}


def razorpay_config():
    return {
        "key_id": clean_env("RAZORPAY_KEY_ID"),
        "key_secret": clean_env("RAZORPAY_KEY_SECRET"),
        "enabled": clean_env("RAZORPAY_ENABLED", "false").lower() in {"1", "true", "yes", "on"},
    }


def razorpay_enabled():
    config = razorpay_config()
    return bool(config["enabled"] and config["key_id"] and config["key_secret"])


def razorpay_client():
    config = razorpay_config()
    client = razorpay.Client(auth=(config["key_id"], config["key_secret"]))
    client.set_app_details({"title": "Pulps & Leaves", "version": "1.0"})
    return client


def google_maps_api_key():
    return clean_env("GOOGLE_MAPS_API_KEY")


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
        "razorpay_payment_id": order.get("Razorpay Payment ID", ""),
    }


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


def pending_razorpay_orders():
    pending = session.get("pending_razorpay_orders", {})
    return pending if isinstance(pending, dict) else {}


def find_pending_razorpay_order_by_token(checkout_token):
    token = str(checkout_token or "").strip()
    if not token:
        return None, None
    for order_id, pending in pending_razorpay_orders().items():
        payload = pending.get("payload", {}) if isinstance(pending, dict) else {}
        if str(payload.get("checkout_token", "")).strip() == token:
            return order_id, pending
    return None, None


def completed_checkout_orders():
    completed = session.get("completed_checkout_orders", {})
    return completed if isinstance(completed, dict) else {}


def remember_completed_order(order):
    if not isinstance(order, dict):
        return
    completed = completed_checkout_orders()
    checkout_token = str(order.get("Checkout Token", "")).strip()
    razorpay_payment_id = str(order.get("Razorpay Payment ID", "")).strip()
    if checkout_token:
        completed[f"token:{checkout_token}"] = order
    if razorpay_payment_id:
        completed[f"payment:{razorpay_payment_id}"] = order
    if len(completed) > 20:
        recent_items = list(completed.items())[-20:]
        completed = dict(recent_items)
    session["completed_checkout_orders"] = completed
    session.pop("order_history_cache", None)


def find_completed_order_by_checkout_token(checkout_token):
    if not checkout_token:
        return None
    return completed_checkout_orders().get(f"token:{checkout_token}")


def find_completed_order_by_payment_id(payment_id):
    if not payment_id:
        return None
    return completed_checkout_orders().get(f"payment:{payment_id}")


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
        return url_for("index", _external=True)
    parsed = urlparse(raw_next)
    if parsed.netloc and parsed.netloc != request.host:
        return url_for("index", _external=True)
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return url_for("index", _external=True)
    return raw_next


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        username = os.getenv("ADMIN_USERNAME", "admin")
        password = os.getenv("ADMIN_PASSWORD", "change-me")
        auth_header = request.headers.get("Authorization", "")
        expected = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
        if auth_header != expected:
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
        expected = f"Bearer {token}" if token else ""
        if not token or not hmac.compare_digest(auth_header, expected):
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        return view(*args, **kwargs)

    return wrapper


@app.get("/")
def index():
    return render_template(
        "index.html",
        cities=AVAILABLE_CITIES,
        products=PRODUCTS,
        coming_soon_products=COMING_SOON_PRODUCTS,
        schedules={key: get_delivery_schedule(key) for key in AVAILABLE_CITIES},
        storage_backend=order_manager.sheets.backend_name,
        customer=customer_payload(current_customer()),
        customer_login_required=customer_login_required(),
        google_login_enabled=google_oauth_enabled(),
        razorpay_enabled=razorpay_enabled(),
        razorpay_key_id=razorpay_config()["key_id"] if razorpay_enabled() else "",
        google_maps_enabled=bool(google_maps_api_key()),
        google_maps_api_key=google_maps_api_key(),
    )


@app.get("/favicon.ico")
def favicon():
    return send_from_directory(app.static_folder, "img/logo.png", mimetype="image/png")


@app.get("/robots.txt")
def robots_txt():
    return app.response_class("User-agent: *\nAllow: /\n", mimetype="text/plain")


@app.post("/api/orders")
def create_order():
    payload = request.get_json(silent=True) or request.form.to_dict()
    customer = current_customer()
    source = payload.get("source", "Website")
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
    if str(payload.get("payment_mode", "")).strip().lower() == "razorpay":
        log_checkout("order_request_invalid_mode", checkout_token=checkout_token)
        return jsonify({"ok": False, "error": "Please complete Razorpay payment verification before placing this order."}), 400

    if checkout_token:
        existing_order = find_completed_order_by_checkout_token(checkout_token)
        if existing_order:
            log_checkout(
                "order_request_idempotent_hit",
                checkout_token=checkout_token,
                order_id=existing_order.get("Order ID", ""),
            )
            return jsonify({"ok": True, "duplicate": True, "order": existing_order}), 200

    clean_data, errors = order_manager.validate_new_order(payload)
    log_checkout(
        "order_request_validated",
        checkout_token=checkout_token,
        has_errors=bool(errors),
        item_count=clean_data.get("quantity", 0),
        total_amount=clean_data.get("total_amount", 0),
    )
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400
    result = order_manager.create_order(payload, source=source)
    log_checkout(
        "order_request_saved",
        checkout_token=checkout_token,
        ok=result["ok"],
        duplicate=result.get("duplicate", False),
        order_id=result.get("order", {}).get("Order ID", "") if result.get("order") else "",
    )
    if result["ok"]:
        remember_completed_order(result["order"])
    if result["ok"] and customer and source == "Website":
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
    return jsonify(result), status


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

    if checkout_token:
        existing_order = find_completed_order_by_checkout_token(checkout_token)
        if existing_order:
            log_checkout(
                "payment_initialize_existing_order",
                checkout_token=checkout_token,
                order_id=existing_order.get("Order ID", ""),
            )
            return jsonify({"ok": True, "duplicate": True, "order": existing_order}), 200
        existing_pending_order_id, existing_pending = find_pending_razorpay_order_by_token(checkout_token)
        if existing_pending_order_id and existing_pending:
            log_checkout(
                "payment_initialize_reused_pending_order",
                checkout_token=checkout_token,
                razorpay_order_id=existing_pending_order_id,
            )
            return jsonify(
                {
                    "ok": True,
                    "key_id": razorpay_config()["key_id"],
                    "order_id": existing_pending_order_id,
                    "amount": existing_pending.get("amount", 0),
                    "currency": "INR",
                    "verification_token": build_razorpay_verification_token(existing_pending_order_id, existing_pending.get("payload", {}), existing_pending.get("amount", 0)),
                    "customer": existing_pending.get("customer", {}),
                }
            )

    clean_data, errors = order_manager.validate_new_order(payload)
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

    pending_orders = pending_razorpay_orders()
    pending_orders[razorpay_order["id"]] = {
        "payload": payload,
        "amount": amount_paise,
        "customer": {
            "name": clean_data["name"],
            "email": clean_data.get("customer_email", ""),
            "contact": clean_data["phone"],
        },
    }
    session["pending_razorpay_orders"] = pending_orders
    session.modified = True
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
            "customer": pending_orders[razorpay_order["id"]]["customer"],
        }
    )


@app.post("/api/verify-payment")
@app.post("/api/payments/razorpay/verify")
def verify_razorpay_payment():
    payload = request.get_json(silent=True) or {}
    razorpay_order_id = str(payload.get("razorpay_order_id", "")).strip()
    razorpay_payment_id = str(payload.get("razorpay_payment_id", "")).strip()
    razorpay_signature = str(payload.get("razorpay_signature", "")).strip()
    verification_token = str(payload.get("verification_token", "")).strip()
    log_checkout(
        "payment_verify_received",
        razorpay_order_id=razorpay_order_id,
        razorpay_payment_id=razorpay_payment_id,
    )
    if not razorpay_order_id or not razorpay_payment_id or not razorpay_signature:
        log_checkout("payment_verify_missing_fields", razorpay_order_id=razorpay_order_id)
        return jsonify({"ok": False, "error": "Missing payment verification fields."}), 400
    duplicate_order = find_completed_order_by_payment_id(razorpay_payment_id)
    if duplicate_order:
        log_checkout(
            "payment_verify_duplicate_hit",
            razorpay_order_id=razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
            order_id=duplicate_order.get("Order ID", ""),
        )
        return jsonify({"ok": True, "duplicate": True, "order": duplicate_order}), 200

    pending_orders = pending_razorpay_orders()
    pending = pending_orders.get(razorpay_order_id)
    if not pending:
        token_state = parse_razorpay_verification_token(verification_token, razorpay_order_id)
        if token_state:
            pending = {
                "payload": token_state.get("payload", {}),
                "amount": token_state.get("amount", 0),
            }

    if not pending:
        log_checkout("payment_verify_missing_pending", razorpay_order_id=razorpay_order_id)
        return jsonify({"ok": False, "error": "Payment session expired. Please try again."}), 400
    if not verify_razorpay_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
        log_checkout("payment_verify_signature_failed", razorpay_order_id=razorpay_order_id, razorpay_payment_id=razorpay_payment_id)
        return jsonify({"ok": False, "error": "Razorpay payment verification failed."}), 400

    customer = current_customer()
    order_payload = dict(pending["payload"])
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

    clean_data, errors = order_manager.validate_new_order(order_payload)
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

    result = order_manager.create_order(order_payload, source=order_payload.get("source", "Website"))
    log_checkout(
        "payment_verify_saved",
        checkout_token=str(order_payload.get("checkout_token", "")).strip(),
        ok=result["ok"],
        duplicate=result.get("duplicate", False),
        order_id=result.get("order", {}).get("Order ID", "") if result.get("order") else "",
    )
    if result["ok"]:
        remember_completed_order(result["order"])
        pending_orders.pop(razorpay_order_id, None)
        session["pending_razorpay_orders"] = pending_orders
        session.modified = True
        if customer:
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
    return jsonify(result), 200 if result["ok"] else 400


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
    remember_customer_checkout_details(
        phone=payload.get("phone", ""),
        city=payload.get("city", ""),
        address=payload.get("address", ""),
    )
    try:
        updated = order_manager.sheets.update_customer_profile(
            customer_payload(customer)["google_subject"],
            {
                "phone": payload.get("phone", ""),
                "city": payload.get("city", ""),
                "address": payload.get("address", ""),
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
                    "phone": payload.get("phone", ""),
                    "city": payload.get("city", ""),
                    "address": payload.get("address", ""),
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

    history_cache = session.get("order_history_cache")
    if isinstance(history_cache, dict) and time.time() - float(history_cache.get("fetched_at", 0) or 0) < 60:
        return jsonify({"ok": True, "orders": history_cache.get("orders", [])})

    identity = customer_payload(customer)
    google_subject = str(identity.get("google_subject", "")).strip()
    email = str(identity.get("email", "")).strip().lower()
    phone = normalize_phone(identity.get("phone", ""))
    matching_orders = []

    try:
        orders = order_manager.sheets.get_all_orders()
    except Exception as error:
        log_checkout("order_history_fallback_empty", error=str(error))
        orders = []

    session_orders = [
        order
        for order in completed_checkout_orders().values()
        if isinstance(order, dict)
    ]
    orders.extend(session_orders)

    seen_order_ids = set()
    for order in orders:
        order_subject = str(order.get("Google Subject", "")).strip()
        order_email = str(order.get("Customer Email", "")).strip().lower()
        order_phone = normalize_phone(order.get("Phone", ""))
        order_id = str(order.get("Order ID", "")).strip()
        if order_id and order_id in seen_order_ids:
            continue
        if (
            (google_subject and order_subject == google_subject)
            or (email and order_email == email)
            or (phone and order_phone == phone)
        ):
            if order_id:
                seen_order_ids.add(order_id)
            matching_orders.append(public_customer_order(order))

    response_orders = list(reversed(matching_orders))
    session["order_history_cache"] = {"fetched_at": time.time(), "orders": response_orders}
    session.modified = True
    return jsonify({"ok": True, "orders": response_orders})


@app.get("/auth/google")
def google_login():
    if not google_oauth_enabled():
        return redirect(url_for("index", account_error="google_not_configured"))
    session["auth_next"] = safe_next_url(request.args.get("next") or url_for("index", _external=True))
    redirect_uri = clean_env("GOOGLE_OAUTH_REDIRECT_URI") or url_for("google_callback", _external=True)
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
    next_url = session.pop("auth_next", url_for("index", _external=True))
    return redirect(safe_next_url(next_url))


@app.post("/auth/logout")
def logout():
    session.pop("customer", None)
    return jsonify({"ok": True})


@app.get("/api/orders/<order_id>")
def get_order(order_id):
    order, error = order_manager.validate_order_id(order_id)
    if error:
        return jsonify({"ok": False, "error": error}), 404
    return jsonify({"ok": True, "order": order})


@app.post("/api/orders/<order_id>/edit")
def edit_order(order_id):
    payload = request.get_json(silent=True) or request.form.to_dict()
    order, error = order_manager.validate_order_id(order_id)
    if error:
        return jsonify({"ok": False, "error": error}), 404
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
        verify_token = os.getenv("META_VERIFY_TOKEN") or os.getenv("WHATSAPP_VERIFY_TOKEN")

        if mode == "subscribe" and challenge:
            if verify_token and token != verify_token:
                return "Invalid verify token", 403
            return app.response_class(challenge, mimetype="text/plain")

        return "Webhook endpoint is ready", 200

    return handle_whatsapp_payload()


@app.post("/webhook/whatsapp")
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
    )


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
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_ENV") == "development")

# Force Vercel rebuild 2
