"""Gmail label management — Organizer/* hierarchy."""

from organizer.utils import gmail_execute

LABEL_SPECS = {
    "Organizer/Important":  {"bg": "#fb4c2f", "text": "#ffffff"},
    "Organizer/Personal":   {"bg": "#fbd75b", "text": "#000000"},
    "Organizer/Receipts":   {"bg": "#7bd148", "text": "#000000"},
    "Organizer/Promotions": {"bg": "#b99aff", "text": "#ffffff"},
    "Organizer/Junk":       {"bg": "#c2c2c2", "text": "#000000"},
    "Organizer/Saved":      {"bg": "#4986e7", "text": "#ffffff"},
    "Organizer/Review Me":  {"bg": "#ffad47", "text": "#ffffff"},
}

_cache: dict = {}


def ensure_labels(service) -> dict:
    """Create missing labels and return {name: id} map."""
    global _cache
    if _cache:
        return _cache

    existing = _fetch_existing(service)

    if "Organizer" not in existing:
        lbl = _create_label(service, "Organizer")
        existing["Organizer"] = lbl["id"]

    label_map = {"Organizer": existing["Organizer"]}

    for name, colors in LABEL_SPECS.items():
        if name not in existing:
            lbl = _create_label(service, name, colors)
            existing[name] = lbl["id"]
        label_map[name] = existing[name]

    _cache = label_map
    return label_map


def apply_label(service, msg_id: str, label_name: str, label_map: dict):
    lid = label_map.get(label_name)
    if lid:
        gmail_execute(
            service.users().messages().modify(
                userId="me", id=msg_id, body={"addLabelIds": [lid]}
            )
        )


def remove_from_inbox(service, msg_id: str):
    gmail_execute(
        service.users().messages().modify(
            userId="me", id=msg_id, body={"removeLabelIds": ["INBOX"]}
        )
    )


def trash_message(service, msg_id: str):
    gmail_execute(service.users().messages().trash(userId="me", id=msg_id))


def _fetch_existing(service) -> dict:
    results = gmail_execute(service.users().labels().list(userId="me"))
    return {l["name"]: l["id"] for l in results.get("labels", [])}


def _create_label(service, name: str, colors: dict = None) -> dict:
    body = {
        "name": name,
        "labelListVisibility": "labelShow",
        "messageListVisibility": "show",
    }
    if colors:
        body["color"] = {
            "backgroundColor": colors["bg"],
            "textColor": colors["text"],
        }
    return gmail_execute(service.users().labels().create(userId="me", body=body))
