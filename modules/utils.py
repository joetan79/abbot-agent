"""Shared helpers: Claude API, auth, persistent memory, tasks, schedules."""

import os, json, re, logging
from datetime import datetime
from pathlib import Path
import anthropic

logger = logging.getLogger(__name__)

# Model selection
MODEL_FAST = "claude-haiku-4-5-20251001"   # Simple tasks
MODEL_SMART = "claude-sonnet-4-5"           # Complex tasks


def clean_response(text: str) -> str:
    # Remove citation tags like <cite index="0-1">...</cite>
    text = re.sub(r'<cite[^>]*>', '', text)
    text = re.sub(r'</cite>', '', text)
    # Remove any other HTML-like tags
    text = re.sub(r'<[^>]+>', '', text)
    # Remove Claude thinking/searching phrases line by line
    skip_phrases = [
        "i'll search",
        "i need to search",
        "based on the search",
        "i'm searching",
        "let me search",
        "i will search",
        "search results i've",
        "i'm unable to find",
        "i cannot find",
        "to get the specific",
        "i recommend checking",
        "these sources would",
        "without access to real-time",
    ]
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        line_lower = line.lower().strip()
        if any(phrase in line_lower for phrase in skip_phrases):
            continue
        cleaned_lines.append(line)
    text = '\n'.join(cleaned_lines)
    # Remove multiple spaces left behind
    text = re.sub(r' +', ' ', text)
    # Remove multiple newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

def ask_claude(system: str, user_msg: str, max_tokens: int = 1500,
               model: str = None) -> str:
    if model is None:
        model = MODEL_FAST
    logger.info(f"Using model: {model} | task: {user_msg[:50]}")
    try:
        r = claude.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        return r.content[0].text
    except Exception as e:
        logger.error(f"Claude error ({model}): {e}")
        return "⚠️ Couldn't reach Claude. Please try again."

ALLOWED_CHAT_IDS = set(
    int(x) for x in os.environ.get("ALLOWED_CHAT_IDS", "").split(",") if x.strip()
)
OWNER_CHAT_ID = int(os.environ.get("OWNER_CHAT_ID", "0"))

def is_allowed(chat_id: int) -> bool:
    return (not ALLOWED_CHAT_IDS) or (chat_id in ALLOWED_CHAT_IDS)

def is_owner(chat_id: int) -> bool:
    return chat_id == OWNER_CHAT_ID

DATA_DIR          = Path("data")
MEMORY_FILE       = DATA_DIR / "memory.json"
PREFERENCES_FILE  = DATA_DIR / "preferences.json"
SCHEDULE_FILE     = DATA_DIR / "schedules.json"
TASKS_FILE        = DATA_DIR / "tasks.json"
CACHE_FILE        = DATA_DIR / "news_cache.json"
DATA_DIR.mkdir(exist_ok=True)

def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except Exception:
        return {}

def _save(path: Path, data: dict):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

def memory_set(key: str, value):
    mem = _load(MEMORY_FILE)
    mem[key] = {"value": value, "updated": datetime.now().isoformat()}
    _save(MEMORY_FILE, mem)

def memory_get(key: str, default=None):
    entry = _load(MEMORY_FILE).get(key)
    return entry["value"] if entry else default

def memory_all() -> dict:
    return {k: v["value"] for k, v in _load(MEMORY_FILE).items()}

def memory_delete(key: str):
    mem = _load(MEMORY_FILE)
    mem.pop(key, None)
    _save(MEMORY_FILE, mem)

def preference_set(key: str, value: str):
    """Store a long-term preference that persists and is always injected into prompts."""
    prefs = _load(PREFERENCES_FILE)
    prefs[key] = {"value": value, "updated": datetime.now().isoformat()}
    _save(PREFERENCES_FILE, prefs)
    memory_set(key, value)  # Also save to memory for backward compatibility
    logger.info(f"Preference saved: {key} = {value}")

def preference_get(key: str, default=None):
    prefs = _load(PREFERENCES_FILE)
    entry = prefs.get(key)
    return entry["value"] if entry else default

def preference_all() -> dict:
    prefs = _load(PREFERENCES_FILE)
    return {k: v["value"] for k, v in prefs.items()}

def get_preferences_prompt() -> str:
    """Build a preferences string from memory/preferences to inject into every system prompt."""
    prefs = preference_all()
    mem = memory_all()
    # Merge both; preferences.json takes priority over memory.json
    all_prefs = {**mem, **prefs}
    if not all_prefs:
        return ""
    lines = ["CRITICAL PREFERENCES - ALWAYS FOLLOW THESE:"]
    for key, value in all_prefs.items():
        lines.append(f"  * {key}: {value}")
    lines.append(
        "These are permanent preferences. NEVER ignore them in any response."
    )
    return "\n".join(lines)

def schedule_save(job_id: str, data: dict):
    jobs = _load(SCHEDULE_FILE)
    jobs[job_id] = data
    _save(SCHEDULE_FILE, jobs)

def schedule_load_all() -> dict:
    return _load(SCHEDULE_FILE)

def schedule_delete(job_id: str):
    jobs = _load(SCHEDULE_FILE)
    jobs.pop(job_id, None)
    _save(SCHEDULE_FILE, jobs)

def task_add(text: str) -> str:
    tasks = _load(TASKS_FILE)
    tid = str(int(datetime.now().timestamp()))
    tasks[tid] = {"text": text, "done": False, "created": datetime.now().isoformat()}
    _save(TASKS_FILE, tasks)
    return tid

def task_done(tid: str) -> bool:
    tasks = _load(TASKS_FILE)
    if tid in tasks:
        tasks[tid]["done"] = True
        tasks[tid]["completed"] = datetime.now().isoformat()
        _save(TASKS_FILE, tasks)
        return True
    return False

def task_list(show_done=False) -> list:
    tasks = _load(TASKS_FILE)
    result = [{"id": k, **v} for k, v in tasks.items() if show_done or not v["done"]]
    return sorted(result, key=lambda x: x["created"])

def task_delete(tid: str) -> bool:
    tasks = _load(TASKS_FILE)
    if tid in tasks:
        del tasks[tid]
        _save(TASKS_FILE, tasks)
        return True
    return False

async def handle_photo(bot, photo, caption: str = "") -> str:
    """Download photo from Telegram and send to Claude for analysis."""
    try:
        import base64
        # Get highest resolution photo
        file = await bot.get_file(photo[-1].file_id)
        
        # Download image bytes
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(file.file_path)
            image_data = base64.standard_b64encode(response.content).decode("utf-8")
        
        # Send to Claude with vision
        r = claude.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1500,
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
                    {
                        "type": "text",
                        "text": caption if caption else "Please describe and analyse this image in detail."
                    }
                ],
            }],
        )
        return r.content[0].text
    except Exception as e:
        logger.error(f"Photo handling error: {e}")
        return "Sorry, I couldn't process that image. Please try again."

# ── Conversation History ──────────────────────────────────────────────────────
HISTORY_FILE = DATA_DIR / "history.json"
MAX_HISTORY  = 50  # messages per user

def history_add(user_id: str, role: str, content: str):
    """Add a message to conversation history."""
    history = _load(HISTORY_FILE)
    if user_id not in history:
        history[user_id] = []
    history[user_id].append({
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat()
    })
    # Keep only last MAX_HISTORY messages
    if len(history[user_id]) > MAX_HISTORY:
        history[user_id] = history[user_id][-MAX_HISTORY:]
    _save(HISTORY_FILE, history)

def history_get(user_id: str, limit: int = 20) -> list:
    """Get recent conversation history for a user."""
    history = _load(HISTORY_FILE)
    messages = history.get(user_id, [])
    # Return in Claude API format (without timestamp)
    return [
        {"role": m["role"], "content": m["content"]}
        for m in messages[-limit:]
    ]

def history_clear(user_id: str):
    """Clear conversation history for a user."""
    history = _load(HISTORY_FILE)
    history[user_id] = []
    _save(HISTORY_FILE, history)

def history_summary(user_id: str) -> str:
    """Get a text summary of recent history for context injection."""
    messages = history_get(user_id, limit=10)
    if not messages:
        return "No previous conversation."
    lines = []
    for m in messages:
        role = "You" if m["role"] == "assistant" else "User"
        # Truncate long messages
        content = m["content"][:200] + "..." if len(m["content"]) > 200 else m["content"]
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def ask_claude_with_history(system: str, user_msg: str,
                             user_id: str, max_tokens: int = 1500,
                             model: str = None) -> str:
    """Send message to Claude with full conversation history for context."""
    if model is None:
        model = MODEL_SMART
    try:
        history = history_get(user_id, limit=20)
        messages = history + [{"role": "user", "content": user_msg}]
        r = claude.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        response_text = r.content[0].text
        history_add(user_id, "user", user_msg)
        history_add(user_id, "assistant", response_text)
        return response_text
    except Exception as e:
        logger.error(f"Claude history error ({model}): {e}")
        return "Sorry, I could not process that. Please try again."


def auto_extract_memory(user_id: str, text: str):
    """Automatically extract and save useful facts from conversation."""
    system = """Extract personal facts or preferences from this message worth remembering long term.
Return ONLY valid JSON array:
[
  {"key": "chinese_script", "value": "Traditional Chinese", "is_preference": true},
  {"key": "city", "value": "Kuala Lumpur", "is_preference": false}
]
is_preference=true for strong preferences (language, format, style rules).
is_preference=false for facts (city, name, job).
If nothing to remember return: []
Only extract clear explicit facts."""
    try:
        raw = ask_claude(system, text, max_tokens=300, model=MODEL_FAST)
        raw = raw.strip().strip("```json").strip("```").strip()
        import json
        facts = json.loads(raw)
        for fact in facts:
            if "key" in fact and "value" in fact:
                memory_set(fact["key"], fact["value"])
                if fact.get("is_preference"):
                    preference_set(fact["key"], fact["value"])
                logger.info(
                    f"Auto-extracted: {fact['key']} = {fact['value']} "
                    f"(pref: {fact.get('is_preference')})"
                )
    except Exception:
        pass  # Silent fail — not critical


def ask_claude_with_search(system: str, user_msg: str,
                            user_id: str = None, max_tokens: int = 1500,
                            model: str = None) -> str:
    """Ask Claude with web search tool enabled for real-time data."""
    if model is None:
        model = MODEL_FAST
    try:
        # Build messages with history if user_id provided
        if user_id:
            history = history_get(user_id, limit=10)
            messages = history + [{"role": "user", "content": user_msg}]
        else:
            messages = [{"role": "user", "content": user_msg}]

        r = claude.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            tools=[{
                "type": "web_search_20250305",
                "name": "web_search"
            }],
            messages=messages,
        )

        # Extract all text from response blocks
        full_response = ""
        for block in r.content:
            if hasattr(block, "type") and block.type == "text":
                full_response += block.text

        # Clean citation/HTML tags from response
        full_response = clean_response(full_response)

        # Save to history if user_id provided
        if user_id and full_response:
            history_add(user_id, "user", user_msg)
            history_add(user_id, "assistant", full_response)

        return full_response or "Sorry, I could not find results for that."
    except Exception as e:
        logger.error(f"Web search error: {e}")
        # Fallback to regular Claude without search
        return ask_claude(system, user_msg, max_tokens, model=model)


def get_cached_news(cache_key: str, max_age_hours: int = 6) -> str | None:
    cache = _load(CACHE_FILE)
    if cache_key in cache:
        cached_time = datetime.fromisoformat(cache[cache_key]["timestamp"])
        age_hours = (datetime.now() - cached_time).total_seconds() / 3600
        if age_hours < max_age_hours:
            logger.info(f"Using cached news: {cache_key}")
            return cache[cache_key]["content"]
    return None


def set_cached_news(cache_key: str, content: str):
    cache = _load(CACHE_FILE)
    cache[cache_key] = {
        "content": content,
        "timestamp": datetime.now().isoformat()
    }
    _save(CACHE_FILE, cache)


def ask_claude_news(system: str, user_msg: str, max_tokens: int = 1500) -> str:
    """Use Haiku model for news - much cheaper for high input token tasks like web search."""
    try:
        r = claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=max_tokens,
            system=system,
            tools=[{
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 3,
            }],
            messages=[{"role": "user", "content": user_msg}],
        )
        full_response = ""
        for block in r.content:
            if hasattr(block, "type") and block.type == "text":
                full_response += block.text
        full_response = clean_response(full_response)
        return full_response or "Could not retrieve news."
    except Exception as e:
        logger.error(f"News fetch error: {e}")
        return ask_claude(system, user_msg, max_tokens)
