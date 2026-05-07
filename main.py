#!/usr/bin/env python3
"""Gmail Organizer — CLI entry point."""

import argparse
import sys
from dotenv import load_dotenv
load_dotenv()  # load ANTHROPIC_API_KEY and ORGANIZER_TIMEZONE from .env if present

from organizer.auth import get_gmail_service, get_calendar_service


def main():
    parser = argparse.ArgumentParser(
        description="Gmail Organizer: triage, categorize, and summarize your inbox.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --auth           # First-time authentication
  python main.py --triage         # Score + label + archive low-priority
  python main.py --spending       # 30-day Amazon/UberEats/DoorDash summary
  python main.py --receipts       # Label all receipts from last year
  python main.py --travel         # Build travel itinerary
  python main.py --bills          # Bills due in the next 7 days
  python main.py --packages       # Package tracking summary
  python main.py --calendar-sync  # Sync email events to Google Calendar
  python main.py --all            # Run everything
        """,
    )

    parser.add_argument("--auth", action="store_true", help="Authenticate with Gmail (first-time setup)")
    parser.add_argument("--triage", action="store_true", help="Triage inbox by importance")
    parser.add_argument("--categorize", action="store_true", help="Auto-categorize inbox emails")
    parser.add_argument("--spending", action="store_true", help="30-day spending summary")
    parser.add_argument("--receipts", action="store_true", help="Find and label receipts")
    parser.add_argument("--travel", action="store_true", help="Build travel itinerary")
    parser.add_argument("--bills", action="store_true", help="Scan for upcoming bills")
    parser.add_argument("--packages", action="store_true", help="Track packages")
    parser.add_argument("--calendar-sync", action="store_true", help="Sync email events to Google Calendar")
    parser.add_argument("--all", action="store_true", help="Run all features")
    parser.add_argument("--max-results", type=int, default=100, help="Max emails to process (default: 100)")

    args = parser.parse_args()

    # If no action flags were passed, show help.
    # Exclude max_results since it always has a non-zero default.
    action_flags = {k: v for k, v in vars(args).items() if k != "max_results"}
    if not any(action_flags.values()):
        parser.print_help()
        sys.exit(0)

    # Authenticate
    print("🔐 Authenticating with Gmail...")
    try:
        service = get_gmail_service()
        print("  ✅ Authenticated successfully.\n")
    except FileNotFoundError as e:
        print(f"  ❌ {e}")
        sys.exit(1)
    except Exception as e:
        print(f"  ❌ Auth failed: {e}")
        sys.exit(1)

    if args.auth:
        print("  Auth complete. You can now run other commands.")
        return

    # Run selected features
    if args.triage or args.all:
        from organizer.triage import triage_inbox
        triage_inbox(service, max_results=args.max_results)

    # Skip standalone categorize when --all is set: triage already classifies + labels categories
    if args.categorize and not args.all:
        from organizer.categorize import categorize_inbox
        categorize_inbox(service, max_results=args.max_results)

    if args.spending or args.all:
        from organizer.spending import spending_summary
        spending_summary(service)

    if args.receipts or args.all:
        from organizer.receipts import find_and_label_receipts
        find_and_label_receipts(service)

    if args.travel or args.all:
        from organizer.travel import build_travel_itinerary
        build_travel_itinerary(service)

    if args.bills or args.all:
        from organizer.bills import scan_bills
        scan_bills(service)

    if args.packages or args.all:
        from organizer.packages import track_packages
        track_packages(service)

    if args.calendar_sync or args.all:
        from organizer.calendar_sync import calendar_sync
        try:
            cal_service = get_calendar_service()
            calendar_sync(service, cal_service)
        except Exception as e:
            print(f"\n  ❌ Calendar sync failed: {e}")
            print("  Tip: delete token.json and re-run --auth to grant Calendar permissions.")

    print("\n✨ Done!")


if __name__ == "__main__":
    main()
