"""Triage scoring and Review Me listing.

--triage  Scores every unread email 1–10, prints top 20.
--review  Lists all emails tagged Organizer/Review Me.
"""

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from organizer.labels import ensure_labels
from organizer.rules import score_priority
from organizer.utils import get_header, gmail_execute, extract_email, age_in_days, build_sent_cache

console = Console()

MAX_UNREAD = 2000


def triage_inbox(service, dry_run: bool = False):
    """Score all unread emails 1–10, print top 20 ranked by priority."""
    console.print("\n[bold cyan]Gmail Triage — Priority Scorer[/bold cyan]")
    if dry_run:
        console.print("  [yellow]DRY RUN — read only[/yellow]\n")

    console.print("  Building sent-mail cache...", end="")
    sent_cache = build_sent_cache(service)
    console.print(f" {len(sent_cache):,} recipients.\n")

    emails = _fetch_unread(service)
    console.print(f"  Scoring {len(emails):,} unread emails...", end="")

    scored = []
    for e in emails:
        s = score_priority(
            subject=e["subject"],
            sender=e["sender"],
            is_unread=True,
            age_days=e["age_days"],
            replied_to=extract_email(e["sender"]).lower() in sent_cache,
            gmail_labels=e["gmail_labels"],
        )
        scored.append({**e, "score": s})

    scored.sort(key=lambda x: -x["score"])
    console.print(" done.\n")
    _print_top20(scored)


def list_review_me(service):
    """Print all emails tagged Organizer/Review Me."""
    console.print("\n[bold cyan]Review Me — Emails Flagged Before Delete/Archive[/bold cyan]\n")

    label_map = ensure_labels(service)
    rid = label_map.get("Organizer/Review Me")
    if not rid:
        console.print("  [yellow]No 'Organizer/Review Me' label found. Run --categorize first.[/yellow]")
        return

    emails = []
    page_token = None

    with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                  console=console, transient=True) as p:
        p.add_task("Fetching Review Me emails...")
        while True:
            result = gmail_execute(
                service.users().messages().list(
                    userId="me", labelIds=[rid], maxResults=100, pageToken=page_token,
                )
            )
            messages = result.get("messages", [])
            if not messages:
                break
            for stub in messages:
                try:
                    msg = gmail_execute(
                        service.users().messages().get(
                            userId="me", id=stub["id"], format="metadata",
                            metadataHeaders=["Subject", "From"],
                        )
                    )
                    headers = msg.get("payload", {}).get("headers", [])
                    emails.append({
                        "subject": get_header(headers, "Subject") or "(no subject)",
                        "sender":  get_header(headers, "From")    or "(unknown)",
                        "age_days": age_in_days(int(msg.get("internalDate", "0"))),
                    })
                except Exception:
                    pass
            page_token = result.get("nextPageToken")
            if not page_token:
                break

    if not emails:
        console.print("  [green]No Review Me emails — you're all clear.[/green]")
        return

    table = Table(title=f"Review Me  ({len(emails)} emails)", show_header=True)
    table.add_column("#",       justify="right", style="dim", width=4)
    table.add_column("From",    min_width=28, max_width=36)
    table.add_column("Subject", min_width=40, max_width=60)
    table.add_column("Age",     justify="right", width=6)

    for i, e in enumerate(emails, 1):
        table.add_row(str(i), _trim(e["sender"], 35), _trim(e["subject"], 58),
                      _age_fmt(e["age_days"]))

    console.print(table)
    console.print(
        f"\n  [bold yellow]{len(emails)} emails await your manual review "
        f"— they will not be auto-deleted.[/bold yellow]"
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_unread(service) -> list:
    emails = []
    page_token = None

    with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                  console=console, transient=True) as p:
        p.add_task("Fetching unread emails...")
        while len(emails) < MAX_UNREAD:
            result = gmail_execute(
                service.users().messages().list(
                    userId="me", q="is:unread",
                    maxResults=min(100, MAX_UNREAD - len(emails)),
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
                            userId="me", id=stub["id"], format="metadata",
                            metadataHeaders=["Subject", "From"],
                        )
                    )
                    headers = msg.get("payload", {}).get("headers", [])
                    emails.append({
                        "msg_id":      stub["id"],
                        "subject":     get_header(headers, "Subject") or "(no subject)",
                        "sender":      get_header(headers, "From")    or "(unknown)",
                        "age_days":    age_in_days(int(msg.get("internalDate", "0"))),
                        "gmail_labels": msg.get("labelIds", []),
                    })
                except Exception:
                    pass
            page_token = result.get("nextPageToken")
            if not page_token:
                break

    return emails


def _print_top20(scored: list):
    top = scored[:20]
    table = Table(title="Top 20 Emails to Action Today", show_header=True)
    table.add_column("Score", justify="center", width=7)
    table.add_column("From",    min_width=28, max_width=36)
    table.add_column("Subject", min_width=40, max_width=58)
    table.add_column("Age",     justify="right", width=6)

    for e in top:
        s = e["score"]
        col = "red" if s >= 8 else "yellow" if s >= 5 else "green"
        table.add_row(
            f"[{col}]{s}/10[/{col}]",
            _trim(e["sender"],  35),
            _trim(e["subject"], 57),
            _age_fmt(e["age_days"]),
        )

    console.print(table)
    if len(scored) > 20:
        console.print(f"\n  [dim]... and {len(scored) - 20} more unread emails not shown.[/dim]")
    console.print()


def _age_fmt(d: float) -> str:
    if d < 1:
        return f"{int(d * 24)}h"
    if d < 7:
        return f"{int(d)}d"
    if d < 30:
        return f"{int(d / 7)}w"
    if d < 365:
        return f"{int(d / 30)}mo"
    return f"{d / 365:.1f}y"


def _trim(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n - 1] + "…"
