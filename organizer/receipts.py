"""Find and label digital receipts from the last year."""

import logging
from typing import Any

from googleapiclient.errors import HttpError
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from organizer.labels import apply_label, ensure_labels
from organizer.utils import gmail_execute

logger = logging.getLogger(__name__)
console = Console()

RECEIPT_QUERIES = [
    (
        "subject:(receipt OR \"order confirmation\" OR "
        "\"purchase confirmation\") newer_than:400d"
    ),
    (
        "subject:(invoice OR \"payment confirmation\" OR "
        "\"transaction receipt\") newer_than:400d"
    ),
    (
        "subject:(\"your order\" OR \"order shipped\" OR "
        "\"has shipped\") newer_than:400d"
    ),
    (
        "subject:(\"order #\" OR \"order number\" OR "
        "\"tracking number\") newer_than:400d"
    ),
]


def find_and_label_receipts(
    service: Any, dry_run: bool = False
) -> None:
    """Find receipts across common query patterns and label them.

    Applies the Organizer/Receipts label to all matching emails.

    Args:
        service: Authenticated Gmail API service object.
        dry_run: If True, count matches but do not apply any labels.

    Returns:
        None
    """
    console.print("\n[bold]Receipt Finder[/bold]")
    if dry_run:
        console.print("  [yellow]DRY RUN — no changes[/yellow]")

    label_map = ensure_labels(service)
    seen: set = set()
    total = 0
    errors = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        for idx, query in enumerate(RECEIPT_QUERIES, 1):
            progress.add_task(
                f"Query {idx}/{len(RECEIPT_QUERIES)}: "
                f"{query[:50]}..."
            )
            page_token = None

            while True:
                try:
                    result = gmail_execute(
                        service.users().messages().list(
                            userId="me",
                            q=query,
                            maxResults=100,
                            pageToken=page_token,
                        )
                    )
                except HttpError as exc:
                    logger.debug(
                        "Receipt query %d failed: %s", idx, exc
                    )
                    errors += 1
                    break  # skip this query on persistent API failure

                for stub in result.get("messages", []):
                    if stub["id"] in seen:
                        continue
                    seen.add(stub["id"])
                    total += 1
                    if not dry_run:
                        try:
                            apply_label(
                                service,
                                stub["id"],
                                "Organizer/Receipts",
                                label_map,
                            )
                        except HttpError as exc:
                            logger.debug(
                                "Label apply failed for %s: %s",
                                stub["id"], exc,
                            )
                            errors += 1

                page_token = result.get("nextPageToken")
                if not page_token:
                    break

    action = "Would label" if dry_run else "Labeled"
    console.print(
        f"  [green]{action} {total:,} receipt emails.[/green]"
    )
    if errors:
        console.print(
            f"  [red]API errors skipped: {errors}[/red]"
        )
