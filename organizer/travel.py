"""Find flight and hotel confirmations and build a chronological itinerary."""
from __future__ import annotations

import re
from dateutil import parser as date_parser
from datetime import datetime
from organizer.utils import get_header, get_body_text, gmail_execute

TRAVEL_QUERIES = [
    "subject:(flight confirmation OR booking confirmation OR itinerary) newer_than:90d",
    "subject:(hotel confirmation OR reservation confirmed OR check-in) newer_than:90d",
    "subject:(boarding pass OR e-ticket) newer_than:90d",
    "from:(delta.com OR united.com OR southwest.com OR aa.com OR jetblue.com "
    "OR spirit.com OR frontier.com) newer_than:90d",
    "from:(marriott.com OR hilton.com OR hyatt.com OR airbnb.com OR booking.com "
    "OR expedia.com OR hotels.com) newer_than:90d",
]

# Patterns to extract dates from confirmation emails
DATE_PATTERNS = [
    r"(?:depart|arrive|check.?in|check.?out|date)\s*[:=]?\s*"
    r"(\w+\s+\d{1,2},?\s*\d{4})",
    r"(\d{1,2}/\d{1,2}/\d{2,4})",
    r"(\w+ \d{1,2}, \d{4})",
]



def _extract_travel_dates(text: str) -> list[datetime]:
    """Try to extract travel-related dates from text."""
    dates = []
    for pattern in DATE_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            try:
                dt = date_parser.parse(m, fuzzy=True)
                # Only future or recent dates
                if dt.year >= datetime.now().year - 1:
                    dates.append(dt)
            except Exception:
                continue
    return dates


def _classify_travel_type(subject: str, sender: str) -> str:
    """Classify as flight, hotel, car, or other."""
    combined = f"{subject} {sender}".lower()
    if any(w in combined for w in ["flight", "boarding", "airline", "e-ticket",
                                     "delta", "united", "southwest", "jetblue",
                                     "american airlines", "spirit", "frontier"]):
        return "✈️  Flight"
    elif any(w in combined for w in ["hotel", "check-in", "reservation",
                                      "marriott", "hilton", "hyatt", "airbnb",
                                      "booking.com"]):
        return "🏨 Hotel"
    elif any(w in combined for w in ["car rental", "hertz", "enterprise", "avis"]):
        return "🚗 Car Rental"
    return "📋 Travel"


def build_travel_itinerary(service):
    """Search for travel confirmations and print a chronological itinerary."""
    print("\n✈️  Building Travel Itinerary...")
    print("=" * 60)

    seen_ids = set()
    itinerary_items = []

    for query in TRAVEL_QUERIES:
        results = gmail_execute(
            service.users().messages().list(userId="me", q=query, maxResults=50)
        )
        messages = results.get("messages", [])

        for msg_meta in messages:
            if msg_meta["id"] in seen_ids:
                continue
            seen_ids.add(msg_meta["id"])

            msg = gmail_execute(
                service.users().messages().get(userId="me", id=msg_meta["id"], format="full")
            )
            headers = msg.get("payload", {}).get("headers", [])
            subject = get_header(headers, "Subject")
            sender = get_header(headers, "From")
            date_str = get_header(headers, "Date")
            body = get_body_text(msg.get("payload", {}))
            snippet = msg.get("snippet", "")

            travel_type = _classify_travel_type(subject, sender)
            travel_dates = _extract_travel_dates(f"{subject} {body}")

            # Use the email date as fallback
            try:
                email_date = date_parser.parse(date_str, fuzzy=True)
            except Exception:
                email_date = datetime.now()

            display_date = travel_dates[0] if travel_dates else email_date

            itinerary_items.append({
                "date": display_date,
                "type": travel_type,
                "subject": subject[:70],
                "sender": sender.split("<")[0].strip()[:30],
            })

    # Sort chronologically
    itinerary_items.sort(key=lambda x: x["date"])

    if not itinerary_items:
        print("  No travel confirmations found in the last 90 days.")
        return

    current_date = None
    for item in itinerary_items:
        item_date = item["date"].strftime("%A, %B %d, %Y")
        if item_date != current_date:
            current_date = item_date
            print(f"\n  📅 {current_date}")
            print(f"  {'─' * 50}")

        print(f"    {item['type']}  {item['subject']}")
        print(f"             From: {item['sender']}")

    print(f"\n  Total travel items found: {len(itinerary_items)}")
