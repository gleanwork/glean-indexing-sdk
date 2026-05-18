"""Webex URL helpers."""

import base64

WEBEX_WEB_BASE_URL = "https://web.webex.com"


def short_id(webex_id: str) -> str:
    """Extract the short UUID from a Webex base64 ID when possible."""
    if not webex_id:
        return webex_id
    try:
        padded = webex_id + "=" * ((4 - len(webex_id) % 4) % 4)
        decoded = base64.b64decode(padded).decode("utf-8")
        return decoded.rsplit("/", 1)[-1] if "/" in decoded else webex_id
    except Exception:
        return webex_id


def room_view_url(room_id: str) -> str:
    """Return a browser URL for a Webex room."""
    return f"{WEBEX_WEB_BASE_URL}/spaces/{room_id}"


def room_app_url(room_id: str) -> str:
    """Return a native Webex app URL for a room."""
    return f"webexteams://im?space={short_id(room_id)}"


def message_view_url(room_id: str, message_id: str) -> str:
    """Return a browser URL for a Webex message."""
    return f"{WEBEX_WEB_BASE_URL}/spaces/{room_id}/messages/{message_id}"


def message_app_url(room_id: str, message_id: str) -> str:
    """Return a native Webex app URL for a message."""
    return f"webexteams://im?space={short_id(room_id)}&message={short_id(message_id)}"
