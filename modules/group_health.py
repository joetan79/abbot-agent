"""Detects and self-heals Telegram group ID changes (supergroup migration, kicks)."""

import logging
import os
import re

from telegram.error import ChatMigrated, Forbidden, BadRequest

logger = logging.getLogger(__name__)

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")


def _update_env_chat_id(old_id: int, new_id: int) -> bool:
    """Replace old_id with new_id inside the ALLOWED_CHAT_IDS= line in .env."""
    try:
        with open(ENV_PATH, "r") as f:
            content = f.read()
        m = re.search(r"^ALLOWED_CHAT_IDS=.*$", content, re.MULTILINE)
        if not m:
            return False
        line = m.group(0)
        new_line = line.replace(str(old_id), str(new_id))
        if new_line == line:
            return False
        content = content[:m.start()] + new_line + content[m.end():]
        with open(ENV_PATH, "w") as f:
            f.write(content)
        return True
    except Exception as e:
        logger.error(f"[GroupHealth] Failed to update .env: {e}")
        return False


async def check_group_membership(bot):
    """Ping each allowed group; auto-fix supergroup migrations, alert on kicks."""
    from modules.utils import ALLOWED_CHAT_IDS, OWNER_CHAT_ID
    from modules.health_monitor import notify_error

    group_ids = [cid for cid in list(ALLOWED_CHAT_IDS) if cid < 0]

    for chat_id in group_ids:
        try:
            await bot.get_chat_member_count(chat_id)
        except ChatMigrated as e:
            new_id = e.new_chat_id
            logger.warning(f"[GroupHealth] Group {chat_id} migrated to supergroup {new_id}")

            ALLOWED_CHAT_IDS.discard(chat_id)
            ALLOWED_CHAT_IDS.add(new_id)
            env_updated = _update_env_chat_id(chat_id, new_id)

            await notify_error(
                bot, f"group_migrated_{chat_id}",
                f"Group {chat_id} was upgraded to a Telegram supergroup "
                f"(new ID: {new_id}).\n\n"
                f"I've switched over automatically — "
                f"{'.env updated, ' if env_updated else '.env update FAILED, '}"
                f"live config updated, no restart needed. Group messages should work now."
            )
        except Forbidden as e:
            logger.warning(f"[GroupHealth] No longer a member of {chat_id}: {e}")
            await notify_error(
                bot, f"group_forbidden_{chat_id}",
                f"I seem to have been removed from group {chat_id} "
                f"({e}). Please re-add and re-admin me — I can't self-heal this one."
            )
        except BadRequest as e:
            logger.warning(f"[GroupHealth] Chat {chat_id} error: {e}")
            await notify_error(
                bot, f"group_badrequest_{chat_id}",
                f"Group {chat_id} check failed: {e}. It may have been deleted "
                f"or I've lost access — please check."
            )
        except Exception as e:
            logger.warning(f"[GroupHealth] Unexpected error checking {chat_id}: {e}")
