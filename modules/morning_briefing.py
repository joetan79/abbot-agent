"""Morning briefing (#1) + Daily planner (#9).
Sends one consolidated morning message: weather, crypto, news headlines,
tasks, reminders, calendar events, and a focus suggestion."""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


async def send_morning_briefing(bot):
    from modules.utils import (
        OWNER_CHAT_ID, ask_claude, ask_claude_with_search,
        MODEL_FAST, task_list, memory_get
    )
    if not OWNER_CHAT_ID:
        return

    city = memory_get("city", "Kuala Lumpur")
    now_str = datetime.now().strftime("%A, %d %b %Y  %H:%M MYT")
    sections = [f"🌅 *Good Morning, Joe!*\n_{now_str}_"]

    # ── Weather ───────────────────────────────────────────────────────────────
    try:
        weather = ask_claude_with_search(
            "You are a concise weather reporter. Use Celsius only. Max 3 lines.",
            f"current weather {city} today temperature celsius humidity",
            max_tokens=120, model=MODEL_FAST,
        )
        sections.append(f"🌤 *Weather ({city}):*\n{weather.strip()}")
    except Exception as e:
        logger.error(f"[Briefing] Weather failed: {e}")

    # ── Crypto ────────────────────────────────────────────────────────────────
    try:
        from modules.coingecko import get_prices
        prices = get_prices(["bitcoin", "ethereum", "solana"])
        if prices:
            lines = []
            symbols = {"bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL"}
            for coin, sym in symbols.items():
                p = prices.get(coin, {})
                usd = p.get("usd", 0)
                chg = p.get("usd_24h_change", 0)
                arrow = "▲" if chg >= 0 else "▼"
                lines.append(f"  {sym} ${usd:,.0f} {arrow}{abs(chg):.1f}%")
            sections.append("💹 *Crypto (24h):*\n" + "\n".join(lines))
    except Exception as e:
        logger.error(f"[Briefing] Crypto failed: {e}")

    # ── News headlines ────────────────────────────────────────────────────────
    try:
        from modules.rssfeed import fetch_ai_news
        from modules.news_pref import rank_articles
        articles = fetch_ai_news(hours=10, count=8)
        articles = rank_articles(articles)[:3]
        if articles:
            headlines = "\n".join(
                f"  {i}. {a['title'][:90]}" for i, a in enumerate(articles, 1)
            )
            sections.append(f"📰 *Top AI News:*\n{headlines}")
    except Exception as e:
        logger.error(f"[Briefing] News failed: {e}")

    # ── Tasks ─────────────────────────────────────────────────────────────────
    try:
        tasks = [t for t in task_list() if not t.get("done")]
        if tasks:
            task_lines = "\n".join(f"  • {t['text'][:60]}" for t in tasks[:5])
            more = f"\n  _(+{len(tasks)-5} more)_" if len(tasks) > 5 else ""
            sections.append(f"📋 *Tasks ({len(tasks)} pending):*\n{task_lines}{more}")
    except Exception as e:
        logger.error(f"[Briefing] Tasks failed: {e}")

    # ── Today's reminders ─────────────────────────────────────────────────────
    try:
        from modules.utils import _load, REMINDERS_FILE
        reminders = _load(REMINDERS_FILE) if hasattr(__import__('modules.utils', fromlist=['REMINDERS_FILE']), 'REMINDERS_FILE') else {}
        today = datetime.now().date().isoformat()
        due_today = []
        for rid, r in reminders.items():
            if not r.get("fired"):
                fire = r.get("fire_at", "")
                if fire and fire[:10] == today:
                    due_today.append(f"  • {fire[11:16]} {r.get('message','')[:50]}")
        if due_today:
            sections.append("⏰ *Reminders today:*\n" + "\n".join(due_today))
    except Exception:
        pass  # Reminders are optional in briefing

    # ── Google Calendar ───────────────────────────────────────────────────────
    try:
        from modules.gcal import is_connected, get_today_events
        if is_connected():
            events = get_today_events()
            if events:
                ev_lines = "\n".join(
                    f"  • {e['time']} {e['title'][:50]}" for e in events[:5]
                )
                sections.append(f"📅 *Calendar today:*\n{ev_lines}")
    except Exception as e:
        logger.debug(f"[Briefing] Calendar skipped: {e}")

    # ── Goals progress ────────────────────────────────────────────────────────
    try:
        from modules.goals import list_goals
        active_goals = list_goals()
        if active_goals:
            g_lines = []
            for g in active_goals[:3]:
                bar = "█" * g["this_week"] + "░" * max(0, g["target_per_week"] - g["this_week"])
                g_lines.append(f"  • {g['description'][:40]} [{bar}] streak {g['streak']}d")
            sections.append("🎯 *Goals this week:*\n" + "\n".join(g_lines))
    except Exception as e:
        logger.error(f"[Briefing] Goals failed: {e}")

    # ── Daily focus suggestion ────────────────────────────────────────────────
    try:
        from modules.goals import get_goals_summary
        from modules.episodic_memory import get_episodic_context
        tasks_text = "\n".join(f"- {t['text']}" for t in task_list() if not t.get("done"))[:300]
        goals_text = get_goals_summary()
        episodic = get_episodic_context()
        focus_prompt = (
            f"Date: {now_str}\nCity: {city}\n"
            f"Pending tasks:\n{tasks_text or 'None'}\n\n"
            f"{goals_text}\n\n"
            f"{episodic}\n\n"
            "Give Joe ONE specific focus suggestion for today. "
            "Base it on his patterns, pending work, or goals. "
            "2 sentences max, practical, actionable. Start with 💡"
        )
        focus = ask_claude(
            "You are Joe's AI daily planner. Be specific and practical.",
            focus_prompt, model=MODEL_FAST, max_tokens=100
        )
        sections.append(focus.strip())
    except Exception as e:
        logger.error(f"[Briefing] Focus failed: {e}")

    # ── Send ──────────────────────────────────────────────────────────────────
    message = "\n\n".join(sections)
    try:
        await bot.send_message(chat_id=OWNER_CHAT_ID, text=message, parse_mode="Markdown")
        logger.info("[Briefing] Morning briefing sent")
    except Exception as e:
        logger.error(f"[Briefing] Send failed with Markdown: {e}")
        try:
            await bot.send_message(chat_id=OWNER_CHAT_ID, text=message)
        except Exception as e2:
            logger.error(f"[Briefing] Send failed plain: {e2}")
