# Gmail Organizer (AI-Powered)

An AI-powered Gmail automation tool that uses **Claude** to intelligently triage, categorize, and summarize your personal inbox. No rigid keyword rules — Claude reads your emails contextually and makes smart decisions about what matters.

## What It Does

| Feature | Command | Description |
|---|---|---|
| **AI Triage** | `--triage` | Claude scores every email by importance, applies priority labels, and archives junk |
| **AI Categorize** | `--categorize` | Sorts emails into 12 personal categories using AI |
| **Spending Summary** | `--spending` | Totals your Amazon / UberEats / DoorDash spending (last 30 days) |
| **Receipt Finder** | `--receipts` | Finds all digital receipts from the past year → labels them |
| **Travel Itinerary** | `--travel` | Extracts flight + hotel confirmations → chronological itinerary |
| **Bill Reminders** | `--bills` | Finds utility / credit card bills due in the next 7 days |
| **Package Tracking** | `--packages` | Finds tracking numbers and summarizes deliveries |
| **Calendar Sync** | `--calendar-sync` | Extracts events from emails → creates Google Calendar entries |

### AI Categories (personal email, not work)

Finance · Shopping · Travel · Social · Food & Delivery · Entertainment · Health & Fitness · Newsletters · Promotions · Account & Security · Personal · Other

### Priority Levels

- 🔴 **High** — Bills due, security alerts, 2FA codes, messages from real people, travel confirmations
- 🟡 **Medium** — Order confirmations, shipping, account notifications, subscription renewals
- 🟢 **Low** → auto-archived — Marketing, promos, newsletters, surveys, "we miss you" emails

## Prerequisites

- Python 3.10+
- A Google Cloud project with Gmail API enabled
- OAuth 2.0 credentials (`credentials.json`)
- An Anthropic API key ([console.anthropic.com](https://console.anthropic.com/))

## Setup

### 1. Clone & Install

```bash
git clone https://github.com/YOUR_USERNAME/gmail-organizer.git
cd gmail-organizer
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Anthropic API Key

Get your key at [console.anthropic.com](https://console.anthropic.com/), then:

```bash
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
```

Or add it to a `.env` file in the project root (already gitignored):

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### 3. Google Cloud / Gmail API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (e.g., `gmail-organizer`)
3. Enable the **Gmail API**: APIs & Services → Library → search "Gmail API" → Enable
4. Create OAuth credentials:
   - APIs & Services → Credentials → Create Credentials → **OAuth client ID**
   - Application type: **Desktop app**
   - Download the JSON → rename to `credentials.json` → place in project root
5. OAuth consent screen:
   - Add your personal Gmail as a test user
   - Required scopes: `gmail.modify`, `gmail.labels`, `calendar` (for `--calendar-sync`)

### 4. Authenticate

```bash
python main.py --auth
```

This opens a browser to authorize your Gmail. After approval, `token.json` is saved locally.

### 5. Run

```bash
# AI triage (recommended — does priority + category + archive)
python main.py --triage

# Just categorize (no priority scoring)
python main.py --categorize

# Spending report
python main.py --spending

# Find and label receipts
python main.py --receipts

# Travel itinerary
python main.py --travel

# Upcoming bills
python main.py --bills

# Package tracking
python main.py --packages

# Sync email events to Google Calendar
python main.py --calendar-sync

# Run everything
python main.py --all

# Process more emails (default is 100)
python main.py --triage --max-results 300
```

## File Structure

```
gmail-organizer/
├── main.py                  # CLI entry point
├── credentials.json         # YOUR OAuth creds (gitignored)
├── token.json               # Auto-generated auth token (gitignored)
├── requirements.txt
├── .gitignore
├── README.md
└── organizer/
    ├── __init__.py
    ├── ai.py                # 🤖 Claude API integration (triage + categorize)
    ├── auth.py              # Gmail API authentication
    ├── labels.py            # Label creation and management
    ├── triage.py            # AI-powered inbox triage
    ├── categorize.py        # AI-powered categorization (standalone)
    ├── spending.py          # Order history / spending summary
    ├── receipts.py          # Receipt finder + labeler
    ├── travel.py            # Travel itinerary builder
    ├── bills.py             # Bill reminder scanner
    └── packages.py          # Package tracking extractor
```

## How the AI Works

Instead of matching keywords like a spam filter, Claude reads each email's sender, subject, and preview text and makes a contextual judgment:

- A Verizon email saying "your bill is ready" → **High priority / Finance**
- A Hinge notification → **Medium priority / Social**
- An email from your mom → **High priority / Personal**
- "50% off at Nike" → **Low priority / Promotions** → archived

Emails are sent to Claude in batches of 10 for efficiency. A typical 100-email triage uses ~10 API calls.

### Cost Estimate

Using Claude Sonnet at ~$3/M input tokens:
- 100 emails ≈ $0.02–0.05
- Running daily for a month ≈ $0.60–1.50

## Safety

- **No permanent deletes.** Low-priority emails are archived (removed from inbox, still searchable).
- `credentials.json`, `token.json`, and `.env` are gitignored.
- Your Gmail password is never stored — uses OAuth tokens only.
- Email content is sent to Anthropic's API for classification. If this is a concern, you can switch to the keyword-based fallback in `triage.py`.

## License

MIT
