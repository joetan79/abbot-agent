"""Cross-chat insights: log family member interactions, send daily digest to Joe."""

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_INSIGHTS_FILE = Path("data/insights.json")


def _load() -> list:
    try:
        return json.loads(_INSIGHTS_FILE.read_text()) if _INSIGHTS_FILE.exists() else []
    except Exception:
        return []


def _save(data: list):
    _INSIGHTS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def log_interaction(member_name: str, question: str, bot_reply: str):
    """Store a non-owner member interaction for the evening digest."""
    insights = _load()
    insights.append({
        "member": member_name,
        "question": question[:250],
        "reply": bot_reply[:300],
        "ts": datetime.now().isoformat(),
    })
    # Rolling window: keep last 100 entries
    if len(insights) > 100:
        insights = insights[-100:]
    _save(insights)


def _todays_insights() -> list:
    today = datetime.now().strftime("%Y-%m-%d")
    return [i for i in _load() if i["ts"][:10] == today]


async def send_daily_digest(bot):
    """9 pm job: summarise today's family interactions and send to Joe."""
    from modules.utils import OWNER_CHAT_ID, ask_claude, MODEL_FAST
    if not OWNER_CHAT_ID:
        return

    entries = _todays_insights()
    if not entries:
        logger.info("[Insights] No interactions today, skipping digest")
        return

    lines = []
    for e in entries:
        t = e["ts"][11:16]
        lines.append(f"[{t}] {e['member']} asked: {e['question']}")
        lines.append(f"  ABbot: {e['reply'][:150]}")
        lines.append("")

    prompt = (
        "Here are today's interactions between ABbot and family members (not Joe):\n\n"
        + "\n".join(lines)
        + "\n\nWrite a brief parent summary for Joe (under 150 words):\n"
        "- What topics came up\n"
        "- Anything Joe might want to follow up on\n"
        "- Any struggles or knowledge gaps noticed\n\n"
        "Be warm and practical. Plain text only."
    )

    try:
        summary = ask_claude(
            "You are a helpful family assistant summarising children's learning activity.",
            prompt,
            max_tokens=350,
            model=MODEL_FAST,
        )
        date_str = datetime.now().strftime("%d %b")
        await bot.send_message(
            chat_id=OWNER_CHAT_ID,
            text=f"👨‍👩‍👦 Family Digest ({date_str})\n\n{summary}",
        )
        logger.info("[Insights] Daily digest sent")

        # Clear today's entries after sending
        all_entries = _load()
        today = datetime.now().strftime("%Y-%m-%d")
        _save([e for e in all_entries if e["ts"][:10] != today])
    except Exception as e:
        logger.error(f"[Insights] Daily digest failed: {e}")
