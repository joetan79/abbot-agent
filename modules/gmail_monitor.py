"""Gmail IMAP monitor — poll for new emails and notify via Telegram."""

import os
import imaplib
import email
import asyncio
import logging
from email.header import decode_header as _decode_header

logger = logging.getLogger(__name__)

GMAIL_ADDRESS      = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
IMAP_HOST          = "imap.gmail.com"
IMAP_PORT          = 993


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


def _fetch_unseen_emails() -> list:
    """
    Connect to Gmail IMAP, fetch UNSEEN emails, mark them read.
    Returns list of dicts with 'from' and 'subject'.
    Runs in a thread (blocking I/O).
    """
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        logger.warning("Gmail credentials not configured — skipping check")
        return []

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
            return []

        for eid in data[0].split():
            try:
                status, msg_data = mail.fetch(eid, "(RFC822)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)

                from_raw    = msg.get("From", "Unknown")
                subject_raw = msg.get("Subject", "(no subject)")

                results.append({
                    "from":    _decode_header_value(from_raw),
                    "subject": _decode_header_value(subject_raw),
                })
                mail.store(eid, "+FLAGS", "\\Seen")
            except Exception as e:
                logger.error(f"Gmail: error processing email {eid}: {e}")

    except imaplib.IMAP4.error as e:
        logger.error(f"Gmail IMAP auth/connection error: {e}")
    except OSError as e:
        logger.error(f"Gmail IMAP network error: {e}")
    except Exception as e:
        logger.error(f"Gmail monitor unexpected error: {e}")
    finally:
        if mail:
            try:
                mail.logout()
            except Exception:
                pass

    return results


async def check_new_emails(bot) -> None:
    """
    Poll Gmail for UNSEEN emails and send Telegram notifications.
    Called by APScheduler every 30 minutes.
    """
    from modules.utils import OWNER_CHAT_ID

    logger.info("📧 Gmail: checking for new emails...")
    try:
        emails = await asyncio.to_thread(_fetch_unseen_emails)
    except Exception as e:
        logger.error(f"Gmail monitor thread error: {e}")
        return

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
