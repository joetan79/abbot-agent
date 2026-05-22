"""Per-chat conversation thread buffer for group context awareness."""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

_CONTEXT_FILE = Path("data/group_context.json")
_MAX_MESSAGES = 15       # max messages kept per chat
_EXPIRY_MINUTES = 30     # conversation "resets" after 30 min of silence


def _load() -> dict:
    try:
        return json.loads(_CONTEXT_FILE.read_text()) if _CONTEXT_FILE.exists() else {}
    except Exception:
        return {}


def _save(data: dict):
    _CONTEXT_FILE.write_text(json.dumps(data, ensure_ascii=False))


def record_message(chat_id: int, sender_name: str, text: str):
    """Add any group message to the conversation buffer."""
    data = _load()
    key = str(chat_id)
    if key not in data:
        data[key] = []

    data[key].append({
        "sender": sender_name,
        "text": text[:200],
        "ts": datetime.now().isoformat(),
    })

    # Drop messages older than expiry window, then keep last N
    cutoff = (datetime.now() - timedelta(minutes=_EXPIRY_MINUTES)).isoformat()
    data[key] = [m for m in data[key] if m["ts"] >= cutoff][-_MAX_MESSAGES:]
    _save(data)


def get_context_str(chat_id: int, exclude_sender: str = None) -> str:
    """Return recent group conversation as a formatted string for the system prompt.

    exclude_sender: skip the very last message if it's from this sender
    (avoids echoing the current message back into its own context).
    """
    data = _load()
    messages = data.get(str(chat_id), [])
    if not messages:
        return ""

    cutoff = (datetime.now() - timedelta(minutes=_EXPIRY_MINUTES)).isoformat()
    recent = [m for m in messages if m["ts"] >= cutoff]

    # Drop the last entry if it's the current sender's message (just recorded)
    if exclude_sender and recent and recent[-1]["sender"] == exclude_sender:
        recent = recent[:-1]

    if not recent:
        return ""

    lines = [f"{m['sender']}: {m['text']}" for m in recent]
    return "Recent group conversation:\n" + "\n".join(lines)
