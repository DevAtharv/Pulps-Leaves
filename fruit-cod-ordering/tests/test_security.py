import hashlib
import hmac
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("STORAGE_MODE", "local")
os.environ.setdefault("FLASK_ENV", "development")
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-more-than-32-bytes")

import app as app_module
from sheets_handler import SheetsHandler


def order(order_id, subject="", email="", phone="9876543210"):
    return {
        "Order ID": order_id,
        "Timestamp": "2026-07-12T10:00:00+05:30",
        "Customer Name": "Test Customer",
        "Phone": phone,
        "Address": "12 Test Road",
        "City": "Bengaluru",
        "Product": "Naivedyam Makhana x 1",
        "Quantity": "1",
        "Total Amount": "379",
        "Payment Mode": "COD",
        "Payment Status": "Pending",
        "Order Status": "Received",
        "Customer Email": email,
        "Google Subject": subject,
        "Razorpay Payment ID": "pay_private",
        "Checkout Token": "checkout-private",
    }


class FakeSheets:
    def __init__(self, orders):
        self.orders = orders

    def get_all_orders(self):
        return [dict(item) for item in self.orders]

    def update_order(self, order_id, updates):
        for item in self.orders:
            if item["Order ID"] == order_id:
                item.update(updates)
                return True
        return False


class FakeManager:
    def __init__(self, orders):
        self.sheets = FakeSheets(orders)
        self.updates = []
        self.last_order_payload = None

    def validate_order_id(self, order_id):
        normalized = str(order_id).upper()
        for item in self.sheets.orders:
            if item["Order ID"] == normalized:
                return item, None
        return None, "Not found"

    def find_order_by_checkout_token(self, token):
        return next((item for item in self.sheets.orders if item.get("Checkout Token") == token), None)

    def find_order_by_payment_id(self, payment_id):
        return next((item for item in self.sheets.orders if item.get("Razorpay Payment ID") == payment_id), None)

    def validate_new_order(self, payload, address_required=True):
        return {"quantity": 1, "total_amount": 379}, {}

    def create_order(self, payload, source="Website", address_required=True):
        self.last_order_payload = {**payload, "source": source}
        return {"ok": True, "duplicate": False, "order": order("PLNEW001", payload.get("google_subject", ""), payload.get("customer_email", ""))}

    def update_address(self, order_id, address):
        self.updates.append((order_id, "Address", address))
        self.sheets.update_order(order_id, {"Address": address})
        return {"ok": True, "order_id": order_id, "updates": {"Address": address}}

    def update_phone(self, order_id, phone):
        self.updates.append((order_id, "Phone", phone))
        self.sheets.update_order(order_id, {"Phone": phone})
        return {"ok": True, "order_id": order_id, "updates": {"Phone": phone}}


class FakeChatbot:
    def handle_message(self, user_id, message):
        return {"reply": "ok", "state": "MAIN", "data": {}}


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.original_manager = app_module.order_manager
        self.original_chatbot = app_module.chatbot
        self.manager = FakeManager(
            [
                order("PLOWN001", subject="google-own", email="owner@example.com"),
                order("PLEMAIL1", email="owner@example.com"),
                order("PLLEGACY", phone="9123456789"),
                order("PLOTHER1", subject="google-other", email="other@example.com", phone="9123456789"),
            ]
        )
        app_module.order_manager = self.manager
        app_module.chatbot = FakeChatbot()
        app_module.app.config.update(TESTING=True, SECRET_KEY="test-session-secret")
        self.client = app_module.app.test_client()

    def tearDown(self):
        app_module.order_manager = self.original_manager
        app_module.chatbot = self.original_chatbot

    def login(self):
        with self.client.session_transaction() as session:
            session["customer"] = {
                "google_subject": "google-own",
                "email": "owner@example.com",
                "name": "Test Customer",
            }

    def test_history_uses_google_identity_not_phone_or_name(self):
        self.login()
        response = self.client.get("/api/me/orders?phone=9123456789")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual([item["order_id"] for item in payload["orders"]], ["PLEMAIL1", "PLOWN001"])
        self.assertNotIn("razorpay_payment_id", payload["orders"][0])

    def test_authenticated_customer_can_place_cod_order(self):
        self.login()
        response = self.client.post(
            "/api/orders",
            json={
                "checkout_token": "checkout-new",
                "payment_method": "cod",
                "name": "Test Customer",
                "phone": "9876543210",
                "city": "bangalore",
                "address": "12 Test Road",
                "cart_items": [{"id": "roasted-himalayan-makhana", "quantity": 1}],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        self.assertEqual(self.manager.last_order_payload["customer_email"], "owner@example.com")
        self.assertEqual(self.manager.last_order_payload["google_subject"], "google-own")
        self.assertEqual(self.manager.last_order_payload["source"], "Website")

    def test_logout_clears_the_customer_session(self):
        self.login()
        response = self.client.post("/auth/logout")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/me/orders").status_code, 401)

    def test_legacy_claim_requires_order_id_and_matching_phone(self):
        self.login()
        wrong = self.client.post(
            "/api/me/orders/claim",
            json={"order_id": "PLLEGACY", "phone": "9876543210"},
        )
        self.assertEqual(wrong.status_code, 404)

        claimed = self.client.post(
            "/api/me/orders/claim",
            json={"order_id": "PLLEGACY", "phone": "9123456789"},
        )
        self.assertEqual(claimed.status_code, 200)
        legacy = next(item for item in self.manager.sheets.orders if item["Order ID"] == "PLLEGACY")
        self.assertEqual(legacy["Google Subject"], "google-own")
        self.assertEqual(legacy["Customer Email"], "owner@example.com")

    def test_order_read_and_edit_require_ownership(self):
        self.login()
        own = self.client.get("/api/orders/PLOWN001")
        self.assertEqual(own.status_code, 200)
        self.assertNotIn("Razorpay Payment ID", own.get_json()["order"])

        other = self.client.get("/api/orders/PLOTHER1")
        self.assertEqual(other.status_code, 404)
        edit = self.client.post("/api/orders/PLOTHER1/edit", json={"address": "99 Attacker Road"})
        self.assertEqual(edit.status_code, 404)
        self.assertEqual(self.manager.updates, [])

    def test_admin_fails_closed_without_credentials(self):
        with patch.dict(os.environ, {"ADMIN_USERNAME": "", "ADMIN_PASSWORD": ""}, clear=False):
            response = self.client.get("/admin")
        self.assertEqual(response.status_code, 503)

    def test_meta_webhook_requires_valid_signature(self):
        body = json.dumps({"from": "919876543210", "message": "hello"}).encode()
        with patch.dict(os.environ, {"META_APP_SECRET": "meta-secret"}, clear=False):
            invalid = self.client.post("/webhook", data=body, content_type="application/json")
            self.assertEqual(invalid.status_code, 401)

            signature = "sha256=" + hmac.new(b"meta-secret", body, hashlib.sha256).hexdigest()
            valid = self.client.post(
                "/webhook",
                data=body,
                content_type="application/json",
                headers={"X-Hub-Signature-256": signature},
            )
        self.assertEqual(valid.status_code, 200)

    def test_idempotency_lookup_uses_persistent_storage(self):
        existing = app_module.find_completed_order_by_checkout_token("checkout-private")
        self.assertEqual(existing["Order ID"], "PLOWN001")

    def test_local_spreadsheet_values_are_formula_safe(self):
        self.assertEqual(SheetsHandler._spreadsheet_safe_value("=IMPORTXML('x')"), "'=IMPORTXML('x')")
        self.assertEqual(SheetsHandler._spreadsheet_safe_value("Normal address"), "Normal address")

    def test_legacy_email_header_maps_to_customer_email(self):
        headers = SheetsHandler._order_headers_from_row(["Order ID", "Email", "Phone"])
        self.assertEqual(headers[1], "Customer Email")


if __name__ == "__main__":
    unittest.main()
