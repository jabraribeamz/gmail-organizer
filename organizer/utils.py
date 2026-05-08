"""Shared utilities for Gmail Organizer."""

import time
import random
from datetime import datetime, timezone
from googleapiclient.errors import HttpError


def get_header(headers: list, name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def gmail_execute(request, retries: int = 5):
    """Execute a Gmail API request with exponential backoff + jitter on 429/5xx."""
    for attempt in range(retries):
        try:
            return request.execute()
        except HttpError as e:
            if e.resp.status in (429, 500, 503) and attempt < retries - 1:
                # jitter avoids thundering-herd if multiple processes back off together
                time.sleep(2 ** attempt + random.uniform(0, 1))
                continue
            raise


def extract_domain(email_addr: str) -> str:
    addr = email_addr or ""
    if "<" in addr:
        addr = addr.split("<")[-1].rstrip(">")
    parts = addr.split("@")
    return parts[-1].lower().strip() if len(parts) == 2 else ""


def extract_email(from_header: str) -> str:
    from_header = from_header or ""
    if "<" in from_header:
        return from_header.split("<")[-1].rstrip(">").lower().strip()
    return from_header.lower().strip()


def age_in_days(internal_date_ms: int) -> float:
    """Return message age in days. Returns 0.0 (treats as brand-new) if date is missing."""
    if not internal_date_ms:
        return 0.0
    now = datetime.now(timezone.utc)
    msg_time = datetime.fromtimestamp(internal_date_ms / 1000, tz=timezone.utc)
    return (now - msg_time).total_seconds() / 86400


def build_sent_cache(service, max_sent: int = 2000) -> set:
    """Return a set of email addresses this account has sent mail to.

    Used to detect senders we've replied to before — a strong signal
    that the email is from a real person we know.
    """
    sent_emails: set = set()
    page_token = None
    fetched = 0

    while fetched < max_sent:
        result = gmail_execute(
            service.users().messages().list(
                userId="me",
                labelIds=["SENT"],
                maxResults=min(100, max_sent - fetched),
                pageToken=page_token,
            )
        )
        messages = result.get("messages", [])
        if not messages:
            break

        for stub in messages:
            try:
                msg = gmail_execute(
                    service.users().messages().get(
                        userId="me", id=stub["id"], format="metadata",
                        metadataHeaders=["To"],
                    )
                )
                to_header = get_header(msg.get("payload", {}).get("headers", []), "To")
                for addr in to_header.split(","):
                    email = extract_email(addr.strip())
                    # Guard: only add strings that are actually email addresses.
                    # Without this, display-name splits like "Doe, John" <j@x.com>
                    # would inject the bare display-name fragment '"doe' into the set.
                    if email and "@" in email:
                        sent_emails.add(email.lower())
                fetched += 1
            except Exception:
                pass

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return sent_emails
