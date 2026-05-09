import json
import os
from datetime import date, datetime
from pathlib import Path

import gspread
import pandas as pd
from gspread.utils import rowcol_to_a1


STATUS_OPTIONS = [
    "Pending",
    "Confirmed",
    "Packed",
    "Out for Delivery",
    "Delivered",
    "Cancelled",
]


ORDER_HEADERS = [
    "Order ID",
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
    "Notes",
    "Order Status",
    "Confirmed",
    "Packed",
    "Delivered",
    "Cancelled",
    "Source",
    "Updated At",
]


class SheetsHandler:
    def __init__(self):
        self.storage_mode = os.getenv("STORAGE_MODE", "auto").lower()
        self.sheet_id = os.getenv("GOOGLE_SHEET_ID", "")
        self.worksheet_name = os.getenv("GOOGLE_WORKSHEET_NAME", "Orders")
        self.daily_worksheets = os.getenv("GOOGLE_DAILY_WORKSHEETS", "true").lower() == "true"
        self.credentials_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
        self.local_file = Path(os.getenv("LOCAL_ORDERS_FILE", "data/orders.xlsx"))
        self._spreadsheet = None
        self._worksheet = None
        self._headers = ORDER_HEADERS.copy()

        if self.storage_mode in {"auto", "sheets"} and self._can_use_sheets():
            self._worksheet = self._connect_google_sheet()
        elif self.storage_mode == "sheets":
            raise RuntimeError("Google Sheets mode is enabled, but sheet id or credentials are missing.")
        else:
            self._ensure_local_file()

    @property
    def backend_name(self):
        return "Google Sheets" if self._worksheet else "Local Excel"

    def append_order(self, order):
        if self._worksheet:
            self._worksheet = self._today_worksheet()
            self._headers = self._prepare_worksheet(self._worksheet)
            row = [order.get(header, "") for header in self._headers]
            self._worksheet.append_row(row, value_input_option="USER_ENTERED")
            return

        records = self.get_all_orders()
        records.append({header: order.get(header, "") for header in ORDER_HEADERS})
        self._write_local_records(records)

    def get_all_orders(self):
        if self._worksheet:
            orders = []
            for worksheet in self._order_worksheets():
                self._prepare_worksheet(worksheet)
                records = worksheet.get_all_records()
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

    def update_order(self, order_id, updates):
        order_id = str(order_id).strip().upper()
        normalized_updates = {
            header: value
            for header, value in updates.items()
            if header in ORDER_HEADERS and value is not None
        }
        normalized_updates["Updated At"] = datetime.now().isoformat(timespec="seconds")

        if self._worksheet:
            for worksheet in self._order_worksheets():
                headers = self._prepare_worksheet(worksheet)
                records = worksheet.get_all_records()
                for index, record in enumerate(records, start=2):
                    if str(record.get("Order ID", "")).strip().upper() == order_id:
                        for header, value in normalized_updates.items():
                            column = headers.index(header) + 1
                            worksheet.update_cell(index, column, value)
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

    def count_orders_with_prefix(self, prefix):
        return sum(1 for order in self.get_all_orders() if str(order.get("Order ID", "")).startswith(prefix))

    def _can_use_sheets(self):
        return bool(self.sheet_id and Path(self.credentials_file).exists())

    def _connect_google_sheet(self):
        credentials_json = os.getenv("GOOGLE_CREDENTIALS_JSON", "")
        if credentials_json:
            client = gspread.service_account_from_dict(json.loads(credentials_json))
        else:
            client = gspread.service_account(filename=self.credentials_file)
        self._spreadsheet = client.open_by_key(self.sheet_id)
        worksheet = self._today_worksheet()
        self._headers = self._prepare_worksheet(worksheet)
        return worksheet

    def format_all_order_tabs(self):
        if not self._worksheet:
            return
        for worksheet in self._order_worksheets():
            self._prepare_worksheet(worksheet)

    def _today_worksheet(self):
        worksheet_title = self._worksheet_title_for_date(date.today())
        try:
            return self._spreadsheet.worksheet(worksheet_title)
        except gspread.WorksheetNotFound:
            return self._spreadsheet.add_worksheet(title=worksheet_title, rows=1000, cols=len(ORDER_HEADERS))

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

        records = worksheet.get_all_records(default_blank="")
        normalized_rows = []
        for record in records:
            normalized_rows.append([record.get(header, "") for header in canonical_headers])

        worksheet.clear()
        rows = [canonical_headers] + normalized_rows
        worksheet.update("A1", rows, value_input_option="USER_ENTERED")
        return canonical_headers

    def _prepare_worksheet(self, worksheet):
        headers = self._ensure_worksheet_headers(worksheet)
        self._repair_shifted_status_values(worksheet, headers)
        self._style_worksheet(worksheet, headers)
        return headers

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
                value_input_option="USER_ENTERED",
            )

    def _style_worksheet(self, worksheet, headers):
        sheet_id = worksheet.id
        column_count = len(headers)
        row_count = max(worksheet.row_count, 1000)

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

    def _ensure_local_file(self):
        self.local_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.local_file.exists():
            pd.DataFrame(columns=ORDER_HEADERS).to_excel(self.local_file, index=False)

    def _write_local_records(self, records):
        self.local_file.parent.mkdir(parents=True, exist_ok=True)
        frame = pd.DataFrame(records, columns=ORDER_HEADERS)
        frame.to_excel(self.local_file, index=False)

    @staticmethod
    def _clean_record(record):
        cleaned = {}
        for header in ORDER_HEADERS:
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
