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
from modules.utils import handle_photo
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from modules.utils import (
    is_owner, is_allowed, schedule_load_all,
    ask_claude_with_history, MODEL_SMART, get_preferences_prompt,
)
from modules.study import cmd_ask, cmd_math, cmd_chinese, cmd_homework, USER_PROFILES
from modules.agent import (
    handle_owner_message, run_scheduled_job,
    cmd_tasks, cmd_schedules, cmd_memory, cmd_news, cmd_report, cmd_skills,
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
            "*Agent:* /tasks /schedules /memory /news /report /skills\n\n"
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
    await update.message.reply_text(msg, parse_mode=None)

async def route_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    chat_id = update.effective_chat.id
    if not is_allowed(chat_id):
        return

    msg = update.message
    is_private = msg.chat.type == "private"
    bot_mentioned = (
        context.bot.username and
        f"@{context.bot.username}" in (msg.text or "")
    )
    is_reply_to_bot = (
        msg.reply_to_message and
        msg.reply_to_message.from_user and
        msg.reply_to_message.from_user.id == context.bot.id
    )

    if not (is_private or bot_mentioned or is_reply_to_bot):
        return

    # Extract the user's message text
    text = (msg.text or "").replace(
        f"@{context.bot.username}", ""
    ).strip()
    if not text:
        return

    # Extract quoted/replied message content
    quoted_text = ""
    if msg.reply_to_message:
        replied_msg = msg.reply_to_message
        if replied_msg.text:
            quoted_text = replied_msg.text
        elif replied_msg.caption:
            quoted_text = replied_msg.caption

    # Build full context with quoted message
    if quoted_text:
        full_context = (
            f"[The user is replying to this message:\n"
            f"\"{quoted_text[:500]}\"\n]\n\n"
            f"User's reply: {text}"
        )
    else:
        full_context = text

    if is_private and is_owner(chat_id):
        # Inject full context (including quoted message) into the update text
        update.message._text = full_context
        await handle_owner_message(update, context)
        return

    username = update.effective_user.username or ""
    user_id = str(update.effective_user.id)
    profile = USER_PROFILES.get(username.lower())
    ctx = (
        f"You are helping {profile['name']}, a Year {profile['year']} student."
        if profile else "You are a helpful assistant."
    )
    prefs = get_preferences_prompt()
    system = (
        f"{ctx}\n{prefs}\n"
        "Be friendly and encouraging. "
        "If the user is replying to a previous message, "
        "use that context to give a relevant answer."
    )
    await msg.chat.send_action("typing")
    await msg.reply_text(
        ask_claude_with_history(system, full_context, user_id, model=MODEL_SMART)
    )

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

async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.photo:
        return
    chat_id = update.effective_chat.id
    if not is_allowed(chat_id):
        return

    msg = update.message
    is_private = msg.chat.type == "private"
    bot_mentioned = (
        context.bot.username and
        f"@{context.bot.username}" in (msg.caption or "")
    )
    is_reply_to_bot = (
        msg.reply_to_message and
        msg.reply_to_message.from_user and
        msg.reply_to_message.from_user.id == context.bot.id
    )

    # In group — only respond if mentioned or replied to
    if not (is_private or bot_mentioned or is_reply_to_bot):
        return

    await msg.chat.send_action("typing")
    caption = msg.caption or ""
    # Remove bot mention from caption if present
    if context.bot.username:
        caption = caption.replace(f"@{context.bot.username}", "").strip()

    reply = await handle_photo(context.bot, msg.photo, caption)
    await msg.reply_text(f"🖼 {reply}")

async def cmd_clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear conversation history for fresh start."""
    if not is_owner(update.effective_chat.id): return
    from modules.utils import history_clear
    user_id = str(update.effective_user.id)
    history_clear(user_id)
    await update.message.reply_text("Memory cleared! Fresh start. 🧹")

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
    app.add_handler(CommandHandler("skills",    cmd_skills))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, route_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_message))
    app.add_handler(CommandHandler("clear", cmd_clear_history))
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
        BotCommand("skills",    "View loaded AI skills"),
        BotCommand("clear",     "Clear conversation history"),
    ])
    logger.info("🤖 AgentBot is running...")
    await app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
