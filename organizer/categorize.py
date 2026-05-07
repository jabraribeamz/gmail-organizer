"""Auto-categorize emails using AI — standalone mode.

Use --triage for combined priority + category (recommended).
Use --categorize to ONLY apply category labels without priority scoring.
"""

from organizer.labels import ensure_labels, apply_label
from organizer.ai import classify_batch
from rich.console import Console

console = Console()


def _get_header(headers: list, name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h.get("value", "")
    return ""


def categorize_inbox(service, max_results: int = 200):
    """Categorize inbox messages using AI (category labels only, no priority)."""
    console.print("\n[bold]🏷️  AI Categorization[/bold]")
    label_map = ensure_labels(service)

    results = (
        service.users()
        .messages()
        .list(userId="me", labelIds=["INBOX"], maxResults=max_results)
        .execute()
    )
    messages = results.get("messages", [])

    if not messages:
        console.print("  Inbox is empty.")
        return

    console.print(f"  Fetching {len(messages)} emails...")

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

    console.print("  🤖 Categorizing with Claude AI...")
    classified = classify_batch(emails, batch_size=10)

    category_counts = {}
    for email in classified:
        category = email.get("category", "Other")
        category_label = f"Organizer/{category}"
        if category_label in label_map:
            apply_label(service, email["msg_id"], category_label, label_map)
            category_counts[category] = category_counts.get(category, 0) + 1

    console.print(f"\n  [green]✅ Categorized {sum(category_counts.values())} of {len(messages)} emails:[/green]")
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        console.print(f"     {cat}: {count}")
