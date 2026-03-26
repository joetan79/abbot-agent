"""Study handlers for Isaac (Year 10) and Arik (Year 6)."""

from telegram import Update
from telegram.ext import ContextTypes
from .utils import ask_claude, ask_claude_with_search, is_allowed, MODEL_SMART, get_preferences_prompt

USER_PROFILES = {
    "IT1019":  {"year": 10, "name": "Isaac"},
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
        await update.message.reply_text("Usage: /ask Why is the sky blue?")
        return
    prefs = get_preferences_prompt()
    sys = (
        f"{_year_ctx(update.effective_user.username)} "
        f"{prefs}\n\n"
        "You are a helpful study assistant. Search the web if needed "
        "for accurate, current information to answer the question clearly."
    )
    await update.message.chat.send_action("typing")
    await update.message.reply_text(ask_claude_with_search(sys, q, model=MODEL_SMART))

async def cmd_math(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_chat.id): return
    p = " ".join(context.args)
    if not p:
        await update.message.reply_text("Usage: `/math 2x + 5 = 15`", parse_mode=None)
        return
    prefs = get_preferences_prompt()
    sys = (
        f"{_year_ctx(update.effective_user.username)} "
        f"{prefs}\n\n"
        "You are a math tutor. "
        "Solve step by step with clear explanation. End with the final answer."
    )
    await update.message.chat.send_action("typing")
    await update.message.reply_text(
        f"➕ *Math Solution*\n\n{ask_claude(sys, f'Solve: {p}', model=MODEL_SMART)}", parse_mode=None)

async def cmd_chinese(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_chat.id): return
    t = " ".join(context.args)
    if not t:
        await update.message.reply_text("Usage: `/chinese 你好` or `/chinese hello`", parse_mode=None)
        return
    prefs = get_preferences_prompt()
    sys = (
        f"{_year_ctx(update.effective_user.username)} "
        f"{prefs}\n\n"
        "You are a Chinese language tutor. "
        "CRITICAL: If user preference says Traditional Chinese, "
        "ALWAYS use Traditional Chinese characters, NEVER Simplified. "
        "For Chinese input: give English translation, Traditional Chinese, Pinyin, grammar note. "
        "For English input: give Traditional Chinese, Pinyin, pronunciation tips."
    )
    await update.message.chat.send_action("typing")
    await update.message.reply_text(
        f"🀄 *Chinese Helper*\n\n{ask_claude(sys, t, model=MODEL_SMART)}", parse_mode=None)

async def cmd_homework(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_chat.id): return
    q = " ".join(context.args)
    if not q:
        await update.message.reply_text("Usage: `/homework What caused World War 1?`", parse_mode=None)
        return
    prefs = get_preferences_prompt()
    sys = (
        f"{_year_ctx(update.effective_user.username)} "
        f"{prefs}\n\n"
        "Homework tutor. "
        "Guide understanding, don't just give answers. End with a short summary they can use."
    )
    await update.message.chat.send_action("typing")
    await update.message.reply_text(
        f"📝 *Homework Help*\n\n{ask_claude(sys, q, model=MODEL_SMART)}", parse_mode=None)
