"""Water intake tracker for Joe.

- "w250" (also "W 250", "w250 咖啡", "w250ml") logs 250ml of anything drunk
  (water, coffee, tea... all count). "w-250" subtracts 250ml from today to
  correct a mistake.
- A photo captioned "w" (or "w 咖啡" etc.) only ESTIMATES how many ml the
  cup/bottle holds — it does not log (Joe's choice, 2026-10-04). He then types
  w<ml> himself.
- Days run midnight to midnight, Asia/Macau time. Reports: 18:00 (today so far)
  and 22:00 (today + the previous 2 days). Only the last 3 days are kept —
  older entries are pruned automatically.
"""

from modules.utils import atomic_write_text
import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytz

logger = logging.getLogger(__name__)

WATER_FILE = Path("data/water_log.json")
TZ = pytz.timezone("Asia/Macau")
KEEP_DAYS = 3
MAX_ML = 3000  # sanity cap for a single entry (catches typos like w25000)

# w250 / W 250 / w250ml / w250 咖啡 / w-250
_CMD_RE = re.compile(r"^\s*[wW]\s*(-?)\s*(\d{1,5})\s*(?:ml|ML|毫升)?(?:\s+(.*))?\s*$")


def _now() -> datetime:
    return datetime.now(TZ)


def _load() -> list:
    try:
        return json.loads(WATER_FILE.read_text()).get("entries", [])
    except Exception:
        return []


def _save(entries: list) -> None:
    atomic_write_text(WATER_FILE, json.dumps({"entries": entries}, ensure_ascii=False, indent=2))


def _prune(entries: list) -> list:
    """Keeps today and the previous KEEP_DAYS-1 days only."""
    cutoff = (_now() - timedelta(days=KEEP_DAYS - 1)).date().isoformat()
    return [e for e in entries if e["ts"][:10] >= cutoff]


def parse_command(text: str):
    """Returns (ml, note) for a water command, else None. ml is negative for a
    correction ("w-250")."""
    m = _CMD_RE.match(text or "")
    if not m:
        return None
    ml = int(m.group(2))
    if ml <= 0 or ml > MAX_ML:
        return None
    return (-ml if m.group(1) else ml), (m.group(3) or "").strip()


def is_estimate_caption(caption: str) -> bool:
    """Photo caption asking for a volume estimate: "w" alone or "w <note>"
    (but not a w<number> log command)."""
    c = (caption or "").strip()
    return bool(re.match(r"^[wW](\s+\D.*)?$", c))


def _day_entries(entries: list, day) -> list:
    d = day.isoformat()
    return sorted((e for e in entries if e["ts"][:10] == d), key=lambda e: e["ts"])


def _total(day_entries: list) -> int:
    return sum(e["ml"] for e in day_entries)


def log_water(ml: int, note: str = "") -> str:
    """Records an entry (negative ml = correction) and returns the reply text."""
    entries = _prune(_load())
    today = _now().date()
    current = _total(_day_entries(entries, today))
    if ml < 0 and current + ml < 0:
        return (f"⚠️ 今天只記錄了 {current}ml，不能扣除 {-ml}ml。\n"
                f"Today's total is only {current}ml — can't subtract {-ml}ml.")
    entries.append({"ts": _now().isoformat(timespec="seconds"), "ml": ml, "note": note})
    _save(entries)
    total = current + ml
    logger.info(f"[Water] logged {ml}ml ({note!r}) — today {total}ml")
    if ml < 0:
        return f"➖ 已扣除 {-ml}ml。今天合共 {total}ml\nRemoved {-ml}ml. Today's total: {total}ml"
    what = f"（{note}）" if note else ""
    return f"💧 已記錄 {ml}ml{what}。今天合共 {total}ml\nLogged {ml}ml. Today's total: {total}ml"


def _format_day(entries: list, until: str = None) -> list:
    lines = []
    for e in entries:
        t = e["ts"][11:16]
        if until and t >= until:
            continue
        sign = "➖ " if e["ml"] < 0 else ""
        note = f" {e['note']}" if e.get("note") else ""
        lines.append(f"  {t}  {sign}{abs(e['ml'])}ml{note}")
    return lines


def build_daily_report() -> str:
    """18:00 report: today from midnight up to 18:00."""
    entries = _prune(_load())
    today = _now().date()
    day = [e for e in _day_entries(entries, today) if e["ts"][11:16] < "18:00"]
    total = _total(day)
    head = f"💧 今日喝水記錄 Today's water（{today.strftime('%m/%d')} 00:00–18:00）"
    if not day:
        return f"{head}\n\n今天到現在還沒有記錄。\nNothing logged yet today."
    return "\n".join([head, "", *_format_day(day), "", f"合共 Total: {total}ml"])


def build_3day_report() -> str:
    """22:00 report: today, yesterday and the day before."""
    entries = _prune(_load())
    today = _now().date()
    labels = ["今天 Today", "昨天 Yesterday", "前天 Day before"]
    lines = ["💧 三日喝水報告 3-day water report", ""]
    totals = []
    for i, label in enumerate(labels):
        day = today - timedelta(days=i)
        de = _day_entries(entries, day)
        total = _total(de)
        totals.append(total)
        lines.append(f"{label}（{day.strftime('%m/%d')}）：{total}ml")
        lines.extend(_format_day(de) or ["  （沒有記錄 no entries）"])
        lines.append("")
    logged = [t for t in totals if t > 0]
    if logged:
        lines.append(f"有記錄日子平均 Average (days with entries): {round(sum(logged) / len(logged))}ml")
    return "\n".join(lines).rstrip()


async def _send(bot, text: str) -> None:
    from modules.utils import OWNER_CHAT_ID
    await bot.send_message(chat_id=OWNER_CHAT_ID, text=text)


async def send_daily_report(bot) -> None:
    await _send(bot, build_daily_report())


async def send_3day_report(bot) -> None:
    await _send(bot, build_3day_report())
    # Persist the pruning so the file never holds more than 3 days.
    _save(_prune(_load()))


async def estimate_from_photos(bot, photos: list, caption: str) -> str:
    """Estimates the liquid volume in a photo of a cup/glass/bottle. Does
    NOT log anything."""
    from modules.utils import claude, MODEL_SMART, model_kwargs, response_text, photo_content_blocks

    schema = {
        "type": "object",
        "properties": {
            "ml": {"type": "integer"},
            "container": {"type": "string"},
            "drink": {"type": "string"},
            "reasoning": {"type": "string"},
        },
        "required": ["ml", "container", "drink", "reasoning"],
        "additionalProperties": False,
    }
    system = (
        "Estimate how many millilitres of drink are in the photo (the amount actually in the "
        "cup/glass/bottle, not its full capacity unless it is full). Use visual references: "
        "printed volumes on bottles/cans, standard sizes (Macau/HK café cups, 330ml cans, "
        "500ml/600ml bottles), hands and other objects for scale. If several drinks are shown, "
        "give the combined total. ml = your single best estimate, rounded to the nearest 10. "
        "container/drink: short descriptions in Traditional Chinese with English, e.g. "
        "\"玻璃杯 glass\", \"咖啡 coffee\". reasoning: one short sentence in Traditional Chinese."
    )
    content = await photo_content_blocks(bot, photos)
    content.append({"type": "text", "text": f"Caption: {caption or '(none)'}"})
    r = await asyncio.to_thread(
        claude.messages.create,
        **model_kwargs(MODEL_SMART, 500),
        system=system,
        messages=[{"role": "user", "content": content}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
        timeout=60.0,
    )
    raw = response_text(r)
    try:
        est = json.loads(raw)
    except Exception:
        logger.error(f"[Water] estimate returned non-JSON: {raw[:200]!r}")
        return raw or "抱歉，估算不到這張圖的水量。Sorry, I couldn't estimate this one."
    ml = int(est["ml"])
    logger.info(f"[Water] photo estimate: {est}")
    if ml <= 0:
        return (f"💧 這張圖看不到飲品。{est['reasoning']}\n"
                "I can't see a drink in this photo.")
    return (
        f"💧 估計約 {ml}ml — {est['drink']}，{est['container']}\n"
        f"{est['reasoning']}\n\n"
        f"要記錄的話請打 w{ml}（未記錄）。\n"
        f"Estimated ~{ml}ml. Not logged — send w{ml} to log it."
    )
