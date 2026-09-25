"""Gmail IMAP monitor — poll for new emails and notify via Telegram."""

import os
import imaplib
import email
import asyncio
import json
import logging
from pathlib import Path
from email.header import decode_header as _decode_header

logger = logging.getLogger(__name__)

GMAIL_ADDRESS      = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
IMAP_HOST          = "imap.gmail.com"
IMAP_PORT          = 993
HEALTH_FILE        = "data/gmail_health.json"

# Emails whose subject starts with one of these are marked read without a
# Telegram notification — e.g. ainews's own daily newsletter, which would
# otherwise ping Joe every single day.
SKIP_SUBJECT_PREFIXES = ("AI & Tech Daily",)


def _decode_header_value(raw: str) -> str:
    """Decode encoded email header (handles =?utf-8?b?...?= etc.)."""
    try:
        parts = _decode_header(raw)
        out = []
        for part, charset in parts:
            if isinstance(part, bytes):
                out.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                out.append(str(part))
        return "".join(out).strip()
    except Exception:
        return str(raw)


def _fetch_unseen_emails() -> tuple[list, str | None]:
    """
    Connect to Gmail IMAP, fetch UNSEEN emails, mark them read.
    Returns (emails, error): emails is a list of dicts with 'from' and
    'subject'; error is None on success, "auth" when Gmail rejected the login,
    or "other" for network/unexpected failures.
    Runs in a thread (blocking I/O).
    """
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        logger.warning("Gmail credentials not configured — skipping check")
        return [], None

    # Google shows app passwords with spaces; strip them for login
    password = GMAIL_APP_PASSWORD.replace(" ", "")

    results = []
    mail = None
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(GMAIL_ADDRESS, password)
        mail.select("INBOX")

        status, data = mail.search(None, "UNSEEN")
        if status != "OK" or not data[0]:
            return [], None

        for eid in data[0].split():
            try:
                status, msg_data = mail.fetch(eid, "(RFC822)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)

                from_raw    = msg.get("From", "Unknown")
                subject_raw = msg.get("Subject", "(no subject)")
                subject = _decode_header_value(subject_raw)

                mail.store(eid, "+FLAGS", "\\Seen")
                if subject.startswith(SKIP_SUBJECT_PREFIXES):
                    logger.info(f"📧 Gmail: skipped — {subject[:60]}")
                    continue
                results.append({
                    "from":    _decode_header_value(from_raw),
                    "subject": subject,
                })
            except Exception as e:
                logger.error(f"Gmail: error processing email {eid}: {e}")

    except imaplib.IMAP4.error as e:
        logger.error(f"Gmail IMAP auth/connection error: {e}")
        return results, "auth"
    except OSError as e:
        logger.error(f"Gmail IMAP network error: {e}")
        return results, "other"
    except Exception as e:
        logger.error(f"Gmail monitor unexpected error: {e}")
        return results, "other"
    finally:
        if mail:
            try:
                mail.logout()
            except Exception:
                pass

    return results, None


def _alert_state() -> bool:
    """True if Joe has already been told the Gmail login is failing."""
    try:
        return json.loads(Path(HEALTH_FILE).read_text()).get("alerted", False)
    except Exception:
        return False


def _set_alert_state(alerted: bool) -> None:
    Path(HEALTH_FILE).write_text(json.dumps({"alerted": alerted}))


async def check_new_emails(bot) -> None:
    """
    Poll Gmail for UNSEEN emails and send Telegram notifications.
    Called by APScheduler every 30 minutes.
    """
    from modules.utils import OWNER_CHAT_ID

    logger.info("📧 Gmail: checking for new emails...")
    try:
        emails, error = await asyncio.to_thread(_fetch_unseen_emails)
    except Exception as e:
        logger.error(f"Gmail monitor thread error: {e}")
        return

    # Previously a failed login fell through to "no new emails" below, which
    # hid a dead app password for 3+ months (2026-06-08 → 09-25). Now: log the
    # failure as such, and tell Joe once per breakage when Gmail rejects the
    # login (network blips don't alert).
    if error:
        logger.warning(f"📧 Gmail: check FAILED ({error}) — see error above")
        if error == "auth" and not _alert_state():
            try:
                await bot.send_message(
                    chat_id=OWNER_CHAT_ID,
                    text=(
                        f"⚠️ Gmail 登入失敗（{GMAIL_ADDRESS}），郵件通知暫停。\n"
                        "App Password 可能已失效，請到 https://myaccount.google.com/apppasswords 建立新的，"
                        "再更新 .env 的 GMAIL_APP_PASSWORD。\n\n"
                        f"Gmail login failed for {GMAIL_ADDRESS} — email notifications are paused. "
                        "The app password has likely expired; create a new one and update GMAIL_APP_PASSWORD in .env."
                    ),
                )
                _set_alert_state(True)
            except Exception as e:
                logger.error(f"Gmail: failed to send login-failure alert: {e}")
        return
    if _alert_state():
        _set_alert_state(False)  # login works again — re-arm the alert

    if not emails:
        logger.info("📧 Gmail: no new emails")
        return

    for em in emails:
        try:
            text = (
                f"📧 New Email\n"
                f"From: {em['from']}\n"
                f"Subject: {em['subject']}"
            )
            await bot.send_message(chat_id=OWNER_CHAT_ID, text=text)
            logger.info(f"📧 Gmail: notified — {em['subject'][:60]}")
        except Exception as e:
            logger.error(f"Gmail: Telegram notify error: {e}")
