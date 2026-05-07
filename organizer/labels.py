"""Gmail label creation and management."""

from organizer.utils import gmail_execute

# All custom labels this app uses — personal email focused
APP_LABELS = [
    # Priority tiers
    "Organizer/High Priority",
    "Organizer/Medium Priority",
    "Organizer/Low Priority",
    # Categories
    "Organizer/Finance",
    "Organizer/Shopping",
    "Organizer/Travel",
    "Organizer/Social",
    "Organizer/Food & Delivery",
    "Organizer/Entertainment",
    "Organizer/Health & Fitness",
    "Organizer/Newsletters",
    "Organizer/Promotions",
    "Organizer/Account & Security",
    "Organizer/Personal",
    "Organizer/Other",
    # Special purpose
    "Receipts",
]

# Cache: label name -> label id
_label_cache: dict[str, str] = {}


def ensure_labels(service) -> dict[str, str]:
    """Create all app labels if they don't exist. Returns name->id map."""
    global _label_cache
    if _label_cache:
        return _label_cache

    existing = gmail_execute(service.users().labels().list(userId="me"))
    existing_map = {lbl["name"]: lbl["id"] for lbl in existing.get("labels", [])}

    for label_name in APP_LABELS:
        if label_name in existing_map:
            _label_cache[label_name] = existing_map[label_name]
        else:
            body = {
                "name": label_name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            }
            result = gmail_execute(service.users().labels().create(userId="me", body=body))
            _label_cache[label_name] = result["id"]
            print(f"  Created label: {label_name}")

    return _label_cache


def apply_label(service, msg_id: str, label_name: str, label_map: dict[str, str]):
    """Apply a single label to a message."""
    apply_labels(service, msg_id, [label_name], label_map)


def apply_labels(service, msg_id: str, label_names: list[str], label_map: dict[str, str]):
    """Apply multiple labels to a message in a single API call."""
    ids = [label_map[n] for n in label_names if n in label_map]
    if not ids:
        return
    gmail_execute(service.users().messages().modify(
        userId="me",
        id=msg_id,
        body={"addLabelIds": ids},
    ))


def archive_message(service, msg_id: str):
    """Remove from inbox (archive) without deleting."""
    gmail_execute(service.users().messages().modify(
        userId="me",
        id=msg_id,
        body={"removeLabelIds": ["INBOX"]},
    ))
