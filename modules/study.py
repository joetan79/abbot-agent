"""Study handlers for student users."""

from telegram import Update
from telegram.ext import ContextTypes
from .utils import ask_claude, ask_claude_with_search, is_allowed, MODEL_SMART
from .skills_loader import load_skills

# Known family/group members keyed by Telegram username (lowercase).
# Add new members here as they join the group.
FAMILY_MEMBERS = {
    "jtan79": {
        "name": "Joe",
        "role": "dad",
        "is_owner": True,
    },
    "it1019": {
        "name": "Isaac",
        "role": "son",
        "age": 10,
        "level": "primary",
    },
    # Arik's username unknown yet — add when confirmed
}

# Human-readable family context injected into every non-owner system prompt
_FAMILY_CONTEXT = (
    "GROUP CONTEXT: This is a family group chat. Members:\n"
    "- Joe (username: JTan79) — dad, the bot owner\n"
    "- Isaac (username: IT1019) — Joe's 10-year-old son, primary school student\n"
    "- Arik — Joe's 6-year-old son (may join later)\n"
    "- Fiona — Joe's wife\n"
    "Never confuse the person currently messaging you with another family member."
)

USER_PROFILES = {}  # kept for backward-compat with cmd_* handlers


def _get_user_context(username: str) -> str:
    key = (username or "").lower()
    member = FAMILY_MEMBERS.get(key)
    if member:
        name = member["name"]
        role = member.get("role", "member")
        age = member.get("age")
        level = member.get("level", "")
        age_str = f", {age} years old" if age else ""
        level_str = f" ({level} school level)" if level else ""
        return (
            f"IMPORTANT: The person messaging you RIGHT NOW is {name.upper()} "
            f"— Joe's {role}{age_str}{level_str}. "
            f"Address them as {name}, not as Joe or anyone else.\n\n"
            f"{_FAMILY_CONTEXT}\n\n"
            f"Respond in a friendly, age-appropriate way for {name}."
        )
    # Unknown sender — still provide family context so the bot understands the group
    display = username or "someone"
    return (
        f"The person messaging you is @{display} (not yet in the known member list).\n\n"
        f"{_FAMILY_CONTEXT}\n\n"
        "Be friendly and helpful."
    )

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
