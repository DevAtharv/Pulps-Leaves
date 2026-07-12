from copy import deepcopy

from ai_parser import extract_address, extract_order_id, extract_phone, extract_quantity, parse_with_optional_ai
from delivery_config import CITIES, PRODUCTS, availability_message, city_by_choice, city_menu_text, get_delivery_schedule, product_by_choice, product_menu_text
from order_manager import OrderManager


MAIN_MENU = (
    "Welcome to Pulps & Leaves COD ordering.\n\n"
    "Please choose an option:\n"
    "1 - New Order\n"
    "2 - Edit Existing Order\n"
    "3 - Know Next Delivery Date\n"
    "4 - Connect to Agent"
)


class ConversationStore:
    """Simple in-memory state store.

    Swap this class for Redis, DynamoDB, Postgres, or a WhatsApp provider store
    when the project moves from one server to multiple workers.
    """

    def __init__(self):
        self._sessions = {}

    def get(self, user_id):
        return deepcopy(self._sessions.get(user_id, {"state": "MAIN", "data": {}, "retries": 0}))

    def save(self, user_id, session):
        self._sessions[user_id] = deepcopy(session)

    def reset(self, user_id):
        self._sessions[user_id] = {"state": "MAIN", "data": {}, "retries": 0}


class ChatbotFlow:
    def __init__(self, order_manager=None, store=None):
        self.order_manager = order_manager or OrderManager()
        self.store = store or ConversationStore()

    def handle_message(self, user_id, message):
        text = str(message or "").strip()
        session = self.store.get(user_id)

        if not text:
            return self._reply(user_id, session, "Please send a message so I can help.\n\n" + MAIN_MENU)

        if text.lower() in {"menu", "main menu", "start", "restart", "hi", "hello"}:
            self.store.reset(user_id)
            return self._response(MAIN_MENU, "MAIN")

        state = session["state"]
        handler = getattr(self, f"_handle_{state.lower()}", self._handle_main)
        reply = handler(user_id, session, text)
        self.store.save(user_id, session)
        return self._response(reply, session["state"], session.get("data", {}))

    def _handle_main(self, user_id, session, text):
        value = text.lower()
        if value in {"1", "new", "new order", "order"}:
            session["state"] = "NEW_CITY"
            session["data"] = {}
            return "Lovely. Which city should we deliver to?\n\n" + city_menu_text()
        if value in {"2", "edit", "edit order", "change order"}:
            session["state"] = "EDIT_ID"
            return "Please share your Order ID. Example: PL7K9Q2M"
        if value in {"3", "delivery", "delivery date", "date"}:
            session["state"] = "DELIVERY_CITY"
            return "Which city do you want the delivery date for?\n\n" + city_menu_text()
        if value in {"4", "agent", "support", "human"}:
            session["state"] = "MAIN"
            return self._agent_message()
        return "I did not catch that choice. Please reply with 1, 2, 3, or 4.\n\n" + MAIN_MENU

    def _handle_new_city(self, user_id, session, text):
        city = city_by_choice(text)
        if not city:
            return "Please choose a supported city:\n\n" + city_menu_text()

        session["data"]["city"] = city
        session["state"] = "NEW_PRODUCT"
        schedule = get_delivery_schedule(city)
        return f"{schedule['message']}\n\nPlease pick your box:\n{product_menu_text()}"

    def _handle_new_product(self, user_id, session, text):
        product = product_by_choice(text)
        if not product:
            parsed = parse_with_optional_ai(text, ["product"])
            product = parsed.get("product")
        if not product:
            return "Please pick one product from the catalog:\n\n" + product_menu_text()
        product_availability_error = availability_message(product)
        if product_availability_error:
            return product_availability_error + "\n\nPlease pick another product:\n" + product_menu_text()

        session["data"]["product"] = product
        session["state"] = "NEW_NAME"
        return "Great choice. Please share the customer name."

    def _handle_new_name(self, user_id, session, text):
        if len(text) < 2:
            return "Please enter the customer's full name."
        session["data"]["name"] = text.title()
        session["state"] = "NEW_ADDRESS"
        return "Please share the full delivery address."

    def _handle_new_address(self, user_id, session, text):
        parsed = parse_with_optional_ai(text, ["address"])
        address = parsed.get("address") or extract_address(text) or text
        if len(address.strip()) < 8:
            return "Please share a complete delivery address, including area or landmark."
        session["data"]["address"] = address.strip()
        session["state"] = "NEW_PHONE"
        return "Please share the 10-digit mobile number for delivery coordination."

    def _handle_new_phone(self, user_id, session, text):
        phone = extract_phone(text)
        if not phone:
            return "That number does not look valid. Please send a 10-digit Indian mobile number."
        session["data"]["phone"] = phone
        session["state"] = "NEW_QTY"
        return "How many boxes would you like? Reply with a number between 1 and 50."

    def _handle_new_qty(self, user_id, session, text):
        quantity = extract_quantity(text)
        if not quantity or quantity < 1 or quantity > 50:
            return "Please send a quantity between 1 and 50."
        session["data"]["quantity"] = quantity
        session["state"] = "NEW_NOTES"
        return "Any notes for delivery? Reply 'none' if there are no notes."

    def _handle_new_notes(self, user_id, session, text):
        session["data"]["notes"] = "" if text.lower() in {"none", "no", "na", "n/a"} else text
        session["state"] = "NEW_CONFIRM"
        return self._order_summary(session["data"]) + "\n\nReply YES to confirm or NO to start again."

    def _handle_new_confirm(self, user_id, session, text):
        value = text.lower()
        if value not in {"yes", "y", "confirm", "no", "n"}:
            return "Please reply YES to confirm or NO to start again."
        if value in {"no", "n"}:
            session["state"] = "NEW_CITY"
            session["data"] = {}
            return "No worries. Let's start fresh. Which city should we deliver to?\n\n" + city_menu_text()

        result = self.order_manager.create_order(session["data"], source="WhatsApp")
        if not result["ok"]:
            session["state"] = "MAIN"
            return "I could not place the order yet: " + "; ".join(result["errors"].values()) + "\n\n" + MAIN_MENU

        order = result["order"]
        session["state"] = "MAIN"
        session["data"] = {}
        return (
            "Order placed.\n"
            f"Order ID: {order['Order ID']}\n"
            f"Status: {order['Order Status']}\n"
            "Payment mode: Cash on Delivery\n\n"
            + MAIN_MENU
        )

    def _handle_edit_id(self, user_id, session, text):
        order_id = extract_order_id(text) or text.strip().upper()
        order, error = self.order_manager.validate_order_id(order_id)
        if error:
            return error + "\n\nPlease share the Order ID again, or type MENU."
        requester_phone = extract_phone(user_id)
        order_phone = extract_phone(order.get("Phone", ""))
        if not requester_phone or not order_phone or requester_phone != order_phone:
            session["state"] = "MAIN"
            session["data"] = {}
            return "I could not verify that order for this WhatsApp number. Please contact support.\n\n" + MAIN_MENU

        session["data"] = {"edit_order_id": order["Order ID"], "edit_phone": order.get("Phone", "")}
        session["state"] = "EDIT_FIELD"
        parsed = parse_with_optional_ai(text, ["address", "phone"])
        if parsed.get("address"):
            result = self.order_manager.update_address(order["Order ID"], parsed["address"])
            session["state"] = "MAIN"
            return self._edit_result(result)
        if parsed.get("phone"):
            result = self.order_manager.update_phone(order["Order ID"], parsed["phone"])
            session["state"] = "MAIN"
            return self._edit_result(result)

        return (
            f"Found order {order['Order ID']} for {order['Customer Name']}.\n\n"
            "What would you like to update?\n"
            "1 - Change Delivery Address\n"
            "2 - Change Contact Number"
        )

    def _handle_edit_field(self, user_id, session, text):
        parsed = parse_with_optional_ai(text, ["address", "phone"])
        order_id = session["data"]["edit_order_id"]
        if parsed.get("address"):
            result = self.order_manager.update_address(order_id, parsed["address"])
            session["state"] = "MAIN"
            return self._edit_result(result)
        if parsed.get("phone"):
            result = self.order_manager.update_phone(order_id, parsed["phone"])
            session["state"] = "MAIN"
            return self._edit_result(result)

        value = text.lower()
        if value in {"1", "address", "change address"}:
            session["state"] = "EDIT_ADDRESS"
            return "Please send the new delivery address."
        if value in {"2", "phone", "number", "mobile", "change number"}:
            session["state"] = "EDIT_PHONE"
            return "Please send the new 10-digit mobile number."
        return "Please choose 1 for address or 2 for contact number."

    def _handle_edit_address(self, user_id, session, text):
        address = extract_address(text) or text
        result = self.order_manager.update_address(session["data"]["edit_order_id"], address)
        session["state"] = "MAIN"
        return self._edit_result(result)

    def _handle_edit_phone(self, user_id, session, text):
        phone = extract_phone(text) or text
        result = self.order_manager.update_phone(session["data"]["edit_order_id"], phone)
        session["state"] = "MAIN"
        return self._edit_result(result)

    def _handle_delivery_city(self, user_id, session, text):
        city = city_by_choice(text)
        if not city:
            return "Please choose one of our delivery cities:\n\n" + city_menu_text()
        session["state"] = "MAIN"
        return self.order_manager.get_delivery_message(city) + "\n\n" + MAIN_MENU

    def _order_summary(self, data):
        city_label = CITIES[data["city"]]["label"]
        return (
            "Please confirm your COD order:\n"
            f"Name: {data['name']}\n"
            f"City: {city_label}\n"
            f"Phone: {data['phone']}\n"
            f"Address: {data['address']}\n"
            f"Product: {data['product']}\n"
            f"Quantity: {data['quantity']}\n"
            f"Notes: {data.get('notes') or 'None'}"
        )

    def _edit_result(self, result):
        if not result["ok"]:
            return result["error"] + "\n\n" + MAIN_MENU
        return f"Updated order {result['order_id']} successfully.\n\n" + MAIN_MENU

    def _reply(self, user_id, session, reply):
        self.store.save(user_id, session)
        return self._response(reply, session.get("state", "MAIN"), session.get("data", {}))

    @staticmethod
    def _agent_message():
        import os

        return (
            "A real person can help from here.\n"
            f"Phone: {os.getenv('SUPPORT_PHONE', '+91 98354 96666')}\n"
            f"Email: {os.getenv('SUPPORT_EMAIL', 'support@pulpsandleaves.example')}\n\n"
            + MAIN_MENU
        )

    @staticmethod
    def _response(reply, state, data=None):
        return {"reply": reply, "state": state, "data": data or {}}
