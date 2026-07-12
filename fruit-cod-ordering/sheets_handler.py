import json
import os
import re
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

import gspread
import pandas as pd
from gspread.exceptions import APIError
from gspread.utils import rowcol_to_a1

from time_utils import timestamp_local, today_local


STATUS_OPTIONS = [
    "Received",
    "Confirmed",
    "Packed",
    "Out for Delivery",
    "Delivered",
    "Cancelled",
]


ORDER_HEADERS = [
    "Order ID",
    "Checkout Token",
    "Timestamp",
    "Customer Name",
    "Phone",
    "Address",
    "City",
    "Product",
    "Quantity",
    "Unit Price",
    "Total Amount",
    "Payment Mode",
    "Payment Status",
    "Razorpay Order ID",
    "Razorpay Payment ID",
    "Notes",
    "Order Status",
    "Confirmed",
    "Packed",
    "Delivered",
    "Cancelled",
    "Source",
    "Customer Email",
    "Google Subject",
    "Updated At",
]

LEGACY_ORDER_HEADERS = [header for header in ORDER_HEADERS if header != "Checkout Token"]
ORDER_HEADER_ALIASES = {
    "Email": "Customer Email",
    "Email Address": "Customer Email",
    "Customer Email ID": "Customer Email",
    "Google Email": "Customer Email",
}


CUSTOMER_HEADERS = [
    "Google Subject",
    "Email",
    "Name",
    "Picture",
    "Phone",
    "Default City",
    "Default Address",
    "Created At",
    "Updated At",
]


ATHARV_HEADERS = [
    "Timestamp",
    "Name",
    "Order ID",
    "Phone",
    "Address",
    "Mode of Payment",
    "Product",
    "Order Amount",
    "Coupon Discount",
    "Online Payment Discount",
    "Total Discount",
    "Razorpay Fee",
    "Razorpay GST",
    "Razorpay Total Fee",
    "Bank Received",
    "Delivered",
    "Order Status",
    "Razorpay Payment ID",
    "Updated At",
]

ATHARV_TAB_DEFAULT_NAME = "Atharv"
REPORT_DELIVERY_FREE_ABOVE = 698
REPORT_DELIVERY_CHARGE = 30
REPORT_FREE_DELIVERY_COUPONS = {"PLB699FD"}


class SheetsHandler:
    def __init__(self):
        self.storage_mode = self._read_env("STORAGE_MODE", "auto").lower()
        self.sheet_id = self._read_env("GOOGLE_SHEET_ID")
        self.worksheet_name = self._read_env("GOOGLE_WORKSHEET_NAME", "Orders")
        self.daily_worksheets = self._read_env("GOOGLE_DAILY_WORKSHEETS", "true").lower() == "true"
        self.credentials_file = self._read_env("GOOGLE_CREDENTIALS_FILE", "credentials.json")
        self.local_file = self._resolve_local_file()
        self.local_customers_file = self._resolve_local_customers_file()
        self.atharv_worksheet_name = self._read_env("ATHARV_WORKSHEET_NAME", ATHARV_TAB_DEFAULT_NAME)
        self.razorpay_fee_rate = self._read_decimal_env("RAZORPAY_FEE_RATE", "0.02")
        self.razorpay_fee_gst_rate = self._read_decimal_env("RAZORPAY_FEE_GST_RATE", "0.18")
        self._spreadsheet = None
        self._worksheet = None
        self._headers = ORDER_HEADERS.copy()
        self._prepared_worksheet_titles = set()

        if self.storage_mode in {"auto", "sheets"} and self._can_use_sheets():
            try:
                self._worksheet = self._connect_google_sheet()
            except Exception:
                if self.storage_mode == "sheets" and not self._allow_local_fallback():
                    raise
                self._ensure_local_file()
        elif self.storage_mode == "sheets":
            if not self._allow_local_fallback():
                raise RuntimeError("Google Sheets mode is enabled, but sheet id or credentials are missing.")
            self._ensure_local_file()
        else:
            self._ensure_local_file()

    @property
    def backend_name(self):
        return "Google Sheets" if self._worksheet else "Local Excel"

    @staticmethod
    def _sheet_update(worksheet, range_name, values, **kwargs):
        return worksheet.update(values, range_name=range_name, **kwargs)

    def append_order(self, order):
        if self._worksheet:
            worksheet = self._active_order_worksheet()
            self._worksheet = worksheet
            self._ensure_order_header_best_effort(worksheet)
            headers = self._headers or ORDER_HEADERS.copy()
            self._compact_data_rows(worksheet, headers, key_column=0)
            row = [order.get(header, "") for header in headers]
            next_row = self._next_available_row(worksheet, key_column=0)
            self._retry_sheet_write(
                lambda: self._sheet_update(
                    worksheet,
                    f"A{next_row}:{rowcol_to_a1(next_row, len(headers))}",
                    [row],
                    value_input_option="RAW",
                )
            )
            self._sync_atharv_order_best_effort(order)
            return

        records = self.get_all_orders()
        records.append({header: order.get(header, "") for header in ORDER_HEADERS})
        self._write_local_records(records)

    def get_all_orders(self):
        if self._worksheet:
            orders = []
            for worksheet in self._order_worksheets():
                records = self._records_from_worksheet_values(worksheet)
                for record in records:
                    if record.get("Order ID"):
                        cleaned = self._clean_record(record)
                        cleaned["_Worksheet"] = worksheet.title
                        orders.append(cleaned)
            return orders

        self._ensure_local_file()
        frame = pd.read_excel(self.local_file, dtype=str).fillna("")
        for header in ORDER_HEADERS:
            if header not in frame.columns:
                frame[header] = ""
        return [self._clean_record(record) for record in frame.to_dict("records") if record.get("Order ID")]

    def find_order(self, order_id):
        order_id = str(order_id).strip().upper()
        for order in self.get_all_orders():
            if str(order.get("Order ID", "")).strip().upper() == order_id:
                return order
        return None

    def find_order_by_checkout_token(self, checkout_token):
        checkout_token = str(checkout_token or "").strip()
        if not checkout_token:
            return None
        for order in reversed(self.get_all_orders()):
            if str(order.get("Checkout Token", "")).strip() == checkout_token:
                return order
        return None

    def find_order_by_razorpay_payment_id(self, payment_id):
        payment_id = str(payment_id or "").strip()
        if not payment_id:
            return None
        for order in reversed(self.get_all_orders()):
            if str(order.get("Razorpay Payment ID", "")).strip() == payment_id:
                return order
        return None

    def update_order(self, order_id, updates):
        order_id = str(order_id).strip().upper()
        normalized_updates = {
            header: value
            for header, value in updates.items()
            if header in ORDER_HEADERS and value is not None
        }
        normalized_updates["Updated At"] = timestamp_local()

        if self._worksheet:
            for worksheet in self._order_worksheets():
                headers = self._prepare_worksheet(worksheet)
                rows = worksheet.get_all_values()
                row_headers = self._order_headers_from_row(rows[0]) if rows else ORDER_HEADERS
                for index, row in enumerate(rows[1:], start=2):
                    if not any(str(value).strip() for value in row):
                        continue
                    record = self._record_from_row(row, row_headers, ORDER_HEADERS)
                    if str(record.get("Order ID", "")).strip().upper() == order_id:
                        for header, value in normalized_updates.items():
                            column = headers.index(header) + 1
                            self._sheet_update(
                                worksheet,
                                rowcol_to_a1(index, column),
                                [[value]],
                                value_input_option="RAW",
                            )
                        record.update(normalized_updates)
                        self._sync_atharv_order_best_effort(record)
                        return True
            return False

        records = self.get_all_orders()
        updated = False
        for record in records:
            if str(record.get("Order ID", "")).strip().upper() == order_id:
                record.update(normalized_updates)
                updated = True
                break
        if updated:
            self._write_local_records(records)
        return updated

    def find_customer(self, google_subject=None, email=None):
        google_subject = str(google_subject or "").strip()
        email = str(email or "").strip().lower()
        for customer in self.get_all_customers():
            if google_subject and customer.get("Google Subject") == google_subject:
                return customer
            if email and customer.get("Email", "").lower() == email:
                return customer
        return None

    def upsert_customer(self, profile):
        now = timestamp_local()
        google_subject = str(profile.get("google_subject", "")).strip()
        email = str(profile.get("email", "")).strip().lower()
        if not google_subject or not email:
            return None

        try:
            existing = self.find_customer(google_subject=google_subject, email=email)
        except Exception:
            existing = None
        existing_phone = existing.get("Phone", "") if existing else ""
        existing_city = existing.get("Default City", "") if existing else ""
        existing_address = existing.get("Default Address", "") if existing else ""
        profile_phone = str(profile.get("phone", "")).strip()
        profile_city = str(profile.get("city", "")).strip()
        profile_address = str(profile.get("address", "")).strip()
        customer = {
            "Google Subject": google_subject,
            "Email": email,
            "Name": str(profile.get("name", "")).strip(),
            "Picture": str(profile.get("picture", "")).strip(),
            "Phone": profile_phone or existing_phone,
            "Default City": profile_city or existing_city,
            "Default Address": profile_address or existing_address,
            "Created At": existing.get("Created At", now) if existing else now,
            "Updated At": now,
        }

        if self._worksheet:
            worksheet = self._customers_worksheet()
            rows = worksheet.get_all_values()
            if not rows:
                self._retry_sheet_write(lambda: self._sheet_update(worksheet, "A1", [CUSTOMER_HEADERS], value_input_option="RAW"))
                rows = [CUSTOMER_HEADERS]
            headers = self._customer_headers_from_row(rows[0])
            for index, row in enumerate(rows[1:], start=2):
                record = self._record_from_row(row, headers, CUSTOMER_HEADERS)
                if str(record.get("Google Subject", "")).strip() == google_subject or str(record.get("Email", "")).strip().lower() == email:
                    customer["Phone"] = profile_phone or record.get("Phone", "")
                    customer["Default City"] = profile_city or record.get("Default City", "")
                    customer["Default Address"] = profile_address or record.get("Default Address", "")
                    customer["Created At"] = record.get("Created At", now) or now
                    self._retry_sheet_write(
                        lambda: self._sheet_update(
                            worksheet,
                            f"A{index}:{rowcol_to_a1(index, len(CUSTOMER_HEADERS))}",
                            [[customer.get(header, "") for header in CUSTOMER_HEADERS]],
                            value_input_option="RAW",
                        )
                    )
                    return customer
            self._compact_data_rows(worksheet, CUSTOMER_HEADERS, key_column=0)
            next_row = self._next_available_row(worksheet, key_column=0)
            self._retry_sheet_write(
                lambda: self._sheet_update(
                    worksheet,
                    f"A{next_row}:{rowcol_to_a1(next_row, len(CUSTOMER_HEADERS))}",
                    [[customer.get(header, "") for header in CUSTOMER_HEADERS]],
                    value_input_option="RAW",
                )
            )
            return customer

        records = self.get_all_customers()
        replaced = False
        for index, record in enumerate(records):
            if record.get("Google Subject") == google_subject or record.get("Email", "").lower() == email:
                records[index] = customer
                replaced = True
                break
        if not replaced:
            records.append(customer)
        self._write_local_customers(records)
        return customer

    def update_customer_profile(self, google_subject, updates):
        google_subject = str(google_subject or "").strip()
        if not google_subject:
            return None
        allowed_updates = {
            "Phone": updates.get("phone", ""),
            "Default City": updates.get("city", ""),
            "Default Address": updates.get("address", ""),
            "Updated At": timestamp_local(),
        }
        allowed_updates = {key: str(value).strip() for key, value in allowed_updates.items() if value is not None}

        if self._worksheet:
            worksheet = self._customers_worksheet()
            rows = worksheet.get_all_values()
            if not rows:
                self._retry_sheet_write(lambda: self._sheet_update(worksheet, "A1", [CUSTOMER_HEADERS], value_input_option="RAW"))
                rows = [CUSTOMER_HEADERS]
            headers = self._customer_headers_from_row(rows[0])
            for index, row in enumerate(rows[1:], start=2):
                record = self._record_from_row(row, headers, CUSTOMER_HEADERS)
                if str(record.get("Google Subject", "")).strip() == google_subject:
                    merged = {header: str(record.get(header, "")) for header in CUSTOMER_HEADERS}
                    merged.update(allowed_updates)
                    self._retry_sheet_write(
                        lambda: self._sheet_update(
                            worksheet,
                            f"A{index}:{rowcol_to_a1(index, len(CUSTOMER_HEADERS))}",
                            [[merged.get(header, "") for header in CUSTOMER_HEADERS]],
                            value_input_option="RAW",
                        )
                    )
                    updated = {header: str(record.get(header, "")) for header in CUSTOMER_HEADERS}
                    updated.update(allowed_updates)
                    return updated
            return None

        records = self.get_all_customers()
        for record in records:
            if record.get("Google Subject") == google_subject:
                record.update(allowed_updates)
                self._write_local_customers(records)
                return record
        return None

    def get_all_customers(self):
        if self._worksheet:
            worksheet = self._customers_worksheet()
            rows = worksheet.get_all_values()
            if not rows:
                return []
            headers = self._customer_headers_from_row(rows[0])
            return [
                self._clean_customer_record(record)
                for record in (self._record_from_row(row, headers, CUSTOMER_HEADERS) for row in rows[1:])
                if record.get("Google Subject") or record.get("Email")
            ]

        self._ensure_local_customers_file()
        frame = pd.read_excel(self.local_customers_file, dtype=str).fillna("")
        for header in CUSTOMER_HEADERS:
            if header not in frame.columns:
                frame[header] = ""
        return [self._clean_customer_record(record) for record in frame.to_dict("records") if record.get("Google Subject") or record.get("Email")]

    def count_orders_with_prefix(self, prefix):
        return sum(1 for order in self.get_all_orders() if str(order.get("Order ID", "")).startswith(prefix))

    def _can_use_sheets(self):
        credentials_json = self._read_env("GOOGLE_CREDENTIALS_JSON")
        return bool(self.sheet_id and (credentials_json or Path(self.credentials_file).exists()))

    def _connect_google_sheet(self):
        credentials_json = self._read_env("GOOGLE_CREDENTIALS_JSON")
        if credentials_json:
            client = gspread.service_account_from_dict(json.loads(credentials_json))
        else:
            client = gspread.service_account(filename=self.credentials_file)
        self._spreadsheet = client.open_by_key(self.sheet_id)
        worksheet = self._today_worksheet()
        self._headers = ORDER_HEADERS.copy()
        return worksheet

    def format_all_order_tabs(self):
        if not self._worksheet:
            return
        for worksheet in self._order_worksheets():
            self._prepare_worksheet(worksheet)

    def _today_worksheet(self):
        worksheet_title = self._worksheet_title_for_date(today_local())
        try:
            return self._spreadsheet.worksheet(worksheet_title)
        except gspread.WorksheetNotFound:
            worksheet = self._spreadsheet.add_worksheet(title=worksheet_title, rows=1000, cols=len(ORDER_HEADERS))
            worksheet.append_row(ORDER_HEADERS, value_input_option="RAW")
            return worksheet

    def _active_order_worksheet(self):
        if not self.daily_worksheets:
            return self._worksheet
        return self._today_worksheet()

    def _order_worksheets(self):
        if not self.daily_worksheets:
            return [self._worksheet]
        prefix = f"{self.worksheet_name} "
        worksheets = [
            worksheet
            for worksheet in self._spreadsheet.worksheets()
            if worksheet.title.startswith(prefix)
        ]
        if not worksheets:
            worksheets = [self._today_worksheet()]
        return worksheets

    def _customers_worksheet(self, prepare=True):
        try:
            worksheet = self._spreadsheet.worksheet("Customers")
        except gspread.WorksheetNotFound:
            worksheet = self._spreadsheet.add_worksheet(title="Customers", rows=1000, cols=len(CUSTOMER_HEADERS))
            worksheet.append_row(CUSTOMER_HEADERS, value_input_option="RAW")
            self._style_customer_worksheet(worksheet)
            return worksheet
        if prepare:
            self._prepare_customer_worksheet(worksheet)
        return worksheet

    def sync_atharv_orders(self):
        if not self._worksheet or not self._spreadsheet:
            return {"ok": False, "error": "Google Sheets is not connected."}

        orders = self.get_all_orders()
        worksheet = self._atharv_worksheet(prepare=False)
        rows = [ATHARV_HEADERS] + [self._atharv_row_from_order(order) for order in orders]
        self._retry_sheet_write(lambda: worksheet.clear())
        self._retry_sheet_write(
            lambda: self._sheet_update(
                worksheet,
                f"A1:{rowcol_to_a1(max(len(rows), 1), len(ATHARV_HEADERS))}",
                rows,
                value_input_option="RAW",
            )
        )
        self._style_atharv_worksheet(worksheet)
        return {"ok": True, "worksheet": worksheet.title, "synced": len(orders)}

    def _atharv_worksheet(self, prepare=True):
        try:
            worksheet = self._spreadsheet.worksheet(self.atharv_worksheet_name)
        except gspread.WorksheetNotFound:
            worksheet = self._spreadsheet.add_worksheet(
                title=self.atharv_worksheet_name,
                rows=1000,
                cols=len(ATHARV_HEADERS),
            )
            worksheet.append_row(ATHARV_HEADERS, value_input_option="RAW")
            self._style_atharv_worksheet(worksheet)
            return worksheet
        if prepare:
            self._prepare_atharv_worksheet(worksheet)
        return worksheet

    def _sync_atharv_order_best_effort(self, order):
        if not self._worksheet or not self._spreadsheet:
            return
        try:
            self._upsert_atharv_order(order)
        except Exception:
            # Reporting should never block accepting or updating an order.
            return

    def _upsert_atharv_order(self, order):
        order_id = str(order.get("Order ID", "")).strip().upper()
        if not order_id:
            return

        worksheet = self._atharv_worksheet()
        row = self._atharv_row_from_order(order)
        rows = worksheet.get_all_values()
        order_id_index = ATHARV_HEADERS.index("Order ID")
        for row_number, existing_row in enumerate(rows[1:], start=2):
            if str(self._row_value(existing_row, order_id_index)).strip().upper() == order_id:
                self._retry_sheet_write(
                    lambda: self._sheet_update(
                        worksheet,
                        f"A{row_number}:{rowcol_to_a1(row_number, len(ATHARV_HEADERS))}",
                        [row],
                        value_input_option="RAW",
                    )
                )
                return

        next_row = self._next_available_row(worksheet, key_column=order_id_index)
        self._retry_sheet_write(
            lambda: self._sheet_update(
                worksheet,
                f"A{next_row}:{rowcol_to_a1(next_row, len(ATHARV_HEADERS))}",
                [row],
                value_input_option="RAW",
            )
        )

    def _atharv_row_from_order(self, order):
        subtotal = self._money_decimal(order.get("Unit Price", "0"))
        order_amount = self._money_decimal(order.get("Total Amount", "0"))
        notes = str(order.get("Notes", "") or "")
        online_discount = self._notes_money(notes, "Online payment discount")
        delivery_charge = self._notes_money(notes, "Delivery charge")
        coupon_codes = self._coupon_codes_from_notes(notes)
        coupon_discount = self._coupon_discount_for_report(
            subtotal,
            order_amount,
            online_discount,
            delivery_charge,
            coupon_codes,
        )
        total_discount = coupon_discount + online_discount
        razorpay_fee, razorpay_gst, razorpay_total_fee, bank_received = self._razorpay_fee_breakup(order, order_amount)
        delivered = self._truthy_sheet_value(order.get("Delivered")) or str(order.get("Order Status", "")).strip() == "Delivered"

        return [
            order.get("Timestamp", ""),
            order.get("Customer Name", ""),
            order.get("Order ID", ""),
            order.get("Phone", ""),
            order.get("Address", ""),
            order.get("Payment Mode", ""),
            order.get("Product", ""),
            self._sheet_money(order_amount),
            self._sheet_money(coupon_discount),
            self._sheet_money(online_discount),
            self._sheet_money(total_discount),
            self._sheet_money(razorpay_fee),
            self._sheet_money(razorpay_gst),
            self._sheet_money(razorpay_total_fee),
            self._sheet_money(bank_received),
            delivered,
            order.get("Order Status", ""),
            order.get("Razorpay Payment ID", ""),
            order.get("Updated At", ""),
        ]

    def _razorpay_fee_breakup(self, order, order_amount):
        if not self._is_razorpay_payment(order) or order_amount <= 0:
            zero = Decimal("0")
            return zero, zero, zero, zero

        fee = self._round_money(order_amount * self.razorpay_fee_rate)
        gst = self._round_money(fee * self.razorpay_fee_gst_rate)
        total_fee = fee + gst
        bank_received = max(order_amount - total_fee, Decimal("0"))
        return fee, gst, total_fee, bank_received

    @staticmethod
    def _is_razorpay_payment(order):
        mode = str(order.get("Payment Mode", "") or "").strip().lower()
        payment_id = str(order.get("Razorpay Payment ID", "") or "").strip()
        razorpay_order_id = str(order.get("Razorpay Order ID", "") or "").strip()
        return "razorpay" in mode or bool(payment_id) or bool(razorpay_order_id)

    @staticmethod
    def _coupon_discount_for_report(subtotal, order_amount, online_discount, delivery_charge, coupon_codes):
        product_coupon_discount = max(subtotal - online_discount + delivery_charge - order_amount, Decimal("0"))
        delivery_coupon_discount = Decimal("0")
        if (
            coupon_codes.intersection(REPORT_FREE_DELIVERY_COUPONS)
            and Decimal("0") < subtotal <= Decimal(str(REPORT_DELIVERY_FREE_ABOVE))
            and delivery_charge == 0
        ):
            delivery_coupon_discount = Decimal(str(REPORT_DELIVERY_CHARGE))
        return product_coupon_discount + delivery_coupon_discount

    @staticmethod
    def _coupon_codes_from_notes(notes):
        match = re.search(r"Coupons applied:\s*([^;]+)", str(notes or ""), flags=re.IGNORECASE)
        if not match:
            return set()
        return {
            code.strip().upper()
            for code in match.group(1).split(",")
            if code.strip()
        }

    @staticmethod
    def _notes_money(notes, label):
        pattern = rf"{re.escape(label)}\s*:?\s*(?:Rs|₹)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)"
        match = re.search(pattern, str(notes or ""), flags=re.IGNORECASE)
        return SheetsHandler._money_decimal(match.group(1)) if match else Decimal("0")

    @staticmethod
    def _money_decimal(value):
        if isinstance(value, Decimal):
            return value
        if isinstance(value, bool):
            return Decimal("0")
        if isinstance(value, (int, float)):
            return Decimal(str(value))
        text = str(value or "").replace(",", "")
        match = re.search(r"-?[0-9]+(?:\.[0-9]+)?", text)
        if not match:
            return Decimal("0")
        try:
            return Decimal(match.group(0))
        except InvalidOperation:
            return Decimal("0")

    @staticmethod
    def _round_money(value):
        return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _sheet_money(value):
        rounded = SheetsHandler._round_money(value)
        if rounded == rounded.to_integral_value():
            return int(rounded)
        return float(rounded)

    @staticmethod
    def _truthy_sheet_value(value):
        if isinstance(value, bool):
            return value
        return str(value or "").strip().lower() in {"true", "yes", "1", "delivered"}

    @staticmethod
    def _resolve_local_file():
        configured_path = SheetsHandler._read_env("LOCAL_ORDERS_FILE")
        if configured_path:
            return Path(configured_path)
        if os.getenv("VERCEL"):
            return Path("/tmp/orders.xlsx")
        return Path("data/orders.xlsx")

    @staticmethod
    def _resolve_local_customers_file():
        configured_path = SheetsHandler._read_env("LOCAL_CUSTOMERS_FILE")
        if configured_path:
            return Path(configured_path)
        if os.getenv("VERCEL"):
            return Path("/tmp/customers.xlsx")
        return Path("data/customers.xlsx")

    @staticmethod
    def _allow_local_fallback():
        if os.getenv("VERCEL"):
            return False
        explicit = SheetsHandler._read_env("LOCAL_PREVIEW_FALLBACK", "").lower()
        if explicit in {"1", "true", "yes"}:
            return True
        return SheetsHandler._read_env("FLASK_ENV", "").lower() == "development"

    @staticmethod
    def _read_env(name, default=""):
        value = os.getenv(name, default)
        if value is None:
            return default
        cleaned = str(value).strip().lstrip("\ufeff")
        if cleaned.startswith('"') and cleaned.endswith('"') and len(cleaned) >= 2:
            cleaned = cleaned[1:-1]
        return cleaned.replace("\\r\\n", "").strip()

    @staticmethod
    def _read_decimal_env(name, default):
        value = SheetsHandler._read_env(name, default)
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return Decimal(str(default))

    def _worksheet_title_for_date(self, value):
        if not self.daily_worksheets:
            return self.worksheet_name
        return f"{self.worksheet_name} {value:%Y-%m-%d}"

    @staticmethod
    def _ensure_worksheet_headers(worksheet):
        first_row = worksheet.row_values(1)
        if not first_row:
            worksheet.append_row(ORDER_HEADERS)
            return ORDER_HEADERS.copy()

        deprecated_headers = {"Phone Verified", "Verified At", "Verification Channel"}
        extras = [header for header in first_row if header and header not in ORDER_HEADERS and header not in deprecated_headers]
        canonical_headers = ORDER_HEADERS + extras
        if first_row == canonical_headers:
            return canonical_headers

        rows = worksheet.get_all_values()
        source_headers = SheetsHandler._order_headers_from_row(first_row)
        normalized_rows = []
        for row in rows[1:]:
            if not any(str(value).strip() for value in row):
                continue
            record = SheetsHandler._record_from_row(row, source_headers, canonical_headers)
            if not str(record.get("Order ID", "")).strip():
                continue
            normalized_rows.append([record.get(header, "") for header in canonical_headers])

        worksheet.clear()
        rows = [canonical_headers] + normalized_rows
        self._sheet_update(worksheet, "A1", rows, value_input_option="RAW")
        return canonical_headers

    @staticmethod
    def _ensure_customer_headers(worksheet):
        first_row = worksheet.row_values(1)
        if not first_row:
            worksheet.append_row(CUSTOMER_HEADERS)
            return CUSTOMER_HEADERS.copy()

        canonical_headers = CUSTOMER_HEADERS.copy()
        if first_row == canonical_headers:
            return canonical_headers

        records = worksheet.get_all_records(default_blank="")
        normalized_rows = [
            [record.get(header, "") for header in canonical_headers]
            for record in records
            if record.get("Google Subject") or record.get("Email")
        ]
        worksheet.clear()
        self._sheet_update(worksheet, "A1", [canonical_headers] + normalized_rows, value_input_option="RAW")
        return canonical_headers

    def _ensure_atharv_headers(self, worksheet):
        first_row = worksheet.row_values(1)
        if not first_row:
            worksheet.append_row(ATHARV_HEADERS, value_input_option="RAW")
            return ATHARV_HEADERS.copy()

        canonical_headers = ATHARV_HEADERS.copy()
        if first_row == canonical_headers:
            return canonical_headers

        rows = worksheet.get_all_values()
        source_headers = [str(header).strip() for header in first_row]
        normalized_rows = []
        for row in rows[1:]:
            if not any(str(value).strip() for value in row):
                continue
            record = {header: "" for header in canonical_headers}
            for index, header in enumerate(source_headers):
                if header in record:
                    record[header] = row[index] if index < len(row) else ""
            if record.get("Order ID"):
                normalized_rows.append([record.get(header, "") for header in canonical_headers])

        worksheet.clear()
        self._sheet_update(worksheet, "A1", [canonical_headers] + normalized_rows, value_input_option="RAW")
        return canonical_headers

    def _prepare_customer_worksheet(self, worksheet):
        headers = self._ensure_customer_headers(worksheet)
        self._compact_data_rows(worksheet, headers, key_column=0)
        self._style_customer_worksheet(worksheet)
        return headers

    def _prepare_atharv_worksheet(self, worksheet):
        headers = self._ensure_atharv_headers(worksheet)
        self._compact_data_rows(worksheet, headers, key_column=ATHARV_HEADERS.index("Order ID"))
        self._style_atharv_worksheet(worksheet)
        return headers

    def _prepare_worksheet(self, worksheet):
        headers = self._ensure_worksheet_headers(worksheet)
        self._repair_shifted_status_values(worksheet, headers)
        self._style_worksheet(worksheet, headers)
        self._prepared_worksheet_titles.add(worksheet.title)
        return headers

    def _ensure_order_header_best_effort(self, worksheet):
        if worksheet.title in self._prepared_worksheet_titles:
            return
        try:
            self._retry_sheet_write(
                lambda: self._sheet_update(
                    worksheet,
                    f"A1:{rowcol_to_a1(1, len(ORDER_HEADERS))}",
                    [ORDER_HEADERS],
                    value_input_option="RAW",
                )
            )
            self._prepared_worksheet_titles.add(worksheet.title)
        except Exception:
            return

    @staticmethod
    def _records_from_worksheet_values(worksheet):
        rows = worksheet.get_all_values()
        if len(rows) < 2:
            return []
        headers = SheetsHandler._order_headers_from_row(rows[0])
        records = []
        for row in rows[1:]:
            if not any(str(value).strip() for value in row):
                continue
            second_cell = SheetsHandler._row_value(row, 1)
            if "Checkout Token" in headers and second_cell and not second_cell.startswith("chk_") and SheetsHandler._looks_like_timestamp(second_cell):
                row_headers = LEGACY_ORDER_HEADERS
            elif "Checkout Token" not in headers and second_cell.startswith("chk_"):
                row_headers = ORDER_HEADERS
            else:
                row_headers = headers
            record = SheetsHandler._record_from_row(row, row_headers, ORDER_HEADERS)
            records.append(record)
        return records

    @staticmethod
    def _order_headers_from_row(row):
        cleaned = [
            ORDER_HEADER_ALIASES.get(str(header).strip(), str(header).strip())
            for header in row
        ]
        if "Order ID" not in cleaned:
            return ORDER_HEADERS.copy()
        return cleaned

    @staticmethod
    def _customer_headers_from_row(row):
        cleaned = [str(header).strip() for header in row]
        if "Google Subject" not in cleaned and "Email" not in cleaned:
            return CUSTOMER_HEADERS.copy()
        return cleaned

    @staticmethod
    def _record_from_row(row, headers, canonical_headers):
        record = {header: "" for header in canonical_headers}
        seen_headers = set()
        for index, header in enumerate(headers):
            if not header or header in seen_headers or header not in record:
                continue
            record[header] = row[index] if index < len(row) else ""
            seen_headers.add(header)
        return record

    def _style_worksheet_if_needed(self, worksheet, headers):
        if worksheet.title in self._prepared_worksheet_titles:
            return
        try:
            self._repair_shifted_status_values(worksheet, headers)
            self._style_worksheet(worksheet, headers)
            self._prepared_worksheet_titles.add(worksheet.title)
        except Exception:
            # Formatting should never block saving a paid order.
            return

    def _next_available_row(self, worksheet, key_column=0):
        rows = worksheet.get_all_values()
        last_real_row = 1
        for row_number, row in enumerate(rows[1:], start=2):
            if self._row_value(row, key_column):
                last_real_row = row_number
        return last_real_row + 1

    def _compact_data_rows(self, worksheet, headers, key_column=0):
        rows = worksheet.get_all_values()
        if len(rows) < 3:
            return

        compacted_rows = []
        saw_blank_after_data = False
        has_gap = False
        for row in rows[1:]:
            if self._row_value(row, key_column):
                if saw_blank_after_data:
                    has_gap = True
                compacted_rows.append([row[index] if index < len(row) else "" for index in range(len(headers))])
                continue
            if compacted_rows and not any(str(value).strip() for value in row):
                saw_blank_after_data = True

        if not has_gap:
            return

        last_row = len(rows)
        last_column = len(headers)
        self._retry_sheet_write(
            lambda: worksheet.batch_clear([f"A2:{rowcol_to_a1(last_row, last_column)}"])
        )
        if compacted_rows:
            self._retry_sheet_write(
                lambda: self._sheet_update(
                    worksheet,
                    f"A2:{rowcol_to_a1(len(compacted_rows) + 1, last_column)}",
                    compacted_rows,
                    value_input_option="RAW",
                )
            )

    @staticmethod
    def is_rate_limit_error(error):
        status_code = getattr(getattr(error, "response", None), "status_code", None)
        if status_code == 429:
            return True
        if isinstance(error, APIError):
            message = str(error).lower()
            if "quota" in message or "rate limit" in message or "resource_exhausted" in message:
                return True
        return "rate limit" in str(error).lower() or "quota exceeded" in str(error).lower()

    def _retry_sheet_write(self, callback, attempts=3):
        last_error = None
        for attempt in range(attempts):
            try:
                return callback()
            except Exception as error:
                last_error = error
                status_code = getattr(getattr(error, "response", None), "status_code", None)
                is_retryable = self.is_rate_limit_error(error) or status_code in {500, 502, 503, 504}
                if not is_retryable or attempt == attempts - 1:
                    raise
                time.sleep(0.5 * (attempt + 1))
        if last_error:
            raise last_error

    def _repair_shifted_status_values(self, worksheet, headers):
        status_headers = ["Confirmed", "Packed", "Delivered", "Cancelled"]
        if not all(header in headers for header in ["Order ID", "Source", "Updated At", *status_headers]):
            return

        rows = worksheet.get_all_values()
        if len(rows) < 2:
            return

        updates = []
        source_index = headers.index("Source")
        updated_index = headers.index("Updated At")
        status_indexes = {header: headers.index(header) for header in status_headers}

        for row_number, row in enumerate(rows[1:], start=2):
            if not self._row_value(row, headers.index("Order ID")):
                continue

            source = self._row_value(row, source_index)
            updated_at = self._row_value(row, updated_index)
            candidate_source = ""
            candidate_updated_at = ""

            for header, index in status_indexes.items():
                value = self._row_value(row, index)
                upper_value = value.upper()
                if upper_value in {"TRUE", "FALSE", ""}:
                    continue
                if value in {"Website", "WhatsApp", "Admin"}:
                    candidate_source = value
                elif self._looks_like_timestamp(value):
                    candidate_updated_at = value
                updates.append((row_number, index + 1, "FALSE"))

            if candidate_source and source.upper() in {"", "FALSE", "TRUE"}:
                updates.append((row_number, source_index + 1, candidate_source))
            if candidate_updated_at and updated_at.upper() in {"", "FALSE", "TRUE"}:
                updates.append((row_number, updated_index + 1, candidate_updated_at))

        if updates:
            worksheet.batch_update(
                [
                    {"range": rowcol_to_a1(row, column), "values": [[value]]}
                    for row, column, value in updates
                ],
                value_input_option="RAW",
            )

    def _style_worksheet(self, worksheet, headers):
        sheet_id = worksheet.id
        column_count = len(headers)
        rows = worksheet.get_all_values()
        last_real_row = 1
        for row_number, row in enumerate(rows[1:], start=2):
            if self._row_value(row, 0):
                last_real_row = row_number
        row_count = max(last_real_row + 20, 200)

        requests = [
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "gridProperties": {
                            "frozenRowCount": 1,
                            "rowCount": row_count,
                            "columnCount": column_count,
                        },
                        "tabColor": {"red": 0.29, "green": 0.36, "blue": 0.22},
                    },
                    "fields": "gridProperties.frozenRowCount,gridProperties.rowCount,gridProperties.columnCount,tabColor",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": column_count,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.15, "green": 0.19, "blue": 0.12},
                            "horizontalAlignment": "CENTER",
                            "verticalAlignment": "MIDDLE",
                            "textFormat": {
                                "bold": True,
                                "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                            },
                            "wrapStrategy": "WRAP",
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat,wrapStrategy)",
                }
            },
            {
                "setBasicFilter": {
                    "filter": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 0,
                            "endColumnIndex": column_count,
                        }
                    }
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
                    "properties": {"pixelSize": 42},
                    "fields": "pixelSize",
                }
            },
        ]

        widths = {
            "Order ID": 150,
            "Timestamp": 170,
            "Customer Name": 180,
            "Phone": 130,
            "Address": 310,
            "City": 130,
            "Product": 190,
            "Quantity": 95,
            "Unit Price": 110,
            "Total Amount": 125,
            "Payment Mode": 120,
            "Notes": 220,
            "Order Status": 160,
            "Confirmed": 105,
            "Packed": 90,
            "Delivered": 105,
            "Cancelled": 105,
            "Source": 105,
            "Updated At": 170,
        }
        for header, width in widths.items():
            if header in headers:
                index = headers.index(header)
                requests.append(
                    {
                        "updateDimensionProperties": {
                            "range": {
                                "sheetId": sheet_id,
                                "dimension": "COLUMNS",
                                "startIndex": index,
                                "endIndex": index + 1,
                            },
                            "properties": {"pixelSize": width},
                            "fields": "pixelSize",
                        }
                    }
                )

        checkbox_headers = ["Confirmed", "Packed", "Delivered", "Cancelled"]
        for header in checkbox_headers:
            if header in headers:
                index = headers.index(header)
                requests.append(
                    {
                        "setDataValidation": {
                            "range": {
                                "sheetId": sheet_id,
                                "startRowIndex": 1,
                                "endRowIndex": row_count,
                                "startColumnIndex": index,
                                "endColumnIndex": index + 1,
                            },
                            "rule": {
                                "condition": {"type": "BOOLEAN"},
                                "strict": False,
                                "showCustomUi": True,
                            },
                        }
                    }
                )

        if "Order Status" in headers:
            index = headers.index("Order Status")
            requests.append(
                {
                    "setDataValidation": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": row_count,
                            "startColumnIndex": index,
                            "endColumnIndex": index + 1,
                        },
                        "rule": {
                            "condition": {
                                "type": "ONE_OF_LIST",
                                "values": [{"userEnteredValue": status} for status in STATUS_OPTIONS],
                            },
                            "strict": True,
                            "showCustomUi": True,
                        },
                    }
                }
            )

        for header in ["Unit Price", "Total Amount"]:
            if header in headers:
                index = headers.index(header)
                requests.append(
                    {
                        "repeatCell": {
                            "range": {
                                "sheetId": sheet_id,
                                "startRowIndex": 1,
                                "endRowIndex": row_count,
                                "startColumnIndex": index,
                                "endColumnIndex": index + 1,
                            },
                            "cell": {
                                "userEnteredFormat": {
                                    "numberFormat": {
                                        "type": "CURRENCY",
                                        "pattern": '"₹"#,##0',
                                    }
                                }
                            },
                            "fields": "userEnteredFormat.numberFormat",
                        }
                    }
                )

        for header in ["Address", "Notes"]:
            if header in headers:
                index = headers.index(header)
                requests.append(
                    {
                        "repeatCell": {
                            "range": {
                                "sheetId": sheet_id,
                                "startRowIndex": 1,
                                "endRowIndex": row_count,
                                "startColumnIndex": index,
                                "endColumnIndex": index + 1,
                            },
                            "cell": {
                                "userEnteredFormat": {
                                    "wrapStrategy": "WRAP",
                                    "verticalAlignment": "TOP",
                                }
                            },
                            "fields": "userEnteredFormat(wrapStrategy,verticalAlignment)",
                        }
                    }
                )

        self._spreadsheet.batch_update({"requests": requests})

    def _style_atharv_worksheet(self, worksheet):
        if not self._spreadsheet:
            return

        sheet_id = worksheet.id
        column_count = len(ATHARV_HEADERS)
        rows = worksheet.get_all_values()
        row_count = max(len(rows) + 50, 300)
        requests = [
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "gridProperties": {
                            "frozenRowCount": 1,
                            "rowCount": row_count,
                            "columnCount": column_count,
                        },
                        "tabColor": {"red": 0.05, "green": 0.38, "blue": 0.34},
                    },
                    "fields": "gridProperties.frozenRowCount,gridProperties.rowCount,gridProperties.columnCount,tabColor",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": column_count,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.04, "green": 0.22, "blue": 0.20},
                            "horizontalAlignment": "CENTER",
                            "verticalAlignment": "MIDDLE",
                            "textFormat": {
                                "bold": True,
                                "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                            },
                            "wrapStrategy": "WRAP",
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat,wrapStrategy)",
                }
            },
            {
                "setBasicFilter": {
                    "filter": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 0,
                            "endColumnIndex": column_count,
                        }
                    }
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
                    "properties": {"pixelSize": 42},
                    "fields": "pixelSize",
                }
            },
        ]

        widths = {
            "Timestamp": 170,
            "Name": 180,
            "Order ID": 135,
            "Phone": 130,
            "Address": 320,
            "Mode of Payment": 145,
            "Product": 230,
            "Order Amount": 125,
            "Coupon Discount": 145,
            "Online Payment Discount": 170,
            "Total Discount": 135,
            "Razorpay Fee": 125,
            "Razorpay GST": 125,
            "Razorpay Total Fee": 145,
            "Bank Received": 135,
            "Delivered": 105,
            "Order Status": 145,
            "Razorpay Payment ID": 190,
            "Updated At": 170,
        }
        for header, width in widths.items():
            index = ATHARV_HEADERS.index(header)
            requests.append(
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": index,
                            "endIndex": index + 1,
                        },
                        "properties": {"pixelSize": width},
                        "fields": "pixelSize",
                    }
                }
            )

        delivered_index = ATHARV_HEADERS.index("Delivered")
        requests.append(
            {
                "setDataValidation": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": row_count,
                        "startColumnIndex": delivered_index,
                        "endColumnIndex": delivered_index + 1,
                    },
                    "rule": {
                        "condition": {"type": "BOOLEAN"},
                        "strict": False,
                        "showCustomUi": True,
                    },
                }
            }
        )

        money_headers = [
            "Order Amount",
            "Coupon Discount",
            "Online Payment Discount",
            "Total Discount",
            "Razorpay Fee",
            "Razorpay GST",
            "Razorpay Total Fee",
            "Bank Received",
        ]
        for header in money_headers:
            index = ATHARV_HEADERS.index(header)
            requests.append(
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": row_count,
                            "startColumnIndex": index,
                            "endColumnIndex": index + 1,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "numberFormat": {
                                    "type": "CURRENCY",
                                    "pattern": '"₹"#,##0.00',
                                }
                            }
                        },
                        "fields": "userEnteredFormat.numberFormat",
                    }
                }
            )

        for header in ["Address", "Product"]:
            index = ATHARV_HEADERS.index(header)
            requests.append(
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": row_count,
                            "startColumnIndex": index,
                            "endColumnIndex": index + 1,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "wrapStrategy": "WRAP",
                                "verticalAlignment": "TOP",
                            }
                        },
                        "fields": "userEnteredFormat(wrapStrategy,verticalAlignment)",
                    }
                }
            )

        self._spreadsheet.batch_update({"requests": requests})

    def _style_customer_worksheet(self, worksheet):
        if not self._spreadsheet:
            return

        sheet_id = worksheet.id
        column_count = len(CUSTOMER_HEADERS)
        rows = worksheet.get_all_values()
        row_count = max(len(rows) + 20, 200)
        requests = [
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "gridProperties": {
                            "frozenRowCount": 1,
                            "rowCount": row_count,
                            "columnCount": column_count,
                        },
                        "tabColor": {"red": 0.93, "green": 0.57, "blue": 0.15},
                    },
                    "fields": "gridProperties.frozenRowCount,gridProperties.rowCount,gridProperties.columnCount,tabColor",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": row_count,
                        "startColumnIndex": 0,
                        "endColumnIndex": column_count,
                    },
                    "cell": {},
                    "fields": "dataValidation",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": column_count,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.15, "green": 0.19, "blue": 0.12},
                            "horizontalAlignment": "CENTER",
                            "verticalAlignment": "MIDDLE",
                            "textFormat": {
                                "bold": True,
                                "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                            },
                            "wrapStrategy": "WRAP",
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat,wrapStrategy)",
                }
            },
            {
                "setBasicFilter": {
                    "filter": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 0,
                            "endColumnIndex": column_count,
                        }
                    }
                }
            },
        ]

        widths = {
            "Google Subject": 230,
            "Email": 240,
            "Name": 180,
            "Picture": 220,
            "Phone": 130,
            "Default City": 140,
            "Default Address": 320,
            "Created At": 170,
            "Updated At": 170,
        }
        for header, width in widths.items():
            index = CUSTOMER_HEADERS.index(header)
            requests.append(
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": index,
                            "endIndex": index + 1,
                        },
                        "properties": {"pixelSize": width},
                        "fields": "pixelSize",
                    }
                }
            )

        self._spreadsheet.batch_update({"requests": requests})

    def _ensure_local_file(self):
        self.local_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.local_file.exists():
            pd.DataFrame(columns=ORDER_HEADERS).to_excel(self.local_file, index=False)

    def _write_local_records(self, records):
        self.local_file.parent.mkdir(parents=True, exist_ok=True)
        safe_records = [
            {header: self._spreadsheet_safe_value(record.get(header, "")) for header in ORDER_HEADERS}
            for record in records
        ]
        frame = pd.DataFrame(safe_records, columns=ORDER_HEADERS)
        frame.to_excel(self.local_file, index=False)

    def _ensure_local_customers_file(self):
        self.local_customers_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.local_customers_file.exists():
            pd.DataFrame(columns=CUSTOMER_HEADERS).to_excel(self.local_customers_file, index=False)

    def _write_local_customers(self, records):
        self.local_customers_file.parent.mkdir(parents=True, exist_ok=True)
        safe_records = [
            {header: self._spreadsheet_safe_value(record.get(header, "")) for header in CUSTOMER_HEADERS}
            for record in records
        ]
        frame = pd.DataFrame(safe_records, columns=CUSTOMER_HEADERS)
        frame.to_excel(self.local_customers_file, index=False)

    @staticmethod
    def _spreadsheet_safe_value(value):
        if not isinstance(value, str):
            return value
        stripped = value.lstrip()
        if stripped and stripped[0] in {"=", "+", "-", "@"} and not stripped.startswith("'"):
            return "'" + value
        return value

    @staticmethod
    def _clean_record(record):
        cleaned = {}
        for header in ORDER_HEADERS:
            value = record.get(header, "")
            cleaned[header] = "" if pd.isna(value) else str(value)
        return cleaned

    @staticmethod
    def _clean_customer_record(record):
        cleaned = {}
        for header in CUSTOMER_HEADERS:
            value = record.get(header, "")
            cleaned[header] = "" if pd.isna(value) else str(value)
        return cleaned

    @staticmethod
    def _row_value(row, index):
        return str(row[index]).strip() if index < len(row) else ""

    @staticmethod
    def _looks_like_timestamp(value):
        text = str(value or "").strip()
        if not text:
            return False
        for candidate in (text, text.replace(" ", "T", 1)):
            try:
                datetime.fromisoformat(candidate)
                return True
            except ValueError:
                continue
        return False
