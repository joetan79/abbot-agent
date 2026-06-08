"""Proactive learning: log what the bot learns, gate web-sourced facts behind approval,
generate proactive suggestions based on conversation patterns."""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

LEARN_LOG_FILE = "data/learn_log.json"

_msg_counter = 0  # in-memory counter for proactive suggestion cadence


# ── Storage ───────────────────────────────────────────────────────────────────

def _load() -> dict:
    try:
        with open(LEARN_LOG_FILE) as f:
            return json.load(f)
    except Exception:
        return {"entries": []}


def _save(data: dict):
    tmp = LEARN_LOG_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, LEARN_LOG_FILE)
    except Exception as e:
        logger.error(f"[Learner] Save failed: {e}")


# ── Logging learnings ─────────────────────────────────────────────────────────

def log_learning(content: str, source_type: str = "conversation", source_url: str = None) -> str:
    """Record a learning. source_type='conversation' is auto-approved; 'web' needs approval."""
    data = _load()
    entry = {
        "id": f"learn_{int(datetime.now().timestamp())}",
        "timestamp": datetime.now().isoformat(),
        "source_type": source_type,
        "content": content[:500],
        "approved": True if source_type == "conversation" else None,
        "source_url": source_url,
    }
    data["entries"].append(entry)
    if len(data["entries"]) > 1000:
        data["entries"] = data["entries"][-1000:]
    _save(data)
    return entry["id"]


# ── Web approval management ───────────────────────────────────────────────────

def get_pending_web_approvals() -> list:
    data = _load()
    return [e for e in data["entries"] if e["source_type"] == "web" and e["approved"] is None]


def approve_learning(learn_id: str):
    data = _load()
    for e in data["entries"]:
        if e["id"] == learn_id:
            e["approved"] = True
            break
    _save(data)


def reject_learning(learn_id: str):
    data = _load()
    for e in data["entries"]:
        if e["id"] == learn_id:
            e["approved"] = False
            break
    _save(data)


def approve_all_pending():
    data = _load()
    changed = 0
    for e in data["entries"]:
        if e["source_type"] == "web" and e["approved"] is None:
            e["approved"] = True
            changed += 1
    _save(data)
    return changed


def reject_all_pending():
    data = _load()
    changed = 0
    for e in data["entries"]:
        if e["source_type"] == "web" and e["approved"] is None:
            e["approved"] = False
            changed += 1
    _save(data)
    return changed


# ── Weekly summary ────────────────────────────────────────────────────────────

def get_weekly_summary() -> dict:
    """Return a summary dict of learnings in the past 7 days."""
    data = _load()
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()
    recent = [e for e in data["entries"] if e.get("timestamp", "") >= cutoff]

    conv = [e for e in recent if e["source_type"] == "conversation"]
    web_approved = [e for e in recent if e["source_type"] == "web" and e.get("approved") is True]
    web_rejected = [e for e in recent if e["source_type"] == "web" and e.get("approved") is False]
    web_pending = [e for e in recent if e["source_type"] == "web" and e.get("approved") is None]

    return {
        "conversation_count": len(conv),
        "web_approved": web_approved,
        "web_rejected_count": len(web_rejected),
        "web_pending": web_pending,
        "sample_conv_learnings": [e["content"] for e in conv[-5:]],
    }


# ── Proactive suggestion ──────────────────────────────────────────────────────

def increment_msg_counter() -> int:
    global _msg_counter
    _msg_counter += 1
    return _msg_counter


def should_suggest() -> bool:
    """Fire every 8th conversational message."""
    return _msg_counter > 0 and _msg_counter % 8 == 0


def generate_proactive_suggestion(user_id: str, recent_text: str) -> str | None:
    """Analyse recent history and return ONE relevant suggestion, or None."""
    try:
        from modules.utils import ask_claude, MODEL_FAST, history_get
        history = history_get(user_id, limit=10)
        if len(history) < 4:
            return None
        history_text = "\n".join(
            f"{m['role']}: {m['content'][:120]}" for m in history[-8:]
        )
        prompt = (
            f"Conversation history:\n{history_text}\n\n"
            f"User's latest message: {recent_text}\n\n"
            "Based on this, generate ONE short proactive suggestion that would genuinely help this user. "
            "Good suggestions: notice a repeated request pattern and suggest scheduling it, "
            "spot a follow-up the user might want, suggest a relevant quiz topic change, "
            "or predict something useful based on clear context.\n\n"
            "Rules:\n"
            "- Only suggest if there is a CLEAR pattern or obvious follow-up\n"
            "- If nothing genuinely useful, reply exactly: NONE\n"
            "- Max 2 sentences, start with 💡\n"
            "- Be specific, not generic ('You might want to know more' is not acceptable)"
        )
        result = ask_claude(
            "You are a smart assistant that notices patterns in conversations.",
            prompt, model=MODEL_FAST, max_tokens=120
        )
        result = result.strip()
        if not result or result.startswith("NONE") or "NONE" in result[:15]:
            return None
        return result
    except Exception as e:
        logger.error(f"[Learner] Proactive suggestion error: {e}")
        return None


# ── Web learning check (async, runs after web-search replies) ─────────────────

async def check_and_prompt_web_learning(bot, chat_id: int, reply: str, query: str):
    """Background task: check if a web-search reply contains a saveable long-term fact.
    If yes, ask the user for approval."""
    try:
        from modules.utils import ask_claude, MODEL_FAST
        prompt = (
            f"User asked: {query}\n\nBot replied: {reply[:600]}\n\n"
            "Does this reply contain a specific fact about the USER'S preferences, habits, interests, "
            "or personal context that would be worth remembering long-term? "
            "(NOT general knowledge, NOT current prices/news — only user-specific learnable facts.)\n\n"
            "If yes: reply with just the fact in one sentence starting with SAVE:\n"
            "If no: reply exactly: NONE"
        )
        result = ask_claude(
            "You identify user-specific facts worth remembering.",
            prompt, model=MODEL_FAST, max_tokens=80
        )
        result = result.strip()
        if not result or result.startswith("NONE") or "NONE" in result[:10]:
            return
        if not result.startswith("SAVE:"):
            return
        fact = result[5:].strip()
        if not fact:
            return

        learn_id = log_learning(fact, source_type="web")
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"🌐 I found something that might be worth remembering:\n\n"
                f"_{fact}_\n\n"
                f"Save this? Reply *yes save* or *no skip*.\n"
                f"(ID: `{learn_id}`)"
            ),
            parse_mode="Markdown"
        )
        logger.info(f"[Learner] Web learning approval requested: {learn_id}")
    except Exception as e:
        logger.error(f"[Learner] Web learning check failed: {e}")
