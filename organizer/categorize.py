"""Bulk email categorization engine.

Scans all mail in pages of 100 (Gmail API max), applies Organizer/* labels,
auto-archives stale Promotions/Junk, and trash-deletes very old Junk.
Protected and important emails are never auto-deleted — they get
'Organizer/Review Me' instead.

--dry-run note: ensure_labels() will create the Organizer/* label structure
in Gmail (necessary infrastructure) but will NOT modify any email messages.
"""

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from organizer.labels import ensure_labels, apply_label, remove_from_inbox, trash_message
from organizer.rules import classify_email, is_protected, is_important_signal
from organizer.utils import get_header, gmail_execute, extract_email, age_in_days, build_sent_cache

console = Console()

PAGE_SIZE = 100   # Gmail API hard maximum per messages.list call

PROMOTIONS_ARCHIVE_DAYS = 30
JUNK_ARCHIVE_DAYS       = 7
JUNK_DELETE_DAYS        = 90


def categorize_inbox(service, max_emails: int = 0, dry_run: bool = False):
    """Scan all emails, apply 5-category labels, run auto-archive / auto-delete.

    Args:
        service: Authenticated Gmail API service.
        max_emails: Stop after this many emails. 0 = no limit (processes entire mailbox).
        dry_run: Preview without modifying any email (labels are still created if missing).
    """
    mode_tag = "[yellow]DRY RUN[/yellow]" if dry_run else "[green]LIVE[/green]"
    console.print(f"\n[bold cyan]Gmail Organizer — Bulk Categorize ({mode_tag})[/bold cyan]")

    label_map = ensure_labels(service)

    console.print("  Building sent-mail cache...", end="")
    sent_cache = build_sent_cache(service)
    console.print(f" {len(sent_cache):,} unique recipients.")

    # Use None total for unlimited mode so the bar is indeterminate rather
    # than misleadingly "done" once the estimate is exceeded.
    if max_emails > 0:
        progress_total = max_emails
        console.print(f"  Processing up to {max_emails:,} emails.\n")
    else:
        progress_total = None
        total_est = _estimate_total(service)
        console.print(f"  Estimated mailbox size: ~{total_est:,} messages (--max 0 = process all)\n")

    stats = {
        "processed": 0,
        "protected": 0,
        "categories": {"Important": 0, "Personal": 0, "Receipts": 0, "Promotions": 0, "Junk": 0},
        "archived": 0,
        "deleted": 0,
        "review_me": 0,
        "errors": 0,
    }

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed:,}" + (f"/{max_emails:,}" if max_emails > 0 else " processed")),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Scanning...", total=progress_total)
        page_token = None

        while True:
            if max_emails > 0 and stats["processed"] >= max_emails:
                break

            fetch_n = min(PAGE_SIZE, max_emails - stats["processed"]) if max_emails > 0 else PAGE_SIZE

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
                if max_emails > 0 and stats["processed"] >= max_emails:
                    break
                try:
                    _process_one(service, stub["id"], label_map, sent_cache, stats, dry_run)
                except Exception:
                    stats["errors"] += 1

                stats["processed"] += 1

                if stats["processed"] % 50 == 0:
                    c = stats["categories"]
                    progress.update(
                        task,
                        completed=stats["processed"],
                        description=(
                            f"Scanning... "
                            f"[red]Imp:{c['Important']}[/red] "
                            f"[yellow]Per:{c['Personal']}[/yellow] "
                            f"[green]Rec:{c['Receipts']}[/green] "
                            f"[magenta]Pro:{c['Promotions']}[/magenta] "
                            f"[dim]Jnk:{c['Junk']}[/dim]"
                        ),
                    )
                else:
                    progress.advance(task, 1)

            page_token = result.get("nextPageToken")
            if not page_token:
                break

    _print_summary(stats, dry_run)


def _process_one(service, msg_id: str, label_map: dict, sent_cache: set,
                 stats: dict, dry_run: bool):
    msg = gmail_execute(
        service.users().messages().get(
            userId="me", id=msg_id, format="metadata",
            metadataHeaders=["Subject", "From", "List-Unsubscribe"],
        )
    )

    headers      = msg.get("payload", {}).get("headers", [])
    subject      = get_header(headers, "Subject")
    sender       = get_header(headers, "From")
    snippet      = msg.get("snippet", "")
    has_unsub    = bool(get_header(headers, "List-Unsubscribe"))
    gmail_labels = msg.get("labelIds", [])
    msg_age      = age_in_days(int(msg.get("internalDate", "0")))
    is_unread    = "UNREAD" in gmail_labels
    replied_to   = extract_email(sender).lower() in sent_cache

    # ── Step 1: Protected check ─────────────────────────────────────────────
    # Protected emails (school, Monroe CT, ASU, Masuk) only get Saved label.
    # They are NEVER archived, deleted, or moved under any circumstances.
    if is_protected(subject, sender, snippet):
        stats["protected"] += 1
        if not dry_run:
            apply_label(service, msg_id, "Organizer/Saved", label_map)
        return

    # ── Step 2: Classify ────────────────────────────────────────────────────
    category = classify_email(subject, sender, snippet, has_unsub, gmail_labels, replied_to)
    stats["categories"][category] = stats["categories"].get(category, 0) + 1
    if not dry_run:
        apply_label(service, msg_id, f"Organizer/{category}", label_map)

    # ── Step 3: Auto-archive / auto-delete ─────────────────────────────────
    do_delete  = (category == "Junk" and msg_age >= JUNK_DELETE_DAYS)
    do_archive = (
        (category == "Promotions" and msg_age >= PROMOTIONS_ARCHIVE_DAYS)
        or (category == "Junk" and JUNK_ARCHIVE_DAYS <= msg_age < JUNK_DELETE_DAYS)
    )

    if not (do_delete or do_archive):
        return

    # Safety gate: if any importance signal is present, route to Review Me
    # instead of deleting or archiving. This email will NEVER be auto-deleted.
    important = is_important_signal(subject, sender, snippet, msg_age, is_unread, replied_to)

    if important:
        stats["review_me"] += 1
        if not dry_run:
            apply_label(service, msg_id, "Organizer/Review Me", label_map)
    elif do_delete:
        stats["deleted"] += 1
        if not dry_run:
            trash_message(service, msg_id)
    else:
        stats["archived"] += 1
        if not dry_run:
            remove_from_inbox(service, msg_id)


def _estimate_total(service) -> int:
    try:
        profile = gmail_execute(service.users().getProfile(userId="me"))
        return profile.get("messagesTotal", 10_000)
    except Exception:
        return 10_000


def _print_summary(stats: dict, dry_run: bool):
    console.print()
    mode = "[yellow]DRY RUN — no changes made[/yellow]" if dry_run else "[green]LIVE — changes applied[/green]"
    console.print(f"  Mode:             {mode}")
    console.print(f"  Total processed:  {stats['processed']:,}")
    console.print(f"  Protected/Saved:  {stats['protected']:,}")
    console.print(f"  Archived:         {stats['archived']:,}")
    console.print(f"  Sent to trash:    {stats['deleted']:,}")

    if stats["review_me"]:
        console.print(
            f"\n  [bold yellow]⚠  {stats['review_me']:,} emails flagged for your review "
            f"(would have been deleted/archived)[/bold yellow]"
        )
        console.print("  Run [bold]python main.py --review[/bold] to see them.\n")

    table = Table(title="Category Breakdown")
    table.add_column("Category", style="cyan")
    table.add_column("Count", justify="right")
    for cat, count in sorted(stats["categories"].items(), key=lambda x: -x[1]):
        table.add_row(cat, f"{count:,}")
    console.print(table)

    if stats["errors"]:
        console.print(f"\n  [red]API errors skipped: {stats['errors']}[/red]")
