"""Find digital receipts from the last year and move them to a Receipts label."""

from organizer.labels import ensure_labels, apply_label
from organizer.utils import gmail_execute

# Gmail search queries that catch receipts
RECEIPT_QUERIES = [
    "subject:(receipt OR order confirmation OR purchase confirmation) newer_than:365d",
    "subject:(invoice OR payment confirmation OR transaction) newer_than:365d",
    "subject:(your order OR order shipped) newer_than:365d",
]



def find_and_label_receipts(service, dry_run: bool = False):
    """Find receipts and apply the Receipts label."""
    print("\n🧾 Finding receipts from the last year...")
    label_map = ensure_labels(service)

    seen_ids = set()
    total_labeled = 0

    for query in RECEIPT_QUERIES:
        page_token = None
        while True:
            results = gmail_execute(
                service.users().messages().list(userId="me", q=query, maxResults=100, pageToken=page_token)
            )
            messages = results.get("messages", [])

            for msg_meta in messages:
                if msg_meta["id"] in seen_ids:
                    continue
                seen_ids.add(msg_meta["id"])

                if not dry_run:
                    apply_label(service, msg_meta["id"], "Receipts", label_map)

                total_labeled += 1

            page_token = results.get("nextPageToken")
            if not page_token:
                break

    action = "Would label" if dry_run else "Labeled"
    print(f"  ✅ {action} {total_labeled} emails with 'Receipts' label.")
    if total_labeled > 0:
        print("     These emails are still searchable but won't clog your main inbox view.")
