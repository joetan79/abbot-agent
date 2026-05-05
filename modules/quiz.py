import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

QUIZ_STATE_FILE = "data/quiz_state.json"

DEFAULT_STATE = {
    "ai_quiz": {
        "pending": False,
        "question": "",
        "answer": "",
        "options": {},
        "explanation": "",
        "sent_at": None,
        "reminder_job_id": None
    },
    "python_quiz": {
        "pending": False,
        "question": "",
        "answer": "",
        "options": {},
        "explanation": "",
        "type": "mcq",
        "sent_at": None,
        "reminder_job_id": None,
        "day_counter": 0
    }
}

def load_quiz_state():
    try:
        with open(QUIZ_STATE_FILE, "r") as f:
            data = json.load(f)
            # Ensure all keys exist (merge with defaults)
            for quiz_key in DEFAULT_STATE:
                if quiz_key not in data:
                    data[quiz_key] = DEFAULT_STATE[quiz_key].copy()
                for field in DEFAULT_STATE[quiz_key]:
                    if field not in data[quiz_key]:
                        data[quiz_key][field] = DEFAULT_STATE[quiz_key][field]
            return data
    except Exception:
        return json.loads(json.dumps(DEFAULT_STATE))

def save_quiz_state(state):
    try:
        with open(QUIZ_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save quiz state: {e}")

def generate_ai_quiz():
    from modules.utils import ask_claude, MODEL_FAST
    prompt = '''Generate a random AI knowledge quiz question. Topics include: AI history, famous models (GPT, BERT, AlphaGo, Stable Diffusion, etc.), AI researchers, AI companies, ML concepts, AI ethics, recent AI breakthroughs, neural network architectures.

Respond ONLY in this exact JSON format with no markdown, no code blocks, no extra text:
{"question": "Question text here?", "options": {"A": "...", "B": "...", "C": "...", "D": "..."}, "answer": "A", "explanation": "Brief explanation why the answer is correct."}

Make it genuinely challenging and educational. Vary the topic each time.'''
    try:
        response = ask_claude("You are a quiz generator. Output only valid JSON.", prompt, model=MODEL_FAST)
        clean = response.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(clean)
    except Exception as e:
        logger.error(f"AI quiz generation failed: {e}")
        try:
            response = ask_claude("You are a quiz generator. Output only valid JSON.", prompt, model=MODEL_FAST)
            clean = response.strip().replace("```json", "").replace("```", "").strip()
            return json.loads(clean)
        except Exception as e2:
            logger.error(f"AI quiz retry failed: {e2}")
            return None

def generate_python_mcq():
    from modules.utils import ask_claude, MODEL_FAST
    prompt = '''Generate a random Python multiple-choice quiz question. Topics: Python syntax, built-in functions, data structures, OOP, decorators, generators, error handling, standard library, Pythonic idioms, list/dict comprehensions, performance tips.

Respond ONLY in this exact JSON format with no markdown, no code blocks, no extra text:
{"question": "Question text here? Include code snippet if relevant using \\n for newlines.", "options": {"A": "...", "B": "...", "C": "...", "D": "..."}, "answer": "B", "explanation": "Brief explanation of the correct answer."}

Make it genuinely challenging. Include short code snippets in the question when relevant.'''
    try:
        response = ask_claude("You are a Python quiz generator. Output only valid JSON.", prompt, model=MODEL_FAST)
        clean = response.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(clean)
    except Exception as e:
        logger.error(f"Python MCQ generation failed: {e}")
        try:
            response = ask_claude("You are a Python quiz generator. Output only valid JSON.", prompt, model=MODEL_FAST)
            clean = response.strip().replace("```json", "").replace("```", "").strip()
            return json.loads(clean)
        except Exception as e2:
            logger.error(f"Python MCQ retry failed: {e2}")
            return None

def generate_python_coding():
    from modules.utils import ask_claude, MODEL_FAST
    prompt = '''Generate a Python coding challenge. It should be solvable in 5-15 lines. Topics: string manipulation, list/dict operations, algorithms, recursion, file handling, decorators, comprehensions, sorting.

Respond ONLY in this exact JSON format with no markdown, no code blocks, no extra text:
{"question": "Clearly describe the coding task. Include input/output examples.", "answer": "# Complete working Python solution\\ndef solution():\\n    pass", "explanation": "Brief explanation of the approach and key concepts used."}'''
    try:
        response = ask_claude("You are a Python coding challenge generator. Output only valid JSON.", prompt, model=MODEL_FAST)
        clean = response.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(clean)
    except Exception as e:
        logger.error(f"Python coding generation failed: {e}")
        try:
            response = ask_claude("You are a Python coding challenge generator. Output only valid JSON.", prompt, model=MODEL_FAST)
            clean = response.strip().replace("```json", "").replace("```", "").strip()
            return json.loads(clean)
        except Exception as e2:
            logger.error(f"Python coding retry failed: {e2}")
            return None

def format_mcq_message(quiz_data, quiz_type):
    emoji = "🧠" if quiz_type == "ai" else "🐍"
    label = "AI Knowledge Quiz" if quiz_type == "ai" else "Python Quiz"
    opts = quiz_data.get("options", {})
    return (
        f"{emoji} *{label}*\n\n"
        f"{quiz_data['question']}\n\n"
        f"A) {opts.get('A', '')}\n"
        f"B) {opts.get('B', '')}\n"
        f"C) {opts.get('C', '')}\n"
        f"D) {opts.get('D', '')}\n\n"
        f"Reply with A, B, C, or D within 30 minutes!"
    )

def format_coding_message(quiz_data):
    return (
        f"🐍 *Python Coding Challenge*\n\n"
        f"{quiz_data['question']}\n\n"
        f"Write your solution and reply within 30 minutes!\n"
        f"_(Reply 'answer' or 'skip' to see the solution)_"
    )

def format_answer_message(quiz_data, quiz_type, is_timeout=True):
    header = "⏰ Time's up!" if is_timeout else "📖 Here's the answer:"
    q_type = quiz_data.get("type", "mcq")
    if q_type == "coding":
        return (
            f"{header}\n\n"
            f"✅ *Solution:*\n"
            f"```python\n{quiz_data['answer']}\n```\n\n"
            f"💡 {quiz_data.get('explanation', '')}"
        )
    else:
        answer_key = quiz_data.get("answer", "")
        opts = quiz_data.get("options", {})
        answer_text = opts.get(answer_key, "")
        return (
            f"{header}\n\n"
            f"✅ *Correct answer: {answer_key}) {answer_text}*\n\n"
            f"💡 {quiz_data.get('explanation', '')}"
        )

async def send_quiz(bot, quiz_type):
    from bot import scheduler
    from apscheduler.triggers.date import DateTrigger

    state = load_quiz_state()
    quiz_key = "ai_quiz" if quiz_type == "ai" else "python_quiz"
    owner_chat_id = _get_owner_chat_id()

    # If previous quiz still pending, send its answer first
    if state[quiz_key]["pending"]:
        try:
            await send_quiz_answer(bot, quiz_type, is_timeout=True)
        except Exception as e:
            logger.error(f"Failed to send overdue quiz answer: {e}")
        state = load_quiz_state()

    # Generate quiz
    quiz_data = None
    if quiz_type == "ai":
        quiz_data = generate_ai_quiz()
        if quiz_data:
            quiz_data["type"] = "mcq"
            msg = format_mcq_message(quiz_data, "ai")
    else:
        day_counter = state[quiz_key].get("day_counter", 0)
        if day_counter % 3 == 0:
            quiz_data = generate_python_coding()
            if quiz_data:
                quiz_data["type"] = "coding"
                msg = format_coding_message(quiz_data)
        else:
            quiz_data = generate_python_mcq()
            if quiz_data:
                quiz_data["type"] = "mcq"
                msg = format_mcq_message(quiz_data, "python")
        state[quiz_key]["day_counter"] = day_counter + 1

    if not quiz_data:
        try:
            await bot.send_message(chat_id=owner_chat_id, text="⚠️ Failed to generate quiz. Will retry next schedule.")
        except Exception:
            pass
        save_quiz_state(state)
        return

    # Send to Telegram
    try:
        await bot.send_message(chat_id=owner_chat_id, text=msg, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Failed to send quiz message: {e}")
        save_quiz_state(state)
        return

    # Schedule 30-min answer job
    fire_time = datetime.now() + timedelta(minutes=30)
    job_id = f"quiz_answer_{quiz_type}_{int(fire_time.timestamp())}"
    try:
        scheduler.add_job(
            send_quiz_answer,
            trigger=DateTrigger(run_date=fire_time),
            args=[bot, quiz_type, True],
            id=job_id,
            replace_existing=True
        )
    except Exception as e:
        logger.error(f"Failed to schedule quiz answer job: {e}")
        job_id = None

    # Update state
    state[quiz_key]["pending"] = True
    state[quiz_key]["question"] = quiz_data.get("question", "")
    state[quiz_key]["answer"] = quiz_data.get("answer", "")
    state[quiz_key]["options"] = quiz_data.get("options", {})
    state[quiz_key]["explanation"] = quiz_data.get("explanation", "")
    state[quiz_key]["type"] = quiz_data.get("type", "mcq")
    state[quiz_key]["sent_at"] = datetime.now().isoformat()
    state[quiz_key]["reminder_job_id"] = job_id
    save_quiz_state(state)

async def send_quiz_answer(bot, quiz_type, is_timeout=True):
    state = load_quiz_state()
    quiz_key = "ai_quiz" if quiz_type == "ai" else "python_quiz"
    owner_chat_id = _get_owner_chat_id()

    if not state[quiz_key]["pending"]:
        return

    msg = format_answer_message(state[quiz_key], quiz_type, is_timeout=is_timeout)
    try:
        await bot.send_message(chat_id=owner_chat_id, text=msg, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Failed to send quiz answer: {e}")

    # Cancel scheduler job if still pending
    job_id = state[quiz_key].get("reminder_job_id")
    if job_id:
        try:
            from bot import scheduler
            scheduler.remove_job(job_id)
        except Exception:
            pass

    state[quiz_key]["pending"] = False
    state[quiz_key]["reminder_job_id"] = None
    save_quiz_state(state)

async def handle_quiz_response(bot, text, quiz_type):
    state = load_quiz_state()
    quiz_key = "ai_quiz" if quiz_type == "ai" else "python_quiz"

    if not state[quiz_key]["pending"]:
        return

    owner_chat_id = _get_owner_chat_id()
    q_type = state[quiz_key].get("type", "mcq")
    text_stripped = text.strip()

    # Show answer keywords
    show_keywords = ["answer", "skip", "show answer", "show", "give up"]
    if text_stripped.lower() in show_keywords:
        await send_quiz_answer(bot, quiz_type, is_timeout=False)
        return

    if q_type == "mcq":
        user_answer = text_stripped.upper()[0] if text_stripped else ""
        correct = state[quiz_key].get("answer", "").upper()
        if user_answer in ["A", "B", "C", "D"]:
            if user_answer == correct:
                explanation = state[quiz_key].get("explanation", "")
                reply = f"✅ Correct! 🎉\n\n💡 {explanation}"
                try:
                    await bot.send_message(chat_id=owner_chat_id, text=reply)
                except Exception as e:
                    logger.error(f"Failed to send correct answer response: {e}")
                # Cancel job
                job_id = state[quiz_key].get("reminder_job_id")
                if job_id:
                    try:
                        from bot import scheduler
                        scheduler.remove_job(job_id)
                    except Exception:
                        pass
                state[quiz_key]["pending"] = False
                state[quiz_key]["reminder_job_id"] = None
                save_quiz_state(state)
            else:
                try:
                    await bot.send_message(chat_id=owner_chat_id, text="❌ Wrong answer! Try again or wait for the answer in 30 minutes.")
                except Exception as e:
                    logger.error(f"Failed to send wrong answer response: {e}")

def _get_owner_chat_id():
    import os
    return int(os.getenv("OWNER_CHAT_ID", "0"))
