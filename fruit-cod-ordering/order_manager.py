import re
import secrets
import string

from ai_parser import normalize_phone
from delivery_config import CITIES, ORDER_STATUSES, availability_message, get_delivery_schedule, normalize_available_city, normalize_city, product_by_choice, product_record
from sheets_handler import SheetsHandler
from time_utils import timestamp_local


ORDER_ID_PATTERN = re.compile(r"^PL[A-Z0-9]{10}$")
ORDER_ID_ALPHABET = string.ascii_uppercase + string.digits


class OrderManager:
    def __init__(self, sheets_handler=None):
        self.sheets = sheets_handler or SheetsHandler()

    def create_order(self, payload, source="Website"):
        clean_data, errors = self.validate_new_order(payload)
        if errors:
            return {"ok": False, "errors": errors}

        order_id = self.generate_order_id()
        unit_price = int(clean_data["subtotal"])
        total_amount = int(clean_data["total_amount"])
        now = timestamp_local()
        notes = clean_data.get("notes", "")
        if clean_data.get("delivery_charge"):
            notes = f"{notes} Delivery charge: Rs {clean_data['delivery_charge']}.".strip()
        order = {
            "Order ID": order_id,
            "Timestamp": now,
            "Customer Name": clean_data["name"],
            "Phone": clean_data["phone"],
            "Address": clean_data["address"],
            "City": CITIES[clean_data["city"]]["label"],
            "Product": clean_data["product_summary"],
            "Quantity": str(clean_data["quantity"]),
            "Unit Price": str(unit_price),
            "Total Amount": str(total_amount),
            "Payment Mode": "COD",
            "Notes": notes,
            "Order Status": "Pending",
            "Confirmed": False,
            "Packed": False,
            "Delivered": False,
            "Cancelled": False,
            "Source": source,
            "Updated At": now,
        }
        self.sheets.append_order(order)
        return {"ok": True, "duplicate": False, "order": order}

    def validate_new_order(self, payload):
        errors = {}
        name = str(payload.get("name", "")).strip()
        address = str(payload.get("address", "")).strip()
        city = normalize_available_city(payload.get("city", ""))
        phone = normalize_phone(payload.get("phone", ""))
        qty_5kg = self._parse_quantity(payload.get("qty_5kg", "0"))
        qty_3kg = self._parse_quantity(payload.get("qty_3kg", "0"))
        uses_cart_quantities = any(key in payload for key in ("qty_5kg", "qty_3kg"))

        if uses_cart_quantities:
            product_lines = []
            subtotal = 0
            total_quantity = qty_5kg + qty_3kg
            product_5kg = product_record("Malda Mango 5Kg Box")
            product_3kg = product_record("Malda Mango 3Kg Box")

            if qty_5kg:
                product_lines.append(f"5Kg Box x {qty_5kg}")
                subtotal += qty_5kg * int(product_5kg["price"])
            if qty_3kg:
                product_lines.append(f"3Kg Box x {qty_3kg}")
                subtotal += qty_3kg * int(product_3kg["price"])

            delivery_charge = 30 if qty_3kg > 0 and qty_5kg == 0 else 0
            product_summary = ", ".join(product_lines)
        else:
            product = product_by_choice(payload.get("product", "")) or str(payload.get("product", "")).strip()
            quantity = self._parse_quantity(payload.get("quantity", "0"))
            selected_product = product_record(product) if product else None
            subtotal = int(selected_product["price"]) * quantity if selected_product else 0
            delivery_charge = 30 if product == "Malda Mango 3Kg Box" and quantity > 0 else 0
            total_quantity = quantity
            product_summary = product

        if len(name) < 2:
            errors["name"] = "Please enter the customer's full name."
        if not phone:
            errors["phone"] = "Please enter a valid 10-digit Indian mobile number."
        if len(address) < 8:
            errors["address"] = "Please enter a complete delivery address."
        if not city:
            errors["city"] = "Please select Bangalore or Hyderabad."
        if not product_summary:
            errors["product"] = "Please choose a product from the catalog."
        elif not uses_cart_quantities:
            product_availability_error = availability_message(product)
            if product_availability_error:
                errors["product"] = product_availability_error
        if total_quantity < 1 or total_quantity > 50:
            errors["quantity"] = "Quantity must be between 1 and 50."

        return (
            {
                "name": name,
                "phone": phone,
                "address": address,
                "city": city,
                "product": product_summary,
                "product_summary": product_summary,
                "quantity": total_quantity,
                "subtotal": subtotal,
                "delivery_charge": delivery_charge,
                "total_amount": subtotal + delivery_charge,
                "notes": str(payload.get("notes", "")).strip(),
            },
            errors,
        )

    @staticmethod
    def _parse_quantity(value):
        try:
            return int(str(value).strip())
        except ValueError:
            return 0

    def generate_order_id(self):
        while True:
            candidate = "PL" + "".join(secrets.choice(ORDER_ID_ALPHABET) for _ in range(10))
            if not self.sheets.find_order(candidate):
                return candidate

    def validate_order_id(self, order_id):
        normalized = str(order_id or "").strip().upper()
        if not ORDER_ID_PATTERN.match(normalized):
            return None, "That Order ID format does not look right. Example: PL7K9Q2M4XB."
        order = self.sheets.find_order(normalized)
        if not order:
            return None, "I could not find that Order ID. Please check the ID and try again."
        return order, None

    def update_address(self, order_id, new_address):
        new_address = str(new_address or "").strip()
        if len(new_address) < 8:
            return {"ok": False, "error": "Please share a complete delivery address."}
        return self._update_order(order_id, {"Address": new_address})

    def update_phone(self, order_id, new_phone):
        phone = normalize_phone(new_phone)
        if not phone:
            return {"ok": False, "error": "Please enter a valid 10-digit Indian mobile number."}
        return self._update_order(order_id, {"Phone": phone})

    def update_status(self, order_id, status):
        if status not in ORDER_STATUSES:
            return {"ok": False, "error": "Please select a valid status."}
        status_flags = {
            "Confirmed": status in {"Confirmed", "Packed", "Out for Delivery", "Delivered"},
            "Packed": status in {"Packed", "Out for Delivery", "Delivered"},
            "Delivered": status == "Delivered",
            "Cancelled": status == "Cancelled",
        }
        return self._update_order(order_id, {"Order Status": status, **status_flags})

    def list_orders(self, city=None, status=None, query=None):
        orders = self.sheets.get_all_orders()
        if city:
            normalized_city = normalize_city(city)
            city_label = CITIES[normalized_city]["label"] if normalized_city else city
            orders = [order for order in orders if order.get("City", "").lower() == city_label.lower()]
        if status:
            orders = [order for order in orders if order.get("Order Status") == status]
        if query:
            q = str(query).strip().lower()
            orders = [
                order
                for order in orders
                if q in order.get("Order ID", "").lower()
                or q in order.get("Customer Name", "").lower()
                or q in order.get("Phone", "").lower()
            ]
        return list(reversed(orders))

    def get_delivery_message(self, city):
        schedule = get_delivery_schedule(city)
        if not schedule:
            return None
        return schedule["message"]

    def _update_order(self, order_id, updates):
        order, error = self.validate_order_id(order_id)
        if error:
            return {"ok": False, "error": error}
        updated = self.sheets.update_order(order["Order ID"], updates)
        if not updated:
            return {"ok": False, "error": "The order could not be updated. Please try again."}
        return {"ok": True, "order_id": order["Order ID"], "updates": updates}
