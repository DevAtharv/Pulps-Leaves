import json
import os
import re
from typing import Any

import requests

from delivery_config import product_by_choice


PHONE_PATTERN = re.compile(r"(?:\+?91[\s-]?)?([6-9]\d[\d\s-]{8,12}\d)")
ORDER_ID_PATTERN = re.compile(r"\bPL[A-Z0-9]{6}\b", re.IGNORECASE)


def normalize_phone(value):
    if not value:
        return None
    digits = re.sub(r"\D", "", str(value))
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) == 10 and digits[0] in "6789":
        return digits
    return None


def extract_phone(text):
    match = PHONE_PATTERN.search(str(text))
    if not match:
        return normalize_phone(text)
    return normalize_phone(match.group(0))


def extract_order_id(text):
    match = ORDER_ID_PATTERN.search(str(text).upper())
    return match.group(0).upper() if match else None


def extract_quantity(text):
    value = str(text).strip().lower()
    match = re.search(r"\b(\d{1,2})\b", value)
    if not match:
        word_numbers = {
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
        }
        for word, number in word_numbers.items():
            if re.search(rf"\b{word}\b", value):
                return number
        return None
    return int(match.group(1))


def extract_address(text):
    value = str(text).strip()
    patterns = [
        r"(?:change|update|set)\s+(?:my\s+)?address\s+(?:to|as)\s+(.+)",
        r"(?:new|delivery)\s+address\s+(?:is|:)\s+(.+)",
        r"address\s*[:\-]\s*(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, value, re.IGNORECASE)
        if match:
            return clean_address(match.group(1))

    if len(value) >= 8 and any(token in value.lower() for token in ["road", "street", "flat", "apt", "apartment", "phase", "sector", "layout", "near", "whitefield"]):
        return clean_address(value)
    return None


def clean_address(value):
    cleaned = re.sub(r"\s+", " ", str(value)).strip(" ,.-")
    return cleaned[:240] if cleaned else None


def extract_product(text):
    return product_by_choice(text)


def parse_edit_message(text):
    return {
        "order_id": extract_order_id(text),
        "phone": extract_phone(text),
        "address": extract_address(text),
    }


def parse_order_message(text):
    return {
        "phone": extract_phone(text),
        "address": extract_address(text),
        "quantity": extract_quantity(text),
        "product": extract_product(text),
    }


def parse_with_optional_ai(text, expected_fields=None):
    """Use a configured AI-compatible endpoint only as a cleanup helper.

    The business flow never depends on AI for decisions. If the endpoint is not
    configured or fails, deterministic parsing remains the source of truth.
    """
    deterministic = parse_order_message(text) | parse_edit_message(text)
    if os.getenv("AI_PARSER_ENABLED", "false").lower() != "true":
        return deterministic

    endpoint = os.getenv("AI_PARSER_ENDPOINT")
    api_key = os.getenv("AI_PARSER_API_KEY")
    model = os.getenv("AI_PARSER_MODEL")
    if not endpoint or not api_key:
        return deterministic

    fields = expected_fields or ["name", "phone", "address", "product", "quantity", "notes", "order_id"]
    prompt = (
        "Extract only the requested customer-order fields from this message. "
        "Return strict JSON. Do not make decisions or invent missing values. "
        f"Fields: {fields}. Message: {text}"
    )
    try:
        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "input": prompt},
            timeout=8,
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        content = _best_effort_content(payload)
        parsed = json.loads(content)
        return {**deterministic, **{key: value for key, value in parsed.items() if value}}
    except Exception:
        return deterministic


def _best_effort_content(payload):
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    if isinstance(payload.get("choices"), list):
        choice = payload["choices"][0]
        message = choice.get("message", {})
        return message.get("content", "{}")
    return "{}"
