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
        "price": 399,
        "mrp": 399,
        "unit": "200g Pack",
        "pieces_label": "Light, crunchy, nutritious",
        "description": "Premium roasted makhana 200g pouch",
        "details": "Premium plain roasted makhana that is light, crunchy, nutritious, and prepared without frying or preservatives.",
        "kicker": "Plain roasted - 200g pack",
        "secondary_title": "Plain Makhana",
        "cart_badge": "Plain roasted",
        "image": "img/naivedyam-front-200g-cutout-20260729.png",
        "image_alt": "Pulps and Leaves Naivedyam plain roasted makhana 200g pouch",
        "image_width": 1024,
        "image_height": 1537,
        "highlights": ["6+ Suta Makhana", "100% natural", "Gluten free", "Roasted, not fried"],
        "available_months": list(range(1, 13)),
        "availability_label": "Available now",
        "variants": [
            {
                "slug": "roasted-himalayan-makhana",
                "name": "Naivedyam Makhana",
                "display_title": "Naivedyam Makhana",
                "option_label": "200 g",
                "price": 399,
                "price_label": "Rs 399",
                "unit": "200g Pack",
                "pieces_label": "Light, crunchy, nutritious",
                "details": "Premium plain roasted makhana that is light, crunchy, nutritious, and prepared without frying or preservatives.",
                "kicker": "Plain roasted - 200g pack",
                "secondary_title": "Plain Makhana",
                "cart_badge": "Plain roasted",
                "image": "img/naivedyam-front-200g-cutout-20260729.png",
                "image_alt": "Pulps and Leaves Naivedyam plain roasted makhana 200g pouch",
                "image_width": 1024,
                "image_height": 1537,
                "highlights": ["6+ Suta Makhana", "100% natural", "Gluten free", "Roasted, not fried"],
            },
            {
                "slug": "roasted-himalayan-makhana-1kg",
                "name": "Naivedyam Makhana 1kg",
                "display_title": "Naivedyam Makhana",
                "option_label": "1 kg",
                "price": 1750,
                "price_label": "Rs 1,750",
                "unit": "1kg Pack",
                "pieces_label": "Whole phool makhana, pantry pack",
                "details": "A generous 1kg pantry pack of plain roasted makhana for families, gifting, and everyday sharing. Light, clean, and never fried.",
                "kicker": "Plain roasted - 1kg pack",
                "secondary_title": "Plain Makhana 1kg",
                "cart_badge": "Plain roasted - 1kg",
                "image": "img/naivedyam-plain-makhana-1kg-20260730.png",
                "image_alt": "Pulps and Leaves plain phool makhana 1kg pack",
                "image_width": 896,
                "image_height": 1200,
                "highlights": ["6+ Suta Makhana", "100% natural", "Gluten free", "Roasted, not fried"],
            },
            {
                "slug": "roasted-himalayan-makhana-100kg",
                "name": "Naivedyam Makhana 100kg Bulk Order",
                "display_title": "Naivedyam Makhana",
                "option_label": "100 kg",
                "price_label": "Price on request",
                "unit": "100kg bulk order",
                "pieces_label": "For wholesale and large requirements",
                "details": "For retail, hospitality, gifting, and wholesale requirements, our team will prepare a tailored 100kg bulk quotation and delivery plan.",
                "kicker": "Bulk enquiry - 100kg",
                "secondary_title": "Plain Makhana 100kg",
                "cart_badge": "Bulk enquiry",
                "image": "img/naivedyam-plain-makhana-100kg-bulk-20260730.png",
                "image_alt": "Pulps and Leaves premium makhana bulk collection",
                "image_width": 1033,
                "image_height": 1024,
                "highlights": ["6+ Suta Makhana", "Wholesale support", "Tailored quotation", "Delivery planning"],
                "inquiry_only": True,
                "inquiry_url": "https://wa.me/919835496666?text=Hello%20Pulps%20%26%20Leaves%2C%20I%20would%20like%20a%20quote%20for%20100kg%20plain%20makhana.",
            },
        ],
    },
    {
        "name": "Roasted Makhana with 3 Masala Packs 200g",
        "display_title": "Roasted Makhana",
        "slug": "roasted-makhana-masala-combo",
        "category": "Makhana",
        "price": 350,
        "mrp": 350,
        "unit": "200g Pack",
        "pieces_label": "Three masala sachets inside",
        "description": "Plain roasted makhana with three masala sachets",
        "details": "Season it your way with Peri Peri, Cheese Blast, and Cream & Onion masala sachets packed alongside plain roasted makhana.",
        "kicker": "3 masala sachets inside - 200g pack",
        "secondary_title": "Roasted Makhana with 3 Masala Packs",
        "cart_badge": "3 flavours inside",
        "image": "img/naivedyam-masala-pack-cutout-200g-20260730.png",
        "image_alt": "Pulps and Leaves roasted makhana 200g pouch with three masala packets",
        "image_width": 408,
        "image_height": 612,
        "highlights": ["Gluten free", "Rich in protein", "No preservatives"],
        "available_months": list(range(1, 13)),
        "availability_label": "Out of stock",
        "in_stock": False,
    },
    {
        "name": "Flavoured Makhana 200g Pack",
        "display_title": "Flavoured Makhana",
        "slug": "flavoured-makhana",
        "category": "Makhana",
        "price": 350,
        "mrp": 350,
        "unit": "200g Pack",
        "pieces_label": "Four flavours, one clean crunch",
        "description": "Premium flavoured makhana 200g pack",
        "details": "Pick bold Peri Peri, creamy Cream & Onion, bright Tangy Tomato, or rich Cheese Blast. Every jar is roasted, never fried.",
        "kicker": "Choose your flavour - 200g jar",
        "secondary_title": "Flavoured Makhana",
        "cart_badge": "Choose a flavour",
        "image": "img/naivedyam-four-flavours-cutout-20260801.png",
        "image_alt": "Pulps and Leaves Peri Peri, Cream and Onion, Tangy Tomato, and Cheese Blast flavoured makhana jars",
        "image_width": 1126,
        "image_height": 795,
        "highlights": ["Roasted, not fried", "Gluten free", "No preservatives"],
        "available_months": list(range(1, 13)),
        "availability_label": "Out of stock",
        "in_stock": False,
        "variant_label": "Choose a flavour",
        "variant_aria_label": "Choose a flavoured makhana jar or combo",
        "variants": [
            {
                "slug": "flavoured-makhana-peri-peri",
                "name": "Peri Peri Makhana",
                "display_title": "Peri Peri Makhana",
                "option_label": "Peri Peri",
                "price": 350,
                "price_label": "Rs 350",
                "unit": "200g Jar",
                "pieces_label": "Bold, warm, and crunchy",
                "details": "A lively Peri Peri roast with a satisfying clean crunch.",
                "kicker": "Peri Peri - 200g jar",
                "secondary_title": "Peri Peri Makhana",
                "cart_badge": "Peri Peri",
                "image": "img/naivedyam-flavoured-peri-peri-cutout-20260801.png",
                "image_alt": "Pulps and Leaves Peri Peri makhana 200g jar",
                "image_width": 250,
                "image_height": 792,
                "highlights": ["Roasted, not fried", "Gluten free", "No preservatives"],
            },
            {
                "slug": "flavoured-makhana-cream-onion",
                "name": "Cream and Onion Makhana",
                "display_title": "Cream and Onion Makhana",
                "option_label": "Cream & Onion",
                "price": 350,
                "price_label": "Rs 350",
                "unit": "200g Jar",
                "pieces_label": "Creamy, savoury, and crunchy",
                "details": "A smooth Cream and Onion flavour with the same light roasted crunch.",
                "kicker": "Cream and Onion - 200g jar",
                "secondary_title": "Cream and Onion Makhana",
                "cart_badge": "Cream and Onion",
                "image": "img/naivedyam-flavoured-cream-onion-cutout-20260801.png",
                "image_alt": "Pulps and Leaves Cream and Onion makhana 200g jar",
                "image_width": 262,
                "image_height": 792,
                "highlights": ["Roasted, not fried", "Gluten free", "No preservatives"],
            },
            {
                "slug": "flavoured-makhana-tangy-tomato",
                "name": "Tangy Tomato Makhana",
                "display_title": "Tangy Tomato Makhana",
                "option_label": "Tangy Tomato",
                "price": 350,
                "price_label": "Rs 350",
                "unit": "200g Jar",
                "pieces_label": "Tangy, bright, and crunchy",
                "details": "A bright tomato flavour paired with lightly roasted makhana.",
                "kicker": "Tangy Tomato - 200g jar",
                "secondary_title": "Tangy Tomato Makhana",
                "cart_badge": "Tangy Tomato",
                "image": "img/naivedyam-flavoured-tangy-tomato-cutout-20260801.png",
                "image_alt": "Pulps and Leaves Tangy Tomato makhana 200g jar",
                "image_width": 284,
                "image_height": 792,
                "highlights": ["Roasted, not fried", "Gluten free", "No preservatives"],
            },
            {
                "slug": "flavoured-makhana-cheese-blast",
                "name": "Cheese Blast Makhana",
                "display_title": "Cheese Blast Makhana",
                "option_label": "Cheese Blast",
                "price": 350,
                "price_label": "Rs 350",
                "unit": "200g Jar",
                "pieces_label": "Rich, cheesy, and crunchy",
                "details": "A rich Cheese Blast flavour with a crisp roasted finish.",
                "kicker": "Cheese Blast - 200g jar",
                "secondary_title": "Cheese Blast Makhana",
                "cart_badge": "Cheese Blast",
                "image": "img/naivedyam-flavoured-cheese-blast-cutout-20260801.png",
                "image_alt": "Pulps and Leaves Cheese Blast makhana 200g jar",
                "image_width": 290,
                "image_height": 792,
                "highlights": ["Roasted, not fried", "Gluten free", "No preservatives"],
            },
            {
                "slug": "flavoured-makhana-four-flavour-combo",
                "name": "Four Flavour Makhana Combo",
                "display_title": "Four Flavour Makhana Combo",
                "option_label": "Combo of 4",
                "price": 1400,
                "price_label": "Rs 1,400",
                "unit": "4 x 200g Jars",
                "pieces_label": "All four flavours in one combo",
                "details": "Bring home Peri Peri, Cream and Onion, Tangy Tomato, and Cheese Blast together.",
                "kicker": "Four flavour combo - 800g",
                "secondary_title": "Four Flavour Makhana Combo",
                "cart_badge": "Four flavour combo",
                "image": "img/naivedyam-four-flavours-cutout-20260801.png",
                "image_alt": "Pulps and Leaves four flavour makhana combo",
                "image_width": 1126,
                "image_height": 795,
                "highlights": ["4 x 200g jars", "Roasted, not fried", "No preservatives"],
            },
        ],
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
        if product.get("in_stock", True):
            lines.append(
                f"{index} - {product['display_title']} ({product['unit']}) - Rs {product['price']} - {product['availability_label']}"
            )
        else:
            lines.append(
                f"{index} - {product['display_title']} ({product['unit']}) - {product['availability_label']}"
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
    return product.get("in_stock", True) and on_date.month in product.get("available_months", [])


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
