# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."
```

Two credential files are required in the project root (both gitignored):
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
python main.py --bills               # bills due in next 7 days
python main.py --packages            # package tracking summary
python main.py --all                 # run everything
python main.py --triage --max-results 300  # process more emails (default: 100)
```

## Architecture

`main.py` is the CLI entry point — it parses flags, authenticates once via `organizer/auth.py`, then calls the appropriate feature function.

**Data flow for AI features (triage/categorize):**
1. `auth.py` — returns a Gmail API service object using OAuth (`credentials.json` / `token.json`)
2. Feature module (e.g. `triage.py`) — fetches email metadata from Gmail API
3. `ai.py` — sends emails to Claude in batches of 10 via `classify_batch()`; returns priority + category + action per email
4. `labels.py` — creates/applies Gmail labels under the `Organizer/` namespace; archives low-priority messages

**Non-AI features** (`spending.py`, `receipts.py`, `travel.py`, `bills.py`, `packages.py`) query Gmail directly using search filters and regex — no Claude API calls.

## Claude API usage

`organizer/ai.py` is the sole integration point with Anthropic. It uses `claude-sonnet-4-20250514` with a hardcoded system prompt (`SYSTEM_PROMPT`) that defines the persona, priority rules, and 12 valid categories. Responses are expected as raw JSON (no markdown). The client is lazily initialized from `ANTHROPIC_API_KEY`.

`classify_batch()` is preferred over `classify_email()` — batching 10 emails per API call keeps costs low (~$0.02–0.05 per 100 emails at Sonnet pricing). If the batch JSON parse fails, it falls back to per-email calls.

## Gmail label structure

All labels live under `Organizer/`:
- `Organizer/High Priority`, `Organizer/Medium Priority`, `Organizer/Low Priority`
- `Organizer/<Category>` for each of the 12 categories

`labels.py:ensure_labels()` is called at the start of any feature that applies labels — it creates missing labels idempotently.

## Safety

Low-priority emails are **archived** (removed from inbox, still searchable) — never deleted. The `auto_archive_low` parameter in `triage_inbox()` defaults to `True` but can be set to `False` to skip archiving.
