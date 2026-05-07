"""Scan emails for events and create Google Calendar entries."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from dateutil import parser as date_parser
from googleapiclient.errors import HttpError
from organizer.utils import get_header, get_body_text, gmail_execute, get_local_timezone

EVENT_QUERIES = [
    "subject:(meeting invitation OR meeting invite OR calendar invite) newer_than:30d",
    "subject:(you are invited OR you're invited OR join us) newer_than:30d",
    "subject:(webinar OR conference OR workshop OR seminar) newer_than:30d",
    "subject:(appointment confirmed OR appointment reminder) newer_than:30d",
    "subject:(reservation confirmed OR booking confirmed) newer_than:30d",
]

_DATE_PATTERNS = [
    r"(?:date|on|scheduled\s+for)\s*[:=]?\s*(\w+day,\s+\w+\s+\d{1,2},?\s*\d{4})",
    r"(?:date|on|scheduled\s+for)\s*[:=]?\s*(\w+\s+\d{1,2},?\s*\d{4})",
    r"(\w+day,\s+\w+\s+\d{1,2},?\s*\d{4})",
    r"(\d{1,2}/\d{1,2}/\d{4})",
    r"(\w+\s+\d{1,2},\s*\d{4})",
]

_TIME_PATTERNS = [
    r"(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)(?:\s*[A-Z]{2,4})?)",
    r"\bat\s+(\d{1,2}:\d{2}(?:\s*(?:AM|PM|am|pm))?)",
    r"(\d{1,2}\s*(?:AM|PM|am|pm))",
]

_LOCATION_PATTERNS = [
    r"(?:location|venue|where|place)\s*[:\-]\s*(.+?)(?:\n|<)",
    r"(?:zoom|teams|meet\.google\.com|webex)[^\s]*\s*(?:link\s*)?[:=]?\s*(https?://\S+)",
    r"(https?://(?:zoom\.us|teams\.microsoft\.com|meet\.google\.com)\S+)",
]

_DURATION_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:hour|hr)s?|(\d+)\s*min(?:ute)?s?",
    re.IGNORECASE,
)


def _extract_date(text: str) -> datetime | None:
    for pattern in _DATE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                dt = date_parser.parse(match.group(1), fuzzy=True)
                if dt.year >= datetime.now().year - 1:
                    return dt
            except Exception:
                continue
    return None


def _extract_time(text: str) -> str | None:
    for pattern in _TIME_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _extract_location(text: str) -> str | None:
    for pattern in _LOCATION_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            loc = match.group(1).strip()
            if loc:
                return loc[:200]
    return None


def _extract_duration_minutes(text: str) -> int:
    total = 0
    for m in _DURATION_RE.finditer(text):
        if m.group(1):
            total += int(float(m.group(1)) * 60)
        elif m.group(2):
            total += int(m.group(2))
    return total if total else 60  # default 1 hour


def _event_exists(cal_service, summary: str, start_dt: datetime) -> bool:
    """Return True if a calendar event with the same title already exists within ±1 hour."""
    # Strip tzinfo before appending "Z" — isoformat() on a tz-aware datetime already
    # includes the offset, making "...+00:00Z" which the Calendar API rejects.
    naive = start_dt.replace(tzinfo=None)
    window_start = (naive - timedelta(hours=1)).isoformat() + "Z"
    window_end = (naive + timedelta(hours=1)).isoformat() + "Z"
    try:
        result = cal_service.events().list(
            calendarId="primary",
            timeMin=window_start,
            timeMax=window_end,
            q=summary[:50],
            singleEvents=True,
        ).execute()
        return bool(result.get("items"))
    except HttpError:
        return False


def _create_event(cal_service, summary: str, start_dt: datetime, duration_min: int,
                  location: str | None, description: str) -> str | None:
    """Insert a Calendar event and return its HTML link, or None on failure."""
    end_dt = start_dt + timedelta(minutes=duration_min)
    # Use local system timezone; strip any parsed tzinfo so the Calendar API
    # interprets the time relative to timeZone, not as a UTC offset.
    tz = get_local_timezone()
    naive_start = start_dt.replace(tzinfo=None)
    naive_end = end_dt.replace(tzinfo=None)
    body = {
        "summary": summary,
        "description": description[:2000],
        "start": {"dateTime": naive_start.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": tz},
        "end":   {"dateTime": naive_end.strftime("%Y-%m-%dT%H:%M:%S"),   "timeZone": tz},
    }
    if location:
        body["location"] = location
    try:
        event = cal_service.events().insert(calendarId="primary", body=body).execute()
        return event.get("htmlLink")
    except HttpError as e:
        print(f"    ⚠️  Calendar API error: {e}")
        return None


def calendar_sync(gmail_service, cal_service):
    """Search emails for events and sync them to Google Calendar."""
    print("\n📅 Calendar Sync")
    print("=" * 60)

    seen_ids: set[str] = set()
    created = 0
    skipped = 0

    for query in EVENT_QUERIES:
        results = gmail_execute(
            gmail_service.users().messages().list(userId="me", q=query, maxResults=50)
        )
        for msg_meta in results.get("messages", []):
            if msg_meta["id"] in seen_ids:
                continue
            seen_ids.add(msg_meta["id"])

            msg = gmail_execute(
                gmail_service.users().messages().get(
                    userId="me", id=msg_meta["id"], format="full"
                )
            )
            headers = msg.get("payload", {}).get("headers", [])
            subject = get_header(headers, "Subject") or "Untitled Event"
            sender  = get_header(headers, "From")
            body    = get_body_text(msg.get("payload", {}))
            snippet = msg.get("snippet", "")
            combined = f"{subject}\n{body[:3000]}"

            event_date = _extract_date(combined)
            if not event_date:
                continue

            time_str = _extract_time(combined)
            if time_str:
                try:
                    parsed_time = date_parser.parse(time_str, fuzzy=True)
                    event_date = event_date.replace(
                        hour=parsed_time.hour, minute=parsed_time.minute
                    )
                except Exception:
                    pass

            # Skip events that are clearly in the past (>7 days ago)
            if event_date < datetime.now() - timedelta(days=7):
                continue

            location    = _extract_location(combined)
            duration    = _extract_duration_minutes(combined)
            description = f"Imported from email.\nFrom: {sender}\n\n{snippet[:500]}"

            if _event_exists(cal_service, subject, event_date):
                skipped += 1
                continue

            link = _create_event(cal_service, subject, event_date, duration, location, description)
            if link:
                created += 1
                date_str = event_date.strftime("%a %b %d %I:%M %p")
                print(f"  ✅ {date_str}  │  {subject[:55]}")
                if location:
                    print(f"              │  📍 {location[:55]}")
            else:
                skipped += 1

    print(f"\n  Events created: {created}  │  Skipped (already exist or errors): {skipped}")
