import asyncio
import fcntl
import json
import logging
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

QUIZ_STATE_FILE = "data/quiz_state.json"

bot_instance = None
_loop = None

DEFAULT_STATE = {
    "ai_quiz": {
        "pending": False,
        "questions": [],
        "current_index": 0,
        "sent_at": None,
        "reminder_job_id": None,
        "last_completed": None,
        "sent_history": []
    },
    "python_quiz": {
        "pending": False,
        "questions": [],
        "current_index": 0,
        "sent_at": None,
        "reminder_job_id": None,
        "day_counter": 0,
        "last_completed": None,
        "sent_history": []
    }
}


def _load_raw():
    try:
        with open(QUIZ_STATE_FILE, "r") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            data = json.load(f)
            fcntl.flock(f, fcntl.LOCK_UN)
            return data
    except Exception:
        return json.loads(json.dumps(DEFAULT_STATE))


def load_quiz_state():
    try:
        data = _load_raw()
        for quiz_key in DEFAULT_STATE:
            if quiz_key not in data:
                data[quiz_key] = DEFAULT_STATE[quiz_key].copy()
            for field in DEFAULT_STATE[quiz_key]:
                if field not in data[quiz_key]:
                    data[quiz_key][field] = DEFAULT_STATE[quiz_key][field]
        return data
    except Exception:
        return json.loads(json.dumps(DEFAULT_STATE))


def save_quiz_state(state, quiz_type):
    path = QUIZ_STATE_FILE
    full = _load_raw()
    full[quiz_type] = state
    tmp = path + ".tmp"
    try:
        with open(tmp, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            json.dump(full, f, indent=2)
            fcntl.flock(f, fcntl.LOCK_UN)
        os.replace(tmp, path)
    except Exception as e:
        logger.error(f"Failed to save quiz state: {e}")


def generate_ai_quiz(recent_topics=None):
    from modules.utils import ask_claude, MODEL_FAST
    avoid = ""
    if recent_topics:
        avoid = (
            "\n\nSTRICT RULE: You must NOT repeat or closely paraphrase any question from this list:\n"
            + "\n".join(recent_topics)
            + "\nGenerate a completely different topic."
        )
    prompt = (
        "Generate a random AI knowledge quiz question. Topics include: AI history, famous models "
        "(GPT, BERT, AlphaGo, Stable Diffusion, etc.), AI researchers, AI companies, ML concepts, "
        "AI ethics, recent AI breakthroughs, neural network architectures.\n\n"
        "Respond ONLY in this exact JSON format with no markdown, no code blocks, no extra text:\n"
        '{"question": "Question text here?", "options": {"A": "...", "B": "...", "C": "...", "D": "..."}, '
        '"answer": "A", "explanation": "Brief explanation why the answer is correct."}\n\n'
        "Make it genuinely challenging and educational. Vary the topic each time."
        + avoid
    )
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
    avoid = ""
    if recent_topics:
        avoid = (
            "\n\nSTRICT RULE: You must NOT repeat or closely paraphrase any question from this list:\n"
            + "\n".join(recent_topics)
            + "\nGenerate a completely different topic."
        )
    prompt = (
        "Generate a random Python multiple-choice quiz question. Topics: Python syntax, built-in functions, "
        "data structures, OOP, decorators, generators, error handling, standard library, Pythonic idioms, "
        "list/dict comprehensions, performance tips.\n\n"
        "Respond ONLY in this exact JSON format with no markdown, no code blocks, no extra text:\n"
        '{"question": "Question text here? Include code snippet if relevant using \\n for newlines.", '
        '"options": {"A": "...", "B": "...", "C": "...", "D": "..."}, "answer": "B", '
        '"explanation": "Brief explanation of the correct answer."}\n\n'
        "Make it genuinely challenging. Include short code snippets in the question when relevant."
        + avoid
    )
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
    avoid = ""
    if recent_topics:
        avoid = (
            "\n\nSTRICT RULE: You must NOT repeat or closely paraphrase any question from this list:\n"
            + "\n".join(recent_topics)
            + "\nGenerate a completely different topic."
        )
    prompt = (
        "Generate a Python coding challenge. It should be solvable in 5-15 lines. Topics: string manipulation, "
        "list/dict operations, algorithms, recursion, file handling, decorators, comprehensions, sorting.\n\n"
        "Respond ONLY in this exact JSON format with no markdown, no code blocks, no extra text:\n"
        '{"question": "Clearly describe the coding task. Include input/output examples.", '
        '"answer": "# Complete working Python solution\\ndef solution():\\n    pass", '
        '"explanation": "Brief explanation of the approach and key concepts used."}'
        + avoid
    )
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


def _parse_multi_answers(text):
    """Parse multi-question answers like '2 C; 3 C' or 'Q2: C, Q3: C'.
    Returns {sent_index: answer_letter} dict, or empty dict if no matches."""
    matches = re.findall(r'[Qq]?(\d+)\s*[:.)\s]\s*([ABCDabcd])', text)
    return {int(n): l.upper() for n, l in matches} if matches else {}


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
        save_quiz_state(state[quiz_key], quiz_key)
        return

    total = len(questions)
    sent_questions = []
    for i, q in enumerate(questions):
        q_type = q.get("type", "mcq")
        if q_type == "coding":
            msg = format_coding_message(q, index=i + 1, total=total)
        else:
            qt = "ai" if quiz_type == "ai" else "python"
            msg = format_mcq_message(q, qt, index=i + 1, total=total)
        try:
            await bot.send_message(chat_id=owner_chat_id, text=msg, parse_mode="Markdown")
            q["sent_index"] = i + 1
            sent_questions.append(q)
            logger.info(f"[Quiz] Sent Q{i+1}/{total} for {quiz_type}")
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"[Quiz] Failed to send Q{i+1}/{total}: {e}")
            logger.error(f"[Quiz] Q{i+1} text was: {q.get('question', '')[:100]}")
            try:
                await bot.send_message(chat_id=owner_chat_id, text=msg)
                q["sent_index"] = i + 1
                sent_questions.append(q)
                logger.warning(f"[Quiz] Q{i+1} sent without Markdown after initial failure: {e}")
            except Exception as e2:
                logger.error(f"[Quiz] Q{i+1} completely failed: {e2}")

    if sent_questions:
        state[quiz_key]["questions"] = sent_questions
        state[quiz_key]["pending"] = True
        state[quiz_key]["sent_at"] = datetime.utcnow().isoformat()
        state[quiz_key]["current_index"] = 0
        save_quiz_state(state[quiz_key], quiz_key)
        logger.info(f"[Quiz] State saved: {len(sent_questions)}/{len(questions)} questions delivered")
    else:
        logger.error(f"[Quiz] No questions delivered for {quiz_type} — state not updated")
        return

    # Register 30-min answer timeout using local time to match the scheduler timezone
    fire_at = datetime.now() + timedelta(minutes=30)
    job_id = f"{quiz_type}_timeout_{int(time.time())}"
    try:
        _scheduler = sys.modules['__main__'].scheduler
        _scheduler.add_job(
            _run_quiz_answer_sync,
            trigger=DateTrigger(run_date=fire_at),
            args=[quiz_type],
            id=job_id,
            replace_existing=True
        )
        # Save job_id to state immediately after registration
        state[quiz_key]["reminder_job_id"] = job_id
        state[quiz_key]["sent_at"] = datetime.now().isoformat()
        save_quiz_state(state[quiz_key], quiz_key)
        # Verify the job actually landed in the scheduler
        registered_ids = [j.id for j in _scheduler.get_jobs()]
        if job_id not in registered_ids:
            logger.error(f"[Quiz] CRITICAL: timeout job {job_id} failed to register!")
        else:
            logger.info(f"[Quiz] Timeout job registered: {job_id}, fires at {fire_at}")
    except Exception as e:
        logger.error(f"[Quiz] Failed to schedule quiz answer job: {e}")
        state[quiz_key]["reminder_job_id"] = None
        save_quiz_state(state[quiz_key], quiz_key)


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
        for pos, q in enumerate(questions[current_index:], current_index):
            q_num = q.get("sent_index", pos + 1)
            q_type = q.get("type", "mcq")
            if q_type == "coding":
                lines.append(f"Q{q_num}) Solution:")
                lines.append(f"```python\n{q['answer']}\n```")
                lines.append(f"💡 {q.get('explanation', '')}")
            else:
                answer_key = q.get("answer", "")
                opts = q.get("options", {})
                answer_text = opts.get(answer_key, "")
                lines.append(f"Q{q_num}) {answer_key}) {answer_text}")
                lines.append(f"💡 {q.get('explanation', '')}")
            lines.append("")
        msg = "\n".join(lines).strip()
    else:
        header = "⏰ Time's up!" if is_timeout else "📖 Here's the answer:"
        msg = header

    try:
        await bot.send_message(chat_id=owner_chat_id, text=msg, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Failed to send quiz answer with Markdown: {e}")
        try:
            await bot.send_message(chat_id=owner_chat_id, text=msg)
            logger.warning("Quiz answer sent without Markdown after initial failure")
        except Exception as e2:
            logger.error(f"Failed to send quiz answer without Markdown: {e2}")
            return  # Don't mark complete — keep pending so user can retry

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
    save_quiz_state(state[quiz_key], quiz_key)


async def handle_quiz_response(bot, text, quiz_type):
    state = load_quiz_state()
    quiz_key = "ai_quiz" if quiz_type == "ai" else "python_quiz"
    owner_chat_id = _get_owner_chat_id()
    text_stripped = text.strip()
    text_lower = text_stripped.lower()

    show_keywords = ["answer", "skip", "show answer", "show", "give up"]
    resend_keywords = ["resend", "resend answer", "show answer", "last answer",
                       "previous answer", "what was the answer", "answer again"]

    if state[quiz_key]["pending"]:
        # Watchdog: verify timeout job still exists; re-register or fire answer if lost
        _reminder_job_id = state[quiz_key].get("reminder_job_id")
        if _reminder_job_id:
            try:
                from apscheduler.triggers.date import DateTrigger as _DT
                _sch = sys.modules['__main__'].scheduler
                _job_ids = [j.id for j in _sch.get_jobs()]
                if _reminder_job_id not in _job_ids:
                    _sent_at_str = state[quiz_key].get("sent_at", "")
                    try:
                        _elapsed = (datetime.now() - datetime.fromisoformat(_sent_at_str)).total_seconds()
                    except Exception:
                        _elapsed = 9999
                    if _elapsed >= 1800:
                        logger.warning(
                            f"[Quiz] Watchdog: {quiz_type} timeout job lost, overdue by "
                            f"{_elapsed - 1800:.0f}s — sending answers now"
                        )
                        await send_quiz_answer(bot, quiz_type, is_timeout=True)
                        return
                    else:
                        _remaining = 1800 - _elapsed
                        _fire_at = datetime.now() + timedelta(seconds=_remaining)
                        _sch.add_job(
                            _run_quiz_answer_sync,
                            trigger=_DT(run_date=_fire_at),
                            args=[quiz_type],
                            id=_reminder_job_id,
                            replace_existing=True
                        )
                        logger.warning(
                            f"[Quiz] Watchdog: re-registered lost timeout job "
                            f"{_reminder_job_id}, fires in {_remaining:.0f}s"
                        )
            except Exception as _we:
                logger.error(f"[Quiz] Watchdog error for {quiz_type}: {_we}")

        if text_lower in show_keywords:
            await send_quiz_answer(bot, quiz_type, is_timeout=False)
            return

        questions = state[quiz_key].get("questions", [])
        current_index = state[quiz_key].get("current_index", 0)

        if not questions or current_index >= len(questions):
            return

        current_q = questions[current_index]
        q_type = current_q.get("type", "mcq")
        total = len(questions)

        if q_type == "mcq":
            # Try multi-answer first: "2 C; 3 C" or "Q2: C, Q3: C"
            multi = _parse_multi_answers(text_stripped)
            if multi:
                feedback_lines = []
                max_answered_idx = current_index - 1
                for q_idx, q in enumerate(questions):
                    sidx = q.get("sent_index", q_idx + 1)
                    if sidx not in multi:
                        continue
                    user_ans = multi[sidx]
                    correct_ans = q.get("answer", "").upper()
                    opts = q.get("options", {})
                    if user_ans == correct_ans:
                        feedback_lines.append(f"✅ Q{sidx} Correct! 💡 {q.get('explanation', '')}")
                    else:
                        correct_text = opts.get(correct_ans, "")
                        feedback_lines.append(f"❌ Q{sidx} Wrong! Correct: {correct_ans}) {correct_text}")
                    max_answered_idx = max(max_answered_idx, q_idx)
                if feedback_lines:
                    try:
                        await bot.send_message(chat_id=owner_chat_id, text="\n\n".join(feedback_lines))
                    except Exception as e:
                        logger.error(f"Failed to send multi-answer feedback: {e}")
                    new_index = max_answered_idx + 1
                    state[quiz_key]["current_index"] = new_index
                    if new_index >= total:
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
                    save_quiz_state(state[quiz_key], quiz_key)
                    return True

            # Single-answer fallback: just a letter like "C"
            user_answer = text_stripped.upper()[0] if text_stripped else ""
            correct = current_q.get("answer", "").upper()
            q_num = current_q.get("sent_index", current_index + 1)
            if user_answer in ["A", "B", "C", "D"]:
                if user_answer == correct:
                    explanation = current_q.get("explanation", "")
                    reply = f"✅ Q{q_num} Correct! 💡 {explanation}"
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
                    save_quiz_state(state[quiz_key], quiz_key)
                else:
                    try:
                        await bot.send_message(chat_id=owner_chat_id, text="❌ Wrong! Try again.")
                    except Exception as e:
                        logger.error(f"Failed to send wrong answer response: {e}")
                return True
        return False

    if any(kw in text_lower for kw in resend_keywords):
        last = state[quiz_key].get("last_completed")
        if last and last.get("questions"):
            header = "📖 Last quiz answers:"
            lines = [header, ""]
            for i, q in enumerate(last["questions"], 1):
                q_num = q.get("sent_index", i)
                q_type = q.get("type", "mcq")
                if q_type == "coding":
                    lines.append(f"Q{q_num}) Solution:")
                    lines.append(f"```python\n{q['answer']}\n```")
                    lines.append(f"💡 {q.get('explanation', '')}")
                else:
                    answer_key = q.get("answer", "")
                    opts = q.get("options", {})
                    answer_text = opts.get(answer_key, "")
                    lines.append(f"Q{q_num}) {answer_key}) {answer_text}")
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
                return True
            except Exception as e:
                logger.error(f"Failed to resend quiz answers: {e}")
    return False


def _get_owner_chat_id():
    return int(os.getenv("OWNER_CHAT_ID", "0"))


def _run_quiz_answer_sync(quiz_type):
    """Sync wrapper so APScheduler can fire send_quiz_answer on the running loop."""
    _main = sys.modules.get('__main__')
    bot = getattr(getattr(_main, 'application', None), 'bot', None)
    if not bot:
        logger.error(f"_run_quiz_answer_sync: no bot available for quiz_type={quiz_type}")
        return
    if _loop and _loop.is_running():
        asyncio.run_coroutine_threadsafe(send_quiz_answer(bot, quiz_type, is_timeout=True), _loop)
    else:
        asyncio.ensure_future(send_quiz_answer(bot, quiz_type, is_timeout=True))


def _run_ai_quiz_sync():
    """Sync wrapper so APScheduler can fire send_quiz for the AI quiz."""
    logger.info(f"[QUIZ] _run_ai_quiz_sync called at {datetime.utcnow().isoformat()}")
    if bot_instance is None:
        logger.error("[QUIZ] bot_instance is None! Cannot send quiz.")
        return
    if _loop and _loop.is_running():
        asyncio.run_coroutine_threadsafe(send_quiz(bot_instance, "ai"), _loop)
    else:
        asyncio.ensure_future(send_quiz(bot_instance, "ai"))


def _run_python_quiz_sync():
    """Sync wrapper so APScheduler can fire send_quiz for the Python quiz."""
    logger.info(f"[QUIZ] _run_python_quiz_sync called at {datetime.utcnow().isoformat()}")
    if bot_instance is None:
        logger.error("[QUIZ] bot_instance is None! Cannot send quiz.")
        return
    if _loop and _loop.is_running():
        asyncio.run_coroutine_threadsafe(send_quiz(bot_instance, "python"), _loop)
    else:
        asyncio.ensure_future(send_quiz(bot_instance, "python"))


def get_quiz_status_report():
    """Return a factual status string — reads directly from disk and scheduler."""
    state = load_quiz_state()
    _main = sys.modules.get('__main__')
    _scheduler = getattr(_main, 'scheduler', None)
    scheduler_job_ids = {j.id for j in _scheduler.get_jobs()} if _scheduler else set()
    now = datetime.now()
    lines = ["Quiz Status\n"]
    for quiz_key, label in [("ai_quiz", "AI Quiz"), ("python_quiz", "Python Quiz")]:
        s = state[quiz_key]
        pending = s.get("pending", False)
        sent_at_str = s.get("sent_at")
        questions = s.get("questions", [])
        current_index = s.get("current_index", 0)
        job_id = s.get("reminder_job_id")
        lines.append(f"{label}:")
        lines.append(f"  pending: {pending}")
        if sent_at_str:
            try:
                sent_at = datetime.fromisoformat(sent_at_str)
                elapsed = (now - sent_at).total_seconds()
                if elapsed < 60:
                    age = f"{elapsed:.0f}s ago"
                elif elapsed < 3600:
                    age = f"{elapsed / 60:.0f}m ago"
                elif elapsed < 86400:
                    age = f"{elapsed / 3600:.1f}h ago"
                else:
                    age = f"{elapsed / 86400:.1f}d ago"
                lines.append(f"  sent_at: {sent_at_str[:19]} ({age})")
            except Exception:
                lines.append(f"  sent_at: {sent_at_str} (unparseable)")
        else:
            lines.append(f"  sent_at: None")
        lines.append(f"  questions: {len(questions)} total, answering #{current_index + 1}")
        if job_id:
            if job_id in scheduler_job_ids:
                try:
                    job = next(j for j in _scheduler.get_jobs() if j.id == job_id)
                    fires = job.next_run_time.strftime("%H:%M:%S") if job.next_run_time else "?"
                    lines.append(f"  timeout job: {job_id}\n    ✅ in scheduler, fires at {fires}")
                except Exception:
                    lines.append(f"  timeout job: {job_id} ✅ in scheduler")
            else:
                lines.append(f"  timeout job: {job_id}\n    ❌ NOT in scheduler!")
        else:
            lines.append(f"  timeout job: None")
        lines.append("")
    return "\n".join(lines).strip()


def restore_quiz_timeouts(scheduler, bot):
    """Re-register 30-min timeout jobs for any quizzes still pending after bot restart."""
    global bot_instance, _loop
    bot_instance = bot
    _loop = asyncio.get_event_loop()
    logger.info(f"[QUIZ] _bot_instance set: {bot}")

    logger.info("[Quiz] restore_quiz_timeouts() called")
    from apscheduler.triggers.date import DateTrigger
    state = load_quiz_state()

    for quiz_type in ["ai", "python"]:
        quiz_key = "ai_quiz" if quiz_type == "ai" else "python_quiz"
        s = state[quiz_key]
        logger.info(
            f"[Quiz] {quiz_key}: pending={s.get('pending')}, sent_at={s.get('sent_at')}, "
            f"job_id={s.get('reminder_job_id')}, questions={len(s.get('questions', []))}"
        )
        if not s.get("pending"):
            continue

        sent_at_str = s.get("sent_at")
        if not sent_at_str:
            logger.warning(f"[Quiz] {quiz_key}: pending=True but sent_at missing — forcing pending=False")
            state[quiz_key]["pending"] = False
            save_quiz_state(state[quiz_key], quiz_key)
            continue

        try:
            sent_at = datetime.fromisoformat(sent_at_str)
        except Exception:
            logger.warning(f"[Quiz] {quiz_key}: sent_at unparseable ({sent_at_str!r}) — forcing pending=False")
            state[quiz_key]["pending"] = False
            save_quiz_state(state[quiz_key], quiz_key)
            continue

        try:
            fire_time = sent_at + timedelta(minutes=30)
            now = datetime.now()
            run_at = fire_time if fire_time > now else now + timedelta(seconds=5)
            job_id = f"{quiz_type}_timeout_{int(time.time())}"
            scheduler.add_job(
                _run_quiz_answer_sync,
                trigger=DateTrigger(run_date=run_at),
                args=[quiz_type],
                id=job_id,
                replace_existing=True
            )
            state[quiz_key]["reminder_job_id"] = job_id
            save_quiz_state(state[quiz_key], quiz_key)
            logger.info(f"[Quiz] Restored timeout for {quiz_type} at {run_at}")
        except Exception as e:
            logger.error(f"[Quiz] Failed to restore timeout for {quiz_type}: {e}")

    ai_s = state.get("ai_quiz", {})
    py_s = state.get("python_quiz", {})
    logger.info(
        f"[Quiz] Restored: ai_quiz pending={ai_s.get('pending', False)} job={ai_s.get('reminder_job_id')}, "
        f"python_quiz pending={py_s.get('pending', False)} job={py_s.get('reminder_job_id')}"
    )
