"""Study handlers for student users."""

from telegram import Update
from telegram.ext import ContextTypes
from .utils import ask_claude, ask_claude_with_search, is_allowed, MODEL_SMART
from .skills_loader import load_skills

USER_PROFILES = {
    # Add Telegram usernames here
    # Format: "username": {"role": "student",
    #                      "level": "secondary"}
}

def _get_user_context(username: str) -> str:
    profile = USER_PROFILES.get(
        (username or "").lower())
    if profile:
        role = profile.get("role", "user")
        level = profile.get("level", "")
        if role == "student" and level:
            return (
                f"You are helping a {level} "
                "level student. Explain clearly "
                "at appropriate level."
            )
        return f"You are helping a {role}."
    return "You are a professional AI assistant."

async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_chat.id): return
    q = " ".join(context.args)
    if not q:
        await update.message.reply_text("Usage: /ask Why is the sky blue?")
        return
    skills = load_skills(scope="study")
    sys = (
        f"{skills}\n\n"
        f"{_get_user_context(update.effective_user.username)} "
        "Answer clearly with real world examples."
    )
    await update.message.chat.send_action("typing")
    await update.message.reply_text(ask_claude_with_search(sys, q, model=MODEL_SMART))

async def cmd_math(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_chat.id): return
    p = " ".join(context.args)
    if not p:
        await update.message.reply_text("Usage: `/math 2x + 5 = 15`", parse_mode=None)
        return
    skills = load_skills(scope="study")
    sys = (
        f"{skills}\n\n"
        f"{_get_user_context(update.effective_user.username)} "
        "You are a math tutor. "
        "Solve step by step."
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
    skills = load_skills(scope="study")
    sys = (
        f"{skills}\n\n"
        f"{_get_user_context(update.effective_user.username)} "
        "You are a Chinese language tutor."
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
    skills = load_skills(scope="study")
    sys = (
        f"{skills}\n\n"
        f"{_get_user_context(update.effective_user.username)} "
        "You are a homework tutor."
    )
    await update.message.chat.send_action("typing")
    await update.message.reply_text(
        f"📝 *Homework Help*\n\n{ask_claude(sys, q, model=MODEL_SMART)}", parse_mode=None)
