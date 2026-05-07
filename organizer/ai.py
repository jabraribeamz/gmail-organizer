"""AI-powered email analysis using the Anthropic Claude API."""
from __future__ import annotations

import json
import os
import anthropic

# Initialize client — reads ANTHROPIC_API_KEY from environment
_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY not set. Get your key at https://console.anthropic.com/ "
                "and run: export ANTHROPIC_API_KEY='sk-ant-...'"
            )
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


# The valid categories and priorities the AI can assign
VALID_CATEGORIES = [
    "Finance",
    "Shopping",
    "Travel",
    "Social",
    "Food & Delivery",
    "Entertainment",
    "Health & Fitness",
    "Newsletters",
    "Promotions",
    "Account & Security",
    "Personal",
    "Other",
]

VALID_PRIORITIES = ["high", "medium", "low"]

SYSTEM_PROMPT = """You are an email triage assistant for a personal Gmail inbox.
Your job is to analyze each email and return a JSON classification.

This is a PERSONAL email account (not work). The owner is a young professional who:
- Orders from Amazon, UberEats, DoorDash frequently
- Has a Verizon phone account
- Is into hockey, golf, and sports bars
- Uses dating apps (Hinge, Bumble, etc.)
- Gets typical personal emails: bills, subscriptions, social media, travel, etc.

For each email, return ONLY valid JSON (no markdown, no explanation):

{
  "priority": "high" | "medium" | "low",
  "category": "<one of the valid categories>",
  "reason": "<1 sentence explaining why>",
  "action": "keep" | "archive"
}

PRIORITY RULES:
- HIGH: Bills/payments due, security alerts, 2FA codes, flight/hotel confirmations,
  messages from real people (friends, family, dates), medical/health, anything time-sensitive
- MEDIUM: Order confirmations, shipping updates, account notifications, app notifications
  that might need attention, subscription renewals
- LOW: Marketing emails, promotional offers, newsletters you didn't ask for, social media
  digest emails, surveys, "we miss you" emails, spam-adjacent

CATEGORY OPTIONS:
- Finance: Banks, credit cards, Venmo, PayPal, tax docs, bills, statements
- Shopping: Amazon, eBay, retail orders, shipping, returns, tracking
- Travel: Flights, hotels, Airbnb, car rentals, trip confirmations
- Social: Dating apps, social media notifications, messages from friends
- Food & Delivery: UberEats, DoorDash, Grubhub, restaurant receipts
- Entertainment: Streaming services, gaming, sports, event tickets, Spotify, Netflix
- Health & Fitness: Gym, health insurance, doctor appointments, pharmacy
- Newsletters: Substack, email newsletters, digests, blog updates
- Promotions: Sales, coupons, marketing emails, "limited time" offers
- Account & Security: Password resets, 2FA, login alerts, account verification
- Personal: Direct messages from real people, personal correspondence
- Other: Anything that doesn't fit above

ACTION RULES:
- "keep": Stays in inbox (all high priority + medium priority)
- "archive": Remove from inbox, still searchable (all low priority)
"""


def classify_email(subject: str, sender: str, snippet: str) -> dict:
    """Use Claude to classify a single email. Returns classification dict."""
    client = _get_client()

    user_msg = (
        f"Classify this email:\n"
        f"From: {sender}\n"
        f"Subject: {subject}\n"
        f"Preview: {snippet[:300]}"
    )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    text = response.content[0].text.strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        # Fallback if JSON parsing fails
        return {
            "priority": "medium",
            "category": "Other",
            "reason": "AI classification failed, defaulting to medium",
            "action": "keep",
        }

    # Validate and sanitize
    if result.get("priority") not in VALID_PRIORITIES:
        result["priority"] = "medium"
    if result.get("category") not in VALID_CATEGORIES:
        result["category"] = "Other"
    if result.get("action") not in ("keep", "archive"):
        result["action"] = "keep"

    return result


def classify_batch(emails: list[dict], batch_size: int = 10) -> list[dict]:
    """Classify multiple emails in batches to reduce API calls.

    Each email dict should have: subject, sender, snippet, msg_id

    Sends up to `batch_size` emails per API call for efficiency.
    Returns list of dicts with original fields + classification.
    """
    client = _get_client()
    results = []

    for i in range(0, len(emails), batch_size):
        batch = emails[i : i + batch_size]

        # Build the batch prompt
        email_list = []
        for idx, email in enumerate(batch):
            email_list.append(
                f"EMAIL {idx + 1}:\n"
                f"  From: {email['sender']}\n"
                f"  Subject: {email['subject']}\n"
                f"  Preview: {email['snippet'][:200]}"
            )

        user_msg = (
            f"Classify each of these {len(batch)} emails. "
            f"Return ONLY a JSON array of objects, one per email, in order.\n\n"
            + "\n\n".join(email_list)
        )

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300 * len(batch),
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )

        text = response.content[0].text.strip()

        try:
            classifications = json.loads(text)
            if not isinstance(classifications, list):
                classifications = [classifications]
        except json.JSONDecodeError:
            # If batch fails, fall back to individual classification
            classifications = []
            for email in batch:
                cls = classify_email(email["subject"], email["sender"], email["snippet"])
                classifications.append(cls)

        # Merge classifications back with original email data
        for email, cls in zip(batch, classifications):
            merged = {**email, **cls}
            results.append(merged)

    return results
