"""
modules/xfeed.py
X (Twitter) feed fetcher via RSSHub public instances.
Pulls tweets from key AI accounts and keywords.
"""

import feedparser
import logging
import hashlib
from datetime import datetime, timezone, timedelta
from modules.utils import get_cached_news, set_cached_news, is_article_published, mark_article_published

logger = logging.getLogger(__name__)

RSSHUB_INSTANCES = [
    "https://rsshub.app",
    "https://rsshub.rssforever.com",
    "https://hub.slarker.me",
    "https://rsshub.nn.ci",
]

X_ACCOUNTS = [
    "OpenAI",
    "AnthropicAI",
    "GoogleDeepMind",
    "karpathy",
    "ylecun",
    "sama",
    "GaryMarcus",
    "emollick",
    "demishassabis",
    "xai",
]

X_KEYWORDS = [
    "LLM release",
    "AI model launched",
    "GPT new",
    "Claude new",
    "Gemini AI",
    "open source LLM",
]

X_CACHE_KEY = "x_feed_cache"


def _build_feed_urls(instance):
    urls = []
    for account in X_ACCOUNTS:
        urls.append(f"{instance}/twitter/user/{account}")
    for keyword in X_KEYWORDS:
        encoded = keyword.replace(" ", "%20")
        urls.append(f"{instance}/twitter/keyword/{encoded}")
    return urls


def _parse_x_date(entry):
    try:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        if hasattr(entry, "updated_parsed") and entry.updated_parsed:
            return datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
    except Exception:
        pass
    return None


def _make_post_id(url):
    return hashlib.md5(url.encode()).hexdigest()[:16]


def _fetch_from_instance(instance, hours, count):
    posts = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    urls = _build_feed_urls(instance)

    for url in urls:
        try:
            feed = feedparser.parse(url, request_headers={"User-Agent": "ABbot/1.0"})
            if feed.bozo and not feed.entries:
                continue

            for entry in feed.entries[:10]:
                pub_date = _parse_x_date(entry)
                if not pub_date or pub_date < cutoff:
                    continue

                link = getattr(entry, "link", "") or ""
                if not link:
                    continue

                title = getattr(entry, "title", "") or ""
                summary = getattr(entry, "summary", title) or title
                if title.startswith("RT @"):
                    continue

                feed_title = feed.feed.get("title", "X / Twitter")
                source_account = feed_title.replace("/ Twitter", "").replace("/ X", "").strip()

                posts.append({
                    "id": _make_post_id(link),
                    "title": title[:200],
                    "summary": summary[:500],
                    "url": link,
                    "source": source_account,
                    "published": pub_date.isoformat(),
                    "pub_date": pub_date,
                    "type": "x_post",
                })
        except Exception as e:
            logger.debug(f"xfeed: feed error {url}: {e}")
            continue

    return posts


def fetch_x_posts(hours=8, count=10):
    cached = get_cached_news(X_CACHE_KEY)
    if cached:
        logger.info("xfeed: returning cached X posts")
        return cached[:count]

    all_posts = []
    seen_ids = set()

    for instance in RSSHUB_INSTANCES:
        try:
            posts = _fetch_from_instance(instance, hours, count)
            if posts:
                logger.info(f"xfeed: got {len(posts)} posts from {instance}")
                for post in posts:
                    pid = post["id"]
                    if pid not in seen_ids:
                        if not is_article_published(post["url"]):
                            seen_ids.add(pid)
                            all_posts.append(post)
                if len(all_posts) >= count:
                    break
        except Exception as e:
            logger.warning(f"xfeed: instance {instance} failed: {e}")
            continue

    if not all_posts:
        logger.warning("xfeed: all RSSHub instances failed or no posts found")
        return []

    all_posts.sort(key=lambda x: x.get("pub_date", datetime.min.replace(tzinfo=timezone.utc)), reverse=True)

    cache_safe = [{k: v for k, v in p.items() if k != "pub_date"} for p in all_posts]
    set_cached_news(X_CACHE_KEY, cache_safe, ttl_hours=1)

    return all_posts[:count]


def fetch_x_posts_via_claude(hours=8, count=10):
    """Fallback: use Claude web search to find recent AI tweets/posts."""
    from modules.utils import ask_claude_with_search
    import json

    prompt = f"""Search for the most recent posts and announcements from AI researchers and labs in the last {hours} hours.
Search for recent activity from: OpenAI, Anthropic, Google DeepMind, Sam Altman (@sama), Andrej Karpathy (@karpathy), Yann LeCun (@ylecun).
Also search for: latest AI model announcements today, new LLM releases.

Return ONLY a JSON array with no other text, no markdown fences, no explanation.
Each item must have these exact keys:
- title: the post text or headline (max 200 chars)
- summary: brief context about why it matters (max 300 chars)
- url: direct URL to the post or source article
- source: account or publication name (e.g. "@OpenAI", "Anthropic Blog")
- published: date string (e.g. "2026-04-18")

Return at most {count} items, newest first. Only include real posts with real verifiable URLs."""

    try:
        response = ask_claude_with_search(
            system="You are a precise JSON generator. Return only a valid JSON array, no markdown, no explanation, no code fences.",
            user_msg=prompt,
            max_tokens=2000,
        )
        clean = response.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        clean = clean.strip()
        posts = json.loads(clean)
        if isinstance(posts, list):
            return posts[:count]
        return []
    except Exception as e:
        logger.warning(f"xfeed claude fallback error: {e}")
        return []


def format_x_posts_for_telegram(posts):
    if not posts:
        return "❌ No recent X posts found."

    lines = ["*X / Twitter Updates* — last 8 hours\n"]
    for i, post in enumerate(posts, 1):
        source = post.get("source", "X")
        title = post.get("title", "")[:180]
        url = post.get("url", "")
        pub = post.get("published", "")
        try:
            dt = datetime.fromisoformat(pub)
            time_str = dt.strftime("%H:%M UTC")
        except Exception:
            time_str = ""

        lines.append(f"{i}. *{source}* {time_str}")
        lines.append(f"   {title}")
        if url:
            lines.append(f"   🔗 {url}")
        lines.append("")

    return "\n".join(lines)


def mark_x_posts_published(posts):
    for post in posts:
        mark_article_published(post["url"], post.get("title", ""))
