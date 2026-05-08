# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Two credential files are required in the project root (both gitignored):
- `credentials.json` — OAuth client credentials downloaded from Google Cloud Console
- `token.json` — auto-generated on first run; do not commit

No API keys or `.env` file needed — this project makes zero paid API calls.

## Running

```bash
python main.py --categorize                  # scan all emails, apply labels, auto-archive/delete stale bulk
python main.py --categorize --dry-run        # preview what would happen without changes
python main.py --categorize --max 5000       # limit to 5000 emails (default: no limit)
python main.py --triage                      # score every unread email 1-10, print top 20 to action today
python main.py --review                      # list all emails flagged for manual review
python main.py --receipts                    # find and label receipt emails from the last year
python main.py --receipts --dry-run          # preview receipt labeling
```

## Architecture

`main.py` authenticates via `organizer/auth.py` (Google OAuth2), then calls the appropriate feature module. No `.env` file or external AI API is used.

**Data flow for `--categorize`:**
1. `auth.py` — loads/refreshes OAuth token from `~/.gmail-organizer/token.json`
2. `categorize.py` — paginates all mail in batches of 500 via `utils.gmail_execute()` (handles 429 backoff)
3. `rules.py` — classifies each email using sender domain tables, subject keyword patterns, and Gmail category labels; no API calls
4. `labels.py` — applies `Organizer/<category>` label via a single Gmail `modify` call per email
5. Auto-archive / auto-delete runs after labeling; protected and important emails are routed to `Organizer/Review Me` instead

**Data flow for `--triage`:**
1. Fetches all unread emails (up to 2000)
2. Builds a sent-mail cache (last 2000 sent) to detect previously-replied-to senders
3. Scores each email 1–10 via `rules.score_priority()` using: real-person detection, urgency keywords, recency, unread status, replied-to history, Gmail category tab
4. Prints top 20 ranked by score

## Module overview

| File | Purpose |
|---|---|
| `organizer/auth.py` | Google OAuth2 — **do not modify** |
| `organizer/rules.py` | Classification engine: `classify_email()`, `is_protected()`, `is_important_signal()`, `score_priority()` |
| `organizer/categorize.py` | Bulk scan + label + auto-clean loop |
| `organizer/triage.py` | Unread scoring (`triage_inbox`) + review listing (`list_review_me`) |
| `organizer/labels.py` | Label creation and caching |
| `organizer/receipts.py` | Receipt finder via Gmail search queries |
| `organizer/utils.py` | `get_header`, `gmail_execute`, `extract_domain`, `extract_email`, `age_in_days`, `build_sent_cache` |

## Gmail label structure

All labels live under `Organizer/`:

| Label | Color | Used for |
|---|---|---|
| `Organizer/Important` | Red | Bills, invoices, contracts, appointments, action required |
| `Organizer/Personal` | Yellow | Real people, replied-to senders, personal domains |
| `Organizer/Receipts` | Green | Order confirmations, shipping, payment receipts |
| `Organizer/Promotions` | Purple | Newsletters, marketing, sales, unsubscribe-linked mail |
| `Organizer/Junk` | Gray | No-reply automated mail, notifications, security codes |
| `Organizer/Saved` | Blue | Protected emails — never archived or deleted |
| `Organizer/Review Me` | Orange | Would-be-deleted emails flagged for manual review |

`labels.py:ensure_labels()` creates missing labels idempotently on every run and caches the name→id map in a module-level dict.

## Auto-clean rules

| Category | Threshold | Action |
|---|---|---|
| Promotions | older than 30 days | archive (remove from inbox) |
| Junk | older than 7 days | archive |
| Junk | older than 90 days | trash |

Before any archive or delete, `rules.is_important_signal()` runs. If triggered, the email gets `Organizer/Review Me` instead and is never auto-deleted.

## Protected emails (Organizer/Saved)

The following emails are detected by `rules.is_protected()` and only receive the `Organizer/Saved` label — they are never archived, deleted, or moved:

- Any email from `masuk.org`, `masukhs.org`, `monroe.ct.us`, `monroect.org`, `asu.edu` (and subdomains)
- Any subject/snippet containing: Masuk, Monroe CT, Monroe Connecticut, Stepney, Stevenson, MHS, Panthers, ASU, Arizona State, graduation, transcript, enrollment, financial aid, student loan, GPA, semester, tuition, FAFSA
