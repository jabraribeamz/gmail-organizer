"""Shared utilities for Gmail Organizer."""

import logging
import time
import random
from datetime import datetime, timezone
from typing import Any

from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


def get_header(headers: list, name: str) -> str:
    """Return the value of a named header from a list of header dicts.

    Args:
        headers: List of dicts with ``name`` and ``value`` keys.
        name: Case-insensitive header name to look up.

    Returns:
        Header value string, or empty string if not found.
    """
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def gmail_execute(request: Any, retries: int = 5) -> Any:
    """Execute a Gmail API request with exponential backoff on 429/5xx.

    Args:
        request: An un-executed Gmail API request object.
        retries: Maximum number of attempts before re-raising.

    Returns:
        The parsed API response dict.

    Raises:
        HttpError: If a non-retryable error occurs or retries are exhausted.
    """
    for attempt in range(retries):
        try:
            return request.execute()
        except HttpError as exc:
            if exc.resp.status in (429, 500, 503) and attempt < retries - 1:
                # Jitter avoids thundering-herd when multiple processes
                # back off at the same time.
                time.sleep(2 ** attempt + random.uniform(0, 1))
                continue
            raise


def extract_domain(email_addr: str) -> str:
    """Return the domain portion of an email address string.

    Handles bare addresses (``user@example.com``) and display-name
    format (``"Name" <user@example.com>``).

    Args:
        email_addr: Raw email address or display-name string.

    Returns:
        Lowercase domain string, or empty string if unparseable.
    """
    addr = email_addr or ""
    if "<" in addr:
        addr = addr.split("<")[-1].rstrip(">")
    parts = addr.split("@")
    return parts[-1].lower().strip() if len(parts) == 2 else ""


def extract_email(from_header: str) -> str:
    """Extract a bare email address from a From header value.

    Args:
        from_header: Raw From header, e.g. ``"Name" <user@example.com>``.

    Returns:
        Lowercase email address string.
    """
    from_header = from_header or ""
    if "<" in from_header:
        return from_header.split("<")[-1].rstrip(">").lower().strip()
    return from_header.lower().strip()


def age_in_days(internal_date_ms: int) -> float:
    """Return message age in days from Gmail's internalDate millis.

    Args:
        internal_date_ms: Gmail internalDate field (milliseconds since
            epoch). Pass 0 or None to treat the message as brand-new.

    Returns:
        Age as a float number of days. Returns 0.0 if date is missing.
    """
    if not internal_date_ms:
        return 0.0
    now = datetime.now(timezone.utc)
    msg_time = datetime.fromtimestamp(
        internal_date_ms / 1000, tz=timezone.utc
    )
    return (now - msg_time).total_seconds() / 86400


def build_sent_cache(service: Any, max_sent: int = 2000) -> set:
    """Return a set of email addresses this account has sent mail to.

    Used to detect senders we've replied to before — a strong signal
    that the email is from a real person we know.

    Args:
        service: Authenticated Gmail API service object.
        max_sent: Maximum number of sent messages to inspect.

    Returns:
        Set of lowercase email address strings.
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
                        userId="me",
                        id=stub["id"],
                        format="metadata",
                        metadataHeaders=["To"],
                    )
                )
                to_header = get_header(
                    msg.get("payload", {}).get("headers", []), "To"
                )
                for addr in to_header.split(","):
                    email = extract_email(addr.strip())
                    # Guard: only add strings that are actual email
                    # addresses. Without this, display-name splits like
                    # "Doe, John" <j@x.com> would inject the bare
                    # display-name fragment '"doe' into the set.
                    if email and "@" in email:
                        sent_emails.add(email.lower())
                fetched += 1
            except (HttpError, KeyError, ValueError) as exc:
                logger.debug("Skipping sent stub %s: %s", stub.get("id"), exc)

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return sent_emails
