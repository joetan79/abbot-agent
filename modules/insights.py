"""Cross-chat insights: log family member interactions, send daily + weekly
digests to Joe."""

import json
import logging
from datetime import datetime, timedelta
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


def get_entries_since(days: int) -> list:
    """Entries from the last `days` days, for send_weekly_family_digest."""
    cutoff = datetime.now() - timedelta(days=days)
    return [i for i in _load() if datetime.fromisoformat(i["ts"]) >= cutoff]


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

        # Entries are NOT cleared here — send_weekly_family_digest needs the
        # full week's history to build its dated summary + suggestions, and
        # only it clears (on confirmed delivery). The rolling 100-entry cap
        # in log_interaction is the backstop against unbounded growth.
    except Exception as e:
        logger.error(f"[Insights] Daily digest failed: {e}")


async def send_weekly_family_digest(bot):
    """Weekly round-up (Sundays 21:00, see bot.py) of family interactions with
    the bot: a dated list of what came up, an overall summary, and 1-3
    concrete suggestions for Joe. Complements the nightly send_daily_digest,
    which only covers a single day. Uses the same chunked + long-timeout send
    and clear-only-on-confirmed-delivery pattern as gout_tracker.send_weekly_report
    — see that function's comment for the data-loss bug this avoids."""
    from modules.utils import OWNER_CHAT_ID, ask_claude, MODEL_SMART

    if not OWNER_CHAT_ID:
        return

    entries = get_entries_since(days=7)
    if not entries:
        await bot.send_message(
            chat_id=OWNER_CHAT_ID,
            text=(
                "👨‍👩‍👦 Weekly Family Digest\n\n"
                "過去一星期冇同家人互動記錄。\n"
                "No family interactions logged this week."
            ),
        )
        return

    lines = []
    for e in sorted(entries, key=lambda x: x["ts"]):
        dt = datetime.fromisoformat(e["ts"])
        lines.append(f"[{dt.strftime('%m-%d %H:%M')}] {e['member']}: {e['question']}")
        lines.append(f"  ABbot: {e['reply'][:150]}")
        lines.append("")
    log_text = "\n".join(lines)

    prompt = (
        f"Here are this week's {len(entries)} interactions between ABbot and "
        f"family members (not Joe):\n\n{log_text}\n\n"
        "Write a weekly family digest for Joe with three parts:\n"
        "1. 日期時間摘要 | Dated summary — one short line per interaction: date, "
        "time, who, and the gist of what was asked/discussed (not the full text)\n"
        "2. 總結 | Summary — a brief overall summary of the week's topics/activity\n"
        "3. 建議 | Suggestions — 1-3 concrete areas Joe could help reinforce or "
        "follow up on, based on real patterns in what's above (repeated "
        "struggles, subjects, engagement) — not generic advice\n\n"
        "Be warm and practical, bilingual (Traditional Chinese/English) per "
        "household style. Plain text only, no markdown."
    )

    try:
        report = ask_claude(
            "You are a helpful family assistant summarising children's "
            "learning activity and interactions with the household AI assistant.",
            prompt,
            max_tokens=900,
            model=MODEL_SMART,
        )
    except Exception as e:
        logger.error(f"[Insights] Weekly digest generation failed: {e}")
        return

    full_text = f"👨‍👩‍👦 Weekly Family Digest\n\n{report}"
    TELEGRAM_MSG_LIMIT = 3500
    SEND_TIMEOUT = 20.0
    if len(full_text) <= TELEGRAM_MSG_LIMIT:
        chunks = [full_text]
    else:
        chunks, chunk, chunk_len = [], [], 0
        for p in full_text.split("\n\n"):
            if chunk and chunk_len + len(p) + 2 > TELEGRAM_MSG_LIMIT:
                chunks.append("\n\n".join(chunk))
                chunk, chunk_len = [], 0
            chunk.append(p)
            chunk_len += len(p) + 2
        if chunk:
            chunks.append("\n\n".join(chunk))

    sent = 0
    for c in chunks:
        try:
            await bot.send_message(
                chat_id=OWNER_CHAT_ID, text=c,
                read_timeout=SEND_TIMEOUT, write_timeout=SEND_TIMEOUT, connect_timeout=SEND_TIMEOUT,
            )
            sent += 1
        except Exception as e:
            logger.error(f"[Insights] weekly digest chunk {sent + 1}/{len(chunks)} send failed: {e}")
            break

    if sent < len(chunks):
        try:
            await bot.send_message(
                chat_id=OWNER_CHAT_ID,
                text=(
                    f"⚠️ 網絡逾時，家庭週報只送出咗 {sent}/{len(chunks)} 部分。\n"
                    f"Network timeout — only {sent}/{len(chunks)} parts of the "
                    "weekly family digest sent."
                ),
                read_timeout=SEND_TIMEOUT, write_timeout=SEND_TIMEOUT, connect_timeout=SEND_TIMEOUT,
            )
        except Exception as e:
            logger.error(f"[Insights] weekly digest failure notice also failed to send: {e}")
        logger.warning(
            f"[Insights] weekly digest only sent {sent}/{len(chunks)} chunks — "
            "keeping this week's entries uncleared for retry"
        )
        return

    logger.info("[Insights] Weekly family digest sent")
    # Clear exactly the entries this report covered — not a blanket wipe — so
    # anything logged concurrently while the report was being generated survives.
    covered_ts = {e["ts"] for e in entries}
    all_entries = _load()
    _save([e for e in all_entries if e["ts"] not in covered_ts])
