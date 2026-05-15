from html import escape

import requests


RESEND_API_URL = "https://api.resend.com/emails"


def _money_label(value):
    raw = str(value or "").strip()
    return raw if raw.lower().startswith("rs") else f"Rs {raw or '0'}"


def build_order_confirmation(order, support_phone, support_email):
    customer_name = str(order.get("Customer Name", "Customer")).strip() or "Customer"
    order_id = str(order.get("Order ID", "")).strip()
    timestamp = str(order.get("Timestamp", "")).strip()
    product = str(order.get("Product", "")).strip()
    quantity = str(order.get("Quantity", "")).strip()
    total_amount = _money_label(order.get("Total Amount", "0"))
    payment_mode = str(order.get("Payment Mode", "")).strip() or "COD"
    payment_status = str(order.get("Payment Status", "")).strip() or "Pending"
    city = str(order.get("City", "")).strip()
    address = str(order.get("Address", "")).strip()

    subject = f"Pulps & Leaves order confirmed: {order_id}"
    text = (
        f"Hi {customer_name},\n\n"
        f"Your Pulps & Leaves order has been placed successfully.\n\n"
        f"Order ID: {order_id}\n"
        f"Placed on: {timestamp}\n"
        f"Items: {product}\n"
        f"Quantity: {quantity}\n"
        f"Total: {total_amount}\n"
        f"Payment: {payment_mode} ({payment_status})\n"
        f"Delivery city: {city}\n"
        f"Delivery address: {address}\n\n"
        f"If you need help, contact us at {support_phone} or {support_email}.\n\n"
        "Thank you for shopping with Pulps & Leaves."
    )

    html = f"""\
<div style="margin:0;padding:24px;background:#f6f8f1;font-family:Arial,sans-serif;color:#172116;">
  <div style="max-width:640px;margin:0 auto;background:#ffffff;border:1px solid #dce4d3;border-radius:18px;overflow:hidden;">
    <div style="padding:24px 24px 16px;background:linear-gradient(135deg,#2d7b33,#16451d);color:#ffffff;">
      <div style="font-size:12px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;opacity:0.88;">Pulps &amp; Leaves</div>
      <h1 style="margin:10px 0 0;font-size:28px;line-height:1.1;">Your order is confirmed</h1>
      <p style="margin:10px 0 0;font-size:15px;line-height:1.6;opacity:0.92;">Thanks for ordering with us. We have saved your order and will process it shortly.</p>
    </div>
    <div style="padding:24px;">
      <p style="margin:0 0 18px;font-size:16px;line-height:1.6;">Hi {escape(customer_name)},</p>
      <div style="padding:16px 18px;border:1px dashed #b8c7ae;border-radius:14px;background:#fbfdf8;text-align:center;">
        <div style="font-size:12px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:#65705f;">Order ID</div>
        <div style="margin-top:8px;font-size:28px;font-weight:800;letter-spacing:0.08em;color:#16451d;">{escape(order_id)}</div>
      </div>
      <table style="width:100%;margin-top:20px;border-collapse:collapse;font-size:14px;line-height:1.6;">
        <tr><td style="padding:10px 0;color:#65705f;">Placed on</td><td style="padding:10px 0;text-align:right;font-weight:700;">{escape(timestamp)}</td></tr>
        <tr><td style="padding:10px 0;color:#65705f;">Items</td><td style="padding:10px 0;text-align:right;font-weight:700;">{escape(product)}</td></tr>
        <tr><td style="padding:10px 0;color:#65705f;">Quantity</td><td style="padding:10px 0;text-align:right;font-weight:700;">{escape(quantity)}</td></tr>
        <tr><td style="padding:10px 0;color:#65705f;">Total</td><td style="padding:10px 0;text-align:right;font-weight:700;">{escape(total_amount)}</td></tr>
        <tr><td style="padding:10px 0;color:#65705f;">Payment</td><td style="padding:10px 0;text-align:right;font-weight:700;">{escape(payment_mode)} ({escape(payment_status)})</td></tr>
        <tr><td style="padding:10px 0;color:#65705f;">City</td><td style="padding:10px 0;text-align:right;font-weight:700;">{escape(city)}</td></tr>
      </table>
      <div style="margin-top:18px;padding:16px 18px;border-radius:14px;background:#fff7e8;">
        <div style="font-size:12px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#7b5520;">Delivery address</div>
        <div style="margin-top:8px;font-size:15px;line-height:1.6;color:#172116;">{escape(address)}</div>
      </div>
      <div style="margin-top:20px;padding-top:18px;border-top:1px solid #e4eadf;">
        <div style="font-size:12px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#65705f;">Need help?</div>
        <p style="margin:8px 0 0;font-size:14px;line-height:1.6;">Contact us at <a href="tel:{escape(support_phone)}" style="color:#2d7b33;text-decoration:none;">{escape(support_phone)}</a> or <a href="mailto:{escape(support_email)}" style="color:#2d7b33;text-decoration:none;">{escape(support_email)}</a>.</p>
      </div>
    </div>
  </div>
</div>
"""
    return {"subject": subject, "text": text, "html": html}


def send_resend_email(api_key, from_email, to_email, subject, html, text, reply_to=None, timeout=20):
    payload = {
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "html": html,
        "text": text,
    }
    if reply_to:
        payload["reply_to"] = reply_to
    response = requests.post(
        RESEND_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()
