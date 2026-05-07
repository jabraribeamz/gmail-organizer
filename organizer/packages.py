"""Find tracking numbers and summarize package deliveries."""

import re
from dateutil import parser as date_parser
from datetime import datetime

PACKAGE_QUERIES = [
    "subject:(shipped OR tracking OR delivery OR out for delivery) newer_than:14d",
    "subject:(your package OR your order has shipped) newer_than:14d",
    "from:(ups.com OR fedex.com OR usps.com OR amazon.com) subject:(tracking OR shipped OR delivered) newer_than:14d",
    "from:(dhl.com OR ontrac.com OR lasership) newer_than:14d",
]

# Tracking number patterns by carrier
TRACKING_PATTERNS = {
    "USPS": [
        r"\b(9[0-9]{21,27})\b",           # USPS tracking (starts with 9)
        r"\b((?:92|94)\d{20,24})\b",       # USPS certified/priority
    ],
    "UPS": [
        r"\b(1Z[A-Z0-9]{16})\b",          # UPS
    ],
    "FedEx": [
        r"\b(\d{12,22})\b",               # FedEx (12-22 digits)
    ],
    "Amazon": [
        r"\b(TBA\d{10,14})\b",            # Amazon logistics
    ],
}

DELIVERY_PATTERNS = [
    r"(?:deliver(?:y|ed)\s+(?:by|on|date|expected))\s*[:=]?\s*(\w+,?\s+\w+\s+\d{1,2})",
    r"(?:arriving|expected|estimated)\s*[:=]?\s*(\w+,?\s+\w+\s+\d{1,2})",
    r"(?:deliver(?:y|ed)\s+(?:by|on))\s*[:=]?\s*(\d{1,2}/\d{1,2})",
]


def _get_header(headers: list, name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h.get("value", "")
    return ""


def _get_body_text(payload: dict) -> str:
    import base64
    body_text = ""
    mime = payload.get("mimeType", "")
    if mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            body_text = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    elif "parts" in payload:
        for part in payload["parts"]:
            body_text += _get_body_text(part)
    return body_text


def _find_tracking(text: str) -> list[tuple[str, str]]:
    """Find tracking numbers. Returns list of (carrier, number)."""
    found = []
    for carrier, patterns in TRACKING_PATTERNS.items():
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for m in matches:
                if len(m) >= 10:  # filter noise
                    found.append((carrier, m))
    return found


def _find_delivery_date(text: str) -> str | None:
    for pattern in DELIVERY_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                dt = date_parser.parse(match.group(1), fuzzy=True)
                return dt.strftime("%a %m/%d")
            except Exception:
                continue
    return None


def _detect_status(text: str) -> str:
    text_lower = text.lower()
    if "delivered" in text_lower:
        return "✅ Delivered"
    elif "out for delivery" in text_lower:
        return "🚚 Out for Delivery"
    elif "in transit" in text_lower:
        return "📦 In Transit"
    elif "shipped" in text_lower:
        return "📬 Shipped"
    else:
        return "📋 Processing"


def track_packages(service):
    """Find package tracking info and summarize."""
    print("\n📦 Package Tracking Summary")
    print("=" * 60)

    seen_ids = set()
    packages = []

    for query in PACKAGE_QUERIES:
        results = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=50)
            .execute()
        )
        messages = results.get("messages", [])

        for msg_meta in messages:
            if msg_meta["id"] in seen_ids:
                continue
            seen_ids.add(msg_meta["id"])

            msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_meta["id"], format="full")
                .execute()
            )
            headers = msg.get("payload", {}).get("headers", [])
            subject = _get_header(headers, "Subject")
            sender = _get_header(headers, "From")
            date_str = _get_header(headers, "Date")
            body = _get_body_text(msg.get("payload", {}))
            snippet = msg.get("snippet", "")
            combined = f"{subject} {body} {snippet}"

            tracking_nums = _find_tracking(combined)
            delivery_date = _find_delivery_date(combined)
            status = _detect_status(combined)

            try:
                email_date = date_parser.parse(date_str, fuzzy=True)
                email_date_str = email_date.strftime("%m/%d")
            except Exception:
                email_date_str = "??/??"

            packages.append({
                "email_date": email_date_str,
                "subject": subject[:55],
                "sender": sender.split("<")[0].strip()[:25],
                "status": status,
                "delivery_date": delivery_date or "TBD",
                "tracking": tracking_nums[:1],  # first match only
            })

    if not packages:
        print("  No recent package shipment emails found.")
        return

    for pkg in packages:
        print(f"  {pkg['status']}")
        print(f"    {pkg['subject']}")
        print(f"    From: {pkg['sender']}  │  Shipped: {pkg['email_date']}  │  ETA: {pkg['delivery_date']}")
        if pkg["tracking"]:
            carrier, num = pkg["tracking"][0]
            print(f"    Tracking: {carrier} {num}")
        print()

    print(f"  Total packages tracked: {len(packages)}")
