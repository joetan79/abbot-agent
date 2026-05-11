import asyncio
import json
import logging
import random
import sys
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
        "questions": [],
        "current_index": 0,
        "sent_at": None,
        "reminder_job_id": None,
        "last_completed": None,
        "sent_history": []
    },
    "python_quiz": {
        "pending": False,
        "question": "",
        "answer": "",
        "options": {},
        "explanation": "",
        "questions": [],
        "current_index": 0,
        "type": "mcq",
        "sent_at": None,
        "reminder_job_id": None,
        "day_counter": 0,
        "last_completed": None,
        "sent_history": []
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

def generate_ai_quiz(recent_topics=None):
    from modules.utils import ask_claude, MODEL_FAST
    avoid = ("\n\nIMPORTANT: Do NOT repeat or closely reuse any of these recent questions or topics:\n" + "\n".join(recent_topics)) if recent_topics else ""
    prompt = '''Generate a random AI knowledge quiz question. Topics include: AI history, famous models (GPT, BERT, AlphaGo, Stable Diffusion, etc.), AI researchers, AI companies, ML concepts, AI ethics, recent AI breakthroughs, neural network architectures.

Respond ONLY in this exact JSON format with no markdown, no code blocks, no extra text:
{"question": "Question text here?", "options": {"A": "...", "B": "...", "C": "...", "D": "..."}, "answer": "A", "explanation": "Brief explanation why the answer is correct."}

Make it genuinely challenging and educational. Vary the topic each time.''' + avoid
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

def generate_python_mcq(recent_topics=None):
    from modules.utils import ask_claude, MODEL_FAST
    avoid = ("\n\nIMPORTANT: Do NOT repeat or closely reuse any of these recent questions or topics:\n" + "\n".join(recent_topics)) if recent_topics else ""
    prompt = '''Generate a random Python multiple-choice quiz question. Topics: Python syntax, built-in functions, data structures, OOP, decorators, generators, error handling, standard library, Pythonic idioms, list/dict comprehensions, performance tips.

Respond ONLY in this exact JSON format with no markdown, no code blocks, no extra text:
{"question": "Question text here? Include code snippet if relevant using \\n for newlines.", "options": {"A": "...", "B": "...", "C": "...", "D": "..."}, "answer": "B", "explanation": "Brief explanation of the correct answer."}

Make it genuinely challenging. Include short code snippets in the question when relevant.''' + avoid
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

def generate_python_coding(recent_topics=None):
    from modules.utils import ask_claude, MODEL_FAST
    avoid = ("\n\nIMPORTANT: Do NOT repeat or closely reuse any of these recent questions or topics:\n" + "\n".join(recent_topics)) if recent_topics else ""
    prompt = '''Generate a Python coding challenge. It should be solvable in 5-15 lines. Topics: string manipulation, list/dict operations, algorithms, recursion, file handling, decorators, comprehensions, sorting.

Respond ONLY in this exact JSON format with no markdown, no code blocks, no extra text:
{"question": "Clearly describe the coding task. Include input/output examples.", "answer": "# Complete working Python solution\\ndef solution():\\n    pass", "explanation": "Brief explanation of the approach and key concepts used."}''' + avoid
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

def format_mcq_message(quiz_data, quiz_type, index=None, total=None):
    emoji = "🧠" if quiz_type == "ai" else "🐍"
    label = "AI Knowledge Quiz" if quiz_type == "ai" else "Python Quiz"
    opts = quiz_data.get("options", {})
    prefix = f"❓ Question {index}/{total}\n\n" if index is not None and total is not None else ""
    now = datetime.now().strftime('%d %b %Y %H:%M')
    return (
        f"{prefix}"
        f"{emoji} *{label}*\n\n"
        f"{quiz_data['question']}\n\n"
        f"A) {opts.get('A', '')}\n"
        f"B) {opts.get('B', '')}\n"
        f"C) {opts.get('C', '')}\n"
        f"D) {opts.get('D', '')}\n\n"
        f"Reply with A, B, C, or D within 30 minutes!\n"
        f"_Generated: {now}_"
    )

def format_coding_message(quiz_data, index=None, total=None):
    prefix = f"❓ Question {index}/{total}\n\n" if index is not None and total is not None else ""
    now = datetime.now().strftime('%d %b %Y %H:%M')
    return (
        f"{prefix}"
        f"🐍 *Python Coding Challenge*\n\n"
        f"{quiz_data['question']}\n\n"
        f"Write your solution and reply within 30 minutes!\n"
        f"_(Reply 'answer' or 'skip' to see the solution)_\n"
        f"_Generated: {now}_"
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
    from apscheduler.triggers.date import DateTrigger

    state = load_quiz_state()
    quiz_key = "ai_quiz" if quiz_type == "ai" else "python_quiz"
    owner_chat_id = _get_owner_chat_id()

    # If previous quiz still pending, skip — the 30-min timeout job handles it
    if state[quiz_key]["pending"]:
        logger.info(f"Quiz {quiz_type} still pending, skipping scheduled send")
        return

    count = random.randint(3, 5)
    questions = []
    recent_topics = state[quiz_key].get("sent_history", [])[-7:]

    if quiz_type == "ai":
        for _ in range(count):
            quiz_data = generate_ai_quiz(recent_topics=recent_topics)
            if quiz_data:
                quiz_data["type"] = "mcq"
                questions.append(quiz_data)
    else:
        day_counter = state[quiz_key].get("day_counter", 0)
        batch_type = "coding" if day_counter % 3 == 0 else "mcq"
        state[quiz_key]["day_counter"] = day_counter + 1
        for _ in range(count):
            if batch_type == "coding":
                quiz_data = generate_python_coding(recent_topics=recent_topics)
                if quiz_data:
                    quiz_data["type"] = "coding"
                    questions.append(quiz_data)
            else:
                quiz_data = generate_python_mcq(recent_topics=recent_topics)
                if quiz_data:
                    quiz_data["type"] = "mcq"
                    questions.append(quiz_data)

    if not questions:
        try:
            await bot.send_message(chat_id=owner_chat_id, text="⚠️ Failed to generate quiz. Will retry next schedule.")
        except Exception:
            pass
        save_quiz_state(state)
        return

    total = len(questions)
    sent_questions = []

    for i, q in enumerate(questions, 1):
        q_type = q.get("type", "mcq")
        if q_type == "coding":
            msg = format_coding_message(q, index=i, total=total)
        else:
            qt = "ai" if quiz_type == "ai" else "python"
            msg = format_mcq_message(q, qt, index=i, total=total)
        try:
            await bot.send_message(chat_id=owner_chat_id, text=msg, parse_mode="Markdown")
            sent_questions.append(q)
        except Exception as e:
            logger.error(f"Failed to send quiz question {i}: {e}")
        if i < total:
            await asyncio.sleep(2)

    logger.warning(f"Quiz sent: {len(sent_questions)}/{len(questions)} delivered")

    # Schedule 30-min answer job for the entire batch
    fire_time = datetime.now() + timedelta(minutes=30)
    job_id = f"quiz_answer_{quiz_type}_{int(fire_time.timestamp())}"
    try:
        # sys.modules['__main__'] avoids the double-import trap where
        # 'from bot import scheduler' always gets the module-level None
        # instead of the AsyncIOScheduler set inside main().
        _scheduler = sys.modules['__main__'].scheduler
        _scheduler.add_job(
            _run_quiz_answer_sync,
            trigger=DateTrigger(run_date=fire_time),
            args=[quiz_type],
            id=job_id,
            replace_existing=True
        )
    except Exception as e:
        logger.error(f"Failed to schedule quiz answer job: {e}")
        job_id = None

    state[quiz_key]["questions"] = sent_questions
    state[quiz_key]["answer"] = ""
    state[quiz_key]["sent_at"] = datetime.now().isoformat()
    state[quiz_key]["reminder_job_id"] = job_id
    if sent_questions:
        state[quiz_key]["pending"] = True
        state[quiz_key]["current_index"] = 0
    save_quiz_state(state)

async def send_quiz_answer(bot, quiz_type, is_timeout=True):
    state = load_quiz_state()
    quiz_key = "ai_quiz" if quiz_type == "ai" else "python_quiz"
    owner_chat_id = _get_owner_chat_id()

    if not state[quiz_key]["pending"]:
        return

    questions = state[quiz_key].get("questions", [])
    current_index = state[quiz_key].get("current_index", 0)

    if questions and current_index < len(questions):
        header = "⏰ Time's up! Here are the answers:" if is_timeout else "📖 Here are the answers:"
        lines = [header, ""]
        for i, q in enumerate(questions[current_index:], current_index + 1):
            q_type = q.get("type", "mcq")
            if q_type == "coding":
                lines.append(f"Q{i}) Solution:")
                lines.append(f"```python\n{q['answer']}\n```")
                lines.append(f"💡 {q.get('explanation', '')}")
            else:
                answer_key = q.get("answer", "")
                opts = q.get("options", {})
                answer_text = opts.get(answer_key, "")
                lines.append(f"Q{i}) {answer_key}) {answer_text}")
                lines.append(f"💡 {q.get('explanation', '')}")
            lines.append("")
        msg = "\n".join(lines).strip()
    else:
        msg = format_answer_message(state[quiz_key], quiz_type, is_timeout=is_timeout)

    try:
        await bot.send_message(chat_id=owner_chat_id, text=msg, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Failed to send quiz answer: {e}")

    job_id = state[quiz_key].get("reminder_job_id")
    if job_id:
        try:
            _scheduler = sys.modules['__main__'].scheduler
            if _scheduler:
                _scheduler.remove_job(job_id)
        except Exception:
            pass

    completed_questions = state[quiz_key].get("questions", [])
    new_topics = [q.get("question", "")[:100] for q in completed_questions if q.get("question")]
    history = state[quiz_key].get("sent_history", [])
    history.extend(new_topics)
    state[quiz_key]["sent_history"] = history[-7:]
    state[quiz_key]["last_completed"] = {
        "questions": completed_questions,
        "completed_at": datetime.now().isoformat()
    }
    state[quiz_key]["pending"] = False
    state[quiz_key]["reminder_job_id"] = None
    state[quiz_key]["questions"] = []
    state[quiz_key]["current_index"] = 0
    save_quiz_state(state)

async def handle_quiz_response(bot, text, quiz_type):
    state = load_quiz_state()
    quiz_key = "ai_quiz" if quiz_type == "ai" else "python_quiz"
    owner_chat_id = _get_owner_chat_id()
    text_stripped = text.strip()
    text_lower = text_stripped.lower()

    show_keywords = ["answer", "skip", "show answer", "show", "give up"]
    resend_keywords = ["resend", "resend answer", "show answer", "last answer",
                       "previous answer", "what was the answer", "answer again"]

    # Bug 1: check pending first — route show/answer/skip to the active batch, not last_completed
    if state[quiz_key]["pending"]:
        if text_lower in show_keywords:
            await send_quiz_answer(bot, quiz_type, is_timeout=False)
            return

        questions = state[quiz_key].get("questions", [])
        current_index = state[quiz_key].get("current_index", 0)

        # Fallback for old state format without questions list
        if not questions:
            q_type = state[quiz_key].get("type", "mcq")
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
                        job_id = state[quiz_key].get("reminder_job_id")
                        if job_id:
                            try:
                                _scheduler = sys.modules['__main__'].scheduler
                                if _scheduler:
                                    _scheduler.remove_job(job_id)
                            except Exception:
                                pass
                        state[quiz_key]["last_completed"] = {
                            "questions": [],
                            "completed_at": datetime.now().isoformat()
                        }
                        state[quiz_key]["pending"] = False
                        state[quiz_key]["reminder_job_id"] = None
                        save_quiz_state(state)
                    else:
                        try:
                            await bot.send_message(chat_id=owner_chat_id, text="❌ Wrong answer! Try again or wait for the answer in 30 minutes.")
                        except Exception as e:
                            logger.error(f"Failed to send wrong answer response: {e}")
            return

        if current_index >= len(questions):
            return

        current_q = questions[current_index]
        q_type = current_q.get("type", "mcq")
        total = len(questions)

        if q_type == "mcq":
            user_answer = text_stripped.upper()[0] if text_stripped else ""
            correct = current_q.get("answer", "").upper()
            if user_answer in ["A", "B", "C", "D"]:
                if user_answer == correct:
                    explanation = current_q.get("explanation", "")
                    n = current_index + 1
                    reply = f"✅ Q{n} Correct! 💡 {explanation}"
                    try:
                        await bot.send_message(chat_id=owner_chat_id, text=reply)
                    except Exception as e:
                        logger.error(f"Failed to send correct answer response: {e}")
                    current_index += 1
                    state[quiz_key]["current_index"] = current_index
                    if current_index >= total:
                        job_id = state[quiz_key].get("reminder_job_id")
                        if job_id:
                            try:
                                _scheduler = sys.modules['__main__'].scheduler
                                if _scheduler:
                                    _scheduler.remove_job(job_id)
                            except Exception:
                                pass
                        # Bug 3: update sent_history; Bug 2: clear current batch
                        completed_questions = state[quiz_key].get("questions", [])
                        new_topics = [q.get("question", "")[:100] for q in completed_questions if q.get("question")]
                        history = state[quiz_key].get("sent_history", [])
                        history.extend(new_topics)
                        state[quiz_key]["sent_history"] = history[-7:]
                        state[quiz_key]["last_completed"] = {
                            "questions": completed_questions,
                            "completed_at": datetime.now().isoformat()
                        }
                        state[quiz_key]["pending"] = False
                        state[quiz_key]["reminder_job_id"] = None
                        state[quiz_key]["questions"] = []
                        state[quiz_key]["current_index"] = 0
                    save_quiz_state(state)
                else:
                    try:
                        await bot.send_message(chat_id=owner_chat_id, text="❌ Wrong! Try again.")
                    except Exception as e:
                        logger.error(f"Failed to send wrong answer response: {e}")
        return

    # Not pending: handle resend/show-last requests only
    if any(kw in text_lower for kw in resend_keywords):
        last = state[quiz_key].get("last_completed")
        if last and last.get("questions"):
            header = "📖 Last quiz answers:"
            lines = [header, ""]
            for i, q in enumerate(last["questions"], 1):
                q_type = q.get("type", "mcq")
                if q_type == "coding":
                    lines.append(f"Q{i}) Solution:")
                    lines.append(f"```python\n{q['answer']}\n```")
                    lines.append(f"💡 {q.get('explanation', '')}")
                else:
                    answer_key = q.get("answer", "")
                    opts = q.get("options", {})
                    answer_text = opts.get(answer_key, "")
                    lines.append(f"Q{i}) {answer_key}) {answer_text}")
                    lines.append(f"💡 {q.get('explanation', '')}")
                lines.append("")
            msg = "\n".join(lines).strip()
            completed_at = last.get("completed_at", "")
            if completed_at:
                try:
                    dt = datetime.fromisoformat(completed_at)
                    msg += f"\n\n_Completed: {dt.strftime('%d %b %Y %H:%M')}_"
                except Exception:
                    pass
            try:
                await bot.send_message(chat_id=owner_chat_id, text=msg, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Failed to resend quiz answers: {e}")

def _get_owner_chat_id():
    import os
    return int(os.getenv("OWNER_CHAT_ID", "0"))

def _run_quiz_answer_sync(quiz_type):
    """Sync wrapper so APScheduler can fire send_quiz_answer on the running loop."""
    _main = sys.modules.get('__main__')
    bot = getattr(getattr(_main, 'application', None), 'bot', None)
    if not bot:
        logger.error(f"_run_quiz_answer_sync: no bot available for quiz_type={quiz_type}")
        return
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(send_quiz_answer(bot, quiz_type, is_timeout=True))
        else:
            loop.run_until_complete(send_quiz_answer(bot, quiz_type, is_timeout=True))
    except Exception as e:
        logger.error(f"Quiz answer sync wrapper error: {e}")

def restore_quiz_timeouts(scheduler, bot):
    """Re-register 30-min timeout jobs for any quizzes still pending after bot restart."""
    from apscheduler.triggers.date import DateTrigger
    state = load_quiz_state()
    changed = False
    for quiz_type in ["ai", "python"]:
        quiz_key = "ai_quiz" if quiz_type == "ai" else "python_quiz"
        if not state[quiz_key].get("pending"):
            continue
        sent_at_str = state[quiz_key].get("sent_at")
        if not sent_at_str:
            continue
        try:
            sent_at = datetime.fromisoformat(sent_at_str)
            fire_time = sent_at + timedelta(minutes=30)
            now = datetime.now()
            # If already overdue, fire 5 seconds after bot start
            run_at = fire_time if fire_time > now else now + timedelta(seconds=5)
            job_id = f"quiz_answer_{quiz_type}_{int(fire_time.timestamp())}"
            scheduler.add_job(
                _run_quiz_answer_sync,
                trigger=DateTrigger(run_date=run_at),
                args=[quiz_type],
                id=job_id,
                replace_existing=True
            )
            state[quiz_key]["reminder_job_id"] = job_id
            changed = True
            logger.info(f"Restored quiz timeout for {quiz_type} at {run_at}")
        except Exception as e:
            logger.error(f"Failed to restore quiz timeout for {quiz_type}: {e}")
    if changed:
        save_quiz_state(state)
