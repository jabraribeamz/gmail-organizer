"""Triage scoring and Review Me listing.

--triage  Scores every unread email 1-10, prints top 20.
--review  Lists all emails tagged Organizer/Review Me.
"""
# pylint: disable=duplicate-code

import logging
from typing import Any

from googleapiclient.errors import HttpError
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from organizer.rules import score_priority
from organizer.utils import (
    age_in_days,
    build_sent_cache,
    extract_email,
    get_header,
    gmail_execute,
)

logger = logging.getLogger(__name__)
console = Console()

MAX_UNREAD = 2000


def triage_inbox(service: Any, dry_run: bool = False) -> None:
    """Score all unread emails 1-10, print top 20 ranked by priority.

    Triage is always read-only; dry_run only affects the display header.

    Args:
        service: Authenticated Gmail API service object.
        dry_run: If True, print a DRY RUN banner (no writes occur either way).

    Returns:
        None
    """
    console.print("\n[bold cyan]Gmail Triage — Priority Scorer[/bold cyan]")
    if dry_run:
        console.print("  [yellow]DRY RUN — read only[/yellow]\n")

    console.print("  Building sent-mail cache...", end="")
    sent_cache = build_sent_cache(service)
    console.print(f" {len(sent_cache):,} recipients.\n")

    emails = _fetch_unread(service)
    console.print(f"  Scoring {len(emails):,} unread emails...", end="")

    scored = []
    for email in emails:
        priority = score_priority(
            subject=email["subject"],
            sender=email["sender"],
            is_unread=True,
            age_days=email["age_days"],
            replied_to=(
                extract_email(email["sender"]).lower() in sent_cache
            ),
            gmail_labels=email["gmail_labels"],
        )
        scored.append({**email, "score": priority})

    scored.sort(key=lambda x: -x["score"])
    console.print(" done.\n")
    _print_top20(scored)


def list_review_me(service: Any) -> None:
    """Print all emails tagged Organizer/Review Me.

    Intentionally read-only: does NOT call ensure_labels() and will
    never create or modify any Gmail labels or messages.

    Args:
        service: Authenticated Gmail API service object.

    Returns:
        None
    """
    console.print(
        "\n[bold cyan]"
        "Review Me — Emails Flagged Before Delete/Archive"
        "[/bold cyan]\n"
    )

    # Fetch existing labels without creating anything.
    result = gmail_execute(service.users().labels().list(userId="me"))
    rid = next(
        (
            lbl["id"]
            for lbl in result.get("labels", [])
            if lbl["name"] == "Organizer/Review Me"
        ),
        None,
    )

    if not rid:
        console.print(
            "  [yellow]No 'Organizer/Review Me' label found. "
            "Run --categorize first.[/yellow]"
        )
        return

    emails: list = []
    page_token = None

    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Fetching Review Me emails...")
        while True:
            result = gmail_execute(
                service.users().messages().list(
                    userId="me",
                    labelIds=[rid],
                    maxResults=100,
                    pageToken=page_token,
                )
            )
            messages = result.get("messages", [])
            if not messages:
                break
            for stub in messages:
                try:
                    msg = gmail_execute(
                        service.users().messages().get(
                            userId="me",
                            id=stub["id"],
                            format="metadata",
                            metadataHeaders=["Subject", "From"],
                        )
                    )
                    headers = msg.get("payload", {}).get("headers", [])
                    emails.append({
                        "subject": (
                            get_header(headers, "Subject")
                            or "(no subject)"
                        ),
                        "sender": (
                            get_header(headers, "From") or "(unknown)"
                        ),
                        "age_days": age_in_days(
                            int(msg.get("internalDate", "0"))
                        ),
                    })
                except (  # pylint: disable=broad-except
                    HttpError, KeyError, ValueError
                ) as exc:
                    logger.debug(
                        "Skipping review-me stub %s: %s",
                        stub.get("id"), exc,
                    )
            page_token = result.get("nextPageToken")
            if not page_token:
                break

    if not emails:
        console.print(
            "  [green]No Review Me emails — you're all clear.[/green]"
        )
        return

    table = Table(
        title=f"Review Me  ({len(emails)} emails)", show_header=True
    )
    table.add_column("#", justify="right", style="dim", width=4)
    table.add_column("From", min_width=28, max_width=36)
    table.add_column("Subject", min_width=40, max_width=60)
    table.add_column("Age", justify="right", width=6)

    for idx, email in enumerate(emails, 1):
        table.add_row(
            str(idx),
            _trim(email["sender"], 35),
            _trim(email["subject"], 58),
            _age_fmt(email["age_days"]),
        )

    console.print(table)
    console.print(
        f"\n  [bold yellow]{len(emails)} emails await your manual review "
        f"— they will not be auto-deleted.[/bold yellow]"
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_unread(service: Any) -> list:
    """Fetch up to MAX_UNREAD unread messages with metadata.

    Args:
        service: Authenticated Gmail API service object.

    Returns:
        List of dicts with msg_id, subject, sender, age_days,
        and gmail_labels keys.
    """
    emails: list = []
    page_token = None

    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Fetching unread emails...")
        while len(emails) < MAX_UNREAD:
            result = gmail_execute(
                service.users().messages().list(
                    userId="me",
                    q="is:unread",
                    maxResults=min(100, MAX_UNREAD - len(emails)),
                    pageToken=page_token,
                )
            )
            messages = result.get("messages", [])
            if not messages:
                break
            for stub in messages:
                # Guard: stop mid-page if we hit the cap.
                if len(emails) >= MAX_UNREAD:
                    break
                try:
                    msg = gmail_execute(
                        service.users().messages().get(
                            userId="me",
                            id=stub["id"],
                            format="metadata",
                            metadataHeaders=["Subject", "From"],
                        )
                    )
                    headers = msg.get("payload", {}).get("headers", [])
                    emails.append({
                        "msg_id": stub["id"],
                        "subject": (
                            get_header(headers, "Subject")
                            or "(no subject)"
                        ),
                        "sender": (
                            get_header(headers, "From") or "(unknown)"
                        ),
                        "age_days": age_in_days(
                            int(msg.get("internalDate", "0"))
                        ),
                        "gmail_labels": msg.get("labelIds", []),
                    })
                except (  # pylint: disable=broad-except
                    HttpError, KeyError, ValueError
                ) as exc:
                    logger.debug(
                        "Skipping unread stub %s: %s",
                        stub.get("id"), exc,
                    )
            page_token = result.get("nextPageToken")
            if not page_token:
                break

    return emails


def _print_top20(scored: list) -> None:
    """Print the top-20 scored emails as a Rich table.

    Args:
        scored: List of email dicts with a 'score' key, sorted descending.

    Returns:
        None
    """
    top = scored[:20]
    table = Table(
        title="Top 20 Emails to Action Today", show_header=True
    )
    table.add_column("Score", justify="center", width=7)
    table.add_column("From", min_width=28, max_width=36)
    table.add_column("Subject", min_width=40, max_width=58)
    table.add_column("Age", justify="right", width=6)

    for email in top:
        score = email["score"]
        col = "red" if score >= 8 else "yellow" if score >= 5 else "green"
        table.add_row(
            f"[{col}]{score}/10[/{col}]",
            _trim(email["sender"], 35),
            _trim(email["subject"], 57),
            _age_fmt(email["age_days"]),
        )

    console.print(table)
    if len(scored) > 20:
        console.print(
            f"\n  [dim]... and {len(scored) - 20} more unread emails "
            f"not shown.[/dim]"
        )
    console.print()


def _age_fmt(days: float) -> str:
    """Format an age-in-days float into a human-readable string.

    Args:
        days: Age in fractional days.

    Returns:
        Short string such as '3h', '5d', '2w', '3mo', '1.2y'.
    """
    if days < 1:
        return f"{int(days * 24)}h"
    if days < 7:
        return f"{int(days)}d"
    if days < 30:
        return f"{int(days / 7)}w"
    if days < 365:
        return f"{int(days / 30)}mo"
    return f"{days / 365:.1f}y"


def _trim(text: str, max_len: int) -> str:
    """Truncate a string to max_len characters, appending ellipsis if needed.

    Args:
        text: Input string.
        max_len: Maximum allowed character length.

    Returns:
        Original string if short enough, otherwise truncated with '…'.
    """
    return text if len(text) <= max_len else text[:max_len - 1] + "…"
