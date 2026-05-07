"""Inbox triage: AI-powered email scoring, categorization, and archiving.

Uses the Anthropic Claude API to intelligently classify each email by
priority (high/medium/low) and category, then applies Gmail labels
and archives low-priority messages.
"""

from organizer.labels import ensure_labels, apply_label, archive_message
from organizer.ai import classify_batch
from rich.console import Console
from rich.table import Table

console = Console()


def _get_header(headers: list, name: str) -> str:
    """Extract a header value by name."""
    for h in headers:
        if h["name"].lower() == name.lower():
            return h.get("value", "")
    return ""


def triage_inbox(service, max_results: int = 100, auto_archive_low: bool = True):
    """AI-powered inbox triage: classify, label, and archive."""
    console.print("\n[bold]📬 AI-Powered Inbox Triage[/bold]")
    label_map = ensure_labels(service)

    # Fetch inbox messages
    results = (
        service.users()
        .messages()
        .list(userId="me", labelIds=["INBOX"], maxResults=max_results)
        .execute()
    )
    messages = results.get("messages", [])

    if not messages:
        console.print("  Inbox is empty. Nothing to triage.")
        return

    console.print(f"  Fetching {len(messages)} emails...")

    # Collect email metadata
    emails = []
    for msg_meta in messages:
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=msg_meta["id"], format="metadata",
                 metadataHeaders=["Subject", "From"])
            .execute()
        )
        headers = msg.get("payload", {}).get("headers", [])
        emails.append({
            "msg_id": msg_meta["id"],
            "subject": _get_header(headers, "Subject"),
            "sender": _get_header(headers, "From"),
            "snippet": msg.get("snippet", ""),
        })

    # Classify with AI in batches
    console.print("  🤖 Classifying with Claude AI...")
    classified = classify_batch(emails, batch_size=10)

    # Apply labels and archive
    stats = {"high": 0, "medium": 0, "low": 0}
    category_counts = {}
    archived = 0

    for email in classified:
        priority = email.get("priority", "medium")
        category = email.get("category", "Other")
        action = email.get("action", "keep")

        # Apply priority label
        priority_label = f"Organizer/{priority.title()} Priority"
        apply_label(service, email["msg_id"], priority_label, label_map)
        stats[priority] = stats.get(priority, 0) + 1

        # Apply category label
        category_label = f"Organizer/{category}"
        if category_label in label_map:
            apply_label(service, email["msg_id"], category_label, label_map)
        category_counts[category] = category_counts.get(category, 0) + 1

        # Archive low priority
        if action == "archive" and auto_archive_low:
            archive_message(service, email["msg_id"])
            archived += 1

    # Print results summary
    console.print(f"\n  [green]✅ Triaged {len(messages)} emails:[/green]")
    console.print(f"     🔴 High:   {stats.get('high', 0)}")
    console.print(f"     🟡 Medium: {stats.get('medium', 0)}")
    console.print(f"     🟢 Low:    {stats.get('low', 0)}")
    if auto_archive_low:
        console.print(f"     📦 Archived: {archived}")

    # Category breakdown
    console.print(f"\n  [bold]Categories:[/bold]")
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        console.print(f"     {cat}: {count}")

    # Show detailed table for high priority
    high_priority = [e for e in classified if e.get("priority") == "high"]
    if high_priority:
        console.print(f"\n  [bold red]⚡ High Priority — Needs Attention:[/bold red]")
        table = Table(show_header=True, header_style="bold")
        table.add_column("From", style="cyan", max_width=25)
        table.add_column("Subject", max_width=45)
        table.add_column("Category", style="magenta", max_width=15)
        table.add_column("Why", style="dim", max_width=35)

        for email in high_priority[:15]:
            sender_short = email["sender"].split("<")[0].strip()[:25]
            table.add_row(
                sender_short,
                email["subject"][:45],
                email.get("category", ""),
                email.get("reason", "")[:35],
            )
        console.print(table)
