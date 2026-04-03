"""Agent handlers — owner personal AI agent."""

import re
import sys
import json, logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from .utils import (
    ask_claude, ask_claude_with_history, ask_claude_with_search, ask_claude_news,
    is_owner, is_allowed,
    memory_set, memory_get, memory_all, memory_delete,
    preference_all, get_preferences_prompt,
    history_add, history_get, history_clear, history_summary,
    auto_extract_memory,
    schedule_save, schedule_load_all, schedule_delete,
    task_add, task_done, task_list, task_delete,
    OWNER_CHAT_ID,
    clean_response,
    get_cached_news, set_cached_news,
    MODEL_FAST, MODEL_SMART,
)
from .skills_loader import load_skills, list_skills

def build_owner_system_prompt(user_id: str, text: str) -> str:
    """Build a rich, context-aware system prompt for the owner."""
    tasks = task_list()
    schedules = schedule_load_all()
    recent_history = history_summary(user_id)
    now = datetime.now().strftime("%A, %d %B %Y %H:%M")

    # Build strict preferences section (preferences.json takes priority over memory.json)
    all_prefs = {**memory_all(), **preference_all()}
    if all_prefs:
        pref_lines = ["CRITICAL PREFERENCES - MUST ALWAYS FOLLOW:"]
        for key, value in all_prefs.items():
            pref_lines.append(f"  - {key}: {value}")
        pref_lines.append(
            "  Never ignore these preferences. They apply to every single response."
        )
        prefs_text = "\n".join(pref_lines)
    else:
        prefs_text = "No preferences stored yet."

    pending_tasks = [t for t in tasks if not t.get("done")]
    tasks_text = "\n".join(f"- {t['text']}" for t in pending_tasks[:5]) or "No pending tasks"

    sched_text = "\n".join(
        f"- {j['time']} ({j['frequency']}): {j['label'][:60]}"
        for j in list(schedules.values())[:5]
    ) or "No active schedules"

    skills_text = load_skills()

    return f"""You are ABbot - smart personal AI agent.

{prefs_text}
{skills_text}

CURRENT CONTEXT:
Date/Time: {now}

PENDING TASKS:
{tasks_text}

ACTIVE SCHEDULES:
{sched_text}

RECENT CONVERSATION:
{recent_history}

RULES:
- ALWAYS follow preferences listed above
- Use conversation history for context
- Be concise and helpful
- Never ignore stored preferences
- If preference says Traditional Chinese, ALWAYS use it
- Never show raw JSON or system data to the user"""

logger = logging.getLogger(__name__)


def is_specific_url(url: str) -> bool:
    """Return True if url points to a specific article, not just a homepage."""
    if not url or not url.startswith('http'):
        return False
    from urllib.parse import urlparse
    parsed = urlparse(url)
    path = parsed.path.strip('/')
    # Path must have at least 2 segments or 20+ chars
    return len(path) > 20 or path.count('/') >= 2


def parse_news_articles(msg: str, time_period: str = "24 hours") -> list:
    """Parse numbered news articles from a Claude response into structured dicts."""
    articles = []

    # Determine max age in hours from time_period string
    hours_match = re.search(r'(\d+)\s+hours?', time_period)
    max_age_hours = int(hours_match.group(1)) if hours_match else 24

    # Find all positions where numbered items start
    # Matches: "1." "2." "1)" "2)" at start of line or after newline
    pattern = r'(?:^|\n)(\d+)[.)]\s+'
    matches = list(re.finditer(pattern, msg))

    for i, match in enumerate(matches):
        # Get text from this match to next match (or end)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(msg)
        chunk = msg[start:end].strip()

        if not chunk:
            continue

        # Split chunk into lines
        lines = [l.strip() for l in chunk.split('\n') if l.strip()]
        if not lines:
            continue

        # First line is title
        title = lines[0]
        title = re.sub(r'\*\*([^*]+)\*\*', r'\1', title)
        title = re.sub(r'#+\s*', '', title)
        title = title.strip()

        # Remaining lines are summary, Date, and Source
        summary_lines = []
        source_url = None
        article_date = None
        for line in lines[1:]:
            if line.startswith('Source:'):
                raw_url = line[len('Source:'):].strip().strip('\n')
                if raw_url == 'NOT_FOUND':
                    source_url = None
                elif raw_url.startswith('http://') or raw_url.startswith('https://'):
                    source_url = raw_url if is_specific_url(raw_url) else None
                else:
                    source_url = None
                logger.info(f"Source URL valid: {is_specific_url(raw_url) if raw_url not in ('NOT_FOUND', '') else False} | {raw_url}")
                continue
            if line.startswith('Date:'):
                date_str = line[len('Date:'):].strip()
                for fmt in ('%B %d, %Y', '%B %d %Y', '%d %B %Y', '%Y-%m-%d'):
                    try:
                        article_date = datetime.strptime(date_str, fmt)
                        break
                    except ValueError:
                        continue
                continue
            if any(skip in line.lower() for skip in
                   ['based on', 'here are', 'search results',
                    'according to', 'following']):
                continue
            line = re.sub(r'\*\*([^*]+)\*\*', r'\1', line)
            line = re.sub(r'\*([^*]+)\*', r'\1', line)
            line = re.sub(r'#+\s*', '', line)
            line = re.sub(r'^[-•]\s*', '', line)
            if line:
                summary_lines.append(line)

        # Skip articles older than time_period
        if article_date:
            age_hours = (datetime.now() - article_date).total_seconds() / 3600
            if age_hours > max_age_hours:
                logger.info(f"Skipped article - too old: {article_date.strftime('%B %d, %Y')} | {title[:40]}")
                continue

        summary = ' '.join(summary_lines)

        # If no summary found, try to extract from title
        if not summary or len(summary) < 20:
            if '. ' in title and len(title) > 60:
                parts = title.split('. ', 1)
                title = parts[0]
                summary = parts[1] if len(parts) > 1 else title
            else:
                summary = title

        if title and len(title) > 8:
            articles.append({
                'title': title[:200],
                'summary': summary[:600],
                'category': 'AI & Tech',
                'source_url': source_url,
            })

        logger.info(f"Article {i+1}: {title[:40]} | source: {source_url}")

    return articles


def parse_intent(text: str) -> dict:
    system = """You are an intent parser for a personal AI agent Telegram bot.
Parse the user message carefully and return ONLY valid JSON.

IMPORTANT RULES:
- If user is asking a QUESTION about schedules (e.g. "what will you send me", "summarize my schedules", "what have I scheduled") → use intent "schedule_summary"
- If user wants to ADD a new schedule → use intent "schedule_add"
- If user wants to LIST/SHOW raw schedules → use intent "schedule_list"
- If user wants to REMOVE a schedule → use intent "schedule_remove"
- If user is asking a question or chatting → use intent "chat"

Return JSON:
{
  "intent": one of [schedule_add, schedule_list, schedule_remove, schedule_summary, task_add, task_list, task_done, task_delete, memory_set, memory_get, memory_list, news, weather, report, chat],
  "time": "HH:MM" or null,
  "frequency": "daily" or "weekly" or "once" or null,
  "day": day of week or null,
  "action": the task to perform as string,
  "key": memory key or null,
  "value": memory value or null,
  "task_id": task id or null,
  "city": city name mentioned or null
}
Return ONLY the JSON object, no markdown, no explanation."""
    raw = ask_claude(system, text, max_tokens=300, model=MODEL_FAST)
    try:
        return json.loads(raw.strip().strip("```json").strip("```").strip())
    except Exception:
        return {"intent": "chat", "action": text}

def extract_time_period(action: str) -> str:
    match = re.search(r'last\s+(\d+)\s+hours?', action.lower())
    if match:
        return f"{match.group(1)} hours"
    return "24 hours"

def is_failed_response(text: str) -> bool:
    """Return True if Claude gave up instead of providing news."""
    failure_phrases = [
        "i cannot find",
        "i'm unable to find",
        "i am unable to find",
        "no news found",
        "cannot provide",
        "i don't have access",
        "i recommend checking",
        "please check",
        "search results do not",
        "most recent tech news in my search",
    ]
    text_lower = text.lower()
    return any(phrase in text_lower for phrase in failure_phrases)


async def run_scheduled_job(bot, job_id: str, action: str):
    """Execute a scheduled job with live web search."""
    logger.info(f"Running scheduled job: {job_id} - {action}")
    # Use job-specific city if set, otherwise fall back to default memory city
    city = memory_get(f"city_{job_id}", None) or memory_get("city", "Kuala Lumpur")
    now  = datetime.now().strftime("%A, %d %B %Y %H:%M")

    if action == "weather":
        system = (
            f"Find current weather for {city}. "
            "Format:\n"
            "Temperature: High XXC / Low XXC\n"
            "Condition: Sunny/Cloudy/Rainy\n"
            "Rain chance: XX%\n"
            "Wind: XX km/h\n"
            "Humidity: XX%\n"
            "Tip: what to wear today.\n"
            "Plain text only."
        )
        msg = ask_claude_news(system, f"Current weather in {city} today {now}")
        msg = clean_response(msg)
        text = f"Weather Report - {city}\n\n{msg}"

    elif action in ("news_ai", "news") or re.search(r'last\s+\d+\s+hours?', action.lower()):
        from modules.rssfeed import fetch_ai_news, format_articles_for_telegram

        time_period = extract_time_period(action)
        hours = int(re.search(r'\d+', time_period).group()) \
                if re.search(r'\d+', time_period) else 24

        # Fetch fresh news from NewsAPI
        news_articles = fetch_ai_news(hours=hours, count=5)

        for i, a in enumerate(news_articles, 1):
            logger.info(
                f"Final article {i}: "
                f"{a.get('title','')[:40]} | "
                f"url: {a.get('source_url', 'MISSING')}"
            )

        if news_articles:
            # Format for Telegram
            text = format_articles_for_telegram(news_articles, time_period)

            # Mark articles as published to prevent duplicates
            from modules.utils import mark_article_published
            for article in news_articles:
                mark_article_published(
                    article.get("source_url", ""),
                    article.get("title", "")
                )
            logger.info(
                f"Marked {len(news_articles)} articles as published"
            )

            # Use Claude to enhance summaries if needed
            system = (
                "You are an AI news analyst. "
                "The following are real news articles "
                "fetched from a live news API. "
                "For each article, if the summary seems "
                "too short or cut off, expand it slightly "
                "based on the title context. "
                "Keep the exact format. Plain text only."
            )
            enhanced = ask_claude(system, text, max_tokens=2000, model=MODEL_FAST)
            if not is_failed_response(enhanced):
                text = enhanced

            # Prepare articles for website
            articles = [{
                "title": a["title"],
                "summary": a["summary"],
                "category": "AI & Tech",
                "source_url": a.get("source_url"),
            } for a in news_articles]

        else:
            # Fallback to Claude web search if NewsAPI fails
            logger.warning("NewsAPI failed, falling back to web search")
            system = (
                f"You are a tech news analyst. Today: {now}. "
                "Find the 5 most recent AI and tech news. "
                "Plain text, numbered list, title then summary. "
                "No explanations about search limitations."
            )
            text = ask_claude_with_search(
                system,
                f"latest AI tech news {datetime.now().strftime('%B %d %Y')}",
                max_tokens=2000,
                model=MODEL_FAST,
            )
            text = clean_response(text)
            text = f"AI & Tech News (past {time_period})\n\n{text}"
            articles = parse_news_articles(text)

        # -- Publish to website --
        if articles:
            logger.info(f"Total articles to publish: {len(articles)}")

            try:
                import httpx
                import os
                website_url = os.environ.get("WEBSITE_URL", "http://localhost:8000")
                api_key = os.environ.get("WEBSITE_API_KEY", "")

                logger.info(f"Publishing {len(articles)} articles to {website_url}")
                logger.info(f"API key present: {bool(api_key)}")

                response = httpx.post(
                    f"{website_url}/api/publish",
                    json={"articles": articles},
                    headers={
                        "X-API-Key": api_key,
                        "Authorization": f"Bearer {api_key}"
                    },
                    timeout=30,
                )

                if response.status_code == 200:
                    logger.info(f"Published {len(articles)} articles to website")
                else:
                    logger.error(f"Publish failed: {response.status_code} - {response.text}")

            except Exception as e:
                logger.error(f"Publish error: {e}", exc_info=True)

            logger.info(f"Publish attempted to: {os.environ.get('WEBSITE_URL', 'http://localhost:8000')}")
        # -- End publish --

    elif action == "news_general":
        now_dt = datetime.now()
        cache_key = f"news_general_{now_dt.strftime('%Y%m%d_%H')}"

        cached = get_cached_news(cache_key)
        if cached:
            msg = cached
        else:
            system = (
                f"News analyst. Date: {now}. "
                "Find top 5 world news from past 24 hours. "
                "Format: '1. TITLE\nSummary (2 sentences max).\nSource: URL\n\n' "
                "Plain text only. No markdown. No intro text."
            )
            msg = ask_claude_news(system, f"Top 5 world news today {now}", max_tokens=2000)
            msg = clean_response(msg)
            set_cached_news(cache_key, msg)

        text = f"News Briefing\n\n{msg}"

    elif action in ("crypto", "crypto_snapshot") or \
         any(c in action.lower() for c in ["btc", "eth", "sol", "crypto"]):
        system = (
            f"You are a crypto analyst. Current date and time: {now}. "
            "Search for LIVE current cryptocurrency prices RIGHT NOW. "
            "Use search to find prices from the last 1 hour only. "
            "If price data is older than 2 hours, say 'Price data may be delayed'. "
            "Show for BTC, ETH, SOL: "
            "current price in USD, 24hr change %, 7 day change %. "
            "Format as clean table. "
            "Add data timestamp at the bottom showing when price was fetched."
        )
        msg = ask_claude_news(system, f"BTC ETH SOL live price USD right now {datetime.now().strftime('%B %d %Y %H:%M')}")
        msg = clean_response(msg)
        text = f"Crypto Snapshot\n\n{msg}"

    elif action == "daily_report":
        tasks    = task_list()
        pending  = "\n".join(f"- {t['text']}" for t in tasks) or "No pending tasks"
        schedules = schedule_load_all()
        sched_list = "\n".join(f"- {v['label']}" for v in schedules.values()) or "None"
        system = (
            f"You are ABbot, personal AI assistant. Today is {now}. "
            "Search for today's top news headline and weather briefly. "
            "Then give a motivating morning briefing covering tasks and schedule."
        )
        msg = ask_claude_with_search(
            system,
            f"Today: {now}\nPending tasks:\n{pending}\nSchedules:\n{sched_list}\n"
            "Give morning briefing with live news and weather.",
            max_tokens=2000,
            model=MODEL_FAST,
        )
        msg = clean_response(msg)
        text = f"Daily Report\n\n{msg}"

    else:
        # Generic scheduled action — use web search for any live data needed
        system = (
            f"You are ABbot, personal AI assistant. Today is {now}. "
            "Use web search if needed to get current/live information. "
            "Be concise and accurate."
        )
        msg = ask_claude_with_search(system, action, model=MODEL_FAST)
        msg = clean_response(msg)
        text = f"Scheduled Report\n{action}\n\n{msg}"

    try:
        await bot.send_message(chat_id=OWNER_CHAT_ID, text=text)
    except Exception as e:
        logger.error(f"Failed to send scheduled message: {e}")

async def handle_owner_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Use full_context if available (includes quoted message)
    text = context.user_data.pop("full_context", None) \
           or update.message.text or ""
    intent_data = parse_intent(text)
    intent = intent_data.get("intent", "chat")
    logger.info(f"DEBUG intent: {intent} | data: {intent_data}")

    # Override: if user is asking a question about schedules, use summary
    question_words = ["what will", "what are", "tell me", "summary", 
                      "summarize", "explain", "describe", "what have",
                      "what did", "what do", "remind me", "what's scheduled"]
    if intent == "schedule_list" and any(w in text.lower() for w in question_words):
        intent = "schedule_summary"
        logger.info(f"DEBUG intent overridden to: schedule_summary")

    if intent == "schedule_add":
        time_str  = intent_data.get("time") or "08:00"
        frequency = intent_data.get("frequency") or "daily"
        action    = intent_data.get("action") or "chat"
        job_id    = f"{action}_{time_str}".replace(":", "").replace(" ", "_")
        h, m      = map(int, time_str.split(":"))
        # Save city specific to this job if mentioned
        job_city = intent_data.get("city")
        if job_city:
            memory_set(f"city_{job_id}", job_city)
        schedule_save(job_id, {
            "label": text[:80], "time": time_str,
            "frequency": frequency, "action": action,
            "city": job_city or memory_get("city", "Kuala Lumpur"),
            "created": datetime.now().isoformat(),
        })

        city_msg = f"\nCity: {job_city}" if job_city else ""
        await update.message.reply_text(
            f"Scheduled!\n\n"
            f"Task: {text[:80]}\n"
            f"Time: {time_str} | Frequency: {frequency}"
            f"{city_msg}\n"
            f"ID: {job_id}\n\n"
            f"Use /schedules to see all."
        ) 

        scheduler = context.application.bot_data.get("scheduler")
        if scheduler:
            bot = context.bot
            if frequency == "daily":
                scheduler.add_job(
                    run_scheduled_job, "cron",
                    hour=h, minute=m,
                    args=[bot, job_id, action],
                    id=job_id, replace_existing=True,
                )
            elif frequency == "weekly" and intent_data.get("day"):
                scheduler.add_job(
                    run_scheduled_job, "cron",
                    day_of_week=intent_data["day"][:3].lower(),
                    hour=h, minute=m,
                    args=[bot, job_id, action],
                    id=job_id, replace_existing=True,
                )
        await update.message.reply_text(
            f"✅ *Scheduled!*\n\n📌 _{text[:80]}_\n⏰ *{time_str}* | 🔁 *{frequency}*\n🆔 `{job_id}`\n\nUse /schedules to see all.",
            parse_mode=None)

    elif intent == "schedule_list":
        jobs = schedule_load_all()
        if not jobs:
            await update.message.reply_text("📅 No schedules yet.")
            return
        lines = ["📅 *Your Schedules:*\n"]
        for jid, j in jobs.items():
            lines.append(f"• *{j['time']}* ({j['frequency']}) — {j['label']}\n  ID: `{jid}`")
        await update.message.reply_text("\n".join(lines), parse_mode=None)

    elif intent == "schedule_summary":
        jobs = schedule_load_all()
        if not jobs:
            await update.message.reply_text("You have no schedules set yet.")
            return
        schedule_text = "\n".join(
            f"- At {j['time']} ({j['frequency']}): {j['label']}"
            for j in jobs.values()
        )
        user_id = str(update.effective_user.id)
        system = build_owner_system_prompt(user_id, text)
        full_prompt = (
            f"User question: {text}\n\n"
            f"Current schedules:\n{schedule_text}\n\n"
            "Answer the user's question conversationally. "
            "Be specific about what will be sent at what time."
        )
        await update.message.chat.send_action("typing")
        reply = ask_claude_with_history(system, full_prompt, user_id, model=MODEL_FAST)
        await update.message.reply_text(reply)

    elif intent == "schedule_remove":
        job_id = intent_data.get("task_id") or intent_data.get("key")
        if job_id:
            schedule_delete(job_id)
            scheduler = context.application.bot_data.get("scheduler")
            if scheduler:
                try: scheduler.remove_job(job_id)
                except Exception: pass
            await update.message.reply_text(f"🗑 Schedule `{job_id}` removed.", parse_mode=None)
        else:
            await update.message.reply_text("Please give me the schedule ID. Use /schedules to see them.")

    elif intent == "task_add":
        action = intent_data.get("action") or text
        tid = task_add(action)
        await update.message.reply_text(f"✅ Task added!\n`{action}`\nID: `{tid}`", parse_mode=None)

    elif intent == "task_list":
        tasks = task_list()
        if not tasks:
            await update.message.reply_text("📋 No pending tasks! You're all clear. 🎉")
            return
        lines = ["📋 *Your Tasks:*\n"]
        for t in tasks:
            lines.append(f"• {t['text']}\n  ID: `{t['id']}`")
        await update.message.reply_text("\n".join(lines), parse_mode=None)

    elif intent == "task_done":
        tid = intent_data.get("task_id")
        if tid and task_done(tid):
            await update.message.reply_text(f"✅ Task done! Great work! 🎉")
        else:
            await update.message.reply_text("Task not found. Use /tasks to see IDs.")

    elif intent == "task_delete":
        tid = intent_data.get("task_id")
        if tid and task_delete(tid):
            await update.message.reply_text(f"🗑 Task deleted.")
        else:
            await update.message.reply_text("Task not found.")

    elif intent == "memory_set":
        key = intent_data.get("key") or "note"
        val = intent_data.get("value") or text
        memory_set(key, val)
        await update.message.reply_text(f"🧠 Got it! I'll remember:\n*{key}* = _{val}_", parse_mode=None)

    elif intent == "memory_get":
        key = intent_data.get("key")
        val = memory_get(key)
        if val:
            await update.message.reply_text(f"🧠 *{key}* = _{val}_", parse_mode=None)
        else:
            await update.message.reply_text(f"Nothing stored for *{key}* yet.", parse_mode=None)

    elif intent == "memory_list":
        mem = memory_all()
        if not mem:
            await update.message.reply_text("🧠 Nothing in memory yet.")
            return
        lines = ["🧠 *My Memory:*\n"]
        for k, v in mem.items():
            lines.append(f"• *{k}*: {v}")
        await update.message.reply_text("\n".join(lines), parse_mode=None)

    elif intent == "news":
        await update.message.chat.send_action("typing")
        await run_scheduled_job(context.bot, "manual_news", "news_ai")

    elif intent == "weather":
        # Extract city from message or use default
        job_city = intent_data.get("city") or memory_get("city", "Kuala Lumpur")
        await update.message.chat.send_action("typing")
        # Temporarily save city for this job
        memory_set("city_manual_weather", job_city)
        await run_scheduled_job(context.bot, "manual_weather", "weather")

    elif intent == "report":
        await update.message.chat.send_action("typing")
        await run_scheduled_job(context.bot, "manual_report", "daily_report")

    else:
        user_id = str(update.effective_user.id)
        auto_extract_memory(user_id, text)
        system = build_owner_system_prompt(user_id, text)
        await update.message.chat.send_action("typing")

        # Use web search for real-time queries
        realtime_keywords = [
            "price", "weather", "news", "today", "current", "now",
            "latest", "score", "rate", "stock", "crypto", "btc",
            "eth", "live", "right now", "this week", "yesterday"
        ]
        needs_search = any(w in text.lower() for w in realtime_keywords)

        if needs_search:
            reply = ask_claude_with_search(system, text, user_id, model=MODEL_SMART)
            reply = clean_response(reply)
        else:
            reply = ask_claude_with_history(system, text, user_id, model=MODEL_SMART)

        await update.message.reply_text(reply)

async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_chat.id): return
    tasks = task_list()
    if not tasks:
        await update.message.reply_text("📋 No pending tasks! You're all clear. 🎉")
        return
    lines = ["📋 *Pending Tasks:*\n"]
    for t in tasks:
        lines.append(f"• {t['text']}\n  ID: `{t['id']}`")
    await update.message.reply_text("\n".join(lines), parse_mode=None)

async def cmd_schedules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_chat.id): return
    jobs = schedule_load_all()
    if not jobs:
        await update.message.reply_text("📅 No schedules yet.\n\nTry: _schedule daily 7am weather_", parse_mode=None)
        return
    lines = ["📅 *Active Schedules:*\n"]
    for jid, j in jobs.items():
        lines.append(f"• *{j['time']}* ({j['frequency']}) — {j['label']}\n  ID: `{jid}`")
    await update.message.reply_text("\n".join(lines), parse_mode=None)

async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_chat.id): return
    mem = memory_all()
    if not mem:
        await update.message.reply_text("🧠 Nothing in memory yet.\n\nTry: _remember my city is Kuala Lumpur_", parse_mode=None)
        return
    lines = ["🧠 *My Memory:*\n"]
    for k, v in mem.items():
        lines.append(f"• *{k}*: {v}")
    await update.message.reply_text("\n".join(lines), parse_mode=None)

async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_chat.id): return
    await update.message.chat.send_action("typing")
    await run_scheduled_job(context.bot, "manual_news", "news_ai")

async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_chat.id): return
    await update.message.chat.send_action("typing")
    await run_scheduled_job(context.bot, "manual_report", "daily_report")

async def cmd_skills(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_chat.id): return
    skills = list_skills()
    if not skills:
        await update.message.reply_text(
            "No skills loaded yet.\n\n"
            "Add .md files to the skills/ folder to teach ABbot new behaviors!"
        )
        return
    skill_list = "\n".join(f"• {s}" for s in skills)
    await update.message.reply_text(
        f"Loaded Skills ({len(skills)}):\n\n{skill_list}\n\n"
        f"Add .md files to skills/ folder to add more."
    )
