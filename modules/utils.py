"""Shared helpers: Claude API, auth, persistent memory, tasks, schedules."""

import os, json, re, logging, time
from datetime import datetime
from pathlib import Path
import anthropic

logger = logging.getLogger(__name__)

# Model selection
MODEL_FAST    = "claude-haiku-4-5-20251001"   # Simple tasks
MODEL_SMART   = "claude-sonnet-4-5"            # Complex tasks + vision
MODEL_PREMIUM = "claude-haiku-4-5-20251001"     # AI Pulse & Updates (xfeed)

# ── Memory Categories ─────────────────────────────────────────────────────────
MEMORY_CATEGORIES = {
    "health": [
        "meal", "food", "diet", "eat", "drink",
        "medication", "medicine", "pill", "vitamin",
        "exercise", "workout", "sleep", "health",
        "doctor", "hospital", "sick", "weight",
        "allergy", "supplement", "nutrition",
    ],
    "personal": [
        "name", "wife", "husband", "child", "son",
        "daughter", "family", "parent", "brother",
        "sister", "friend", "birthday", "anniversary",
        "address", "phone", "email", "hobby",
        "interest", "preference", "like", "dislike",
    ],
    "work": [
        "work", "job", "office", "meeting", "project",
        "deadline", "client", "boss", "team", "task",
        "report", "presentation", "conference", "call",
        "business", "company", "colleague", "manager",
    ],
    "finance": [
        "money", "budget", "expense", "income", "salary",
        "investment", "saving", "bank", "loan", "debt",
        "credit", "payment", "bill", "tax", "cost",
        "finance", "financial", "spend", "profit",
    ],
    "travel": [
        "travel", "trip", "flight", "hotel", "visa",
        "passport", "holiday", "vacation", "destination",
        "airport", "booking", "ticket", "tour", "city",
    ],
    "schedule": [
        "schedule", "calendar", "appointment", "reminder",
        "time", "daily", "weekly", "routine", "habit",
        "morning", "evening", "night", "lunch", "dinner",
    ],
    "learning": [
        "study", "learn", "course", "book", "read",
        "class", "exam", "test", "school", "university",
        "skill", "language", "practice", "homework",
    ],
    "preferences": [
        "prefer", "always", "never", "must", "should",
        "format", "style", "tone", "language", "unit",
        "celsius", "fahrenheit", "traditional", "simplified",
    ],
}


def categorize_memory(key: str, value: str) -> str:
    """Determine category of a memory entry."""
    text = (key + " " + str(value)).lower()
    scores = {}
    for category, keywords in MEMORY_CATEGORIES.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[category] = score
    if not scores:
        return "general"
    return max(scores, key=scores.get)


def memory_set_categorized(key: str, value):
    """Save memory with auto-category tagging."""
    mem = _load(MEMORY_FILE)
    category = categorize_memory(key, str(value))
    mem[key] = {
        "value": value,
        "category": category,
        "updated": datetime.now().isoformat()
    }
    _save(MEMORY_FILE, mem)
    logger.info(
        f"Memory saved: [{category}] "
        f"{key} = {str(value)[:50]}"
    )


def parse_duration_to_seconds(text: str) -> int | None:
    """Parse strings like '30 minutes', '2 hours', '1 day' into seconds.
    Returns None if not parseable. Handles Chinese units too."""
    text = text.lower().strip()
    patterns = [
        (r'(\d+)\s*(?:s|sec|second|seconds)', 1),
        (r'(\d+)\s*(?:m|min|minute|minutes)', 60),
        (r'(\d+)\s*(?:h|hr|hour|hours)', 3600),
        (r'(\d+)\s*(?:d|day|days)', 86400),
        (r'(\d+)\s*秒', 1),
        (r'(\d+)\s*分(?:钟|鐘)?', 60),
        (r'(\d+)\s*(?:小时|小時|时|時)', 3600),
        (r'(\d+)\s*天', 86400),
    ]
    for pat, mult in patterns:
        m = re.search(pat, text)
        if m:
            return int(m.group(1)) * mult
    return None


def clean_response(text: str) -> str:
    # Remove citation tags like <cite index="0-1">...</cite>
    text = re.sub(r'<cite[^>]*>', '', text)
    text = re.sub(r'</cite>', '', text)
    # Remove any other HTML-like tags
    text = re.sub(r'<[^>]+>', '', text)
    # Remove markdown bold **text**
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    # Remove markdown italic *text*
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    # Remove markdown headers ## text
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
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
        "here are the top",
        "here are some",
        "based on my",
        "i recommend checking",
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

# In-memory counter for API failures — read by the health monitor periodic check
_api_fail_counts: dict[str, int] = {}

def _record_api_fail(error_type: str):
    _api_fail_counts[error_type] = _api_fail_counts.get(error_type, 0) + 1

def get_and_reset_api_fails() -> dict[str, int]:
    """Return current failure counts and reset them."""
    counts = dict(_api_fail_counts)
    _api_fail_counts.clear()
    return counts


def ask_claude(system: str, user_msg: str, max_tokens: int = 1500,
               model: str = None, max_retries: int = 2) -> str:
    if model is None:
        model = MODEL_FAST
    logger.info(f"Using model: {model} | task: {user_msg[:50]}")
    for attempt in range(max_retries + 1):
        try:
            r = claude.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
                timeout=30.0,
            )
            return r.content[0].text
        except anthropic.APITimeoutError:
            logger.warning(
                f"Claude timeout attempt {attempt+1}/{max_retries+1}")
            if attempt < max_retries:
                time.sleep(2)
                continue
            _record_api_fail("timeout")
            return "Sorry, response timed out. Please try again."
        except anthropic.RateLimitError:
            logger.warning("Rate limit hit")
            if attempt < max_retries:
                time.sleep(5)
                continue
            _record_api_fail("rate_limit")
            return "Too many requests. Please wait a moment and try again."
        except Exception as e:
            logger.error(f"Claude error ({model}): {e}")
            if attempt < max_retries:
                time.sleep(1)
                continue
            if "529" in str(e) or "overload" in str(e).lower():
                _record_api_fail("overload_529")
            else:
                _record_api_fail("api_error")
            return "Sorry, I had trouble responding. Please try again."
    return "Sorry, please try again."

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
CACHE_FILE              = DATA_DIR / "news_cache.json"
PUBLISHED_ARTICLES_FILE = DATA_DIR / "published_articles.json"
ARTICLE_STATS_FILE      = DATA_DIR / "article_stats.json"
TIME_WINDOWS_FILE = DATA_DIR / "time_windows.json"
PHOTO_CACHE_FILE  = DATA_DIR / "photo_cache.json"
DATA_DIR.mkdir(exist_ok=True)

DEFAULT_TIME_WINDOWS = {
    "meal":       {"hours": 16, "label": "meal"},
    "food":       {"hours": 16, "label": "meal"},
    "fasting":    {"hours": 16, "label": "meal"},
    "breakfast":  {"hours": 16, "label": "meal"},
    "lunch":      {"hours": 16, "label": "meal"},
    "dinner":     {"hours": 16, "label": "meal"},
    "supper":     {"hours": 16, "label": "meal"},
    "study":      {"hours": 4,  "label": "study"},
    "homework":   {"hours": 4,  "label": "study"},
    "learning":   {"hours": 4,  "label": "study"},
    "revision":   {"hours": 4,  "label": "study"},
    "exercise":   {"hours": 48, "label": "exercise"},
    "workout":    {"hours": 48, "label": "exercise"},
    "gym":        {"hours": 48, "label": "exercise"},
    "run":        {"hours": 48, "label": "exercise"},
    "medication": {"hours": 8,  "label": "medication"},
    "medicine":   {"hours": 8,  "label": "medication"},
    "pill":       {"hours": 8,  "label": "medication"},
    "vitamin":    {"hours": 24, "label": "vitamin"},
    "supplement": {"hours": 24, "label": "vitamin"},
    "sleep":      {"hours": 16, "label": "sleep"},
    "nap":        {"hours": 4,  "label": "nap"},
    "rest":       {"hours": 8,  "label": "rest"},
    "work":       {"hours": 14, "label": "work"},
    "prayer":     {"hours": 6,  "label": "prayer"},
    "water":      {"hours": 2,  "label": "water"},
    "drink":      {"hours": 2,  "label": "water"},
    "break":      {"hours": 2,  "label": "break"},
    "meeting":    {"hours": 24, "label": "meeting"},
    "reading":    {"hours": 4,  "label": "reading"},
}


def save_time_window(
        activity: str,
        hours: float,
        label: str = "") -> bool:
    try:
        windows = _load(TIME_WINDOWS_FILE)
        key = activity.lower().strip()
        old_hours = None
        if key in windows:
            old_val = windows[key]
            if isinstance(old_val, dict):
                old_hours = old_val.get("hours")
        windows[key] = {
            "hours": hours,
            "label": label or key,
            "updated": datetime.now().isoformat(),
            "custom": True,
        }
        _save(TIME_WINDOWS_FILE, windows)
        if old_hours and old_hours != hours:
            logger.info(
                f"Window updated: "
                f"{key} {old_hours}hrs→{hours}hrs"
            )
        else:
            logger.info(
                f"Window saved: {key}={hours}hrs"
            )
        return True
    except Exception as e:
        logger.error(
            f"Save time window error: {e}")
        return False


def get_time_window(activity: str) -> dict | None:
    key = activity.lower().strip()
    custom = _load(TIME_WINDOWS_FILE)
    if key in custom:
        return custom[key]
    for ckey, cval in custom.items():
        if ckey in key or key in ckey:
            return cval
    if key in DEFAULT_TIME_WINDOWS:
        return DEFAULT_TIME_WINDOWS[key]
    for dkey, dval in DEFAULT_TIME_WINDOWS.items():
        if dkey in key or key in dkey:
            return dval
    return None


def get_all_time_windows() -> dict:
    custom = _load(TIME_WINDOWS_FILE)
    return {**DEFAULT_TIME_WINDOWS, **custom}


def delete_time_window(activity: str) -> bool:
    windows = _load(TIME_WINDOWS_FILE)
    key = activity.lower().strip()
    if key in windows:
        del windows[key]
        _save(TIME_WINDOWS_FILE, windows)
        return True
    return False

def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except Exception:
        return {}

def _save(path: Path, data: dict):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

def memory_set(key: str, value):
    """Save memory with auto-categorization."""
    mem = _load(MEMORY_FILE)
    category = categorize_memory(key, str(value))
    mem[key] = {
        "value": value,
        "category": category,
        "updated": datetime.now().isoformat()
    }
    _save(MEMORY_FILE, mem)

def memory_get(key: str, default=None):
    """Get memory value, handles both formats."""
    entry = _load(MEMORY_FILE).get(key)
    if entry is None:
        return default
    if isinstance(entry, dict):
        return entry.get("value", default)
    return entry  # old format compatibility

def memory_all() -> dict:
    """Get all memories as key:value dict."""
    mem = _load(MEMORY_FILE)
    result = {}
    for k, v in mem.items():
        if isinstance(v, dict):
            result[k] = v.get("value", "")
        else:
            result[k] = v
    return result

def memory_delete(key: str):
    mem = _load(MEMORY_FILE)
    mem.pop(key, None)
    _save(MEMORY_FILE, mem)

def memory_get_by_category(category: str) -> dict:
    """Get all memory entries for a category."""
    mem = _load(MEMORY_FILE)
    result = {}
    for key, data in mem.items():
        if isinstance(data, dict):
            mem_cat = data.get(
                "category",
                categorize_memory(key, str(data.get("value", "")))
            )
            if mem_cat == category:
                result[key] = data.get("value", "")
        else:
            if categorize_memory(key, str(data)) == category:
                result[key] = data
    return result

def memory_get_all_categorized() -> dict:
    """Get all memories organized by category."""
    mem = _load(MEMORY_FILE)
    categorized = {}
    for key, data in mem.items():
        if isinstance(data, dict):
            value = data.get("value", "")
            cat = data.get(
                "category",
                categorize_memory(key, str(value))
            )
        else:
            value = data
            cat = categorize_memory(key, str(data))
        if cat not in categorized:
            categorized[cat] = {}
        categorized[cat][key] = value
    return categorized

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


def get_core_preferences() -> str:
    """
    Get only core preference memories.
    Used when no specific category detected.
    Minimal token usage.
    """
    all_mem = _load(MEMORY_FILE)
    core_entries = {}
    for key, data in all_mem.items():
        if isinstance(data, dict):
            value = data.get("value", "")
            cat = data.get(
                "category",
                categorize_memory(key, str(value))
            )
        else:
            value = data
            cat = categorize_memory(key, str(data))
        if cat == "preferences":
            core_entries[key] = value
    if not core_entries:
        return ""
    lines = ["CORE PREFERENCES:"]
    for k, v in list(core_entries.items())[:10]:
        lines.append(f"- {k}: {v}")
    return "\n".join(lines)


def get_relevant_memories(
        query: str,
        max_categories: int = 3,
        max_entries_per_category: int = 5) -> str:
    """
    Get memories most relevant to the query.
    Uses 3-layer selective injection to control token cost.

    Layer 1 — Category keyword match:
      Score query against category keyword lists.
      Inject top matching categories.

    Layer 2 — Direct key/value text search:
      Search query words directly in all memory
      keys and values. Catches named things like
      "Whiskers", "ABC 1234" with no category hit.

    Layer 3 — Safety net:
      If nothing matched, return 3 most recently
      updated memories so context is never empty.
    """
    if not query:
        return get_core_preferences()

    query_lower = query.lower()
    # Meaningful words only (skip single/two-char words)
    query_words = [w for w in query_lower.split() if len(w) > 2]

    all_mem = _load(MEMORY_FILE)
    result_lines = []
    total_entries = 0
    matched_keys: set = set()
    # Tracks whether a specific/intentional match was found
    # (beyond the automatic preferences baseline).
    # Layer 3 fires when this stays False.
    has_specific_match = False

    # ── Layer 1: Category keyword scoring ────────────────────────────────────
    category_scores = {}
    for category, keywords in MEMORY_CATEGORIES.items():
        score = sum(1 for kw in keywords if kw in query_lower)
        if score > 0:
            category_scores[category] = score

    # Always include preferences (minimal baseline).
    # Adding +1 means it never scores zero, but real hits
    # (other categories or direct text) outscore it.
    category_scores["preferences"] = \
        category_scores.get("preferences", 0) + 1

    top_categories = sorted(
        category_scores.items(),
        key=lambda x: x[1],
        reverse=True
    )[:max_categories]

    for category, score in top_categories:
        cat_entries = {}
        for key, data in all_mem.items():
            if isinstance(data, dict):
                value = data.get("value", "")
                mem_cat = data.get(
                    "category",
                    categorize_memory(key, str(value))
                )
            else:
                value = data
                mem_cat = categorize_memory(key, str(data))
            if mem_cat == category:
                cat_entries[key] = value

        if cat_entries:
            limited = dict(
                list(cat_entries.items())[:max_entries_per_category]
            )
            result_lines.append(f"\n[{category.upper()} MEMORIES]")
            for k, v in limited.items():
                result_lines.append(f"- {k}: {v}")
                matched_keys.add(k)
            total_entries += len(limited)
            # Preferences is always included as baseline,
            # so only count other categories as specific matches.
            if category != "preferences":
                has_specific_match = True

    # ── Layer 2: Direct key/value text search ────────────────────────────────
    # Catches named things ("Whiskers", "ABC 1234") that have no category hit.
    if query_words:
        direct_matches = {}
        for key, data in all_mem.items():
            if key in matched_keys:
                continue  # already included from Layer 1
            if isinstance(data, dict):
                value = data.get("value", "")
            else:
                value = data
            key_lower = key.lower()
            val_lower = str(value).lower()
            if any(
                word in key_lower or word in val_lower
                for word in query_words
            ):
                direct_matches[key] = value

        if direct_matches:
            result_lines.append("\n[DIRECT MATCHES]")
            for k, v in list(direct_matches.items())[:5]:
                result_lines.append(f"- {k}: {v}")
                matched_keys.add(k)
            total_entries += len(direct_matches)
            has_specific_match = True

    # ── Layer 3: Safety net — 3 most recent memories ─────────────────────────
    # Fires when neither L1 (beyond preferences) nor L2 found anything.
    # Ensures the response always has some useful personal context.
    if not has_specific_match:
        recent = []
        for key, data in all_mem.items():
            if key in matched_keys:
                continue  # skip already-shown preference entries
            if isinstance(data, dict):
                value = data.get("value", "")
                updated = data.get("updated", "")
            else:
                value = data
                updated = ""
            recent.append((key, value, updated))
        recent.sort(key=lambda x: x[2], reverse=True)
        if recent:
            result_lines.append("\n[RECENT MEMORIES]")
            for k, v, _ in recent[:3]:
                result_lines.append(f"- {k}: {v}")
            total_entries += min(3, len(recent))

    if not result_lines:
        return get_core_preferences()

    logger.debug(
        f"Memory injection: {total_entries} entries "
        f"(~{total_entries * 15} tokens)"
    )

    return (
        "RELEVANT MEMORIES (use these in response):\n" +
        "\n".join(result_lines)
    )

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
            model=MODEL_SMART,
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


def photo_cache_set(message_id: int, file_id: str):
    cache = _load(PHOTO_CACHE_FILE)
    cache[str(message_id)] = file_id
    # Keep at most 200 entries to avoid unbounded growth
    if len(cache) > 200:
        oldest_keys = list(cache.keys())[:-200]
        for k in oldest_keys:
            del cache[k]
    _save(PHOTO_CACHE_FILE, cache)


def photo_cache_get(message_id: int) -> str | None:
    cache = _load(PHOTO_CACHE_FILE)
    return cache.get(str(message_id))


async def handle_photo_reanalysis(bot, file_id: str, user_question: str) -> str:
    """Re-analyze a cached photo with a follow-up question or correction."""
    try:
        import base64
        import httpx
        file = await bot.get_file(file_id)
        async with httpx.AsyncClient() as client:
            response = await client.get(file.file_path)
            image_data = base64.standard_b64encode(response.content).decode("utf-8")

        prompt = (
            f"The user has a follow-up about this image:\n\n{user_question}\n\n"
            "Please look at the image carefully and answer accurately."
        )
        r = claude.messages.create(
            model=MODEL_SMART,
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
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        return r.content[0].text
    except Exception as e:
        logger.error(f"Photo re-analysis error: {e}")
        return "Sorry, I couldn't re-analyse that image. Please try again."


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
                             model: str = None,
                             max_retries: int = 1,
                             history_text: str = None) -> str:
    """Send message to Claude with full conversation history for context.
    history_text: if provided, saved to history instead of user_msg (keeps history clean of quoted-context prefixes)."""
    if model is None:
        model = MODEL_SMART
    save_text = history_text if history_text is not None else user_msg
    for attempt in range(max_retries + 1):
        try:
            history = history_get(user_id, limit=10)
            messages = history + [{"role": "user", "content": user_msg}]
            r = claude.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                timeout=20.0,
            )
            response_text = r.content[0].text
            history_add(user_id, "user", save_text)
            history_add(user_id, "assistant", response_text)
            return response_text
        except anthropic.APITimeoutError:
            logger.warning(f"History timeout attempt {attempt+1}")
            _record_api_fail("history_timeout")
            if attempt < max_retries:
                time.sleep(2)
                continue
            logger.info("Falling back to no-history call")
            return ask_claude(system, user_msg, max_tokens, model)
        except Exception as e:
            logger.error(f"Claude history error ({model}): {e}")
            if attempt < max_retries:
                time.sleep(1)
                continue
            return ask_claude(system, user_msg, max_tokens, model)
    return "Sorry, please try again."


def auto_extract_memory(user_id: str, text: str):
    """
    Auto extract and save memories from conversation.
    Uses categorized storage for better retrieval.
    """
    system = """Extract personal facts or preferences from this message worth remembering long term.
Return ONLY valid JSON array:
[
  {
    "key": "meal_breakfast",
    "value": "oats and banana at 7am",
    "is_preference": true,
    "importance": "high"
  }
]
importance: "high" = must always follow
            "medium" = helpful context
            "low" = nice to know
If nothing worth remembering return: []
Only extract clear explicit facts.
Do not extract questions or temporary info."""
    try:
        raw = ask_claude(system, text, max_tokens=300, model=MODEL_FAST)
        raw = raw.strip().strip("```json").strip("```").strip()
        import json
        facts = json.loads(raw)
        for fact in facts:
            if "key" in fact and "value" in fact:
                key = fact["key"]
                value = fact["value"]
                importance = fact.get("importance", "medium")
                memory_set_categorized(key, value)
                logger.info(
                    f"Auto-saved [{importance}]: "
                    f"{key} = {str(value)[:50]}"
                )
    except Exception as e:
        logger.debug(f"Auto-extract error: {e}")


def get_topic_preferences(topic: str) -> str:
    """
    Get memories for a specific topic.
    Enhanced version using categories.
    """
    # Map topic to category
    topic_to_category = {
        "weather": "preferences",
        "news": "preferences",
        "crypto": "finance",
        "study": "learning",
        "meal": "health",
        "food": "health",
        "health": "health",
        "work": "work",
        "personal": "personal",
        "travel": "travel",
        "schedule": "schedule",
        "finance": "finance",
    }

    category = topic_to_category.get(topic.lower(), "preferences")

    # Get category memories
    cat_memories = memory_get_by_category(category)

    # Also search by keywords
    all_mem = _load(MEMORY_FILE)
    topic_keywords = topic.lower().split()

    keyword_memories = {}
    for key, data in all_mem.items():
        if isinstance(data, dict):
            value = data.get("value", "")
        else:
            value = data
        key_lower = key.lower()
        val_lower = str(value).lower()
        if any(kw in key_lower or kw in val_lower for kw in topic_keywords):
            keyword_memories[key] = value

    # Merge both
    combined = {**cat_memories, **keyword_memories}

    if not combined:
        return ""

    lines = [
        f"Remembered {topic} preferences "
        f"(follow exactly):"
    ]
    for k, v in combined.items():
        lines.append(f"- {k}: {v}")
    lines.append(
        "These are personal preferences. "
        "Always follow them."
    )
    return "\n".join(lines)


def ask_claude_with_search(system: str, user_msg: str,
                            user_id: str = None, max_tokens: int = 1500,
                            model: str = None,
                            history_text: str = None) -> str:
    """Ask Claude with web search tool enabled for real-time data.
    history_text: if provided, saved to history instead of user_msg."""
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
            timeout=90.0,
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
            save_text = history_text if history_text is not None else user_msg
            history_add(user_id, "user", save_text)
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


def is_article_published(url: str) -> bool:
    """Check if article URL was already sent."""
    if not url:
        return False
    published = _load(PUBLISHED_ARTICLES_FILE)
    return url in published

def _increment_article_stats():
    """Increment the cumulative total_ever counter in article_stats.json."""
    try:
        if ARTICLE_STATS_FILE.exists():
            stats = json.loads(ARTICLE_STATS_FILE.read_text())
        else:
            stats = {"total_ever": 443}  # seed with known baseline
        stats["total_ever"] = stats.get("total_ever", 443) + 1
        stats["last_updated"] = datetime.now().isoformat()
        ARTICLE_STATS_FILE.write_text(json.dumps(stats, indent=2))
    except Exception as e:
        logger.warning(f"Could not update article_stats.json: {e}")

def mark_article_published(url: str, title: str,
                            pub_date: str = ""):
    """Mark article as published so it won't repeat."""
    if not url:
        return
    published = _load(PUBLISHED_ARTICLES_FILE)
    published[url] = {
        "title": title[:100],
        "marked_at": datetime.now().isoformat(),
        "pub_date": pub_date,   # original article publish date
    }
    _save(PUBLISHED_ARTICLES_FILE, published)
    _increment_article_stats()

def get_published_count() -> int:
    """Get count of published articles."""
    return len(_load(PUBLISHED_ARTICLES_FILE))

def clear_old_published(days: int = 14):
    """Clear articles older than X days, and those missing marked_at."""
    import datetime as dt
    published = _load(PUBLISHED_ARTICLES_FILE)
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=days)

    kept = {}
    removed_missing = 0
    removed_old = 0

    for url, data in published.items():
        if not isinstance(data, dict) or "marked_at" not in data:
            removed_missing += 1
            continue
        try:
            parsed = dt.datetime.fromisoformat(data["marked_at"])
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            if parsed >= cutoff:
                kept[url] = data
            else:
                removed_old += 1
        except Exception:
            removed_missing += 1

    _save(PUBLISHED_ARTICLES_FILE, kept)
    if removed_missing:
        logger.info(
            f"Published cleanup: removed {removed_missing} entries "
            f"missing marked_at (old format)"
        )
    if removed_old:
        logger.info(
            f"Published cleanup: removed {removed_old} entries "
            f"older than {days} days"
        )
    total = removed_missing + removed_old
    logger.info(
        f"Published cleanup done: {total} removed, {len(kept)} kept"
    )


def ask_claude_news(system: str, user_msg: str, max_tokens: int = 1500) -> str:
    """Use Haiku model for news - much cheaper for high input token tasks like web search."""
    try:
        r = claude.messages.create(
            model=MODEL_FAST,
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
