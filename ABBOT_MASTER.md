# ABbot Master Documentation
**Version:** April 2026  
**Author:** Generated from project files  
**Purpose:** Brief a new AI conversation so development can continue without the original conversation history.

---

## TABLE OF CONTENTS

1. [Project Overview](#1-project-overview)
2. [Complete File Structure](#2-complete-file-structure)
3. [Core Modules Explained](#3-core-modules-explained)
4. [Bot Commands](#4-bot-commands)
5. [Data Files](#5-data-files)
6. [Skills System](#6-skills-system)
7. [Environment Variables](#7-environment-variables)
8. [Key Features and How They Work](#8-key-features-and-how-they-work)
9. [Model Usage Strategy](#9-model-usage-strategy)
10. [ainews Website](#10-ainews-website)
11. [Known Issues and Fixes](#11-known-issues-and-fixes)
12. [Development Commands](#12-development-commands)
13. [How to Continue Development](#13-how-to-continue-development)
14. [Telegram Bot Usage Guide](#14-telegram-bot-usage-guide)

---

## 1. PROJECT OVERVIEW

### What is ABbot?
ABbot is a professional AI agent running on a VPS, accessed via Telegram. It is powered by the Anthropic Claude API and uses two models: Haiku (for fast/cheap tasks like scheduling and intent parsing) and Sonnet (for owner conversations and quality responses). It manages schedules, memories, reminders, crypto prices, AI news, and study assistance.

### Infrastructure
| Item | Value |
|------|-------|
| VPS | srv1310875 |
| OS | Ubuntu/Debian |
| Location | `/home/claudeProj/agentbot/` |
| Running | screen session `agentbot` |
| Python | 3.12 with venv |
| Start command | `bash /home/claudeProj/agentbot/start.sh` |

### Connected Systems
- **Telegram Bot:** ABbot (owner-only agent mode + allowed group/private chats)
- **Website:** https://abai.cloud (ainews project)
- **GitHub:** joetan79/abbot-agent (private)
- **GitHub:** joetan79/ainews (private)
- **Auto-sync:** `gsync` command (every 6 hours via cron)

---

## 2. COMPLETE FILE STRUCTURE

### agentbot (`/home/claudeProj/agentbot/`)
```
/home/claudeProj/agentbot/
├── bot.py                        # Main entry point, Telegram handlers, scheduler
├── start.sh                      # Startup script
├── setup.sh                      # Initial setup script
├── requirements.txt              # Python dependencies
├── .env                          # Environment variables (NOT in git)
├── .env.example                  # Template for .env
├── .gitignore
├── README.md
├── bot.log                       # Runtime log file
│
├── modules/
│   ├── __init__.py
│   ├── agent.py                  # Owner AI agent logic, intent routing, scheduled jobs
│   ├── utils.py                  # Shared helpers: Claude API, memory, tasks, schedules
│   ├── study.py                  # Study commands: /ask /math /chinese /homework
│   ├── rssfeed.py                # RSS feed fetching, article scoring, formatting
│   ├── coingecko.py              # CoinGecko API for live crypto prices
│   ├── skills_loader.py          # Loads .md skill files into system prompts
│   ├── reminders.py              # One-time reminder CRUD (data/reminders.json)
│   └── newsapi_backup.py         # NewsAPI fallback (rarely used)
│
├── skills/
│   ├── agent_behavior.md         # General behavior rules
│   ├── chinese_traditional.md    # Always use Traditional Chinese rules
│   ├── communication_style.md    # Tone, language, formatting defaults
│   ├── crypto_analysis.md        # Crypto analysis style guide
│   ├── crypto_reporting.md       # Crypto reporting format rules
│   ├── news_reporting.md         # News reporting style guide
│   ├── response_style.md         # Response length/format rules
│   ├── study_assistant.md        # Study help guidelines
│   └── weather_reporting.md      # Weather format + CELSIUS enforced
│
└── data/
    ├── memory.json               # Persistent key-value memory (categorized)
    ├── preferences.json          # High-priority preferences (always injected)
    ├── schedules.json            # APScheduler job definitions
    ├── tasks.json                # To-do tasks
    ├── reminders.json            # Pending one-time reminders
    ├── time_windows.json         # Custom activity time windows
    ├── history.json              # Per-user conversation history (50 msg max)
    ├── news_cache.json           # Cached news results (6hr TTL)
    └── published_articles.json   # Dedup tracker: articles already sent
```

### ainews (`/home/claudeProj/ainews/`)
```
/home/claudeProj/ainews/
├── main.py                       # FastAPI backend, all routes
├── database.py                   # SQLAlchemy models (NewsArticle, Subscriber)
├── newsletter.py                 # Resend email integration
├── abbot_publisher.py            # Receives news articles from ABbot
├── sample_data.py                # Dev/test seed data
├── nginx.conf                    # Nginx reverse proxy config
├── setup_https.sh                # HTTPS setup script
├── setup_no_domain.sh            # No-domain setup script
├── start.sh                      # uvicorn startup script
├── requirements.txt
├── .env / .env.example
├── ainews.db                     # SQLite database
│
├── templates/
│   ├── base.html                 # Base layout (dark/light mode, Google Translate)
│   ├── index.html                # Homepage (article list grouped by date)
│   ├── article.html              # Single article view with related articles
│   ├── admin.html                # Admin dashboard (HTTP Basic auth)
│   └── unsubscribe.html          # Email unsubscribe page
│
└── static/
    ├── style.css                 # All site styles
    ├── favicon.ico
    ├── favicon.svg
    └── apple-touch-icon.png
```

---

## 3. CORE MODULES EXPLAINED

### `modules/utils.py`
**Purpose:** Shared utility layer used by all other modules.

| Function | Description |
|----------|-------------|
| `ask_claude(system, user_msg, ...)` | Single-turn Claude API call (Haiku by default) |
| `ask_claude_with_history(...)` | Multi-turn Claude call with conversation history |
| `ask_claude_with_search(...)` | Claude call with web_search_20250305 tool enabled |
| `ask_claude_news(...)` | Haiku call with web search, optimized for news cost |
| `memory_set(key, value)` | Save memory with auto-categorization |
| `memory_get(key)` | Retrieve memory value (handles old + new format) |
| `memory_all()` | Get all memories as flat key:value dict |
| `memory_get_all_categorized()` | Get memories grouped by category |
| `memory_get_by_category(cat)` | Get memories for one category |
| `memory_delete(key)` | Remove a memory entry |
| `get_relevant_memories(query)` | 3-layer selective memory injection (see §8.4) |
| `get_core_preferences()` | Return only "preferences" category memories |
| `preference_set/get/all()` | High-priority preference management |
| `get_preferences_prompt()` | Build CRITICAL PREFERENCES string for prompts |
| `auto_extract_memory(user_id, text)` | Auto-extract and save facts from conversation |
| `history_add/get/clear(user_id, ...)` | Conversation history management |
| `schedule_save/load_all/delete(...)` | Schedule CRUD (data/schedules.json) |
| `task_add/done/list/delete(...)` | Task CRUD (data/tasks.json) |
| `save_time_window(activity, hours)` | Save custom time window |
| `get_time_window(activity)` | Lookup time window (custom first, then default) |
| `is_article_published(url)` | Check dedup tracker |
| `mark_article_published(url, title)` | Record article as sent |
| `get_cached_news/set_cached_news(...)` | 6-hour news cache (data/news_cache.json) |
| `handle_photo(bot, photo, caption)` | Download and analyze photo via Claude vision |
| `clean_response(text)` | Strip citations, markdown, thinking phrases |

**Constants:**
- `MODEL_FAST = "claude-haiku-4-5-20251001"`
- `MODEL_SMART = "claude-sonnet-4-5"`
- `MAX_HISTORY = 50` messages per user

**Default time windows defined in `DEFAULT_TIME_WINDOWS`:**
```
meal/food/breakfast/lunch/dinner/supper: 16 hours
study/homework/learning/revision:         4 hours  (overridden to 6 in time_windows.json)
exercise/workout/gym/run:                48 hours
medication/medicine/pill:                 8 hours
vitamin/supplement:                      24 hours
sleep:                                   16 hours
nap:                                      4 hours
work:                                    14 hours
prayer:                                   6 hours
water/drink:                              2 hours
```

---

### `modules/agent.py`
**Purpose:** Owner AI agent logic — intent routing, scheduled job execution, activity detection.

| Function | Description |
|----------|-------------|
| `build_owner_system_prompt(user_id, text)` | Build rich system prompt with tasks, schedules, history, core prefs, skills |
| `parse_intent(text)` | Haiku-based JSON intent classifier (returns dict with intent, city, activity, etc.) |
| `handle_owner_message(update, context)` | Main owner message router (private chat) |
| `run_scheduled_job(bot, job_id, action)` | Execute scheduled actions (weather/news/crypto/report) |
| `detect_activity_completion(text)` | Haiku-based activity detector for auto-reminders |
| `handle_activity_reminder(update, ctx, info)` | Create one-time reminder after activity |
| `parse_news_articles(msg, time_period)` | Parse Claude news response into article dicts |
| `fire_reminder(bot, rid, chat_id, msg)` | Send a scheduled reminder and delete it |
| `cmd_tasks/schedules/memory/news/report/skills/memories/forget(...)` | Telegram command handlers |

**Intent types parsed:**
`schedule_add`, `schedule_list`, `schedule_remove`, `schedule_summary`, `task_add`, `task_list`, `task_done`, `task_delete`, `memory_set`, `memory_get`, `memory_list`, `news`, `weather`, `report`, `time_window_set`, `chat`

---

### `modules/study.py`
**Purpose:** Study commands open to all allowed users (not just owner).

| Function | Description |
|----------|-------------|
| `cmd_ask(update, ctx)` | Answer any question with web search + Sonnet |
| `cmd_math(update, ctx)` | Step-by-step math solution with Sonnet |
| `cmd_chinese(update, ctx)` | Chinese translation/tutoring with Sonnet |
| `cmd_homework(update, ctx)` | Homework help with Sonnet |
| `_get_user_context(username)` | Returns context string for known users (USER_PROFILES dict) |

**USER_PROFILES:** Dict mapping Telegram usernames to role/level. Currently empty — generic "professional AI assistant" context used for all users.

---

### `modules/rssfeed.py`
**Purpose:** RSS feed integration for real-time AI & tech news.

| Function | Description |
|----------|-------------|
| `fetch_ai_news(hours, count)` | 4-tier fallback fetch from RSS feeds (72hr hard cutoff) |
| `format_articles_for_telegram(articles, period)` | Format article list for Telegram message |
| `calculate_relevance_score(title, summary)` | Score 0-100 for AI/tech relevance |
| `is_relevant(title, summary, min_score)` | Check article passes relevance threshold |
| `auto_categorize(title, summary)` | Assign category: AI Models/Business/Policy/Research/Robotics/Hardware |
| `meets_quality_standards(article)` | Filter clickbait, short titles, low relevance |
| `parse_date(entry)` | Robust RSS date parser (never falls back to now()) |
| `check_feed_health()` | Test all feeds and return status dict |

**Feed lists:**
- `AI_TECH_FEEDS`: TechCrunch AI, The Verge AI, VentureBeat AI, Ars Technica, Reuters Tech, ZDNet AI, Bloomberg Tech, AI News, InfoQ AI
- `RESEARCH_FEEDS`: Google AI Blog, OpenAI News, Hugging Face Blog, MIT Tech Review, The Batch (DeepLearning.AI), Towards Data Science, Synced AI
- `CRYPTO_FEEDS`: CoinDesk, CoinTelegraph, Decrypt

**4-Tier fallback logic:**
- Tier 1: Fetch from AI_TECH_FEEDS — last 24 hours
- Tier 2: Wider window (48 hours) if Tier 1 yields too few
- Tier 3: Include RESEARCH_FEEDS — up to 72 hours
- Tier 4: Fallback to any available recent articles

---

### `modules/coingecko.py`
**Purpose:** Real-time crypto prices via CoinGecko API (free, no key required).

| Function | Description |
|----------|-------------|
| `get_prices(coins)` | Fetch prices for given coins (default: BTC, ETH, SOL) |
| `get_trending()` | Fetch top 5 trending coins |
| `build_crypto_report(coins)` | Format complete crypto report with 24h/7d changes |
| `extract_coins_from_text(text)` | Parse coin mentions from free-form text |
| `format_price/change/volume(...)` | Number formatters |

**Supported coins:** BTC, ETH, SOL, BNB, XRP, ADA, DOGE, USDT, USDC

---

### `modules/skills_loader.py`
**Purpose:** Load `.md` skill files into system prompts.

| Function | Description |
|----------|-------------|
| `load_skills(scope)` | Load skills for a given scope, returns formatted string |
| `list_skills()` | List available skill file names |
| `get_skill_token_estimate()` | Return rough token count per skill |

**Scope → files loaded:**
```
"core":    communication_style, agent_behavior, response_style, chinese_traditional
"news":    communication_style, response_style, news_reporting
"crypto":  communication_style, response_style, crypto_reporting
"study":   communication_style, response_style, chinese_traditional, study_assistant
"weather": communication_style, response_style, weather_reporting
"all":     all 8 skills in priority order
```

---

### `modules/reminders.py`
**Purpose:** One-time reminder storage (data/reminders.json).

| Function | Description |
|----------|-------------|
| `save_reminder(id, chat_id, msg, fire_at, type)` | Persist a reminder |
| `delete_reminder(id)` | Remove a reminder |
| `get_all_reminders()` | Return all reminders dict |
| `get_reminders_by_type(type)` | Filter by type (meal, study, exercise, etc.) |
| `delete_reminders_by_type(type)` | Remove all reminders of a type (used when replacing) |

---

## 4. BOT COMMANDS

### All Registered Commands (from `bot.py`)

| Command | Handler | Access | Purpose |
|---------|---------|--------|---------|
| `/start` | `cmd_start` | All allowed | Welcome message, shows command list |
| `/ask <question>` | `cmd_ask` | All allowed | Answer any question (Sonnet + web search) |
| `/math <problem>` | `cmd_math` | All allowed | Step-by-step math solution |
| `/chinese <text>` | `cmd_chinese` | All allowed | Chinese translation and tutoring |
| `/homework <q>` | `cmd_homework` | All allowed | Homework help |
| `/tasks` | `cmd_tasks` | Owner only | View pending tasks |
| `/schedules` | `cmd_schedules` | Owner only | View active schedules |
| `/memory` | `cmd_memory` | Owner only | View raw memory dump |
| `/memories` | `cmd_memories` | Owner only | View memories grouped by category |
| `/forget <key>` | `cmd_forget` | Owner only | Delete a specific memory entry |
| `/news` | `cmd_news` | Owner only | Fetch latest AI & tech news now |
| `/report` | `cmd_report` | Owner only | Run daily report now |
| `/skills` | `cmd_skills` | Owner only | List loaded skills with token estimates |
| `/newsstatus` | `cmd_newsstatus` | Owner only | Show count of tracked published articles |
| `/feedhealth` | `cmd_feedhealth` | Owner only | Check RSS feed health (ok/empty/error) |
| `/reminders` | `cmd_reminders` | Owner only | View pending one-time reminders |
| `/cancelreminder <id>` | `cmd_cancel_reminder` | Owner only | Cancel a pending reminder |
| `/windows` | `cmd_windows` | Owner only | View all time windows (custom + default) |
| `/clear` | `cmd_clear_history` | Owner only | Clear conversation history |

### Message Handlers
- `TEXT & ~COMMAND` → `route_message` (private owner → `handle_owner_message`; others → Sonnet chat)
- `PHOTO` → `handle_photo_message` (Claude vision analysis)

---

## 5. DATA FILES

### `data/schedules.json`
Active APScheduler job definitions. Restored on bot restart.

**Current active schedules (as of April 2026):**
| Time | Action |
|------|--------|
| 02:00 daily | Top 5 AI-relevant news last 8 hours |
| 07:00 daily | Crypto snapshot (BTC, ETH, SOL) |
| 08:00 daily | Weather report for Macau (high/low temps) |
| 10:00 daily | Top 5 AI-relevant news last 8 hours |
| 18:00 daily | Top 5 AI-relevant news last 8 hours |
| 19:00 daily | Crypto snapshot (BTC, ETH, SOL) |

**Schema per entry:**
```json
{
  "label": "schedule description",
  "time": "HH:MM",
  "frequency": "daily" | "weekly",
  "action": "action string",
  "city": "city name",
  "created": "ISO timestamp"
}
```

---

### `data/time_windows.json`
Custom activity time window overrides (merged over DEFAULT_TIME_WINDOWS).

**Current custom windows:**
```json
{
  "study":    {"hours": 6,  "label": "study",    "custom": true},
  "exercise": {"hours": 48, "label": "exercise", "custom": true},
  "fasting":  {"hours": 16, "label": "fasting",  "custom": true}
}
```

---

### `data/memory.json`
Persistent key-value memory store. Each entry has `value`, `category`, `updated` fields.

**Sample entries (April 2026):**
```json
"name":             {"value": "Joe",       "category": "personal"}
"city_manual_weather": {"value": "Macau",  "category": "travel"}
"weather_unit":     {"value": "celsius",   "category": "preferences"}
"weather_preference": {"value": "celsius only", "category": "preferences"}
"weather_preferences": {"value": "Temperature in Celsius only, Include dew point, Wind speed in km/h, Include humidity percentage, Include UV index, Include rain chance", "category": "preferences"}
"chinese_script":   {"value": "Traditional Chinese"}
"priority_item":    {"value": "SOL"}
"kids":             {"value": "Isaac who is 10 years old, and Arik who is 6 years old"}
"group_chat_purpose": {"value": "kids brainstorming and studying QnA - help with educational questions and discussions"}
```

**Memory categories:** `health`, `personal`, `work`, `finance`, `travel`, `schedule`, `learning`, `preferences`, `general`

---

### `data/published_articles.json`
Deduplication tracker. 157+ articles tracked as of April 2026. Articles older than 7 days are auto-cleaned when count > 1000.

```json
"https://example.com/article-url": {
  "title": "Article title",
  "marked_at": "ISO timestamp",
  "pub_date": "original publish date"
}
```

---

### `data/tasks.json`
Simple to-do list.
```json
"1773104188": {"text": "clean it", "done": false, "created": "..."},
"1773667581": {"text": "clean up", "done": false, "created": "..."}
```

---

### `data/reminders.json`
One-time reminder fire schedule. Empty when none pending.

---

### `data/preferences.json`
High-priority preferences that override memory.json values in prompts.

---

### `data/history.json`
Per-user conversation history. Up to 50 messages per user. Keyed by Telegram user ID.

---

## 6. SKILLS SYSTEM

Skills are `.md` files in `skills/` that are appended to system prompts. They define behavior rules without changing core code.

### `skills/agent_behavior.md`
General behavior rules: be concise, lead with the answer, use bullet points for lists, tables for comparisons, acknowledge outdated info.

### `skills/chinese_traditional.md`
CRITICAL: Always use Traditional Chinese (繁體中文). Never Simplified. Always include Pinyin with tone marks. Show: Original → Traditional Chinese → Pinyin.

### `skills/communication_style.md`
Default English. Chinese = Traditional. Dates in DD Mon YYYY format. 24-hour time. Professional but friendly tone. Emoji sparingly.

### `skills/crypto_analysis.md`
Show percentage change, compare to BTC dominance, brief market sentiment, avoid jargon.

### `skills/crypto_reporting.md`
Show current price, 24hr change, 7d change. Flag >5% moves. No financial advice. Add "Prices are for reference only" disclaimer. Prices in USD.

### `skills/news_reporting.md`
Lead with most impactful story. Summaries under 3 sentences. Explain WHY it matters. Neutral professional language. Format numbers as $2B not $2,000,000,000.

### `skills/response_style.md`
Under 300 words unless detail requested. Lead with most important point. Tables for comparisons. Code blocks for code. No "Great question!" padding.

### `skills/study_assistant.md`
Confirm understanding first. Real-world examples. Step-by-step for math. Pronunciation guides. Encourage understanding not memorization.

### `skills/weather_reporting.md`
**CRITICAL: ALWAYS Celsius (°C). NEVER Fahrenheit.** Include: temp, high/low, feels like, humidity, dew point, wind km/h, rain chance %, UV index, visibility, 6-hour outlook, clothing recommendation.

---

## 7. ENVIRONMENT VARIABLES

### agentbot `.env`
| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API authentication |
| `ANTHROPIC_API_KEY` | Claude API access (Haiku + Sonnet) |
| `OWNER_CHAT_ID` | Owner's Telegram chat ID (Joe) — grants full agent access |
| `ALLOWED_CHAT_IDS` | Comma-separated list of allowed chat IDs (study group etc.) |
| `WEBSITE_URL` | ainews website URL (https://abai.cloud) for article publishing |
| `WEBSITE_API_KEY` | Shared API key for ABbot → ainews /api/publish endpoint |
| `NEWSAPI_KEY` | NewsAPI key (backup only — RSS feeds are primary) |

### ainews `.env`
| Variable | Purpose |
|----------|---------|
| `WEBSITE_API_KEY` | Shared with agentbot — validates /api/publish requests |
| `SITE_URL` | https://abai.cloud |
| `RESEND_API_KEY` | Resend email service for subscriber notifications |
| `FROM_EMAIL` | noreply@abai.cloud |
| `DATABASE_URL` | SQLite path (sqlite:///./ainews.db) |
| `ADMIN_PASSWORD` | HTTP Basic auth password for /admin page |

---

## 8. KEY FEATURES AND HOW THEY WORK

### 8.1 News System

**Source:** RSS feeds (primary) via `modules/rssfeed.py`

**Feed list:**
- AI_TECH_FEEDS (9 feeds): TechCrunch AI, The Verge AI, VentureBeat AI, Ars Technica, Reuters Tech, ZDNet AI, Bloomberg Tech, AI News, InfoQ AI
- RESEARCH_FEEDS (7 feeds): Google AI Blog, OpenAI News, Hugging Face Blog, MIT Tech Review, The Batch, Towards Data Science, Synced AI
- CRYPTO_FEEDS (3 feeds): CoinDesk, CoinTelegraph, Decrypt

**Schedule:** 3x daily via APScheduler (02:00, 10:00, 18:00) — fetches last 8 hours each run

**Article filtering pipeline:**
1. Parse RSS entry date (never falls back to `datetime.now()`)
2. 72-hour hard cutoff — articles older than 72 hours are always rejected
3. `meets_quality_standards()` — minimum title length (20 chars), summary length (50 chars), relevance score ≥ 5
4. `calculate_relevance_score()` — 0-100 score using 4 keyword tiers
5. Dedup check against `published_articles.json`

**4-tier fallback:**
- Tier 1: AI_TECH_FEEDS last 24h
- Tier 2: AI_TECH_FEEDS last 48h (if Tier 1 too few)
- Tier 3: AI_TECH_FEEDS + RESEARCH_FEEDS last 72h
- Tier 4: Any available recent articles

**Source URL priority:** Article must pass `is_specific_url()` — path > 20 chars or ≥ 2 path segments. Homepage URLs are discarded.

**Dedup tracking:** `published_articles.json` — keyed by article URL. Auto-cleaned to 7-day window when > 1000 entries.

**Publishes to:** Telegram message + abai.cloud website via `POST /api/publish`

---

### 8.2 Crypto Prices

**Source:** CoinGecko API (free, no API key needed)  
**File:** `modules/coingecko.py`  
**Default coins:** BTC, ETH, SOL  
**Data includes:** Price USD, 24h change %, 7d change %, 24h volume, market cap  
**Triggered by:** Scheduled job (07:00, 19:00) or natural language ("BTC price", "帮我查比特币价格")  
**Trending:** Top 5 trending coins appended to report  

---

### 8.3 Weather

**Source:** Claude with `web_search_20250305` tool  
**Preferences:** Read from `memory.json` — scans all weather-related keys  
**CRITICAL:** System prompt explicitly enforces Celsius only:
```
"CRITICAL RULES:
- Use CELSIUS (°C) ONLY unless user specifically requested Fahrenheit
- NEVER use Fahrenheit by default"
```
**City resolution order:**
1. Job-specific memory (`city_{job_id}`)
2. Extracted from action string via regex
3. `memory.json` key "city" (defaults to Kuala Lumpur if not set)

**Current default city:** Macau (from `city_manual_weather` memory key)  
**Skills applied:** `weather` scope (communication_style + response_style + weather_reporting)

---

### 8.4 Memory System

**File:** `data/memory.json`  
**Format:** `{key: {value, category, updated}}`  
**Categories:** health, personal, work, finance, travel, schedule, learning, preferences, general  

**Auto-categorization:** `categorize_memory(key, value)` scores the key+value text against keyword lists and assigns the highest-scoring category.

**3-layer retrieval (`get_relevant_memories(query)`):**
1. **Layer 1 — Category scoring:** Match query against category keyword lists; inject top matching categories. `preferences` always included as baseline.
2. **Layer 2 — Direct text search:** Search query words directly in all memory keys/values. Catches named things like person names, places.
3. **Layer 3 — Safety net:** If nothing matched beyond preferences, return 3 most recently updated memories.

**`preferences.json`:** Separate file for high-priority preferences. Merged over memory.json in `get_preferences_prompt()`. Always injected into every system prompt.

**Commands:** `/memories` (categorized view), `/forget <key>`, natural language "remember X is Y"

**Auto-extraction:** `auto_extract_memory()` runs on owner messages, uses Haiku to extract explicit facts and saves them automatically.

---

### 8.5 Scheduling System

**File:** `data/schedules.json`  
**Engine:** APScheduler (`AsyncIOScheduler`)  
**Persistence:** `restore_schedules()` called at bot startup — rebuilds APScheduler jobs from JSON  
**Natural language:** `parse_intent()` extracts time/frequency/action/city from natural language  
**Supported frequencies:** daily, weekly (with day-of-week)  

**Natural language examples:**
- "schedule daily 8am weather in KL"
- "schedule daily 7pm crypto report"
- "schedule weekly Monday 9am report"

**Commands:** `/schedules` to view, "remove schedule X" to delete

---

### 8.6 Task Management

**File:** `data/tasks.json`  
**ID:** Unix timestamp as string  
**Schema:** `{text, done, created, completed?}`  
**Commands:** `/tasks`, "add task: X", "done <id>", "delete task <id>"  

---

### 8.7 Time Window Reminders

**Files:** `data/time_windows.json` (custom windows), `data/reminders.json` (pending reminders)  

**How it works:**
1. User sends message reporting completing an activity (e.g., "finished dinner")
2. `detect_activity_completion()` — Haiku API call detects activity + confidence
3. Pre-filter: questions and requests are rejected without API call
4. If high/medium confidence: `handle_activity_reminder()` calculates fire time
5. Uses **exact Telegram message timestamp** (not user-provided time)
6. Looks up time window from custom → default dict
7. Saves reminder via `reminders.py` and schedules APScheduler `"date"` job
8. Replaces any existing same-type reminder

**Activity detection — English trigger phrases:** done, finished, complete, completed, took my, had my, just had, just finished, just woke, woke up, done with, all done

**Activity detection — Chinese trigger phrases:** 吃完, 完了, 做完, 运动完, 温习完, 溫習完, 睡醒, 下班, 吃药, 吃藥, 喝水

**Smart meal naming:** Based on hour:
- 05:00–10:59 → breakfast
- 11:00–14:59 → lunch
- 15:00–17:59 → tea/snack
- 18:00–21:59 → dinner
- 22:00–04:59 → supper

**Reminder restoration on restart:** `restore_reminders()` re-queues future reminders and sends delayed reminders that fired within the last 2 hours (with "(Delayed)" prefix).

**Commands:** `/reminders`, `/cancelreminder <id>`, `/windows`, "remember my study window is 6 hours"

---

### 8.8 Skills System

**Folder:** `skills/`  
**Format:** `.md` files with plain text rules  
**Loading:** `load_skills(scope)` called per request type  
**Token cost:** ~450 tokens total for all 8 skills  
**Scopes:** core (4 files), news (3), crypto (3), study (4), weather (3), all (8)  

**To add a new skill:** Create `skills/new_skill.md` and add it to `SKILL_PRIORITY` list in `skills_loader.py`.

---

### 8.9 Conversation History

**File:** `data/history.json`  
**Per-user limit:** 50 messages maximum  
**Format:** `{role, content, timestamp}` list per user_id  
**API format:** Timestamps stripped before sending to Claude  
**Used by:** `ask_claude_with_history()` — injects last 20 messages as multi-turn conversation  
**Fallback:** If history call times out, falls back to no-history `ask_claude()`  
**Command:** `/clear` resets history for owner  

---

### 8.10 Study Mode

**File:** `modules/study.py`  
**Model:** Sonnet (`MODEL_SMART`) — always uses the smart model  
**Web search:** Enabled for `/ask` and `/homework`; disabled for `/math` and `/chinese`  
**Access:** All `ALLOWED_CHAT_IDS`, not just owner  
**Language:** Traditional Chinese enforced via `chinese_traditional` skill in study scope  
**User profiles:** `USER_PROFILES` dict (currently empty — all users get generic context)  

---

## 9. MODEL USAGE STRATEGY

### Haiku (`claude-haiku-4-5-20251001`) — Fast and cheap
Used for tasks where speed and cost matter:
- `parse_intent()` — classify user message intent
- `run_scheduled_job()` — weather, news, crypto, reports
- `auto_extract_memory()` — extract facts from conversation
- `detect_activity_completion()` — detect if user finished an activity
- News formatting via `ask_claude_news()`
- All `ask_claude()` calls default to Haiku unless overridden

### Sonnet (`claude-sonnet-4-5`) — Smart and quality
Used for tasks requiring reasoning and quality:
- Owner conversations (via `ask_claude_with_history()` default)
- Study help: `/ask`, `/math`, `/chinese`, `/homework`
- Group chat responses (via `route_message()`)
- Photo analysis (`handle_photo()`)
- Complex analysis requests

**Cost optimization notes:**
- `ask_claude_news()` uses Haiku even for news fetching (high input token task)
- News results are cached for 6 hours (`news_cache.json`)
- Memory injection is selective via 3-layer retrieval (not all memories every time)
- Skills loaded per scope (not "all" for every request)

---

## 10. AINEWS WEBSITE

**Location:** `/home/claudeProj/ainews/`  
**URL:** https://abai.cloud  
**Running:** screen session `ainews`  
**Start command:** `uvicorn main:app --host 127.0.0.1 --port 8000`  
**Proxy:** Nginx reverse proxy with SSL  
**Framework:** FastAPI + Jinja2 templates + SQLite (SQLAlchemy)

### Key Routes
| Route | Purpose |
|-------|---------|
| `GET /` | Homepage — latest 20 published articles grouped by date |
| `GET /article/{id}` | Single article with 3 related articles |
| `POST /subscribe` | Email subscription with welcome email via Resend |
| `GET /unsubscribe?email=...` | Email unsubscribe |
| `POST /api/publish` | ABbot publishes articles here (API key auth) |
| `GET /admin` | Admin dashboard (HTTP Basic auth: admin / ADMIN_PASSWORD) |
| `GET /admin/export` | Export subscribers as CSV |

### Features
- Dark/light mode toggle (CSS + localStorage)
- Google Translate widget (English ↔ Chinese)
- Email subscription with Resend API
- Admin page with subscriber management and article management
- Auto-publishes from ABbot 3x daily
- Subscriber email digest sent on publish event

### Database Models (SQLAlchemy, SQLite)
- **NewsArticle:** id, title, summary, category, source_url, published_date, is_published
- **Subscriber:** id, email, subscribed_at, is_active

### How ABbot publishes to website
`modules/agent.py` `run_scheduled_job()` news block calls:
```python
httpx.post(
    f"{WEBSITE_URL}/api/publish",
    json={"articles": [...]},
    headers={"X-API-Key": api_key, "Authorization": f"Bearer {api_key}"},
    timeout=30,
)
```

---

## 11. KNOWN ISSUES AND FIXES

| # | Issue | Status | File/Location |
|---|-------|--------|---------------|
| 1 | Weather shows Fahrenheit sometimes | **Fixed** — Celsius enforced in two places: `weather_reporting.md` skill + explicit `CRITICAL RULES` in `run_scheduled_job()` system prompt | `modules/agent.py` ~line 340, `skills/weather_reporting.md` |
| 2 | News source links intermittent | **Fixed** — 4-tier fallback with `is_specific_url()` validation; homepage URLs discarded | `modules/rssfeed.py`, `modules/agent.py` |
| 3 | Old articles (2024/2025) in news | **Fixed** — 72-hour hard cutoff in RSS parser; `parse_date()` never falls back to `datetime.now()` | `modules/rssfeed.py` `parse_date()` |
| 4 | `datetime` import conflict in weather block | **Fixed** — removed local imports that conflicted with module-level import | `modules/agent.py` ~line 1142 |
| 5 | Duplicate API calls for same message | **Fixed** — `_processed_updates` set in `bot.py` tracks update IDs; duplicates skipped | `bot.py` `route_message()` |

---

## 12. DEVELOPMENT COMMANDS

### Daily Operations
```bash
# Sync to GitHub
gsync

# Check running screens
screen -ls

# View agentbot logs (live)
tail -f /home/claudeProj/agentbot/bot.log

# View last 50 log lines
tail -50 /home/claudeProj/agentbot/bot.log

# Restart agentbot
screen -r agentbot
# Press Ctrl+C to stop
source venv/bin/activate
python bot.py
# Press Ctrl+A then D to detach

# Restart ainews
screen -r ainews
# Press Ctrl+C to stop
source venv/bin/activate
uvicorn main:app --host 127.0.0.1 --port 8000
# Press Ctrl+A then D to detach

# Check port conflicts
lsof -i :8000
kill -9 $(lsof -t -i:8000)
```

### Claude Code Usage
```bash
# Always run from project directory
cd /home/claudeProj/agentbot
claude

# For ainews changes
cd /home/claudeProj/ainews
claude
```

### Useful Debug Commands
```bash
# Check memory contents
cat /home/claudeProj/agentbot/data/memory.json

# Check active schedules
cat /home/claudeProj/agentbot/data/schedules.json

# Count published articles
python3 -c "import json; d=json.load(open('data/published_articles.json')); print(f'{len(d)} articles')"

# Test RSS feed manually
cd /home/claudeProj/agentbot && source venv/bin/activate
python3 -c "from modules.rssfeed import fetch_ai_news; arts = fetch_ai_news(hours=24, count=5); [print(a['title']) for a in arts]"

# Test CoinGecko
python3 -c "from modules.coingecko import build_crypto_report; print(build_crypto_report())"
```

---

## 13. HOW TO CONTINUE DEVELOPMENT

### Starting a New Claude Code Session

1. `cd /home/claudeProj/agentbot`
2. `claude`
3. Share `ABBOT_MASTER.md` at the start: "Read ABBOT_MASTER.md for full project context"
4. State what you want to build or fix
5. Claude Code handles implementation
6. Always run `gsync` after changes

### Standard Development Workflow
1. Describe the feature or bug
2. Claude Code reads the relevant files
3. Claude Code implements the change
4. Test: restart bot and try in Telegram
5. `gsync` to backup to GitHub

### Adding a New Feature — Checklist
- [ ] Intent: Does it need a new intent type in `parse_intent()`?
- [ ] Handler: Add handler function in `agent.py`
- [ ] Command: Register in `bot.py` `main()` with `CommandHandler`
- [ ] BotCommand: Add to `set_my_commands()` list
- [ ] Skill: If new behavior rules needed, add `skills/feature.md`
- [ ] Data: If persistent storage needed, add to `data/` and CRUD in `utils.py`

### Adding a New Skill
1. Create `skills/new_skill.md` with rules
2. Add skill name to `SKILL_PRIORITY` in `skills_loader.py`
3. Add scope entry in `scope_map` if needed
4. No other code changes required

### Pending Improvements (not yet built)
- Voice message support (OpenAI Whisper for transcription)
- Google Calendar integration
- More news categories (cybersecurity, hardware)
- Mobile app for abai.cloud
- Real-time streaming transcription
- Pushover/push notifications as Telegram alternative

---

## 14. TELEGRAM BOT USAGE GUIDE

### Owner Commands (full agent mode)
```
/start              — Welcome message with command list
/tasks              — View all pending tasks
/schedules          — View active scheduled jobs
/memory             — View raw memory dump
/memories           — View memories grouped by category
/forget <key>       — Delete a specific memory entry
/news               — Fetch latest AI & tech news now
/report             — Run daily report now
/skills             — List loaded skills + token estimates
/feedhealth         — Check RSS feed health status
/newsstatus         — Show count of tracked published articles
/reminders          — View pending one-time reminders
/cancelreminder <id>— Cancel a specific reminder
/windows            — View all activity time windows
/clear              — Clear conversation history
```

### Study Commands (all allowed users)
```
/ask <question>     — Answer any question (Sonnet + web search)
/math <problem>     — Step-by-step math solution
/chinese <text>     — Chinese translation/tutoring
/homework <q>       — Homework help with explanation
```

### Natural Language Examples

**Scheduling:**
```
schedule daily 8am weather in KL
schedule daily 7am crypto snapshot
schedule weekly Monday 9am daily report
remove the 2am news schedule
what schedules do I have?
```

**Tasks:**
```
add task: review quarterly report
add task: call accountant
done 1773104188
what tasks do I have?
```

**Memory:**
```
remember my city is Kuala Lumpur
remember weather in Celsius
remember my study window is 6 hours
remember kids: Isaac 10 years old, Arik 6 years old
```

**Time Windows:**
```
remember my fasting window is 16 hours
my exercise window is 48 hours
medication every 8 hours
change study to 6 hours
```

**Activity Completions (auto-reminder):**
```
finished dinner          → sets meal reminder (16 hrs)
done studying            → sets study reminder (6 hrs)
finished my workout      → sets exercise reminder (48 hrs)
took my medication       → sets medication reminder (8 hrs)
just woke up             → sets sleep reminder (16 hrs)
吃完了                   → sets meal reminder (16 hrs)
溫習完了                 → sets study reminder (6 hrs)
運動完了                 → sets exercise reminder (48 hrs)
吃藥了                   → sets medication reminder (8 hrs)
```

**Queries:**
```
weather in Tokyo
BTC price now
latest AI news
latest AI news last 8 hours
天气怎么样
帮我查比特币价格
最新AI新闻
我的任务
今天有什么安排
```

**Photo:**
```
Send any photo (with optional caption for specific question)
→ Claude analyzes it via vision API
```

### Group Chat Behavior
- Only responds when @mentioned or when replying to bot's message
- Uses `is_allowed()` check against `ALLOWED_CHAT_IDS`
- Routing: if private + owner → full agent mode; else → Sonnet chat
- Quoted/replied messages are included as context

---

*Generated from project files — April 13, 2026*  
*Location: `/home/claudeProj/agentbot/ABBOT_MASTER.md`*
