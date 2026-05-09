# Pulps & Leaves COD Ordering System

Production-style Flask ordering backend for a fruit and mango business. It supports website COD orders, a WhatsApp-ready conversational flow, Google Sheets storage, order edits, city-wise delivery schedules, and an admin dashboard.

## What is included

- Rule-based chatbot flow with state management
- AI-assisted parsing hooks for messy phone, address, product, and edit messages
- Website COD order form
- Edit order flow by Order ID
- Delivery schedule lookup
- Seasonal catalog rules: only Malda Mango boxes are orderable now; tea and makhana are shown as coming soon
- Google Sheets integration through `gspread`
- Local Excel fallback for development
- Admin dashboard with search, city filter, status filter, and status editing
- WhatsApp webhook-ready endpoint for Meta Cloud API, Twilio, WATI, Interakt, or similar providers

## Project structure

```text
fruit-cod-ordering/
  app.py
  chatbot_flow.py
  order_manager.py
  sheets_handler.py
  ai_parser.py
  delivery_config.py
  templates/
  static/
  data/
  credentials.example.json
  .env.example
  requirements.txt
```

## Local setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python app.py
```

Open `http://127.0.0.1:5000`.

Admin dashboard:

```text
http://127.0.0.1:5000/admin
```

Default local admin credentials are set in `.env.example`:

```text
admin / change-me
```

Change them before real use.

## Google Sheets setup

1. Create a Google Cloud project.
2. Enable the Google Sheets API.
3. Create a service account.
4. Create a JSON key for that service account.
5. Save the key as `credentials.json` in this project folder.
6. Create a Google Sheet.
7. Share the Sheet with the service account email from `credentials.json`.
8. Copy the Sheet ID from the Sheet URL.
9. Update `.env`:

```text
STORAGE_MODE=sheets
GOOGLE_SHEET_ID=your-sheet-id
GOOGLE_WORKSHEET_NAME=Orders
GOOGLE_DAILY_WORKSHEETS=true
GOOGLE_CREDENTIALS_FILE=credentials.json
```

On Vercel, add the full service-account JSON as one environment variable instead of uploading `credentials.json`:

```text
GOOGLE_CREDENTIALS_JSON={"type":"service_account",...}
```

With `GOOGLE_DAILY_WORKSHEETS=true`, the app automatically creates one worksheet tab per day:

```text
Orders 2026-05-09
Orders 2026-05-10
Orders 2026-05-11
```

New orders go into today's tab. Order lookup and edits search across all dated order tabs, so a customer can still update an older order by Order ID.

The app creates the expected header row automatically in each daily tab:

```text
Order ID, Timestamp, Customer Name, Phone, Address, City, Product, Quantity, Unit Price, Total Amount, Payment Mode, Notes, Order Status, Confirmed, Packed, Delivered, Cancelled, Source, Updated At
```

For local development, keep:

```text
STORAGE_MODE=auto
```

When no Google credentials are present, the app writes to `data/orders.xlsx`.

## Order ID format

Generated IDs use:

```text
PL + day + month-code + year + city-code + sequence
```

Example:

```text
PL09MY26BLR0001
```

The sequence increments per date and city.

## Product availability

Product availability lives in `delivery_config.py`.

- Mango products use `available_months: [4, 5, 6, 7]`.
- Tea and makhana live in `COMING_SOON_PRODUCTS` and are not accepted by the order validator yet.

Both website and chatbot orders call the same backend validation, so out-of-season or coming-soon products are blocked before they reach Google Sheets.

## API endpoints

Create website order:

```http
POST /api/orders
```

Payload:

```json
{
  "name": "Aarav Rao",
  "phone": "9876543210",
  "address": "Flat 4, Whitefield Main Road, Bangalore",
  "city": "bangalore",
  "product": "Alphonso Mango Box",
  "quantity": 2,
  "notes": "Call before delivery"
}
```

Edit order:

```http
POST /api/orders/<ORDER_ID>/edit
```

Payload:

```json
{
  "address": "New delivery address",
  "phone": "9876543210"
}
```

Chatbot:

```http
POST /api/chatbot/message
```

Payload:

```json
{
  "user_id": "whatsapp-phone-or-session-id",
  "message": "1"
}
```

WhatsApp adapter endpoint:

```http
POST /webhook/whatsapp
```

This accepts a simple `{ "from": "...", "message": "..." }` payload and also includes a parser for Meta Cloud API-style message payloads. To go live, connect this endpoint to the provider webhook and add the provider-specific outbound send call.

## Optional AI parsing

The chatbot is deterministic by default. The AI parser is only a helper for messy inputs such as:

```text
change address to Whitefield near Forum Mall
my new number is 9876543210
```

To enable an OpenAI-compatible or internal extraction endpoint, set:

```text
AI_PARSER_ENABLED=true
AI_PARSER_ENDPOINT=https://your-parser-endpoint
AI_PARSER_API_KEY=your-key
AI_PARSER_MODEL=your-model
```

If the endpoint fails, the app falls back to regex and rule-based parsing.

## Main chatbot menu

```text
1 - New Order
2 - Edit Existing Order
3 - Know Next Delivery Date
4 - Connect to Agent
```

Conversation state is currently in memory for beginner readability. For production multi-worker deployment, replace `ConversationStore` in `chatbot_flow.py` with Redis or a database-backed store.
