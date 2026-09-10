"""Gout / uric acid food diary — Joe's personal diet tracking for gout
management. Private feature: photo/text meal logs + a weekly pattern report,
sent only to OWNER_CHAT_ID, never the family group. See skills/gout_diet.md
for the purine reference and report rules Claude follows."""

import logging
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

LOG_FILE = Path("data/gout_log.json")

# Caption keywords (case-insensitive substring match) that mark a photo as a
# meal to log, distinguishing it from homework/general photos on the same
# handler. Only checked for the owner — see bot.py handle_photo_message.
FOOD_LOG_KEYWORDS = ["food", "meal", "log", "尿酸", "嘌呤", "餐"]

# "ask"/"問" wins over the log keywords above — e.g. "ask food" or "問餐" gets
# analysed and answered but NOT saved to the diary. Checked first in
# bot.py's handle_photo_message, so "ask food" doesn't also match "food" above.
FOOD_QUERY_KEYWORDS = ["ask", "問"]

LEVEL_EMOJI = {"🔴": "high", "🟡": "moderate", "🟢": "low"}


def is_food_log_caption(caption: str) -> bool:
    c = (caption or "").lower()
    return any(kw in c for kw in FOOD_LOG_KEYWORDS)


def is_food_query_caption(caption: str) -> bool:
    c = (caption or "").lower()
    return any(kw in c for kw in FOOD_QUERY_KEYWORDS)


def _load_log() -> dict:
    from modules.utils import _load
    return _load(LOG_FILE)


def _save_log(data: dict) -> None:
    from modules.utils import _save
    _save(LOG_FILE, data)


def _extract_level(text: str) -> str:
    """Returns the level for whichever rating emoji appears FIRST in the text —
    not just any match — since a later hypothetical aside (e.g. "...would push
    this to 🟡 or 🔴") can otherwise outrank the actual 🟢 rating stated up front."""
    positions = [(text.find(emoji), level) for emoji, level in LEVEL_EMOJI.items() if emoji in text]
    if not positions:
        return "unknown"
    return min(positions, key=lambda p: p[0])[1]


def _add_entry(source: str, description: str, analysis: str) -> None:
    log = _load_log()
    entry_id = uuid.uuid4().hex[:10]
    log[entry_id] = {
        "id": entry_id,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "source": source,  # "photo" or "text"
        "description": description[:200],
        "analysis": analysis,
        "level": _extract_level(analysis),
    }
    _save_log(log)


def remove_entry(hint: str = "") -> str:
    """Deletes one logged meal and returns a confirmation/error message.
    With a hint (e.g. a food name), removes the most recent entry whose
    description or analysis matches it. With no hint, removes the single
    most recent entry — the common case of "oops, undo that last log"."""
    log = _load_log()
    if not log:
        return "你暫時未有任何食物記錄。\nYou don't have any food log entries right now."

    entries = sorted(log.values(), key=lambda e: e["timestamp"], reverse=True)

    target = None
    if hint.strip():
        hint_lower = hint.strip().lower()
        for e in entries:
            if hint_lower in e["description"].lower() or hint_lower in e["analysis"].lower():
                target = e
                break
        if not target:
            return (
                f"搵唔到同「{hint}」相符嘅記錄，冇刪除任何嘢。\n"
                f"Couldn't find a logged meal matching \"{hint}\" to remove — nothing was deleted."
            )
    else:
        target = entries[0]

    del log[target["id"]]
    _save_log(log)
    logged_at = target["timestamp"][:16].replace("T", " ")
    return f"已移除：{target['description']}（記錄於 {logged_at}）\nRemoved: {target['description']} (logged {logged_at})"


def correct_last_entry(correction_text: str) -> str:
    """Re-analyzes the most recently logged meal in light of a correction Joe
    just gave (e.g. "not organ meat, just BBQ pork") and REPLACES that entry —
    rather than adding a new separate one. Without this, each correction in a
    back-and-forth ("actually no offal" / "no, just roast pork, no organs")
    silently created a brand new duplicate entry instead of fixing the
    original, so one meal fragmented into several wrong log rows."""
    from modules.utils import ask_claude, MODEL_SMART
    from modules.skills_loader import load_skills

    log = _load_log()
    if not log:
        return (
            "你未有最近嘅食物記錄可以更正 — 直接講返嗰餐嘅內容，我幫你重新記錄。\n"
            "You don't have a recent food log entry to correct — describe the meal and I'll log it fresh."
        )

    last = max(log.values(), key=lambda e: e["timestamp"])

    system = load_skills(scope="gout")
    prompt = (
        f"Joe previously logged this meal:\n{last['description']}\n\n"
        f"Previous analysis:\n{last['analysis']}\n\n"
        f"Joe is now correcting that: {correction_text}\n\n"
        "Re-identify the food and re-rate its purine load taking the correction "
        "into account. Write it as ONE complete, fresh meal log entry reflecting "
        "the correction — don't just describe what changed.\n\n"
        "At the very end, on its own line, add a short plain-text summary of the "
        "CORRECTED meal only (just the food items, comma-separated, no formatting, "
        "no old/wrong items), in Traditional Chinese matching the food names Joe "
        "used, prefixed exactly with 'SUMMARY: ' — e.g. 'SUMMARY: 苦瓜湯、燒豬肉、白飯、3隻蛋'."
    )
    raw = ask_claude(system, prompt, max_tokens=900, model=MODEL_SMART)

    # Split off the SUMMARY line so the stored description reflects the
    # CORRECTED meal cleanly — previously this concatenated the old (now
    # wrong) description with "(corrected: ...)", so a status listing like
    # get_today_summary() showed both the stale wrong items and the fix
    # stacked together, and each further correction made it worse.
    match = re.search(r"\n *SUMMARY:\s*(.+?)\s*$", raw, re.IGNORECASE | re.DOTALL)
    if match:
        description = match.group(1).strip()
        analysis = raw[:match.start()].rstrip()
    else:
        description = correction_text  # fallback if the model skipped the summary line
        analysis = raw

    del log[last["id"]]
    entry_id = uuid.uuid4().hex[:10]
    log[entry_id] = {
        "id": entry_id,
        "timestamp": last["timestamp"],  # keep the original meal time, not the correction time
        "source": last["source"],
        "description": description[:200],
        "analysis": analysis,
        "level": _extract_level(analysis),
    }
    _save_log(log)
    return analysis


def get_today_summary() -> str:
    """Everything actually logged today, read straight from the log file —
    used to answer "what's my log tonight/today" honestly instead of letting
    the general chat fallback improvise an answer from stale conversation
    history (it has no access to the real data at all).

    Shows each entry's FULL stored analysis (purine/calories/heart/weight +
    suggestions) — the same detail already shown when the meal was logged —
    not just a bare one-line food list, since that fuller breakdown is the
    actual point of checking the log."""
    log = _load_log()
    today = datetime.now().strftime("%Y-%m-%d")
    todays = [e for e in log.values() if e["timestamp"].startswith(today)]
    if not todays:
        return "今日仲未記錄任何嘢。\nNothing logged today yet."
    todays.sort(key=lambda e: e["timestamp"])
    level_label = {
        "high": "🔴 高/High", "moderate": "🟡 中/Moderate",
        "low": "🟢 低/Low", "unknown": "⚪ 未知/Unknown",
    }
    blocks = [
        f"🕐 {e['timestamp'][11:16]} 整體 {level_label.get(e.get('level', 'unknown'), '⚪')} — {e['description']}\n\n{e['analysis']}"
        for e in todays
    ]
    header = f"今日飲食記錄 | Today's food log（共 {len(todays)} 餐 | {len(todays)} meal(s)）"
    return header + "\n\n" + "\n\n---\n\n".join(blocks)


def get_entries_since(days: int = 7) -> list:
    log = _load_log()
    cutoff = datetime.now() - timedelta(days=days)
    entries = []
    for e in log.values():
        try:
            ts = datetime.fromisoformat(e["timestamp"])
        except Exception:
            continue
        if ts >= cutoff:
            entries.append(e)
    entries.sort(key=lambda e: e["timestamp"])
    return entries


async def _vision_analyze(bot, photo, caption: str, will_log: bool) -> str:
    """Downloads a Telegram photo and asks Claude to assess its purine/gout
    risk. `will_log` only changes the wording of the instruction sent to
    Claude (logged vs. quick lookup) — it does NOT itself write to the diary;
    callers decide whether to call _add_entry."""
    from modules.utils import claude, MODEL_SMART
    from modules.skills_loader import load_skills
    import base64
    import httpx

    file = await bot.get_file(photo[-1].file_id)
    async with httpx.AsyncClient() as client:
        response = await client.get(file.file_path)
        image_data = base64.standard_b64encode(response.content).decode("utf-8")

    intent_line = (
        "This is a meal Joe is logging for gout/uric acid tracking."
        if will_log else
        "Joe is just asking about this food's purine/gout risk — a quick lookup, NOT being logged to his diary."
    )
    prompt = (
        (f"Caption: {caption}\n\n" if caption else "") +
        f"{intent_line} Identify the food and rate its purine load per the rules above."
    )

    r = claude.messages.create(
        model=MODEL_SMART,
        max_tokens=900,
        system=load_skills(scope="gout"),
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": image_data,
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }],
    )
    return r.content[0].text


async def analyze_meal_photo(bot, photo, caption: str = "") -> str:
    """Downloads a Telegram photo, asks Claude to assess its purine/gout
    risk, logs the result, and returns the reply text to send back to Joe."""
    try:
        analysis = await _vision_analyze(bot, photo, caption, will_log=True)
        _add_entry("photo", caption or "(photo)", analysis)
        return analysis
    except Exception as e:
        logger.error(f"[Gout] photo analysis failed: {e}")
        return "Sorry, I couldn't analyse that meal photo. Please try again."


async def query_meal_photo(bot, photo, caption: str = "") -> str:
    """Like analyze_meal_photo but does NOT save to the food diary — for the
    "ask food"/"問餐" quick-lookup trigger (see is_food_query_caption)."""
    try:
        return await _vision_analyze(bot, photo, caption, will_log=False)
    except Exception as e:
        logger.error(f"[Gout] photo query failed: {e}")
        return "Sorry, I couldn't analyse that meal photo. Please try again."


def analyze_meal_text(description: str) -> str:
    """Logs a text-described meal (no photo) and returns the reply text."""
    from modules.utils import ask_claude, MODEL_SMART
    from modules.skills_loader import load_skills

    system = load_skills(scope="gout")
    prompt = (
        f"Joe is logging this meal for gout/uric acid tracking: {description}\n\n"
        "Identify the food and rate its purine load per the rules above."
    )
    analysis = ask_claude(system, prompt, max_tokens=900, model=MODEL_SMART)
    _add_entry("text", description, analysis)
    return analysis


async def send_weekly_report(bot) -> None:
    """Compiles the last 7 days of logged meals into a pattern report, sends
    it to Joe privately, then CLEARS those entries — each week's report
    starts from a fresh diary rather than accumulating forever. Registered
    as the "gout_weekly_report" action in run_scheduled_job (modules/agent.py),
    scheduled Monday mornings."""
    from modules.utils import ask_claude, OWNER_CHAT_ID, MODEL_SMART
    from modules.skills_loader import load_skills

    if not OWNER_CHAT_ID:
        logger.warning("[Gout] OWNER_CHAT_ID not set, skipping weekly report")
        return

    entries = get_entries_since(days=7)
    if not entries:
        await bot.send_message(
            chat_id=OWNER_CHAT_ID,
            text=(
                "🩺 每週飲食健康報告 | Weekly Diet & Health Report\n\n"
                "呢個星期未記錄過任何餐 — 影相 caption 打「food」/「meal」/「log」/"
                "「尿酸」/「嘌呤」/「餐」（或者直接同我講食咗咩）就可以開始記錄。\n"
                "No meals logged this week — caption a food photo with "
                "\"food\"/\"meal\"/\"log\"/\"尿酸\"/\"嘌呤\"/\"餐\" (or just tell me "
                "what you ate) to start tracking."
            ),
        )
        return

    # Full analysis (not just the first ~150 chars) so the secondary
    # calories/heart/weight lines near the end of each entry actually reach
    # the report prompt instead of being truncated away.
    lines = [f"[{e['timestamp'][:10]}] {e['description']}: {e['analysis'][:600]}" for e in entries]
    log_text = "\n\n".join(lines)

    system = load_skills(scope="gout")
    report = ask_claude(
        system,
        f"Here are Joe's {len(entries)} logged meals from the past 7 days:\n\n{log_text}\n\n"
        "Write his weekly report (uric acid first and most detailed, then brief "
        "calories/heart/weight patterns) per the Weekly report rules above. Write it "
        "bilingually per communication_style.md.",
        max_tokens=1500,
        model=MODEL_SMART,
    )
    await bot.send_message(chat_id=OWNER_CHAT_ID, text=f"🩺 每週飲食健康報告 | Weekly Diet & Health Report\n\n{report}")

    # Clear exactly the entries this report covered — not a blanket wipe — so
    # any meal logged concurrently while the report was being generated survives.
    log = _load_log()
    for e in entries:
        log.pop(e["id"], None)
    _save_log(log)
