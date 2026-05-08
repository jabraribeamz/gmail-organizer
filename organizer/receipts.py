"""Find and label digital receipts from the last year."""

from organizer.labels import ensure_labels, apply_label
from organizer.utils import gmail_execute
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

RECEIPT_QUERIES = [
    'subject:(receipt OR "order confirmation" OR "purchase confirmation") newer_than:400d',
    'subject:(invoice OR "payment confirmation" OR "transaction receipt") newer_than:400d',
    'subject:("your order" OR "order shipped" OR "has shipped") newer_than:400d',
    'subject:("order #" OR "order number" OR "tracking number") newer_than:400d',
]


def find_and_label_receipts(service, dry_run: bool = False):
    """Find receipts across common query patterns and apply Organizer/Receipts."""
    console.print("\n[bold]Receipt Finder[/bold]")
    if dry_run:
        console.print("  [yellow]DRY RUN — no changes[/yellow]")

    label_map = ensure_labels(service)
    seen: set = set()
    total = 0

    with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                  console=console, transient=True) as p:
        for i, query in enumerate(RECEIPT_QUERIES, 1):
            p.add_task(f"Query {i}/{len(RECEIPT_QUERIES)}: {query[:50]}...")
            page_token = None

            while True:
                result = gmail_execute(
                    service.users().messages().list(
                        userId="me", q=query, maxResults=100, pageToken=page_token,
                    )
                )
                for stub in result.get("messages", []):
                    if stub["id"] in seen:
                        continue
                    seen.add(stub["id"])
                    total += 1
                    if not dry_run:
                        apply_label(service, stub["id"], "Organizer/Receipts", label_map)

                page_token = result.get("nextPageToken")
                if not page_token:
                    break

    action = "Would label" if dry_run else "Labeled"
    console.print(f"  [green]{action} {total:,} receipt emails.[/green]")
