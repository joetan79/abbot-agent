"""Agent self-monitoring: real-time error alerts + weekly log analysis."""

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# Cooldown: same error type won't alert more than once per 15 minutes
_COOLDOWN_SECONDS = 900
_last_alert: dict[str, float] = {}

LOG_FILE = Path("bot.log")


def _should_alert(error_type: str) -> bool:
    now = time.time()
    if now - _last_alert.get(error_type, 0) > _COOLDOWN_SECONDS:
        _last_alert[error_type] = now
        return True
    return False


async def notify_error(bot, error_type: str, message: str):
    """Send a rate-limited error alert to the owner via Telegram."""
    if not _should_alert(error_type):
        return
    from modules.utils import OWNER_CHAT_ID
    if not OWNER_CHAT_ID:
        return
    try:
        now_str = datetime.now().strftime("%H:%M")
        text = f"⚠️ ABbot Alert [{now_str}]\n\n{message}"
        await bot.send_message(chat_id=OWNER_CHAT_ID, text=text)
        logger.info(f"[Health] Alert sent: {error_type}")
    except Exception as e:
        logger.error(f"[Health] Failed to send alert: {e}")


def _read_recent_errors(days: int = 7, max_lines: int = 150) -> str:
    """Read ERROR lines from bot.log for the past N days."""
    if not LOG_FILE.exists():
        return "Log file not found."

    cutoff = datetime.now() - timedelta(days=days)
    cutoff_str = cutoff.strftime("%Y-%m-%d")

    errors = []
    seen = set()  # deduplicate identical messages

    try:
        with open(LOG_FILE, "r", errors="replace") as f:
            for line in f:
                if " | ERROR | " not in line:
                    continue
                # Only lines within the date range
                if line[:10] < cutoff_str:
                    continue
                # Strip timestamp prefix for dedup, keep message core
                core = line[32:].strip() if len(line) > 32 else line.strip()
                if core not in seen:
                    seen.add(core)
                    errors.append(line.strip())
                if len(errors) >= max_lines:
                    break
    except Exception as e:
        return f"Could not read log: {e}"

    if not errors:
        return "No errors in the past week."

    return "\n".join(errors)


async def run_api_fail_check(bot):
    """Every 10 min: check API failure counters and alert if threshold exceeded."""
    from modules.utils import get_and_reset_api_fails
    counts = get_and_reset_api_fails()
    if not counts:
        return

    # Only alert if any single error type hit 3+ failures in the window
    serious = {k: v for k, v in counts.items() if v >= 3}
    if not serious:
        return

    lines = [f"  • {k}: {v} times" for k, v in serious.items()]
    message = (
        "Anthropic API is having issues (last 10 min):\n"
        + "\n".join(lines)
        + "\n\nBot will auto-retry with Sonnet when possible."
    )
    await notify_error(bot, "api_fail_burst", message)


async def run_weekly_analysis(bot):
    """Weekly job: analyse recent errors with Claude Haiku and report to owner."""
    from modules.utils import OWNER_CHAT_ID, ask_claude, MODEL_FAST
    if not OWNER_CHAT_ID:
        return

    logger.info("[Health] Running weekly log analysis")
    error_text = _read_recent_errors(days=7, max_lines=150)

    if error_text == "No errors in the past week.":
        try:
            await bot.send_message(
                chat_id=OWNER_CHAT_ID,
                text="✅ Weekly Health Check\n\nNo errors in the past 7 days. All good!"
            )
        except Exception:
            pass
        return

    prompt = (
        "You are analysing error logs for ABbot, a Telegram assistant bot.\n\n"
        "Here are the unique errors from the past 7 days:\n\n"
        f"{error_text}\n\n"
        "Please:\n"
        "1. Summarise the main error patterns (group similar ones)\n"
        "2. Identify which are most frequent or serious\n"
        "3. Give 2-3 concrete improvement suggestions\n\n"
        "Keep the response concise — under 300 words. Use plain text, no markdown."
    )

    try:
        analysis = ask_claude(
            "You are a helpful bot health analyst. Be concise and practical.",
            prompt,
            max_tokens=500,
            model=MODEL_FAST,
        )
        now_str = datetime.now().strftime("%Y-%m-%d")
        report = f"📊 Weekly Health Report ({now_str})\n\n{analysis}"
        await bot.send_message(chat_id=OWNER_CHAT_ID, text=report)
        logger.info("[Health] Weekly analysis sent")
    except Exception as e:
        logger.error(f"[Health] Weekly analysis failed: {e}")
