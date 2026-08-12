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
from order_manager import OrderManager
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
        self.backend_name = "Test"

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
        self.create_order_calls = 0

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
        self.create_order_calls += 1
        self.last_order_payload = {**payload, "source": source}
        created = order("PLNEW001", payload.get("google_subject", ""), payload.get("customer_email", ""))
        created["Checkout Token"] = payload.get("checkout_token", "")
        return {"ok": True, "duplicate": False, "order": created}

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

    def test_history_reports_storage_failure_instead_of_empty_orders(self):
        self.login()
        with patch.object(self.manager.sheets, "get_all_orders", side_effect=RuntimeError("sheet unavailable")):
            response = self.client.get("/api/me/orders")
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.get_json()["ok"])

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

    def test_checkout_retry_uses_signed_session_reference_without_sheet_read(self):
        self.login()
        payload = {
            "checkout_token": "checkout-retry",
            "payment_method": "cod",
            "name": "Test Customer",
            "phone": "9876543210",
            "city": "bangalore",
            "address": "12 Test Road",
            "cart_items": [{"id": "roasted-himalayan-makhana", "quantity": 1}],
        }
        with patch.object(app_module, "find_completed_order_by_checkout_token", side_effect=AssertionError("sheet lookup should not run")):
            first = self.client.post("/api/orders", json=payload)
            retry = self.client.post("/api/orders", json=payload)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(retry.status_code, 200)
        self.assertTrue(retry.get_json()["duplicate"])
        self.assertEqual(retry.get_json()["order"]["Order ID"], "PLNEW001")
        self.assertEqual(self.manager.create_order_calls, 1)
        with self.client.session_transaction() as session:
            stored_reference = session["completed_checkout_refs"]["checkout-retry"]
        self.assertNotIn("owner@example.com", json.dumps(stored_reference))
        self.assertNotIn("google-own", json.dumps(stored_reference))

    def test_new_order_id_does_not_query_persistent_order_storage(self):
        class NoLookupSheets(FakeSheets):
            def find_order(self, order_id):
                raise AssertionError("new order IDs must not read the full order store")

        manager = OrderManager(sheets_handler=NoLookupSheets([]))
        self.assertRegex(manager.generate_order_id(), r"^PL[A-Z0-9]{6}$")

    def test_logout_clears_the_customer_session(self):
        self.login()
        response = self.client.post("/auth/logout")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/me/orders").status_code, 401)

    def test_legacy_order_claim_endpoint_is_removed(self):
        self.login()
        response = self.client.post(
            "/api/me/orders/claim",
            json={"order_id": "PLLEGACY", "phone": "9123456789"},
        )
        self.assertEqual(response.status_code, 404)

    def test_email_only_customer_renders_as_signed_in(self):
        with self.client.session_transaction() as session:
            session["customer"] = {"email": "owner@example.com", "name": "Test Customer"}

        response = self.client.get("/")
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('aria-label="Profile"', page)
        self.assertNotIn('aria-label="Login with Google"', page)
        self.assertNotIn("Link an older order", page)

    def test_profile_requires_google_login(self):
        response = self.client.get("/profile")
        self.assertEqual(response.status_code, 302)

    def test_authenticated_profile_renders_without_wallet(self):
        self.login()
        response = self.client.get("/profile")
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Account overview", page)
        self.assertIn("Your orders", page)
        self.assertIn("Default address", page)
        self.assertNotIn("wallet", page.lower())

    def test_authenticated_home_profile_links_to_profile_page(self):
        self.login()
        page = self.client.get("/").get_data(as_text=True)
        self.assertIn('href="/profile" aria-label="Profile"', page)

    def test_profile_update_rejects_invalid_delivery_details(self):
        self.login()
        response = self.client.post(
            "/api/me",
            json={"phone": "123", "city": "unknown", "address": "x"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.get_json()["errors"]), {"phone", "city", "address"})

    def test_coupon_offers_are_visible_and_server_validated(self):
        page = self.client.get("/").get_data(as_text=True)
        self.assertIn("Coupon offer", page)
        self.assertIn('data-coupon-apply="FREESHIP"', page)
        self.assertNotIn('data-coupon-apply="NAIVEDYAM10"', page)
        self.assertEqual(page.count("data-coupon-apply="), 1)
        preview = self.client.post("/api/coupons/preview", json={"code": "FREESHIP"})
        self.assertEqual(preview.status_code, 200)
        self.assertTrue(preview.get_json()["coupon"]["waives_delivery"])
        self.assertEqual(self.client.post("/api/coupons/preview", json={"code": "NAIVEDYAM10"}).status_code, 404)
        self.assertEqual(self.client.post("/api/coupons/preview", json={"code": "PL99FS022E"}).status_code, 404)

    def test_coupon_totals_are_calculated_on_the_server(self):
        manager = OrderManager(sheets_handler=FakeSheets([]))
        base_payload = {
            "name": "Test Customer",
            "phone": "9876543210",
            "city": "bangalore",
            "address": "12 Test Road",
            "cart_items": [{"id": "roasted-himalayan-makhana", "quantity": 1}],
            "payment_method": "cod",
        }
        standard, standard_errors = manager.validate_new_order(base_payload)
        self.assertEqual(standard_errors, {})
        self.assertEqual(standard["subtotal"], 399)
        self.assertEqual(standard["delivery_charge"], 40)
        self.assertEqual(standard["total_amount"], 439)

        free_ship, free_ship_errors = manager.validate_new_order(
            {**base_payload, "coupon_codes": ["FREESHIP"]}
        )
        self.assertEqual(free_ship_errors, {})
        self.assertEqual(free_ship["coupon_discount"], 0)
        self.assertEqual(free_ship["delivery_charge"], 0)
        self.assertEqual(free_ship["total_amount"], 399)

    def test_makhana_cart_uses_the_public_rs_399_price(self):
        manager = OrderManager(sheets_handler=FakeSheets([]))
        clean_data, errors = manager.validate_new_order(
            {
                "name": "Test Customer",
                "phone": "9876543210",
                "city": "bangalore",
                "address": "12 Test Road",
                "cart_items": [{"id": "roasted-himalayan-makhana", "quantity": 1}],
                "coupon_codes": ["LOVEFORMALDA"],
                "payment_method": "cod",
            }
        )
        self.assertEqual(errors, {})
        self.assertEqual(clean_data["subtotal"], 399)
        self.assertEqual(clean_data["discount"], 0)
        self.assertEqual(clean_data["delivery_charge"], 40)
        self.assertEqual(clean_data["total_amount"], 439)

    def test_one_kg_plain_makhana_uses_the_server_validated_price(self):
        manager = OrderManager(sheets_handler=FakeSheets([]))
        clean_data, errors = manager.validate_new_order(
            {
                "name": "Test Customer",
                "phone": "9876543210",
                "city": "bangalore",
                "address": "12 Test Road",
                "cart_items": [{"id": "roasted-himalayan-makhana-1kg", "quantity": 1}],
                "payment_method": "cod",
            }
        )
        self.assertEqual(errors, {})
        self.assertEqual(clean_data["subtotal"], 1750)
        self.assertEqual(clean_data["delivery_charge"], 40)
        self.assertEqual(clean_data["total_amount"], 1790)
        self.assertIn("Naivedyam Makhana 1kg x 1", clean_data["product_summary"])

    def test_bulk_plain_makhana_cannot_be_submitted_as_a_checkout_item(self):
        manager = OrderManager(sheets_handler=FakeSheets([]))
        clean_data, errors = manager.validate_new_order(
            {
                "name": "Test Customer",
                "phone": "9876543210",
                "city": "bangalore",
                "address": "12 Test Road",
                "cart_items": [{"id": "roasted-himalayan-makhana-100kg", "quantity": 1}],
                "payment_method": "cod",
            }
        )
        self.assertEqual(clean_data["subtotal"], 0)
        self.assertIn("product", errors)

    def test_masala_makhana_is_available_at_the_server_validated_price(self):
        manager = OrderManager(sheets_handler=FakeSheets([]))
        clean_data, errors = manager.validate_new_order(
            {
                "name": "Test Customer",
                "phone": "9876543210",
                "city": "bangalore",
                "address": "12 Test Road",
                "cart_items": [{"id": "roasted-makhana-masala-combo", "quantity": 1}],
                "payment_method": "cod",
            }
        )
        self.assertEqual(errors, {})
        self.assertEqual(clean_data["subtotal"], 350)
        self.assertEqual(clean_data["delivery_charge"], 40)
        self.assertEqual(clean_data["total_amount"], 390)
        self.assertIn("Roasted Makhana with 3 Masala Packs x 1", clean_data["product_summary"])

    def test_flavoured_makhana_is_available_at_the_server_validated_price(self):
        manager = OrderManager(sheets_handler=FakeSheets([]))
        clean_data, errors = manager.validate_new_order(
            {
                "name": "Test Customer",
                "phone": "9876543210",
                "city": "bangalore",
                "address": "12 Test Road",
                "cart_items": [{"id": "flavoured-makhana-peri-peri", "quantity": 1}],
                "payment_method": "cod",
            }
        )
        self.assertEqual(errors, {})
        self.assertEqual(clean_data["subtotal"], 350)
        self.assertEqual(clean_data["delivery_charge"], 40)
        self.assertEqual(clean_data["total_amount"], 390)
        self.assertIn("Peri Peri Makhana x 1", clean_data["product_summary"])

    def test_homepage_renders_three_products_three_slides_and_order_celebration(self):
        page = self.client.get("/").get_data(as_text=True)
        hero = page.split('<section class="hero"', 1)[1].split('<div class="hero-pagination"', 1)[0]
        self.assertIn('data-id="roasted-makhana-masala-combo"', page)
        self.assertIn("naivedyam-masala-pack-cutout-200g-20260730.png", page)
        self.assertIn('data-id="flavoured-makhana-peri-peri"', page)
        self.assertIn("naivedyam-four-flavours-cutout-20260801.png", page)
        self.assertIn("pulps-leaves-worldwide-map-20260812.png", page)
        self.assertIn("pl-lotus-hero-desktop-20260730.avif", page)
        self.assertIn("hero-product--masala", page)
        self.assertIn("hero-product--flavours", page)
        self.assertEqual(page.count("data-hero-slide "), 3)
        self.assertIn('data-price="399"', page)
        self.assertIn("6+ Suta Makhana", page)
        self.assertIn("is-featured-highlight", page)
        self.assertEqual(page.count('data-in-stock="false"'), 0)
        self.assertNotIn('class="product-stock-status"', page)
        self.assertNotIn("Out of stock", page)
        self.assertIn("data-order-success-modal", page)
        self.assertIn("data-order-success-id", page)
        self.assertIn('class="makhana-burst"', page)
        self.assertNotIn('class="hero-actions"', hero)
        self.assertIn("Patna, Bihar", page)

    def test_homepage_keeps_original_copy_and_uses_maps_for_delivery_address(self):
        page = self.client.get("/").get_data(as_text=True)
        storefront_script = (PROJECT_ROOT / "static" / "js" / "storefront-v2.js").read_text(encoding="utf-8")
        self.assertIn("Plain roasted - 200g pack", page)
        self.assertNotRegex(page, r"[\u0900-\u097F]")
        self.assertIn('node.textContent = quantity > 0 ? "Go to Cart" : "Add to Bag";', storefront_script)
        self.assertIn("data-feature-plus", page)
        self.assertIn("data-buy-now", page)
        self.assertIn("Instagram feed", page)
        self.assertNotIn("Our story", page)
        self.assertNotIn("social-card", page)
        self.assertEqual(page.count('class="instagram-reel"'), 4)
        self.assertEqual(page.count("/embed/"), 4)
        self.assertIn("data-address-map", page)
        self.assertIn("google.com/maps/search/", storefront_script)
        self.assertNotIn("roots-map-section", page)
        self.assertIn("data-order-success-id", page)

    def test_category_and_privacy_pages_are_available(self):
        mango = self.client.get("/mango")
        tea = self.client.get("/tea")
        policy = self.client.get("/privacy-and-policy")

        self.assertEqual(mango.status_code, 200)
        self.assertIn("Mango season has ended.", mango.get_data(as_text=True))
        self.assertIn("5kg-420.webp", mango.get_data(as_text=True))
        self.assertEqual(tea.status_code, 200)
        self.assertIn("Tea is almost ready.", tea.get_data(as_text=True))
        self.assertIn("tea-420.webp", tea.get_data(as_text=True))
        self.assertEqual(policy.status_code, 200)
        self.assertIn("Privacy &amp; policy", policy.get_data(as_text=True))

    def test_google_callback_stays_on_the_current_live_host(self):
        with patch.dict(os.environ, {"GOOGLE_OAUTH_REDIRECT_URI": "https://pulpsandleaves.com/auth/google/callback"}, clear=False):
            with app_module.app.test_request_context("/", base_url="https://www.pulpsandleaves.com"):
                self.assertEqual(
                    app_module.google_callback_url(),
                    "https://www.pulpsandleaves.com/auth/google/callback",
                )

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

    def test_order_headers_are_case_and_format_tolerant(self):
        headers = SheetsHandler._order_headers_from_row([" order id ", "E-MAIL ADDRESS", "google subject"])
        self.assertEqual(headers, ["Order ID", "Customer Email", "Google Subject"])

    def test_order_history_includes_the_original_orders_tab(self):
        class Worksheet:
            def __init__(self, title):
                self.title = title

        class Spreadsheet:
            def worksheets(self):
                return [
                    Worksheet("Customers"),
                    Worksheet("Orders"),
                    Worksheet("Orders 2026-07-29"),
                    Worksheet("Atharv"),
                ]

        handler = SheetsHandler.__new__(SheetsHandler)
        handler.daily_worksheets = True
        handler.worksheet_name = "Orders"
        handler._spreadsheet = Spreadsheet()
        handler._worksheet = Worksheet("Orders 2026-07-29")

        self.assertEqual(
            [worksheet.title for worksheet in handler._order_worksheets()],
            ["Orders", "Orders 2026-07-29"],
        )


if __name__ == "__main__":
    unittest.main()
