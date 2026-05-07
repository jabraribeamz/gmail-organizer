"""Shared helpers used across organizer modules."""

import base64
import time
from googleapiclient.errors import HttpError


# Cache so we only hit the geolocation API once per process
_timezone_cache: str = ""


def get_local_timezone() -> str:
    """Return the IANA timezone for the device's current location.

    Resolution order:
    1. IP geolocation (ip-api.com) — reflects actual current location,
       updates automatically when traveling, same method laptops use
    2. tzlocal — reads macOS system timezone setting
    3. ORGANIZER_TIMEZONE env var
    4. "America/New_York" as last resort
    """
    global _timezone_cache
    if _timezone_cache:
        return _timezone_cache

    import os
    import json
    import urllib.request

    # 1. IP geolocation — free, no API key, 45 req/min limit
    try:
        with urllib.request.urlopen("http://ip-api.com/json/?fields=timezone", timeout=3) as r:
            data = json.loads(r.read().decode())
            tz = data.get("timezone", "")
            if tz:
                _timezone_cache = tz
                return _timezone_cache
    except Exception:
        pass

    # 2. System timezone via tzlocal
    try:
        from tzlocal import get_localzone_name
        tz = get_localzone_name()
        if tz:
            _timezone_cache = tz
            return _timezone_cache
    except Exception:
        pass

    # 3. Env var / hardcoded fallback
    _timezone_cache = os.environ.get("ORGANIZER_TIMEZONE", "America/New_York")
    return _timezone_cache


def get_header(headers: list, name: str) -> str:
    """Extract a header value by name from a Gmail message headers list."""
    for h in headers:
        if h["name"].lower() == name.lower():
            return h.get("value", "")
    return ""


def get_body_text(payload: dict) -> str:
    """Recursively extract plain text from a Gmail message payload."""
    body_text = ""
    mime = payload.get("mimeType", "")

    if mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            body_text = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    elif "parts" in payload:
        for part in payload["parts"]:
            body_text += get_body_text(part)

    return body_text


def gmail_execute(request, retries: int = 5):
    """Execute a Gmail API request with exponential backoff on rate-limit errors."""
    delay = 1.0
    for attempt in range(retries):
        try:
            return request.execute()
        except HttpError as e:
            if e.resp.status == 429 and attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
            else:
                raise
