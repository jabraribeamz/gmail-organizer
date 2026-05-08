#!/usr/bin/env python3
"""Gmail Organizer CLI — rule-based, zero API cost.

Usage:
    python main.py --categorize             Scan all emails, apply labels, auto-clean
    python main.py --categorize --dry-run   Preview without changes
    python main.py --triage                 Score unread emails 1-10, show top 20
    python main.py --review                 List emails flagged for manual review
    python main.py --receipts               Find and label receipt emails
    python main.py --max 5000               Process up to N emails (default: all)
"""

import argparse
from organizer.auth import get_service
from organizer.categorize import categorize_inbox
from organizer.triage import triage_inbox, list_review_me
from organizer.receipts import find_and_label_receipts


def main():
    parser = argparse.ArgumentParser(
        description="Gmail Organizer — free rule-based email triage"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--categorize", action="store_true",
        help="Scan all emails, apply 5-category labels, auto-archive/delete stale bulk mail",
    )
    mode.add_argument(
        "--triage", action="store_true",
        help="Score every unread email 1-10 by priority, print top 20 to action today",
    )
    mode.add_argument(
        "--review", action="store_true",
        help="List all emails flagged 'Review Me' (protected from auto-delete)",
    )
    mode.add_argument(
        "--receipts", action="store_true",
        help="Find and label receipt emails from the last year",
    )

    parser.add_argument(
        "--max", type=int, default=0,
        help="Max emails to process for --categorize (default: 0 = no limit)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would happen without making any changes",
    )

    args = parser.parse_args()
    service = get_service()

    if args.categorize:
        categorize_inbox(service, max_emails=args.max, dry_run=args.dry_run)
    elif args.triage:
        triage_inbox(service, dry_run=args.dry_run)
    elif args.review:
        list_review_me(service)
    elif args.receipts:
        find_and_label_receipts(service, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
