#!/bin/bash
echo "🤖 Creating AgentBot files..."

# Create folders
mkdir -p modules data

# ── modules/__init__.py ──────────────────────────────────────────────────────
cat > modules/__init__.py << 'EOF'
EOF

# ── requirements.txt ─────────────────────────────────────────────────────────
cat > requirements.txt << 'EOF'
python-telegram-bot==21.5
anthropic
python-dotenv
apscheduler==3.10.4
EOF

# ── .env.example ─────────────────────────────────────────────────────────────
cat > .env.example << 'EOF'
TELEGRAM_BOT_TOKEN=your_bot_token_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
OWNER_CHAT_ID=your_personal_telegram_chat_id
ALLOWED_CHAT_IDS=your_chat_id,family_group_chat_id
EOF

# ── modules/utils.py ─────────────────────────────────────────────────────────
cat > modules/utils.py << 'EOF'
"""Shared helpers: Claude API, auth, persistent memory, tasks, schedules."""

import os, json, logging
from datetime import datetime
from pathlib import Path
import anthropic

logger = logging.getLogger(__name__)

claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

def ask_claude(system: str, user_msg: str, max_tokens: int = 1500) -> str:
    try:
        r = claude.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        return r.content[0].text
    except Exception as e:
        logger.error(f"Claude error: {e}")
        return "⚠️ Couldn't reach Claude. Please try again."

ALLOWED_CHAT_IDS = set(
    int(x) for x in os.environ.get("ALLOWED_CHAT_IDS", "").split(",") if x.strip()
)
OWNER_CHAT_ID = int(os.environ.get("OWNER_CHAT_ID", "0"))

def is_allowed(chat_id: int) -> bool:
    return (not ALLOWED_CHAT_IDS) or (chat_id in ALLOWED_CHAT_IDS)

def is_owner(chat_id: int) -> bool:
    return chat_id == OWNER_CHAT_ID

DATA_DIR      = Path("data")
MEMORY_FILE   = DATA_DIR / "memory.json"
SCHEDULE_FILE = DATA_DIR / "schedules.json"
TASKS_FILE    = DATA_DIR / "tasks.json"
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
EOF

# ── modules/study.py ──────────────────────────────────────────────────────────
cat > modules/study.py << 'EOF'
"""Study handlers for Isaac (Year 10) and Arik (Year 6)."""

from telegram import Update
from telegram.ext import ContextTypes
from .utils import ask_claude, is_allowed

USER_PROFILES = {
    "isaac_username": {"year": 10, "name": "Isaac"},
    "arik_username":  {"year": 6,  "name": "Arik"},
}

def _year_ctx(username: str) -> str:
    p = USER_PROFILES.get((username or "").lower())
    return f"You are helping {p['name']}, a Year {p['year']} student." if p else \
           "You are helping a student."

async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_chat.id): return
    q = " ".join(context.args)
    if not q:
        await update.message.reply_text("Usage: `/ask Why is the sky blue?`", parse_mode="Markdown")
        return
    sys = (f"{_year_ctx(update.effective_user.username)} Answer clearly and concisely "
           "with a simple real-world example where helpful.")
    await update.message.chat.send_action("typing")
    await update.message.reply_text(f"💡 {ask_claude(sys, q)}")

async def cmd_math(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_chat.id): return
    p = " ".join(context.args)
    if not p:
        await update.message.reply_text("Usage: `/math 2x + 5 = 15`", parse_mode="Markdown")
        return
    sys = (f"{_year_ctx(update.effective_user.username)} You are a math tutor. "
           "Solve step by step with clear explanation. End with the final answer.")
    await update.message.chat.send_action("typing")
    await update.message.reply_text(
        f"➕ *Math Solution*\n\n{ask_claude(sys, f'Solve: {p}')}", parse_mode="Markdown")

async def cmd_chinese(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_chat.id): return
    t = " ".join(context.args)
    if not t:
        await update.message.reply_text("Usage: `/chinese 你好` or `/chinese hello`", parse_mode="Markdown")
        return
    sys = ("Chinese language tutor. For Chinese: give English translation, Pinyin, grammar note. "
           "For English: give Simplified Chinese, Pinyin, pronunciation tips.")
    await update.message.chat.send_action("typing")
    await update.message.reply_text(
        f"🀄 *Chinese Helper*\n\n{ask_claude(sys, t)}", parse_mode="Markdown")

async def cmd_homework(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_chat.id): return
    q = " ".join(context.args)
    if not q:
        await update.message.reply_text("Usage: `/homework What caused World War 1?`", parse_mode="Markdown")
        return
    sys = (f"{_year_ctx(update.effective_user.username)} Homework tutor. "
           "Guide understanding, don't just give answers. End with a short summary they can use.")
    await update.message.chat.send_action("typing")
    await update.message.reply_text(
        f"📝 *Homework Help*\n\n{ask_claude(sys, q)}", parse_mode="Markdown")
EOF

# ── modules/agent.py ──────────────────────────────────────────────────────────
cat > modules/agent.py << 'EOF'
"""Agent handlers — owner personal AI agent."""

import json, logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from .utils import (
    ask_claude, is_owner, is_allowed,
    memory_set, memory_get, memory_all,
    schedule_save, schedule_load_all, schedule_delete,
    task_add, task_done, task_list, task_delete,
    OWNER_CHAT_ID,
)

logger = logging.getLogger(__name__)

def parse_intent(text: str) -> dict:
    system = """You are an intent parser for a personal AI agent Telegram bot.
Parse the user message and return ONLY valid JSON:
{
  "intent": one of [schedule_add, schedule_list, schedule_remove, task_add, task_list, task_done, task_delete, memory_set, memory_get, memory_list, news, weather, report, chat],
  "time": "HH:MM" or null,
  "frequency": "daily" or "weekly" or "once" or null,
  "day": day of week or null,
  "action": the task to perform as string,
  "key": memory key or null,
  "value": memory value or null,
  "task_id": task id or null
}
Return ONLY the JSON object, no markdown, no explanation."""
    raw = ask_claude(system, text, max_tokens=300)
    try:
        return json.loads(raw.strip().strip("```json").strip("```").strip())
    except Exception:
        return {"intent": "chat", "action": text}

async def run_scheduled_job(bot, job_id: str, action: str):
    city = memory_get("city", "Kuala Lumpur")
    if action == "weather":
        system = f"Weather assistant. City: {city}. Give a brief morning weather summary and what to wear."
        msg = ask_claude(system, f"Morning weather summary for {city}, {datetime.now().strftime('%A %d %B')}")
        text = f"🌤 *Morning Weather — {city}*\n\n{msg}"
    elif action in ("news_ai", "news"):
        system = "News analyst. Summarize top 5 AI and tech news stories from past 24hrs. Each: headline + 2 sentence summary + why it matters."
        msg = ask_claude(system, f"Top 5 AI/tech news for {datetime.now().strftime('%A %d %B %Y')}", max_tokens=1500)
        text = f"📰 *Morning AI & Tech News*\n\n{msg}"
    elif action == "news_general":
        system = "News briefing assistant. Top 5 world news stories — headline and 2 sentence summary each."
        msg = ask_claude(system, f"Top 5 news for {datetime.now().strftime('%A %d %B %Y')}", max_tokens=1500)
        text = f"📰 *Morning News Briefing*\n\n{msg}"
    elif action == "daily_report":
        tasks = task_list()
        pending = "\n".join(f"• {t['text']}" for t in tasks) or "No pending tasks"
        schedules = schedule_load_all()
        sched_list = "\n".join(f"• {v['label']}" for v in schedules.values()) or "None"
        system = "Personal productivity assistant. Give a motivating morning briefing."
        msg = ask_claude(system,
            f"Today: {datetime.now().strftime('%A %d %B %Y')}\n"
            f"Pending tasks:\n{pending}\nActive schedules:\n{sched_list}\n"
            "Give a short motivating morning briefing and one productivity tip.")
        text = f"📋 *Daily Morning Report*\n\n{msg}"
    else:
        msg = ask_claude("Personal AI assistant. Be concise and helpful.", action)
        text = f"🤖 *Scheduled Task*\n_{action}_\n\n{msg}"
    try:
        await bot.send_message(chat_id=OWNER_CHAT_ID, text=text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Failed to send scheduled message: {e}")

async def handle_owner_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    intent_data = parse_intent(text)
    intent = intent_data.get("intent", "chat")

    if intent == "schedule_add":
        time_str  = intent_data.get("time") or "08:00"
        frequency = intent_data.get("frequency") or "daily"
        action    = intent_data.get("action") or "chat"
        job_id    = f"{action}_{time_str}".replace(":", "").replace(" ", "_")
        h, m      = map(int, time_str.split(":"))
        schedule_save(job_id, {
            "label": text[:80], "time": time_str,
            "frequency": frequency, "action": action,
            "created": datetime.now().isoformat(),
        })
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
            parse_mode="Markdown")

    elif intent == "schedule_list":
        jobs = schedule_load_all()
        if not jobs:
            await update.message.reply_text("📅 No schedules yet.")
            return
        lines = ["📅 *Your Schedules:*\n"]
        for jid, j in jobs.items():
            lines.append(f"• *{j['time']}* ({j['frequency']}) — {j['label']}\n  ID: `{jid}`")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    elif intent == "schedule_remove":
        job_id = intent_data.get("task_id") or intent_data.get("key")
        if job_id:
            schedule_delete(job_id)
            scheduler = context.application.bot_data.get("scheduler")
            if scheduler:
                try: scheduler.remove_job(job_id)
                except Exception: pass
            await update.message.reply_text(f"🗑 Schedule `{job_id}` removed.", parse_mode="Markdown")
        else:
            await update.message.reply_text("Please give me the schedule ID. Use /schedules to see them.")

    elif intent == "task_add":
        action = intent_data.get("action") or text
        tid = task_add(action)
        await update.message.reply_text(f"✅ Task added!\n`{action}`\nID: `{tid}`", parse_mode="Markdown")

    elif intent == "task_list":
        tasks = task_list()
        if not tasks:
            await update.message.reply_text("📋 No pending tasks! You're all clear. 🎉")
            return
        lines = ["📋 *Your Tasks:*\n"]
        for t in tasks:
            lines.append(f"• {t['text']}\n  ID: `{t['id']}`")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

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
        await update.message.reply_text(f"🧠 Got it! I'll remember:\n*{key}* = _{val}_", parse_mode="Markdown")

    elif intent == "memory_get":
        key = intent_data.get("key")
        val = memory_get(key)
        if val:
            await update.message.reply_text(f"🧠 *{key}* = _{val}_", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"Nothing stored for *{key}* yet.", parse_mode="Markdown")

    elif intent == "memory_list":
        mem = memory_all()
        if not mem:
            await update.message.reply_text("🧠 Nothing in memory yet.")
            return
        lines = ["🧠 *My Memory:*\n"]
        for k, v in mem.items():
            lines.append(f"• *{k}*: {v}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    elif intent == "news":
        await update.message.chat.send_action("typing")
        await run_scheduled_job(context.bot, "manual_news", "news_ai")

    elif intent == "weather":
        await update.message.chat.send_action("typing")
        await run_scheduled_job(context.bot, "manual_weather", "weather")

    elif intent == "report":
        await update.message.chat.send_action("typing")
        await run_scheduled_job(context.bot, "manual_report", "daily_report")

    else:
        mem_summary = str(memory_all())[:500]
        system = (
            "You are a personal AI agent assistant named AgentBot. "
            f"Owner context from memory: {mem_summary}. "
            f"Be concise and helpful. Today: {datetime.now().strftime('%A %d %B %Y %H:%M')}."
        )
        await update.message.chat.send_action("typing")
        await update.message.reply_text(ask_claude(system, text))

async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_chat.id): return
    tasks = task_list()
    if not tasks:
        await update.message.reply_text("📋 No pending tasks! You're all clear. 🎉")
        return
    lines = ["📋 *Pending Tasks:*\n"]
    for t in tasks:
        lines.append(f"• {t['text']}\n  ID: `{t['id']}`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_schedules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_chat.id): return
    jobs = schedule_load_all()
    if not jobs:
        await update.message.reply_text("📅 No schedules yet.\n\nTry: _schedule daily 7am weather_", parse_mode="Markdown")
        return
    lines = ["📅 *Active Schedules:*\n"]
    for jid, j in jobs.items():
        lines.append(f"• *{j['time']}* ({j['frequency']}) — {j['label']}\n  ID: `{jid}`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_chat.id): return
    mem = memory_all()
    if not mem:
        await update.message.reply_text("🧠 Nothing in memory yet.\n\nTry: _remember my city is Kuala Lumpur_", parse_mode="Markdown")
        return
    lines = ["🧠 *My Memory:*\n"]
    for k, v in mem.items():
        lines.append(f"• *{k}*: {v}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_chat.id): return
    await update.message.chat.send_action("typing")
    await run_scheduled_job(context.bot, "manual_news", "news_ai")

async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_chat.id): return
    await update.message.chat.send_action("typing")
    await run_scheduled_job(context.bot, "manual_report", "daily_report")
EOF

# ── bot.py ────────────────────────────────────────────────────────────────────
cat > bot.py << 'EOF'
#!/usr/bin/env python3
"""AgentBot — Personal AI Agent + Family Study Assistant"""

import os, logging, asyncio
from dotenv import load_dotenv
load_dotenv()

from telegram import Update, BotCommand
from telegram.ext import (
    Application, CommandHandler,
    MessageHandler, ContextTypes, filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from modules.utils import is_owner, is_allowed, schedule_load_all, ask_claude
from modules.study import cmd_ask, cmd_math, cmd_chinese, cmd_homework, USER_PROFILES
from modules.agent import (
    handle_owner_message, run_scheduled_job,
    cmd_tasks, cmd_schedules, cmd_memory, cmd_news, cmd_report,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_chat.id): return
    if is_owner(update.effective_chat.id):
        msg = (
            "🤖 *AgentBot is online!*\n\n"
            "*Study:* /ask /math /chinese /homework\n\n"
            "*Agent:* /tasks /schedules /memory /news /report\n\n"
            "*💬 Just talk to me naturally!*\n"
            "• _Schedule daily 7am weather_\n"
            "• _Report AI top 5 news at 8am daily_\n"
            "• _Add task: review project proposal_\n"
            "• _Remember my city is Kuala Lumpur_\n"
        )
    else:
        msg = (
            "👋 *Hi! I'm AgentBot!*\n\n"
            "📚 /ask — any question\n"
            "➕ /math — math solver\n"
            "🀄 /chinese — Chinese translation\n"
            "📝 /homework — homework help\n"
        )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def route_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    chat_id = update.effective_chat.id
    if not is_allowed(chat_id): return
    msg = update.message
    is_private = msg.chat.type == "private"
    bot_mentioned = context.bot.username and f"@{context.bot.username}" in (msg.text or "")
    is_reply_to_bot = (
        msg.reply_to_message and
        msg.reply_to_message.from_user and
        msg.reply_to_message.from_user.id == context.bot.id
    )
    if is_private and is_owner(chat_id):
        await handle_owner_message(update, context)
        return
    if not (is_private or bot_mentioned or is_reply_to_bot): return
    text = (msg.text or "").replace(f"@{context.bot.username}", "").strip()
    if not text: return
    username = update.effective_user.username or ""
    profile = USER_PROFILES.get(username.lower())
    ctx = f"You are helping {profile['name']}, a Year {profile['year']} student." \
          if profile else "You are a helpful assistant."
    await msg.chat.send_action("typing")
    await msg.reply_text(ask_claude(f"{ctx} Be friendly and encouraging.", text))

def restore_schedules(scheduler, bot):
    jobs = schedule_load_all()
    for job_id, j in jobs.items():
        try:
            h, m = map(int, j["time"].split(":"))
            freq = j.get("frequency", "daily")
            action = j.get("action", "chat")
            if freq == "daily":
                scheduler.add_job(
                    run_scheduled_job, "cron",
                    hour=h, minute=m,
                    args=[bot, job_id, action],
                    id=job_id, replace_existing=True,
                )
            elif freq == "weekly" and j.get("day"):
                scheduler.add_job(
                    run_scheduled_job, "cron",
                    day_of_week=j["day"][:3].lower(),
                    hour=h, minute=m,
                    args=[bot, job_id, action],
                    id=job_id, replace_existing=True,
                )
            logger.info(f"Restored: {job_id} at {j['time']} ({freq})")
        except Exception as e:
            logger.error(f"Failed to restore {job_id}: {e}")

async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    scheduler = AsyncIOScheduler()
    app.bot_data["scheduler"] = scheduler
    restore_schedules(scheduler, app.bot)
    scheduler.start()
    logger.info("⏰ Scheduler started")
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("ask",       cmd_ask))
    app.add_handler(CommandHandler("math",      cmd_math))
    app.add_handler(CommandHandler("chinese",   cmd_chinese))
    app.add_handler(CommandHandler("homework",  cmd_homework))
    app.add_handler(CommandHandler("tasks",     cmd_tasks))
    app.add_handler(CommandHandler("schedules", cmd_schedules))
    app.add_handler(CommandHandler("memory",    cmd_memory))
    app.add_handler(CommandHandler("news",      cmd_news))
    app.add_handler(CommandHandler("report",    cmd_report))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, route_message))
    await app.bot.set_my_commands([
        BotCommand("start",     "Welcome & help"),
        BotCommand("ask",       "Ask any question"),
        BotCommand("math",      "Step-by-step math"),
        BotCommand("chinese",   "Chinese translation"),
        BotCommand("homework",  "Homework help"),
        BotCommand("tasks",     "View pending tasks"),
        BotCommand("schedules", "View active schedules"),
        BotCommand("memory",    "View bot memory"),
        BotCommand("news",      "Top AI & tech news"),
        BotCommand("report",    "Daily report now"),
    ])
    logger.info("🤖 AgentBot is running...")
    await app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    asyncio.run(main())
EOF

echo ""
echo "✅ All files created! Here is what was created:"
ls -la
echo ""
echo "📁 modules/:"
ls -la modules/
echo ""
echo "Next steps:"
echo "1. cp .env.example .env"
echo "2. nano .env  (fill in your tokens)"
echo "3. pip install -r requirements.txt"
echo "4. python bot.py"
