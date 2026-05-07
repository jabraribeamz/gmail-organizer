"""Gmail label creation and management."""

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

    existing = service.users().labels().list(userId="me").execute()
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
            result = service.users().labels().create(userId="me", body=body).execute()
            _label_cache[label_name] = result["id"]
            print(f"  Created label: {label_name}")

    return _label_cache


def apply_label(service, msg_id: str, label_name: str, label_map: dict[str, str]):
    """Apply a label to a message."""
    label_id = label_map.get(label_name)
    if not label_id:
        return
    service.users().messages().modify(
        userId="me",
        id=msg_id,
        body={"addLabelIds": [label_id]},
    ).execute()


def archive_message(service, msg_id: str):
    """Remove from inbox (archive) without deleting."""
    service.users().messages().modify(
        userId="me",
        id=msg_id,
        body={"removeLabelIds": ["INBOX"]},
    ).execute()
