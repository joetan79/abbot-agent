"""
Dynamic one-time reminders for ABbot.
Handles any activity time window reminders.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
REMINDERS_FILE = DATA_DIR / "reminders.json"
DATA_DIR.mkdir(exist_ok=True)


def save_reminder(
        reminder_id: str,
        chat_id: int,
        message: str,
        fire_at: datetime,
        reminder_type: str = "general",
        auto_delete: bool = True) -> bool:
    try:
        reminders = _load_reminders()
        reminders[reminder_id] = {
            "chat_id": chat_id,
            "message": message,
            "fire_at": fire_at.isoformat(),
            "type": reminder_type,
            "auto_delete": auto_delete,
            "created_at": datetime.now(
                timezone.utc).isoformat(),
            "fired": False,
        }
        _save_reminders(reminders)
        logger.info(
            f"Reminder saved: {reminder_id} "
            f"fires at "
            f"{fire_at.strftime('%d %b %H:%M UTC')}"
        )
        return True
    except Exception as e:
        logger.error(f"Save reminder error: {e}")
        return False


def delete_reminder(reminder_id: str) -> bool:
    try:
        reminders = _load_reminders()
        if reminder_id in reminders:
            del reminders[reminder_id]
            _save_reminders(reminders)
            logger.info(
                f"Reminder deleted: {reminder_id}")
            return True
        return False
    except Exception as e:
        logger.error(
            f"Delete reminder error: {e}")
        return False


def get_all_reminders() -> dict:
    return _load_reminders()


def get_reminders_by_type(
        reminder_type: str) -> dict:
    all_r = _load_reminders()
    return {
        k: v for k, v in all_r.items()
        if v.get("type") == reminder_type
        and not v.get("fired", False)
    }


def delete_reminders_by_type(
        reminder_type: str) -> int:
    reminders = _load_reminders()
    to_delete = [
        k for k, v in reminders.items()
        if v.get("type") == reminder_type
    ]
    for k in to_delete:
        del reminders[k]
    if to_delete:
        _save_reminders(reminders)
    logger.info(
        f"Deleted {len(to_delete)} "
        f"{reminder_type} reminders"
    )
    return len(to_delete)


def _load_reminders() -> dict:
    try:
        if REMINDERS_FILE.exists():
            return json.loads(
                REMINDERS_FILE.read_text())
        return {}
    except Exception:
        return {}


def _save_reminders(data: dict):
    REMINDERS_FILE.write_text(
        json.dumps(data, indent=2,
                   ensure_ascii=False))
