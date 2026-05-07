"""Scan for upcoming bills and credit card statements due in the next 7 days."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from dateutil import parser as date_parser
from organizer.utils import get_header, get_body_text, gmail_execute

BILL_QUERIES = [
    "subject:(bill OR statement OR payment due OR amount due) newer_than:14d",
    "subject:(utility OR electric OR water OR gas OR internet OR phone bill) newer_than:14d",
    "from:(aps.com OR srp OR cox.com OR tmobile OR verizon OR att.com) newer_than:14d",
    "subject:(credit card statement OR minimum payment) newer_than:14d",
]

# Patterns for due dates
DUE_DATE_PATTERNS = [
    r"(?:due\s+(?:date|by|on))\s*[:=]?\s*(\w+\s+\d{1,2},?\s*\d{2,4})",
    r"(?:pay\s+by|payment\s+due)\s*[:=]?\s*(\w+\s+\d{1,2},?\s*\d{2,4})",
    r"(?:due\s+(?:date|by|on))\s*[:=]?\s*(\d{1,2}/\d{1,2}/\d{2,4})",
]

# Patterns for amounts
AMOUNT_PATTERNS = [
    r"(?:amount\s+due|total\s+due|minimum\s+(?:payment|due)|balance\s+due|pay)"
    r"\s*[:=]?\s*\$?([\d,]+\.\d{2})",
    r"\$([\d,]+\.\d{2})",
]



def _extract_due_date(text: str) -> datetime | None:
    for pattern in DUE_DATE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                return date_parser.parse(match.group(1), fuzzy=True)
            except Exception:
                continue
    return None


def _extract_amount(text: str) -> float | None:
    for pattern in AMOUNT_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                val = float(match.group(1).replace(",", ""))
                if 1.0 < val < 50000:
                    return val
            except ValueError:
                continue
    return None


def scan_bills(service):
    """Find bills due in the next 7 days."""
    print("\n📄 Bill Reminders (Next 7 Days)")
    print("=" * 60)

    now = datetime.now()
    cutoff = now + timedelta(days=7)

    seen_ids = set()
    bills = []

    for query in BILL_QUERIES:
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
            body = get_body_text(msg.get("payload", {}))
            combined = f"{subject} {body}"

            due_date = _extract_due_date(combined)
            amount = _extract_amount(combined)

            # Include overdue bills and bills due within 7 days
            if due_date and due_date.date() <= cutoff.date():
                bills.append({
                    "due_date": due_date,
                    "amount": amount,
                    "subject": subject[:60],
                    "sender": sender.split("<")[0].strip()[:30],
                })

    # Sort by due date
    bills.sort(key=lambda x: x["due_date"])

    if not bills:
        print("  No bills due in the next 7 days found.")
        return

    for bill in bills:
        due_str = bill["due_date"].strftime("%a %m/%d")
        amount_str = f"${bill['amount']:,.2f}" if bill["amount"] else "Amount TBD"
        overdue = " ⚠️  OVERDUE" if bill["due_date"].date() < now.date() else ""

        print(f"  📌 {due_str}  │  {amount_str:>12}  │  {bill['subject']}{overdue}")
        print(f"                │              │  From: {bill['sender']}")

    total = sum(b["amount"] for b in bills if b["amount"])
    print(f"\n  Total due this week: ${total:,.2f}")
