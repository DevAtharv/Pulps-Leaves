import base64
import os
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, url_for

from ai_parser import normalize_phone
from chatbot_flow import ChatbotFlow
from delivery_config import CITIES, COMING_SOON_PRODUCTS, ORDER_STATUSES, PRODUCTS, city_by_choice, get_delivery_schedule
from order_manager import OrderManager


load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")

order_manager = OrderManager()
chatbot = ChatbotFlow(order_manager=order_manager)


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


@app.get("/")
def index():
    return render_template(
        "index.html",
        cities=CITIES,
        products=PRODUCTS,
        coming_soon_products=COMING_SOON_PRODUCTS,
        schedules={key: get_delivery_schedule(key) for key in CITIES},
        storage_backend=order_manager.sheets.backend_name,
    )


@app.post("/api/orders")
def create_order():
    payload = request.get_json(silent=True) or request.form.to_dict()
    clean_data, errors = order_manager.validate_new_order(payload)
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400
    result = order_manager.create_order(payload, source=payload.get("source", "Website"))
    status = 200 if result["ok"] else 400
    return jsonify(result), status


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


@app.post("/webhook/whatsapp")
def whatsapp_webhook():
    """Webhook-ready endpoint for Meta, Twilio, WATI, or Interakt adapters.

    Today it returns the generated reply as JSON. In production the provider
    adapter can take this same reply and send it through the provider API.
    """
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
