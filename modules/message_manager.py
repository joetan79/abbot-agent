"""
Message deletion management for ABbot.
Handles immediate deletion, scheduled deletion, and message tracking.

Telegram API limits:
- Messages can only be deleted if sent less than 48 hours ago.
- Bot can delete its own messages + incoming messages in private chats.
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
DELETIONS_FILE = DATA_DIR / "message_deletions.json"
MESSAGE_LOG_FILE = DATA_DIR / "bot_messages.json"

MAX_DELETE_AGE_HOURS = 47  # Leave 1hr safety margin under Telegram's 48hr limit
MESSAGE_LOG_LIMIT = 100    # per chat_id, rolling


def _load_json(path, default):
    try:
        if path.exists():
            with open(path) as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {path}: {e}")
    return default


def _save_json(path, data):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Error saving {path}: {e}")


# --- Bot message tracking (for "delete last N" feature) ---

def track_bot_message(chat_id: int, message_id: int):
    """Track outgoing bot messages per chat. Rolling window of MESSAGE_LOG_LIMIT."""
    data = _load_json(MESSAGE_LOG_FILE, {})
    key = str(chat_id)
    entries = data.get(key, [])
    entries.append({
        "message_id": message_id,
        "sent_at": datetime.now().isoformat(),
    })
    entries = entries[-MESSAGE_LOG_LIMIT:]
    data[key] = entries
    _save_json(MESSAGE_LOG_FILE, data)


def get_recent_bot_messages(chat_id: int, n: int) -> list:
    """Return up to n most recent bot message IDs for a chat, newest first.
    Filters out messages older than 47 hours (cannot delete)."""
    data = _load_json(MESSAGE_LOG_FILE, {})
    entries = data.get(str(chat_id), [])
    cutoff = datetime.now() - timedelta(hours=MAX_DELETE_AGE_HOURS)
    eligible = []
    for e in reversed(entries):
        try:
            sent_at = datetime.fromisoformat(e["sent_at"])
            if sent_at >= cutoff:
                eligible.append(e)
        except Exception:
            continue
        if len(eligible) >= n:
            break
    return eligible


def forget_bot_message(chat_id: int, message_id: int):
    """Remove a message from the tracking log after it's been deleted."""
    data = _load_json(MESSAGE_LOG_FILE, {})
    key = str(chat_id)
    if key in data:
        data[key] = [e for e in data[key] if e["message_id"] != message_id]
        _save_json(MESSAGE_LOG_FILE, data)


# --- Scheduled deletion storage ---

def save_scheduled_deletion(deletion_id: str, chat_id: int, message_id: int,
                             fire_at: datetime, note: str = ""):
    data = _load_json(DELETIONS_FILE, {})
    data[deletion_id] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "fire_at": fire_at.isoformat(),
        "note": note,
        "created_at": datetime.now().isoformat(),
    }
    _save_json(DELETIONS_FILE, data)


def get_scheduled_deletion(deletion_id: str):
    data = _load_json(DELETIONS_FILE, {})
    return data.get(deletion_id)


def remove_scheduled_deletion(deletion_id: str):
    data = _load_json(DELETIONS_FILE, {})
    if deletion_id in data:
        del data[deletion_id]
        _save_json(DELETIONS_FILE, data)


def get_all_scheduled_deletions():
    return _load_json(DELETIONS_FILE, {})


# --- Direct delete with error handling ---

async def delete_message_safe(bot, chat_id: int, message_id: int) -> tuple:
    """Attempt to delete a message. Returns (success, error_message)."""
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        forget_bot_message(chat_id, message_id)
        return True, ""
    except Exception as e:
        err = str(e)
        if "message to delete not found" in err.lower():
            forget_bot_message(chat_id, message_id)
            return False, "already_gone"
        if "message can't be deleted" in err.lower() or "too old" in err.lower():
            return False, "too_old"
        logger.error(f"Delete failed chat={chat_id} msg={message_id}: {e}")
        return False, err
