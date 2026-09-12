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
# Includes plain meal-time words (lunch/dinner/etc.) since those are the most
# natural thing to caption a food photo with — missing "lunch" here is what
# let 6 real lunch photos fall through to the generic (non-food) handler on
# 2026-09-11 13:37-13:41 with zero purine/calorie analysis or logging.
FOOD_LOG_KEYWORDS = [
    "food", "meal", "log", "lunch", "dinner", "breakfast", "brunch", "snack", "supper",
    "尿酸", "嘌呤", "餐", "午餐", "晚餐", "早餐", "宵夜", "下午茶",
]

# "ask"/"問" wins over the log keywords above — e.g. "ask food" or "問餐" gets
# analysed and answered but NOT saved to the diary. Checked first in
# bot.py's handle_photo_message, so "ask food" doesn't also match "food" above.
FOOD_QUERY_KEYWORDS = ["ask", "問"]

LEVEL_EMOJI = {"🔴": "high", "🟡": "moderate", "🟢": "low"}
LEVELS_KEYS = ["purine", "sugar", "heart", "bp", "weight"]


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


def _parse_levels_tag(text: str) -> tuple:
    """Splits off the 'LEVELS: purine=high|sugar=moderate|...' machine-
    readable tag Claude appends per gout_diet.md (step 7 of "When logging a
    meal"), returning (display_text_with_the_tag_line_removed, levels_dict).
    ABbot is a general health advisor now, not just a uric-acid tracker — this
    is what lets _recent_pattern_context() detect a bad STREAK on blood
    pressure/sugar/heart/weight specifically, not only purine.

    Scans for "LEVELS:" ANYWHERE within each line (not requiring it at
    position 0, and not requiring the line to BE just the tag) so it survives
    Claude wrapping the tag in markdown — backtick code-span, bold, a leading
    bullet — which it does fairly often despite being told this is a plain
    machine-readable line. A line that contains the marker is dropped
    entirely from the displayed text, wrapper and all. Falls back to the old
    single-emoji purine extraction if the tag is missing/malformed — e.g.
    older entries logged before this existed, or the model forgot to add it —
    so nothing crashes on partial/legacy data."""
    lines = text.split("\n")
    levels = {}
    kept_lines = []
    for line in lines:
        upper = line.upper()
        if "LEVELS:" in upper:
            idx = upper.index("LEVELS:")
            tag_body = line[idx + len("LEVELS:"):]
            for pair in tag_body.split("|"):
                if "=" not in pair:
                    continue
                k, v = pair.split("=", 1)
                k = k.strip().strip("`*_").lower()
                v = v.strip().strip("`*_").lower()
                if k in LEVELS_KEYS and v in ("low", "moderate", "high"):
                    levels[k] = v
        else:
            kept_lines.append(line)
    display_text = "\n".join(kept_lines).rstrip()
    if "purine" not in levels:
        levels["purine"] = _extract_level(display_text)
    return display_text, levels


def _record_history(user_turn: str, assistant_turn: str) -> None:
    """Adds this food interaction to the normal conversation history so a
    bare text follow-up (e.g. "糖分是否會很高？" with no reply-to and no
    keyword of its own) can still work via the general chat handler's
    ask_claude_with_history — previously EVERY food log/query interaction
    (photo or text, saved or not) was invisible to conversation history
    entirely, since these functions call ask_claude directly instead of
    ask_claude_with_history. That's the actual root cause behind "the bot
    forgot what food we were just discussing" — not a reply-to-message
    problem (already fixed separately) and not a missing-skill problem
    (also already fixed) but the interaction never being recorded at all.
    See chat 2026-09-12 17:38 — "ask this ok?" photo query at 17:37 was
    completely absent from history_summary() a minute later."""
    from modules.utils import OWNER_CHAT_ID, history_add
    if not OWNER_CHAT_ID:
        return
    try:
        history_add(str(OWNER_CHAT_ID), "user", user_turn[:500])
        history_add(str(OWNER_CHAT_ID), "assistant", assistant_turn[:1500])
    except Exception as e:
        logger.error(f"[Gout] history_add failed: {e}")


def _add_entry(source: str, description: str, analysis: str) -> str:
    """Stores the entry — with the LEVELS tag parsed into structured data and
    stripped from the saved/displayed text — and returns the CLEANED analysis.
    Callers must send this return value back to Joe, not the raw `analysis`
    they passed in (which still has the machine-readable tag in it)."""
    log = _load_log()
    entry_id = uuid.uuid4().hex[:10]
    display_text, levels = _parse_levels_tag(analysis)
    log[entry_id] = {
        "id": entry_id,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "source": source,  # "photo" or "text"
        "description": description[:200],
        "analysis": display_text,
        "level": levels.get("purine", "unknown"),
        "levels": levels,
    }
    _save_log(log)
    return display_text


def remove_entry(hint: str = "") -> str:
    """Deletes one logged meal and returns a confirmation/error message.
    With a hint (e.g. a food name OR a time like "13:51"), removes the most
    recent entry whose description, analysis, or timestamp matches it. With
    no hint, removes the single most recent entry — the common case of
    "oops, undo that last log"."""
    log = _load_log()
    if not log:
        return "你暫時未有任何食物記錄。\nYou don't have any food log entries right now."

    entries = sorted(log.values(), key=lambda e: e["timestamp"], reverse=True)

    target = None
    if hint.strip():
        hint_lower = hint.strip().lower()
        for e in entries:
            if (
                hint_lower in e["description"].lower()
                or hint_lower in e["analysis"].lower()
                or hint_lower in e["timestamp"].lower()
            ):
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
        "the correction — don't just describe what changed. Still include the "
        "usual LEVELS tag per the rules above.\n\n"
        "Then, on its own line AFTER the LEVELS tag, add a short plain-text summary "
        "of the CORRECTED meal only (just the food items, comma-separated, no "
        "formatting, no old/wrong items), in Traditional Chinese matching the food "
        "names Joe used, prefixed exactly with 'SUMMARY: ' — e.g. "
        "'SUMMARY: 苦瓜湯、燒豬肉、白飯、3隻蛋'."
    )
    raw = ask_claude(system, prompt, max_tokens=900, model=MODEL_SMART)

    # Strip LEVELS first (it can land before or after SUMMARY depending on
    # how closely the model follows "after the LEVELS tag" above — the line-
    # based scan in _parse_levels_tag finds it either way), then split off
    # the SUMMARY line so the stored description reflects the CORRECTED meal
    # cleanly — previously this concatenated the old (now wrong) description
    # with "(corrected: ...)", so a status listing like get_today_summary()
    # showed both the stale wrong items and the fix stacked together, and
    # each further correction made it worse.
    raw, levels = _parse_levels_tag(raw)
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
        "level": levels.get("purine", "unknown"),
        "levels": levels,
    }
    _save_log(log)
    _record_history(f"[Corrected a food log entry] {correction_text}", analysis)
    return analysis


_LEVEL_LABEL = {
    "high": "🔴 高/High", "moderate": "🟡 中/Moderate",
    "low": "🟢 低/Low", "unknown": "⚪ 未知/Unknown",
}
_DOW_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def get_log_summary(day_ref: str = "today") -> str:
    """Everything actually logged for a given day (or the past week), read
    straight from the log file — used to answer "what's my log today/
    yesterday/this week" honestly instead of letting the general chat
    fallback improvise an answer from stale conversation history (it has no
    access to the real data at all, and will confidently fabricate a "no
    records" table rather than admit it can't check — see chat 2026-09-12).

    Entries persist until the NEXT weekly report fires (send_weekly_report
    clears only what it just reported on) — so "yesterday" or "this week"
    are valid, real queries right up until Monday's report, not just "today".

    day_ref: "today"/"yesterday" (also 今日/今天/昨日/昨天), a weekday name
    ("monday".."sunday", matching the most recent past occurrence — "today"
    if today IS that weekday), "week"/"this week" (也支援 本週/呢個星期,
    past 7 days), or an explicit "YYYY-MM-DD" date. Unrecognised input falls
    back to "today".

    Shows each entry's FULL stored analysis (purine/calories/heart/weight +
    suggestions) — the same detail already shown when the meal was logged —
    not just a bare one-line food list, since that fuller breakdown is the
    actual point of checking the log."""
    log = _load_log()
    now = datetime.now()
    ref = (day_ref or "today").strip().lower()

    if ref in ("week", "this week", "本週", "本周", "呢個星期", "這星期", "這一星期"):
        cutoff = now - timedelta(days=7)
        matches = [e for e in log.values() if datetime.fromisoformat(e["timestamp"]) >= cutoff]
        label = "本週 | This week"
    else:
        if ref in ("today", "今日", "今天"):
            target_date = now.date()
        elif ref in ("yesterday", "昨日", "昨天"):
            target_date = (now - timedelta(days=1)).date()
        elif ref in _DOW_NAMES:
            days_back = (now.weekday() - _DOW_NAMES.index(ref)) % 7
            target_date = (now - timedelta(days=days_back)).date()
        else:
            try:
                target_date = datetime.strptime(ref, "%Y-%m-%d").date()
            except ValueError:
                target_date = now.date()
        date_str = target_date.strftime("%Y-%m-%d")
        matches = [e for e in log.values() if e["timestamp"].startswith(date_str)]
        label = date_str

    if not matches:
        return (
            f"{label} 冇任何記錄（可能已經隨住週報清咗，或者嗰日冇記錄）。\n"
            f"No entries for {label} (may already have been cleared by a weekly report, or nothing was logged that day)."
        )

    matches.sort(key=lambda e: e["timestamp"])
    blocks = [
        f"🕐 {e['timestamp'][11:16]} 整體 {_LEVEL_LABEL.get(e.get('level', 'unknown'), '⚪')} — {e['description']}\n\n{e['analysis']}"
        for e in matches
    ]
    header = f"{label} 飲食記錄 | Food log for {label}（共 {len(matches)} 餐 | {len(matches)} meal(s)）"
    return header + "\n\n" + "\n\n---\n\n".join(blocks)


def get_today_summary() -> str:
    """Back-compat wrapper — see get_log_summary()."""
    return get_log_summary("today")


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


_INDICATOR_LABEL = {
    "purine": "purine", "sugar": "blood sugar", "heart": "heart/cholesterol",
    "bp": "blood pressure", "weight": "weight",
}


def _recent_pattern_context(days: int = 3) -> str:
    """Short per-INDICATOR summary of recent ratings (BEFORE the meal
    currently being logged), injected into the analysis prompt so Claude's
    tone can reflect an emerging pattern on ANY of the five health areas —
    not just purine, and not just react to this one meal in isolation. ABbot
    is a general health advisor now, so a 3-day run of 🔴 blood pressure
    deserves the same callout as a 3-day run of 🔴 purine, even if purine
    itself looks fine that week. See gout_diet.md's "Tone escalation" rules
    for how this gets used; this function only supplies the facts, never the
    tone itself. Older entries logged before the LEVELS tag existed only have
    a purine level (from the legacy single-emoji extraction) — that's fine,
    they just won't contribute to the other four indicators' counts."""
    entries = get_entries_since(days=days)
    if not entries:
        return ""
    per_indicator = {k: {"high": 0, "moderate": 0, "low": 0} for k in LEVELS_KEYS}
    for e in entries:
        levels = e.get("levels") or {"purine": e.get("level", "unknown")}
        for k, v in levels.items():
            if k in per_indicator and v in per_indicator[k]:
                per_indicator[k][v] += 1
    lines = []
    for k in LEVELS_KEYS:
        c = per_indicator[k]
        if c["high"] or c["moderate"]:
            lines.append(f"{_INDICATOR_LABEL[k]}: {c['high']} high, {c['moderate']} moderate, {c['low']} low")
    if not lines:
        return ""
    return (
        f"Context (not this meal — Joe's last {days} days before it, per indicator):\n"
        + "\n".join(lines)
        + "\nFactor this into your tone per the Tone escalation rules — track each "
        "indicator's own streak separately, don't just repeat these numbers verbatim."
    )


async def _vision_analyze_ids(bot, file_ids: list, caption: str, will_log: bool) -> str:
    """Downloads one or more Telegram photos (by file_id) and asks Claude to
    assess their purine/gout risk AS ONE MEAL. Pass multiple file_ids when
    several photos are the same meal (e.g. Joe photographing each dish of one
    lunch separately) — they go into ONE vision call so the log ends up as
    one meal entry, not N duplicate/fragmented ones. `will_log` only changes
    the wording of the instruction sent to Claude (logged vs. quick lookup) —
    it does NOT itself write to the diary; callers decide whether to call
    _add_entry."""
    from modules.utils import claude, MODEL_SMART
    from modules.skills_loader import load_skills
    import base64
    import httpx

    content = []
    async with httpx.AsyncClient() as client:
        for fid in file_ids:
            file = await bot.get_file(fid)
            response = await client.get(file.file_path)
            image_data = base64.standard_b64encode(response.content).decode("utf-8")
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": image_data},
            })

    intent_line = (
        "This is a meal Joe is logging for gout/uric acid tracking."
        if will_log else
        "Joe is just asking about this food's purine/gout risk — a quick lookup, NOT being logged to his diary."
    )
    multi_note = (
        f" These {len(file_ids)} photos are all part of the SAME meal (e.g. separate "
        "dishes on the table) — analyse and rate them together as ONE meal, not separately."
        if len(file_ids) > 1 else ""
    )
    recent_ctx = _recent_pattern_context()
    prompt = (
        (f"Caption: {caption}\n\n" if caption else "") +
        f"{intent_line}{multi_note} Identify the food and rate its purine load per the rules above." +
        (f"\n\n{recent_ctx}" if recent_ctx else "")
    )
    content.append({"type": "text", "text": prompt})

    r = claude.messages.create(
        model=MODEL_SMART,
        max_tokens=900,
        system=load_skills(scope="gout"),
        messages=[{"role": "user", "content": content}],
    )
    return r.content[0].text


async def analyze_meal_photo(bot, photos, caption: str = "") -> str:
    """Downloads one or more Telegram photos of the SAME meal, asks Claude to
    assess purine/gout risk across all of them together, logs ONE combined
    entry, and returns the reply text to send back to Joe.

    `photos` is a list of Telegram photo-size arrays — pass [msg.photo] for a
    single photo, or one array per photo when several images are one meal
    (e.g. Joe photographing each dish separately). Multiple images go into a
    single vision call so the log ends up as one meal, not N fragmented ones."""
    try:
        file_ids = [p[-1].file_id for p in photos]
        analysis = await _vision_analyze_ids(bot, file_ids, caption, will_log=True)
        display_text = _add_entry("photo", caption or "(photo)", analysis)
        _record_history(f"[Logged a food photo] {caption or '(no caption)'}", display_text)
        return display_text
    except Exception as e:
        logger.error(f"[Gout] photo analysis failed: {e}")
        return "Sorry, I couldn't analyse that meal photo. Please try again."


async def query_meal_photo(bot, photos, caption: str = "") -> str:
    """Like analyze_meal_photo but does NOT save to the food diary — for the
    "ask food"/"問餐" quick-lookup trigger (see is_food_query_caption). Still
    strips the LEVELS tag (per gout_diet.md's format, unconditional on
    logging) so Joe never sees the raw machine-readable line. Still recorded
    to conversation history even though it's not saved to the diary — a
    "just asking" photo is exactly the kind of thing a bare text follow-up
    refers back to (see _record_history's docstring)."""
    try:
        file_ids = [p[-1].file_id for p in photos]
        analysis = await _vision_analyze_ids(bot, file_ids, caption, will_log=False)
        display_text, _levels = _parse_levels_tag(analysis)
        _record_history(f"[Asked about a food photo] {caption or '(no caption)'}", display_text)
        return display_text
    except Exception as e:
        logger.error(f"[Gout] photo query failed: {e}")
        return "Sorry, I couldn't analyse that meal photo. Please try again."


def analyze_meal_text(description: str) -> str:
    """Logs a text-described meal (no photo) and returns the reply text."""
    from modules.utils import ask_claude, MODEL_SMART
    from modules.skills_loader import load_skills

    system = load_skills(scope="gout")
    recent_ctx = _recent_pattern_context()
    prompt = (
        f"Joe is logging this meal for gout/uric acid tracking: {description}\n\n"
        "Identify the food and rate its purine load per the rules above."
        + (f"\n\n{recent_ctx}" if recent_ctx else "")
    )
    analysis = ask_claude(system, prompt, max_tokens=900, model=MODEL_SMART)
    display_text = _add_entry("text", description, analysis)
    _record_history(f"[Logged a meal] {description}", display_text)
    return display_text


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
                "🩺 每週飲食記錄報告 | Weekly Food Log Report\n\n"
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
    await bot.send_message(chat_id=OWNER_CHAT_ID, text=f"🩺 每週飲食記錄報告 | Weekly Food Log Report\n\n{report}")

    # Clear exactly the entries this report covered — not a blanket wipe — so
    # any meal logged concurrently while the report was being generated survives.
    log = _load_log()
    for e in entries:
        log.pop(e["id"], None)
    _save_log(log)
