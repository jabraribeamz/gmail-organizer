"""Order history: summarize spending on Amazon, UberEats, DoorDash over last 30 days."""
from __future__ import annotations

import re
from datetime import datetime
from dateutil import parser as date_parser
from organizer.utils import get_header, get_body_text, gmail_execute

# Senders to look for
SPENDING_QUERIES = {
    "Amazon": "from:amazon.com subject:(order OR receipt OR purchase) newer_than:30d",
    "UberEats": "from:uber.com subject:(receipt OR order) newer_than:30d",
    "DoorDash": "from:doordash.com subject:(receipt OR order) newer_than:30d",
}

# Regex patterns to extract dollar amounts from email bodies
AMOUNT_PATTERNS = [
    r"(?:order\s+total|grand\s+total|total\s+charged|amount\s+charged|total)"
    r"\s*[:=]?\s*\$?([\d,]+\.\d{2})",
    r"\$([\d,]+\.\d{2})",
]


def _extract_amounts(text: str) -> list[float]:
    """Extract dollar amounts from email text."""
    amounts = []
    for pattern in AMOUNT_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            try:
                val = float(m.replace(",", ""))
                if 0.50 < val < 10000:  # filter out noise
                    amounts.append(val)
            except ValueError:
                continue
    return amounts



def spending_summary(service):
    """Print a 30-day spending summary for Amazon, UberEats, DoorDash."""
    print("\n💰 Spending Summary (Last 30 Days)")
    print("=" * 50)

    grand_total = 0.0

    for vendor, query in SPENDING_QUERIES.items():
        results = gmail_execute(
            service.users().messages().list(userId="me", q=query, maxResults=50)
        )
        messages = results.get("messages", [])

        vendor_total = 0.0
        order_count = 0
        orders = []

        for msg_meta in messages:
            msg = gmail_execute(
                service.users().messages().get(userId="me", id=msg_meta["id"], format="full")
            )
            headers = msg.get("payload", {}).get("headers", [])
            subject = get_header(headers, "Subject")
            date_str = get_header(headers, "Date")
            body = get_body_text(msg.get("payload", {}))

            amounts = _extract_amounts(f"{subject} {body}")
            if amounts:
                # Take the largest amount (likely the total)
                total = max(amounts)
                vendor_total += total
                order_count += 1

                try:
                    date_obj = date_parser.parse(date_str, fuzzy=True)
                    date_display = date_obj.strftime("%m/%d")
                except Exception:
                    date_display = "??/??"
                orders.append((date_display, total, subject[:50]))

        print(f"\n  {vendor}:")
        if orders:
            for date_display, amount, subj in orders[:10]:  # show up to 10
                print(f"    {date_display}  ${amount:>8.2f}  {subj}")
            print(f"    {'─' * 40}")
            print(f"    {order_count} orders  │  Total: ${vendor_total:,.2f}")
        else:
            print(f"    No orders found.")

        grand_total += vendor_total

    print(f"\n{'=' * 50}")
    print(f"  GRAND TOTAL (30 days): ${grand_total:,.2f}")
