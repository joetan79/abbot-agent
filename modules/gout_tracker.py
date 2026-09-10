"""Gout / uric acid food diary — Joe's personal diet tracking for gout
management. Private feature: photo/text meal logs + a weekly pattern report,
sent only to OWNER_CHAT_ID, never the family group. See skills/gout_diet.md
for the purine reference and report rules Claude follows."""

import logging
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
        return "You don't have any food log entries right now."

    entries = sorted(log.values(), key=lambda e: e["timestamp"], reverse=True)

    target = None
    if hint.strip():
        hint_lower = hint.strip().lower()
        for e in entries:
            if hint_lower in e["description"].lower() or hint_lower in e["analysis"].lower():
                target = e
                break
        if not target:
            return f"Couldn't find a logged meal matching \"{hint}\" to remove — nothing was deleted."
    else:
        target = entries[0]

    del log[target["id"]]
    _save_log(log)
    return f"Removed: {target['description']} (logged {target['timestamp'][:16].replace('T', ' ')})"


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
        max_tokens=600,
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
    analysis = ask_claude(system, prompt, max_tokens=600, model=MODEL_SMART)
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
                "🩺 Weekly Uric Acid Report\n\n"
                "No meals logged this week — caption a food photo with "
                "\"food\"/\"meal\"/\"log\"/\"尿酸\"/\"嘌呤\"/\"餐\" (or just tell me "
                "what you ate) to start tracking."
            ),
        )
        return

    lines = [f"[{e['timestamp'][:10]}] {e['description']}: {e['analysis'][:150]}" for e in entries]
    log_text = "\n\n".join(lines)

    system = load_skills(scope="gout")
    report = ask_claude(
        system,
        f"Here are Joe's {len(entries)} logged meals from the past 7 days:\n\n{log_text}\n\n"
        "Write his weekly gout/uric acid pattern report per the Weekly report rules above.",
        max_tokens=1000,
        model=MODEL_SMART,
    )
    await bot.send_message(chat_id=OWNER_CHAT_ID, text=f"🩺 Weekly Uric Acid Report\n\n{report}")

    # Clear exactly the entries this report covered — not a blanket wipe — so
    # any meal logged concurrently while the report was being generated survives.
    log = _load_log()
    for e in entries:
        log.pop(e["id"], None)
    _save_log(log)
