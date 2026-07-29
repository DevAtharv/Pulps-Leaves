from time_utils import today_local


BUSINESS_NAME = "Pulps & Leaves"

CITIES = {
    "bangalore": {"label": "Bengaluru", "code": "BLR"},
    "hyderabad": {"label": "Hyderabad", "code": "HYD"},
    "pune": {"label": "Pune", "code": "PUN"},
    "mumbai": {"label": "Mumbai", "code": "MUM"},
    "chennai": {"label": "Chennai", "code": "CHE"},
    "bhubaneswar": {"label": "Bhubaneswar", "code": "BBI"},
}

AVAILABLE_CITY_KEYS = ("bangalore", "hyderabad", "pune", "mumbai")
AVAILABLE_CITIES = {key: CITIES[key] for key in AVAILABLE_CITY_KEYS}

CITY_ALIASES = {
    "bengaluru": "bangalore",
    "blr": "bangalore",
    "hyd": "hyderabad",
    "bom": "mumbai",
    "bombay": "mumbai",
    "madras": "chennai",
    "bbsr": "bhubaneswar",
    "bhubaneshwar": "bhubaneswar",
}

PRODUCTS = [
    {
        "name": "Naivedyam Makhana 200g Pack",
        "display_title": "Naivedyam Makhana",
        "slug": "roasted-himalayan-makhana",
        "category": "Makhana",
        "price": 350,
        "mrp": 350,
        "unit": "200g Pack",
        "pieces_label": "Light, crunchy, nutritious",
        "description": "Premium roasted makhana 200g pouch",
        "available_months": list(range(1, 13)),
        "availability_label": "Available now",
    },
]

COMING_SOON_PRODUCTS = [
    {
        "name": "Pulps & Leaves Tea",
        "slug": "assam-breakfast-tea",
        "category": "Tea",
        "description": "Tea is launching soon with Pulps & Leaves.",
    },
    {
        "name": "Malda Mango",
        "slug": "malda-mango",
        "category": "Mangoes",
        "description": "Mango season has ended. Mangoes will return next harvest.",
    },
]

DELIVERY_SCHEDULES = {
    "bangalore": {"start": "2026-06-28", "end": "2026-06-30", "label": "end of June"},
    "hyderabad": {"start": "2026-06-28", "end": "2026-06-30", "label": "end of June"},
    "pune": {"start": "2026-06-28", "end": "2026-06-30", "label": "end of June"},
    "mumbai": {"start": "2026-06-28", "end": "2026-06-30", "label": "end of June"},
    "chennai": {"start": "2026-06-09", "end": "2026-06-12", "label": "9th-12th June"},
    "bhubaneswar": {"start": "2026-06-11", "end": "2026-06-14", "label": "11th-14th June"},
}

ORDER_STATUSES = [
    "Received",
    "Confirmed",
    "Packed",
    "Out for Delivery",
    "Delivered",
    "Cancelled",
]

MONTH_CODES = {
    1: "JA",
    2: "FE",
    3: "MR",
    4: "AP",
    5: "MY",
    6: "JN",
    7: "JL",
    8: "AU",
    9: "SE",
    10: "OC",
    11: "NO",
    12: "DE",
}


def normalize_city(value):
    if not value:
        return None

    cleaned = str(value).strip().lower()
    cleaned = CITY_ALIASES.get(cleaned, cleaned)
    return cleaned if cleaned in CITIES else None


def normalize_available_city(value):
    normalized = normalize_city(value)
    return normalized if normalized in AVAILABLE_CITIES else None


def city_menu_text():
    return "\n".join(
        f"{index} - {city['label']}"
        for index, city in enumerate(AVAILABLE_CITIES.values(), start=1)
    )


def product_menu_text():
    lines = []
    for index, product in enumerate(PRODUCTS, start=1):
        lines.append(
            f"{index} - {product['display_title']} ({product['unit']}) - Rs {product['price']} - {product['availability_label']}"
        )
    return "\n".join(lines)


def product_by_choice(value):
    text = str(value).strip().lower()
    if text.isdigit():
        index = int(text) - 1
        if 0 <= index < len(PRODUCTS):
            return PRODUCTS[index]["name"]

    for product in PRODUCTS:
        if product["slug"] == text or product["name"].lower() == text:
            return product["name"]
        if product.get("display_title", "").lower() == text and product["unit"].lower() in text:
            return product["name"]
        if text in product["name"].lower():
            return product["name"]
        if text in f"{product.get('display_title', '')} {product['unit']}".lower():
            return product["name"]
    return None


def product_record(value):
    product_name = product_by_choice(value)
    if not product_name:
        return None
    for product in PRODUCTS:
        if product["name"] == product_name:
            return product
    return None


def is_product_available(product_value, on_date=None):
    on_date = on_date or today_local()
    product = product_record(product_value)
    if not product:
        return False
    return on_date.month in product.get("available_months", [])


def availability_message(product_value, on_date=None):
    product = product_record(product_value)
    if not product:
        return "Please choose a product from the catalog."
    if is_product_available(product_value, on_date):
        return None
    return (
        f"{product['name']} is not available right now. Naivedyam Makhana is available now; "
        "tea is launching soon, and mangoes return next harvest."
    )


def city_by_choice(value):
    text = str(value).strip().lower()
    if text.isdigit():
        index = int(text) - 1
        keys = list(AVAILABLE_CITIES.keys())
        if 0 <= index < len(keys):
            return keys[index]
    return normalize_available_city(text)


def get_delivery_schedule(city_key):
    normalized = normalize_available_city(city_key)
    if not normalized:
        return None

    city = CITIES[normalized]
    schedule = DELIVERY_SCHEDULES[normalized]
    return {
        "city_key": normalized,
        "city": city["label"],
        "city_code": city["code"],
        "start": schedule["start"],
        "end": schedule["end"],
        "label": schedule["label"],
        "message": f"Good news, {city['label']}! Your next delivery slot is between {schedule['label']}.",
    }


def today_order_prefix(city_key, today=None):
    today = today or today_local()
    city = CITIES[normalize_city(city_key)]
    return f"PL{today:%d}{MONTH_CODES[today.month]}{today:%y}{city['code']}"
