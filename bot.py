#!/usr/bin/env python3
"""AgentBot — ABbot Professional AI Agent"""

import os, logging, asyncio
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
load_dotenv()

from telegram import Update, BotCommand
from telegram.ext import (
    Application, CommandHandler,
    MessageHandler, ContextTypes, filters,
)
from modules.utils import handle_photo
from modules import gmail_monitor
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from modules.utils import (
    is_owner, is_allowed, schedule_load_all,
    ask_claude_with_history, MODEL_SMART, get_preferences_prompt,
    clear_old_published,
)
from modules.study import cmd_ask, cmd_math, cmd_chinese, cmd_homework, USER_PROFILES
from modules.agent import (
    handle_owner_message, run_scheduled_job,
    cmd_tasks, cmd_schedules, cmd_memory, cmd_news, cmd_xfeed, cmd_report, cmd_skills,
    cmd_memories, cmd_forget,
    handle_delete_last, fire_scheduled_deletion,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# Deduplication: track processed update IDs to skip Telegram retries
_processed_updates: set = set()
_MAX_PROCESSED = 1000

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_chat.id): return
    if is_owner(update.effective_chat.id):
        msg = (
            "ABbot - Professional AI Agent\n\n"
            "Commands:\n"
            "/tasks - Pending tasks\n"
            "/schedules - Active schedules\n"
            "/memory - Stored memory\n"
            "/memories - Memory by category\n"
            "/forget <key> - Delete a memory\n"
            "/news - Latest AI & Tech news\n"
            "/report - Daily report\n"
            "/skills - Loaded skills\n"
            "/newsstatus - News tracking stats\n"
            "/clear - Clear chat history\n\n"
            "Just talk naturally:\n"
            "- Schedule daily 7am weather in KL\n"
            "- Add task: review quarterly report\n"
            "- What is BTC price now?\n"
            "- Translate this to Traditional Chinese\n"
            "- Latest AI news last 8 hours"
        )
    else:
        msg = (
            "ABbot AI Assistant\n\n"
            "How can I help you today?\n\n"
            "I can help with:\n"
            "- Questions and research\n"
            "- Math and calculations\n"
            "- Language translation\n"
            "- Analysis and explanations\n\n"
            "Just type your question!"
        )
    await update.message.reply_text(msg, parse_mode=None)

async def route_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _processed_updates

    # Deduplicate Telegram retries
    update_id = update.update_id
    if update_id in _processed_updates:
        logger.debug(f"Duplicate update {update_id}, skipping")
        return
    _processed_updates.add(update_id)
    if len(_processed_updates) > _MAX_PROCESSED:
        oldest = sorted(_processed_updates)
        _processed_updates = set(oldest[-500:])

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
    text = (msg.text or "").strip()
    if context.bot.username:
        text = text.replace(f"@{context.bot.username}", "").strip()
    if not text:
        return

    logger.info(
        f"Message from "
        f"{update.effective_user.username}: "
        f"{text[:50]}"
    )

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

    try:
        if is_private and is_owner(chat_id):
            await handle_owner_message(update, context)
            return

        username = update.effective_user.username or ""
        user_id = str(update.effective_user.id)
        from modules.study import _get_user_context
        ctx = _get_user_context(username)
        prefs = get_preferences_prompt()
        system = (
            f"{ctx}\n{prefs}\n"
            "Be friendly and encouraging. "
            "If the user is replying to a previous message, "
            "use that context to give a relevant answer."
        )
        await msg.chat.send_action("typing")
        await msg.reply_text(
            ask_claude_with_history(system, full_context, user_id, model=MODEL_SMART, history_text=text)
        )
    except Exception as e:
        logger.error(f"route_message error: {e}")
        try:
            await msg.reply_text(
                "Sorry, I had trouble with that. Please try again."
            )
        except Exception:
            pass

def restore_reminders(scheduler, bot):
    from modules.reminders import (
        _load_reminders, delete_reminder)
    from modules.agent import fire_reminder
    reminders = _load_reminders()
    now = datetime.now(timezone.utc)
    restored = 0
    expired = 0
    for rid, reminder in reminders.items():
        try:
            fire_at_str = reminder.get(
                "fire_at", "")
            if not fire_at_str:
                continue
            fire_at = datetime.fromisoformat(
                fire_at_str)
            if fire_at.tzinfo is None:
                fire_at = fire_at.replace(
                    tzinfo=timezone.utc)
            chat_id = reminder.get("chat_id")
            message = reminder.get("message", "")
            if fire_at <= now:
                if fire_at >= now - timedelta(
                        hours=2):
                    scheduler.add_job(
                        fire_reminder,
                        "date",
                        run_date=now + timedelta(
                            seconds=10),
                        args=[bot, rid,
                              chat_id,
                              f"(Delayed) {message}"],
                        id=f"delayed_{rid}",
                        replace_existing=True,
                    )
                else:
                    delete_reminder(rid)
                    expired += 1
            else:
                scheduler.add_job(
                    fire_reminder,
                    "date",
                    run_date=fire_at,
                    args=[bot, rid,
                          chat_id, message],
                    id=rid,
                    replace_existing=True,
                )
                restored += 1
        except Exception as e:
            logger.error(
                f"Restore reminder error "
                f"{rid}: {e}")
    logger.info(
        f"Reminders restored={restored} "
        f"expired={expired}")


def restore_scheduled_deletions(application, scheduler):
    """Re-queue pending deletions after bot restart."""
    from modules.message_manager import get_all_scheduled_deletions, remove_scheduled_deletion
    now = datetime.now()
    all_deletions = get_all_scheduled_deletions()
    restored = 0
    fired_late = 0
    cleaned = 0
    for deletion_id, entry in list(all_deletions.items()):
        try:
            fire_at = datetime.fromisoformat(entry["fire_at"])
        except Exception:
            remove_scheduled_deletion(deletion_id)
            cleaned += 1
            continue
        try:
            age_hours = (now - datetime.fromisoformat(entry["created_at"])).total_seconds() / 3600
        except Exception:
            age_hours = 0
        if age_hours > 48:
            remove_scheduled_deletion(deletion_id)
            cleaned += 1
            continue
        if fire_at <= now:
            scheduler.add_job(
                fire_scheduled_deletion,
                "date",
                run_date=now + timedelta(seconds=2),
                args=[application.bot, deletion_id],
                id=deletion_id,
                replace_existing=True,
            )
            fired_late += 1
        else:
            scheduler.add_job(
                fire_scheduled_deletion,
                "date",
                run_date=fire_at,
                args=[application.bot, deletion_id],
                id=deletion_id,
                replace_existing=True,
            )
            restored += 1
    logger.info(f"Deletions restored={restored} fired_late={fired_late} cleaned={cleaned}")


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

async def cmd_feedhealth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_chat.id):
        return
    await update.message.chat.send_action("typing")
    from modules.rssfeed import check_feed_health
    health = check_feed_health()
    ok = sum(1 for v in health.values() if v["status"] == "ok")
    empty = sum(1 for v in health.values() if v["status"] == "empty")
    error = sum(1 for v in health.values() if v["status"] == "error")
    lines = [
        "RSS Feed Health",
        f"OK: {ok} | Empty: {empty} | Error: {error}",
        "",
    ]
    for name, result in health.items():
        status = result["status"]
        icon = "✅" if status == "ok" else "⚠️" if status == "empty" else "❌"
        entries = result.get("entries", 0)
        lines.append(
            f"{icon} {name}: {entries} entries"
            if status == "ok" else
            f"{icon} {name}: {status}"
        )
    await update.message.reply_text("\n".join(lines))


async def cmd_newsstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_chat.id):
        return
    from modules.utils import get_published_count
    count = get_published_count()
    await update.message.reply_text(
        f"News Stats:\n"
        f"Total articles tracked: {count}\n"
        f"(Articles already sent won't repeat)"
    )


async def cmd_reminders(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_chat.id):
        return
    from modules.reminders import get_all_reminders
    reminders = get_all_reminders()
    if not reminders:
        await update.message.reply_text(
            "No pending reminders.\n\n"
            "Tell me when you finish any activity\n"
            "and I will set a reminder automatically!"
        )
        return
    now = datetime.now(timezone.utc)
    MYT = timedelta(hours=8)
    lines = [
        f"Pending Reminders ({len(reminders)})\n"
    ]
    for rid, r in reminders.items():
        try:
            fire_at = datetime.fromisoformat(
                r.get("fire_at", ""))
            if fire_at.tzinfo is None:
                fire_at = fire_at.replace(
                    tzinfo=timezone.utc)
            fire_local = fire_at + MYT
            diff = fire_at - now
            if diff.total_seconds() > 0:
                hrs = diff.total_seconds() / 3600
                if hrs < 1:
                    tl = f"{int(hrs*60)}min"
                elif hrs < 24:
                    tl = f"{hrs:.1f}hrs"
                else:
                    tl = f"{hrs/24:.1f}days"
                status = f"in {tl}"
            else:
                status = "firing soon"
            rtype = r.get("type", "general")
            preview = r.get("message", "")[:50]
            lines.append(
                f"• [{rtype}] "
                f"{fire_local.strftime('%d %b %H:%M')} "
                f"MYT ({status})\n"
                f"  {preview}...\n"
                f"  ID: {rid}"
            )
        except Exception:
            lines.append(f"• {rid}: (error)")
    lines.append(
        "\nUse /cancelreminder <id> to cancel."
    )
    await update.message.reply_text(
        "\n".join(lines))


async def cmd_cancel_reminder(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_chat.id):
        return
    rid = " ".join(context.args).strip()
    if not rid:
        await update.message.reply_text(
            "Usage: /cancelreminder <id>\n"
            "Use /reminders to see IDs."
        )
        return
    from modules.reminders import delete_reminder
    scheduler = context.application.bot_data.get(
        "scheduler")
    if scheduler:
        try:
            scheduler.remove_job(rid)
        except Exception:
            pass
    if delete_reminder(rid):
        await update.message.reply_text(
            f"Reminder cancelled: {rid}")
    else:
        await update.message.reply_text(
            f"Reminder not found: {rid}")


async def cmd_windows(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_chat.id):
        return
    from modules.utils import (
        get_all_time_windows,
        _load,
        TIME_WINDOWS_FILE,
        DEFAULT_TIME_WINDOWS,
    )
    custom = _load(TIME_WINDOWS_FILE)
    emoji_map = {
        "meal": "🍽️", "food": "🍽️",
        "breakfast": "🍽️", "lunch": "🍽️",
        "dinner": "🍽️", "supper": "🍽️",
        "study": "📚", "homework": "📚",
        "learning": "📚", "revision": "📚",
        "exercise": "💪", "workout": "💪",
        "gym": "💪", "run": "💪",
        "medication": "💊", "medicine": "💊",
        "pill": "💊", "vitamin": "💊",
        "supplement": "💊",
        "sleep": "😴", "nap": "😴", "rest": "😴",
        "prayer": "🙏",
        "water": "💧", "drink": "💧",
        "work": "💼", "meeting": "🤝",
        "reading": "📖", "break": "☕",
    }
    lines = ["Time Windows\n"]
    if custom:
        lines.append("Your Custom Windows:")
        for key, val in custom.items():
            if isinstance(val, dict):
                hours = val.get("hours", 0)
                emoji = emoji_map.get(key, "⏰")
                lines.append(
                    f"  {emoji} {key}: "
                    f"{hours} hours"
                )
        lines.append("")
    lines.append("Default Windows:")
    shown = set()
    for key, val in DEFAULT_TIME_WINDOWS.items():
        if isinstance(val, dict):
            label = val.get("label", key)
            if label not in shown:
                hours = val.get("hours", 0)
                emoji = emoji_map.get(key, "⏰")
                lines.append(
                    f"  {emoji} {label}: "
                    f"{hours} hours"
                )
                shown.add(label)
    lines.append(
        "\nTo set custom window:\n"
        "Remember my [activity] window "
        "is [X] hours\n\n"
        "Example:\n"
        "Remember my study window is 4 hours"
    )
    await update.message.reply_text(
        "\n".join(lines))

async def cmd_delete_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from modules.utils import OWNER_CHAT_ID
    if update.effective_user.id != OWNER_CHAT_ID or update.effective_chat.type != "private":
        return
    try:
        n = int(context.args[0]) if context.args else 1
    except (ValueError, IndexError):
        n = 1
    await handle_delete_last(update, context, n)


async def cmd_pending_deletes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from modules.utils import OWNER_CHAT_ID
    from modules.message_manager import get_all_scheduled_deletions
    if update.effective_user.id != OWNER_CHAT_ID or update.effective_chat.type != "private":
        return
    data = get_all_scheduled_deletions()
    if not data:
        await update.message.reply_text("No pending deletions.")
        return
    lines = ["Pending deletions:"]
    for did, entry in sorted(data.items(), key=lambda kv: kv[1]["fire_at"]):
        fire_at = datetime.fromisoformat(entry["fire_at"]).strftime("%d %b %H:%M")
        lines.append(f"• {did}: msg {entry['message_id']} → {fire_at}")
    await update.message.reply_text("\n".join(lines))


async def error_handler(
        update: object,
        context: ContextTypes.DEFAULT_TYPE):
    logger.error(
        f"Update caused error: {context.error}",
        exc_info=context.error,
    )
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Sorry, something went wrong. Please try again."
            )
        except Exception:
            pass


async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    scheduler = AsyncIOScheduler()
    app.bot_data["scheduler"] = scheduler
    restore_schedules(scheduler, app.bot)
    restore_reminders(scheduler, app.bot)
    restore_scheduled_deletions(app, scheduler)
    scheduler.add_job(
        clear_old_published, "cron",
        hour=3, minute=0,
        id="daily_published_cleanup",
        replace_existing=True,
    )
    scheduler.add_job(
        gmail_monitor.check_new_emails,
        "interval",
        minutes=30,
        args=[app.bot],
        id="gmail_monitor",
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc),
    )
    scheduler.start()
    logger.info("⏰ Scheduler started")
    logger.info("📧 Gmail monitor scheduled every 30 minutes")
    logger.info("🗑️ Daily published_articles cleanup scheduled at 03:00")
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("ask",       cmd_ask))
    app.add_handler(CommandHandler("math",      cmd_math))
    app.add_handler(CommandHandler("chinese",   cmd_chinese))
    app.add_handler(CommandHandler("homework",  cmd_homework))
    app.add_handler(CommandHandler("tasks",     cmd_tasks))
    app.add_handler(CommandHandler("schedules", cmd_schedules))
    app.add_handler(CommandHandler("memory",    cmd_memory))
    app.add_handler(CommandHandler("news",      cmd_news))
    app.add_handler(CommandHandler("xfeed",     cmd_xfeed))
    app.add_handler(CommandHandler("report",    cmd_report))
    app.add_handler(CommandHandler("skills",    cmd_skills))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, route_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_message))
    app.add_handler(CommandHandler("clear",      cmd_clear_history))
    app.add_handler(CommandHandler("newsstatus", cmd_newsstatus))
    app.add_handler(CommandHandler("feedhealth", cmd_feedhealth))
    app.add_handler(CommandHandler("memories",       cmd_memories))
    app.add_handler(CommandHandler("forget",         cmd_forget))
    app.add_handler(CommandHandler("reminders",      cmd_reminders))
    app.add_handler(CommandHandler("cancelreminder", cmd_cancel_reminder))
    app.add_handler(CommandHandler("windows",        cmd_windows))
    app.add_handler(CommandHandler("deletelast",     cmd_delete_last))
    app.add_handler(CommandHandler("pendingdeletes", cmd_pending_deletes))
    app.add_error_handler(error_handler)
    await app.bot.set_my_commands([
        BotCommand("start",          "Welcome & help"),
        BotCommand("tasks",          "View pending tasks"),
        BotCommand("schedules",      "View active schedules"),
        BotCommand("memory",         "View bot memory"),
        BotCommand("news",           "Top AI & Tech news"),
        BotCommand("xfeed",          "Fetch latest X / Twitter AI updates"),
        BotCommand("report",         "Daily report now"),
        BotCommand("skills",         "View loaded AI skills"),
        BotCommand("newsstatus",     "News tracking stats"),
        BotCommand("feedhealth",     "Check RSS feed health"),
        BotCommand("memories",       "View all stored memories"),
        BotCommand("forget",         "Delete a memory entry"),
        BotCommand("clear",          "Clear conversation history"),
        BotCommand("reminders",      "View pending reminders"),
        BotCommand("cancelreminder", "Cancel a reminder"),
        BotCommand("windows",        "View time windows"),
        BotCommand("deletelast",     "Delete last N bot messages (owner)"),
        BotCommand("pendingdeletes", "View pending scheduled deletions"),
    ])
    logger.info("🤖 AgentBot is running...")
    await app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
