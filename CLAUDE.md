# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the project root (already gitignored):
```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

Two credential files are also required in the project root (both gitignored):
- `credentials.json` — OAuth client credentials downloaded from Google Cloud Console
- `token.json` — auto-generated on first auth run; do not commit

First-time auth: `python main.py --auth`

## Running

```bash
python main.py --triage              # AI classify + label + archive low-priority
python main.py --categorize          # categorize only, no priority/archive
python main.py --spending            # 30-day Amazon/UberEats/DoorDash totals
python main.py --receipts            # label all receipts from last year
python main.py --travel              # build chronological travel itinerary
python main.py --bills               # bills due in next 7 days (includes overdue)
python main.py --packages            # package tracking summary
python main.py --calendar-sync       # extract email events → Google Calendar
python main.py --all                 # run everything (triage covers categorize, no double-classify)
python main.py --triage --max-results 300  # process more emails (default: 100)
```

## Architecture

`main.py` loads `.env` via `python-dotenv`, authenticates via `organizer/auth.py`, then calls feature functions. `--all` skips standalone `--categorize` since `--triage` already applies category labels.

**Data flow for AI features (triage/categorize):**
1. `auth.py` — `_get_credentials()` loads/refreshes OAuth token; `get_gmail_service()` and `get_calendar_service()` each call it independently (token cached in `token.json`)
2. Feature module fetches email metadata from Gmail API via `utils.gmail_execute()` (handles 429 rate-limit with exponential backoff)
3. `ai.py` — batches 10 emails per Claude API call via `classify_batch()`; returns priority + category + action per email using `claude-sonnet-4-6`
4. `labels.py` — `apply_labels()` batches all label IDs into a single Gmail `modify` call per email

**Non-AI features** (`spending.py`, `receipts.py`, `travel.py`, `bills.py`, `packages.py`) use Gmail search filters + regex — no Claude API calls.

**`calendar_sync.py`** uses regex to extract dates/times/locations from emails matching event-like queries, then creates Google Calendar entries via the Calendar API. Timezone is auto-detected from the OS via `tzlocal` (`utils.get_local_timezone()`).

## Shared utilities (`organizer/utils.py`)

- `get_header(headers, name)` — extract a Gmail message header value
- `get_body_text(payload)` — recursively decode plain-text body from Gmail payload
- `gmail_execute(request)` — wraps any Google API request with 429 exponential backoff
- `get_local_timezone()` — returns IANA timezone string from system via `tzlocal`; falls back to `ORGANIZER_TIMEZONE` env var, then `"America/New_York"`

## Gmail label structure

All labels live under `Organizer/`:
- `Organizer/High Priority`, `Organizer/Medium Priority`, `Organizer/Low Priority`
- `Organizer/<Category>` for each of the 12 categories

`labels.py:ensure_labels()` is called at the start of any labeling feature — creates missing labels idempotently and caches the name→id map in a module-level dict.

## Safety

Low-priority emails are **archived** (removed from inbox, still searchable) — never deleted. The `auto_archive_low` parameter in `triage_inbox()` defaults to `True` but can be set to `False` to skip archiving.
