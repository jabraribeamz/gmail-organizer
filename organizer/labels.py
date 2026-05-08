"""Gmail label management — Organizer/* hierarchy."""

import logging
from typing import Any, Optional

from googleapiclient.errors import HttpError

from organizer.utils import gmail_execute

logger = logging.getLogger(__name__)

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


def ensure_labels(service: Any) -> dict:
    """Create missing labels and return {name: id} map.

    Idempotent: safe to call multiple times. Handles 409 Conflict if a
    label was created by a concurrent process between list and create.

    Args:
        service: Authenticated Gmail API service object.

    Returns:
        Dict mapping label name strings to their Gmail label ID strings.
    """
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

    # Update in-place so callers holding a reference see the new data,
    # and we avoid a global rebinding (no `global _cache` needed).
    _cache.update(label_map)
    return _cache


def apply_label(
    service: Any, msg_id: str, label_name: str, label_map: dict
) -> None:
    """Apply a single Organizer label to a Gmail message.

    Args:
        service: Authenticated Gmail API service object.
        msg_id: Gmail message ID string.
        label_name: Full label name, e.g. ``"Organizer/Important"``.
        label_map: Dict mapping label names to Gmail label IDs.
    """
    lid = label_map.get(label_name)
    if lid:
        gmail_execute(
            service.users().messages().modify(
                userId="me", id=msg_id, body={"addLabelIds": [lid]}
            )
        )


def remove_from_inbox(service: Any, msg_id: str) -> None:
    """Archive a message by removing it from the INBOX label.

    Args:
        service: Authenticated Gmail API service object.
        msg_id: Gmail message ID string.
    """
    gmail_execute(
        service.users().messages().modify(
            userId="me",
            id=msg_id,
            body={"removeLabelIds": ["INBOX"]},
        )
    )


def trash_message(service: Any, msg_id: str) -> None:
    """Move a message to Gmail Trash.

    Args:
        service: Authenticated Gmail API service object.
        msg_id: Gmail message ID string.
    """
    gmail_execute(
        service.users().messages().trash(userId="me", id=msg_id)
    )


def _fetch_existing(service: Any) -> dict:
    """Fetch all existing Gmail labels and return a name→id mapping.

    Args:
        service: Authenticated Gmail API service object.

    Returns:
        Dict mapping label name strings to their Gmail label ID strings.
    """
    results = gmail_execute(service.users().labels().list(userId="me"))
    return {
        label["name"]: label["id"]
        for label in results.get("labels", [])
    }


def _create_label(
    service: Any, name: str, colors: Optional[dict] = None
) -> dict:
    """Create a label. Falls back to no color on 400 (invalid color).

    Handles 409 Conflict by re-fetching the already-existing label.

    Args:
        service: Authenticated Gmail API service object.
        name: Label name string to create.
        colors: Optional dict with ``bg`` and ``text`` hex color keys.

    Returns:
        Dict with at minimum an ``"id"`` key for the created label.

    Raises:
        HttpError: On unexpected API errors.
    """
    body: dict = {
        "name": name,
        "labelListVisibility": "labelShow",
        "messageListVisibility": "show",
    }
    if colors:
        body["color"] = {
            "backgroundColor": colors["bg"],
            "textColor": colors["text"],
        }

    try:
        return gmail_execute(
            service.users().labels().create(userId="me", body=body)
        )
    except HttpError as exc:
        if exc.resp.status == 400 and colors:
            # Gmail rejected the color hex; retry without color.
            body.pop("color", None)
            return gmail_execute(
                service.users().labels().create(userId="me", body=body)
            )
        if exc.resp.status == 409:
            # Label created by a concurrent process between list/create.
            existing = _fetch_existing(service)
            if name in existing:
                return {"id": existing[name]}
        raise
