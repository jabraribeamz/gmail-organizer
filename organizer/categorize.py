"""Bulk email categorization engine.

Scans all mail in pages of 100 (Gmail API max), applies Organizer/*
labels, auto-archives stale Promotions/Junk, and trash-deletes very
old Junk. Protected and important emails are never auto-deleted — they
get 'Organizer/Review Me' instead.

--dry-run note: ensure_labels() will create the Organizer/* label
structure in Gmail (necessary infrastructure) but will NOT modify any
email messages.
"""

import logging
from typing import Any

from googleapiclient.errors import HttpError
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from organizer.labels import (
    apply_label,
    ensure_labels,
    remove_from_inbox,
    trash_message,
)
from organizer.rules import classify_email, is_important_signal, is_protected
from organizer.utils import (
    age_in_days,
    build_sent_cache,
    extract_email,
    get_header,
    gmail_execute,
)

logger = logging.getLogger(__name__)
console = Console()

PAGE_SIZE = 100   # Gmail API hard maximum per messages.list call

PROMOTIONS_ARCHIVE_DAYS = 30
JUNK_ARCHIVE_DAYS = 7
JUNK_DELETE_DAYS = 90


def categorize_inbox(  # pylint: disable=too-many-branches,too-many-locals
    service: Any, max_emails: int = 0, dry_run: bool = False
) -> None:
    """Scan all emails, apply 5-category labels, run auto-archive/delete.

    Args:
        service: Authenticated Gmail API service object.
        max_emails: Stop after this many emails. 0 = no limit
            (processes entire mailbox).
        dry_run: Preview without modifying any email (labels are
            still created if missing).

    Returns:
        None
    """
    mode_tag = (
        "[yellow]DRY RUN[/yellow]" if dry_run else "[green]LIVE[/green]"
    )
    console.print(
        f"\n[bold cyan]Gmail Organizer — Bulk Categorize "
        f"({mode_tag})[/bold cyan]"
    )

    label_map = ensure_labels(service)

    console.print("  Building sent-mail cache...", end="")
    sent_cache = build_sent_cache(service)
    console.print(f" {len(sent_cache):,} unique recipients.")

    # Use None total for unlimited mode so the bar is indeterminate
    # rather than misleadingly "done" once the estimate is exceeded.
    if max_emails > 0:
        progress_total = max_emails
        console.print(f"  Processing up to {max_emails:,} emails.\n")
    else:
        progress_total = None
        total_est = _estimate_total(service)
        console.print(
            f"  Estimated mailbox size: ~{total_est:,} messages "
            f"(--max 0 = process all)\n"
        )

    stats: dict = {
        "processed": 0,
        "protected": 0,
        "categories": {
            "Important": 0,
            "Personal": 0,
            "Receipts": 0,
            "Promotions": 0,
            "Junk": 0,
        },
        "archived": 0,
        "deleted": 0,
        "review_me": 0,
        "errors": 0,
    }

    count_fmt = (
        f"/{max_emails:,}" if max_emails > 0 else " processed"
    )
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed:,}" + count_fmt),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Scanning...", total=progress_total)
        page_token = None

        while True:
            processed = stats["processed"]
            capped = bool(max_emails) and processed >= max_emails
            if capped:
                break

            if max_emails > 0:
                fetch_n = min(
                    PAGE_SIZE, max_emails - processed
                )
            else:
                fetch_n = PAGE_SIZE

            result = gmail_execute(
                service.users().messages().list(
                    userId="me",
                    maxResults=fetch_n,
                    pageToken=page_token,
                    q="-in:sent -in:drafts",
                    includeSpamTrash=False,
                )
            )

            messages = result.get("messages", [])
            if not messages:
                break

            for stub in messages:
                at_cap = (
                    bool(max_emails)
                    and stats["processed"] >= max_emails
                )
                if at_cap:
                    break
                try:
                    _process_one(
                        service, stub["id"],
                        label_map, sent_cache, stats, dry_run,
                    )
                except (  # pylint: disable=broad-except
                    HttpError, KeyError, ValueError, AttributeError
                ) as exc:
                    logger.debug(
                        "Skipping message %s: %s", stub.get("id"), exc
                    )
                    stats["errors"] += 1

                stats["processed"] += 1

                if stats["processed"] % 50 == 0:
                    cat = stats["categories"]
                    progress.update(
                        task,
                        completed=stats["processed"],
                        description=(
                            "Scanning... "
                            f"[red]Imp:{cat['Important']}[/red] "
                            f"[yellow]Per:{cat['Personal']}[/yellow] "
                            f"[green]Rec:{cat['Receipts']}[/green] "
                            "[magenta]"
                            f"Pro:{cat['Promotions']}"
                            "[/magenta] "
                            f"[dim]Jnk:{cat['Junk']}[/dim]"
                        ),
                    )
                else:
                    progress.advance(task, 1)

            page_token = result.get("nextPageToken")
            if not page_token:
                break

    _print_summary(stats, dry_run)


def _process_one(  # pylint: disable=too-many-arguments
    # pylint: disable=too-many-positional-arguments,too-many-locals
    service: Any,
    msg_id: str,
    label_map: dict,
    sent_cache: set,
    stats: dict,
    dry_run: bool,
) -> None:
    """Fetch one message, classify it, label it, and apply auto-clean rules.

    Args:
        service: Authenticated Gmail API service object.
        msg_id: Gmail message ID string.
        label_map: Dict mapping Organizer label names to label IDs.
        sent_cache: Set of email addresses previously sent to.
        stats: Mutable stats dict updated in-place.
        dry_run: If True, skip all write operations.

    Returns:
        None
    """
    msg = gmail_execute(
        service.users().messages().get(
            userId="me",
            id=msg_id,
            format="metadata",
            metadataHeaders=["Subject", "From", "List-Unsubscribe"],
        )
    )

    headers = msg.get("payload", {}).get("headers", [])
    subject = get_header(headers, "Subject")
    sender = get_header(headers, "From")
    snippet = msg.get("snippet", "")
    has_unsub = bool(get_header(headers, "List-Unsubscribe"))
    gmail_labels = msg.get("labelIds", [])
    msg_age = age_in_days(int(msg.get("internalDate", "0")))
    is_unread = "UNREAD" in gmail_labels
    replied_to = extract_email(sender).lower() in sent_cache

    # Step 1: Protected check ─────────────────────────────────────────
    # Protected emails (school, Monroe CT, ASU, Masuk) only get Saved.
    # They are NEVER archived, deleted, or moved under any circumstances.
    if is_protected(subject, sender, snippet):
        stats["protected"] += 1
        if not dry_run:
            apply_label(service, msg_id, "Organizer/Saved", label_map)
        return

    # Step 2: Classify ────────────────────────────────────────────────
    category = classify_email(
        subject, sender, snippet, has_unsub, gmail_labels, replied_to
    )
    stats["categories"][category] = (
        stats["categories"].get(category, 0) + 1
    )
    if not dry_run:
        apply_label(service, msg_id, f"Organizer/{category}", label_map)

    # Step 3: Auto-archive / auto-delete ──────────────────────────────
    do_delete = category == "Junk" and msg_age >= JUNK_DELETE_DAYS
    do_archive = (
        (category == "Promotions" and msg_age >= PROMOTIONS_ARCHIVE_DAYS)
        or (
            category == "Junk"
            and JUNK_ARCHIVE_DAYS <= msg_age < JUNK_DELETE_DAYS
        )
    )

    if not (do_delete or do_archive):
        return

    # Safety gate: if any importance signal is present, route to
    # Review Me instead of deleting/archiving — never auto-deleted.
    important = is_important_signal(
        subject, sender, snippet, msg_age, is_unread, replied_to
    )

    if important:
        stats["review_me"] += 1
        if not dry_run:
            apply_label(
                service, msg_id, "Organizer/Review Me", label_map
            )
    elif do_delete:
        stats["deleted"] += 1
        if not dry_run:
            trash_message(service, msg_id)
    else:
        stats["archived"] += 1
        if not dry_run:
            remove_from_inbox(service, msg_id)


def _estimate_total(service: Any) -> int:
    """Fetch the approximate total message count from the Gmail profile.

    Args:
        service: Authenticated Gmail API service object.

    Returns:
        Estimated message count, or 10 000 if the API call fails.
    """
    try:
        profile = gmail_execute(
            service.users().getProfile(userId="me")
        )
        return profile.get("messagesTotal", 10_000)
    except HttpError:  # pylint: disable=broad-except
        return 10_000


def _print_summary(stats: dict, dry_run: bool) -> None:
    """Print a formatted summary table of the categorization run.

    Args:
        stats: Dict of counters collected during the run.
        dry_run: If True, print DRY RUN mode indicator.

    Returns:
        None
    """
    console.print()
    if dry_run:
        mode = "[yellow]DRY RUN — no changes made[/yellow]"
    else:
        mode = "[green]LIVE — changes applied[/green]"
    console.print(f"  Mode:             {mode}")
    console.print(f"  Total processed:  {stats['processed']:,}")
    console.print(f"  Protected/Saved:  {stats['protected']:,}")
    console.print(f"  Archived:         {stats['archived']:,}")
    console.print(f"  Sent to trash:    {stats['deleted']:,}")

    if stats["review_me"]:
        console.print(
            f"\n  [bold yellow]"
            f"{stats['review_me']:,} emails flagged for your review "
            f"(would have been deleted/archived)[/bold yellow]"
        )
        console.print(
            "  Run [bold]python main.py --review[/bold] to see them.\n"
        )

    table = Table(title="Category Breakdown")
    table.add_column("Category", style="cyan")
    table.add_column("Count", justify="right")
    for cat, count in sorted(
        stats["categories"].items(), key=lambda x: -x[1]
    ):
        table.add_row(cat, f"{count:,}")
    console.print(table)

    if stats["errors"]:
        console.print(
            f"\n  [red]API errors skipped: {stats['errors']}[/red]"
        )
