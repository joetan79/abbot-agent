"""Long-term episodic memory: compresses weekly conversations into persistent summaries
that survive restarts and give ABbot memory spanning months."""

import json
import logging
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
EPISODIC_FILE = "data/episodic_memory.json"


def _load() -> dict:
    try:
        with open(EPISODIC_FILE) as f:
            return json.load(f)
    except Exception:
        return {"weeks": []}


def _save(data: dict):
    tmp = EPISODIC_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, EPISODIC_FILE)
    except Exception as e:
        logger.error(f"[Episodic] Save failed: {e}")


def compress_week():
    """Read the past 7 days of learn_log + memories and compress into a summary.
    Called by the weekly scheduled job (Monday). One MODEL_SMART call."""
    try:
        from modules.utils import ask_claude, MODEL_SMART, MEMORY_FILE, HISTORY_FILE, OWNER_CHAT_ID, _load as _load_json
        from modules.learner import get_weekly_summary

        # Gather source material
        ls = get_weekly_summary()
        conv_items = ls.get("sample_conv_learnings", [])
        approved_web = [e["content"] for e in ls.get("web_approved", [])]

        # Memories saved/updated this week, and Joe's own chat messages from
        # the week. This used to read data/memory_categorized.json, which
        # doesn't exist (memories live in memory.json), so memories never
        # reached the weekly summary at all.
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        recent_mem = []
        try:
            for k, v in _load_json(MEMORY_FILE).items():
                if isinstance(v, dict) and v.get("updated", "") >= week_ago:
                    recent_mem.append(f"[memory] {k}: {v.get('value')}")
        except Exception:
            pass
        joe_msgs = []
        try:
            for m in _load_json(HISTORY_FILE).get(str(OWNER_CHAT_ID), []):
                if m.get("role") == "user" and m.get("timestamp", "") >= week_ago:
                    joe_msgs.append(f"[Joe said] {m['content'][:300]}")
        except Exception:
            pass

        if not conv_items and not approved_web and not recent_mem and not joe_msgs:
            logger.info("[Episodic] Nothing to compress this week")
            return

        source = "\n".join(
            recent_mem[:30] + joe_msgs[-25:] + conv_items[:10] + approved_web[:5]
        )

        prompt = (
            "Summarise what was learned about this user (Joe) this week into 5-8 concise bullet points.\n"
            "Focus on: interests, preferences, patterns, goals, what he was working on.\n"
            "Be specific — avoid vague statements like 'interested in technology'.\n"
            "Only include things that say something lasting about Joe or his family — skip "
            "one-off requests (weather lookups, a single quiz) and bot/setup chatter.\n"
            "If there is nothing meaningful, output exactly: NONE\n\n"
            f"Source material:\n{source}\n\n"
            "Output bullet points only, one per line, starting with •"
        )

        summary = ask_claude(
            "You are a concise memory summariser. Output bullet points only.",
            prompt, model=MODEL_SMART, max_tokens=400
        )
        # Don't store "no information this week" filler — it was being
        # injected into every chat's system prompt as LONG-TERM MEMORY.
        if summary.strip().upper().startswith("NONE") or "•" not in summary:
            logger.info("[Episodic] Nothing meaningful this week — not saved")
            return

        week_str = datetime.now().strftime("%Y-W%W")
        data = _load()
        # Replace existing entry for this week if re-run
        data["weeks"] = [w for w in data["weeks"] if w.get("week") != week_str]
        data["weeks"].append({
            "week": week_str,
            "period": f"{(datetime.now() - timedelta(days=7)).strftime('%d %b')} – {datetime.now().strftime('%d %b %Y')}",
            "summary": summary.strip(),
            "compressed_at": datetime.now().isoformat(),
        })
        # Keep last 12 weeks
        data["weeks"] = data["weeks"][-12:]
        _save(data)
        logger.info(f"[Episodic] Week {week_str} compressed")
        return summary
    except Exception as e:
        logger.error(f"[Episodic] Compression failed: {e}")
        return None


def get_episodic_context() -> str:
    """Returns the last 3 weekly summaries for injection into the system prompt."""
    data = _load()
    weeks = data.get("weeks", [])[-3:]
    if not weeks:
        return ""
    lines = ["LONG-TERM MEMORY (who Joe is, built from past conversations):"]
    for w in reversed(weeks):
        lines.append(f"\n[{w['period']}]")
        lines.append(w.get("summary", "").strip())
    return "\n".join(lines)


def get_full_memory() -> str:
    """Returns all stored episodic weeks — for 'what do you know about me?' queries."""
    data = _load()
    weeks = data.get("weeks", [])
    if not weeks:
        return "No episodic memory built yet. It compresses weekly every Monday."
    lines = ["📖 Everything I know about you (built over time):\n"]
    for w in reversed(weeks):
        lines.append(f"── {w['period']} ──")
        lines.append(w.get("summary", "").strip())
        lines.append("")
    return "\n".join(lines)
