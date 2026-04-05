"""
RSS Feed integration for real-time AI and tech news.
Free, no API key, real-time updates.
"""

import re
import feedparser
import logging
from datetime import datetime, timezone, timedelta
from time import mktime
from modules.utils import is_article_published, mark_article_published

logger = logging.getLogger(__name__)

# Top AI and Tech RSS feeds
AI_TECH_FEEDS = [
    {
        "name": "TechCrunch AI",
        "url": "https://techcrunch.com/category/artificial-intelligence/feed/",
    },
    {
        "name": "The Verge AI",
        "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    },
    {
        "name": "VentureBeat AI",
        "url": "https://venturebeat.com/category/ai/feed/",
    },
    {
        "name": "Ars Technica",
        "url": "https://feeds.arstechnica.com/arstechnica/index",
    },
    {
        "name": "Wired AI",
        "url": "https://www.wired.com/feed/tag/artificial-intelligence/rss",
    },
    {
        "name": "MIT Tech Review",
        "url": "https://www.technologyreview.com/feed/",
    },
    {
        "name": "Reuters Tech",
        "url": "https://feeds.reuters.com/reuters/technologyNews",
    },
    {
        "name": "ZDNet AI",
        "url": "https://www.zdnet.com/topic/artificial-intelligence/rss.xml",
    },
]

# Crypto RSS feeds
CRYPTO_FEEDS = [
    {
        "name": "CoinDesk",
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    },
    {
        "name": "CoinTelegraph",
        "url": "https://cointelegraph.com/rss",
    },
    {
        "name": "Decrypt",
        "url": "https://decrypt.co/feed",
    },
]

# Keywords to filter AI/tech relevant articles
AI_KEYWORDS = [
    "artificial intelligence", "ai ", " ai",
    "machine learning", "deep learning",
    "openai", "anthropic", "claude", "chatgpt",
    "gpt", "llm", "large language",
    "nvidia", "google ai", "microsoft ai",
    "gemini", "copilot", "neural",
    "robot", "automation", "tech", "software",
    "apple", "meta ai", "samsung ai",
]


def parse_date(entry) -> datetime:
    """Parse RSS entry date to datetime object."""
    try:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            return datetime.fromtimestamp(
                mktime(entry.published_parsed),
                tz=timezone.utc
            )
        if hasattr(entry, "updated_parsed") and entry.updated_parsed:
            return datetime.fromtimestamp(
                mktime(entry.updated_parsed),
                tz=timezone.utc
            )
    except Exception:
        pass
    return datetime.now(timezone.utc)


def is_relevant(title: str, summary: str) -> bool:
    """Check if article is AI/tech relevant."""
    text = (title + " " + summary).lower()
    return any(kw in text for kw in AI_KEYWORDS)


def parse_article(item) -> dict | None:
    """Parse a feedparser entry into an article dict. Returns None if invalid."""
    if not item:
        return None

    title = ""
    if hasattr(item, "title"):
        title = item.title
    elif isinstance(item, dict):
        title = item.get("title", "")

    if not title or title == "[Removed]":
        return None
    title = title.strip()

    # Get summary - check multiple fields
    summary = ""
    for field in ["summary", "description", "content", "subtitle"]:
        if hasattr(item, field):
            val = getattr(item, field)
            if val:
                if isinstance(val, list):
                    summary = val[0].get("value", "") if val else ""
                else:
                    summary = str(val)
                break
        elif isinstance(item, dict):
            val = item.get(field, "")
            if val:
                summary = str(val)
                break

    if not summary:
        return None

    summary = re.sub(r"<[^>]+>", "", summary)
    summary = re.sub(r"\s+", " ", summary).strip()
    summary = summary[:500]

    # Get URL - check ALL possible field names
    # RSS feedparser uses "link"; some feeds use "url", "href", "id"
    source_url = ""
    url_fields = ["link", "url", "href", "id", "guid", "feedburner_origlink"]

    for field in url_fields:
        val = ""
        if hasattr(item, field):
            val = str(getattr(item, field) or "")
        elif isinstance(item, dict):
            val = str(item.get(field, "") or "")

        if val and val.startswith("http"):
            source_url = val
            break

    # Also check links list (some RSS formats)
    if not source_url and hasattr(item, "links"):
        for link in (item.links or []):
            href = link.get("href", "")
            if href and href.startswith("http"):
                source_url = href
                break

    if not source_url:
        logger.warning(f"No URL found for: {title[:50]}")
        # Don't return None - keep article but log the missing URL

    # Get source name
    source_name = ""
    if hasattr(item, "source"):
        src = item.source
        if isinstance(src, dict):
            source_name = src.get("title", src.get("name", ""))
        elif hasattr(src, "title"):
            source_name = src.title

    pub_dt = parse_date(item)
    pub_str = pub_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    article = {
        "title": title,
        "summary": summary,
        "source_name": source_name,
        "source_url": source_url,
        "published_at": pub_str,
        "pub_dt": pub_dt,
    }

    logger.debug(
        f"Parsed: {title[:40]} | "
        f"url: {source_url[:60] or 'MISSING'}"
    )

    return article


def fetch_ai_news(hours: int = 24, count: int = 5) -> list:
    """
    Fetch latest AI and tech news from RSS feeds.
    Always tries to include source URLs.
    Falls back gracefully if duplicates filter removes too many articles.
    """
    from modules.utils import is_article_published

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Collect ALL articles from all feeds
    all_articles = []

    for feed_info in AI_TECH_FEEDS:
        try:
            logger.info(f"Fetching: {feed_info['name']}")
            feed = feedparser.parse(feed_info["url"])

            if not feed.entries:
                logger.warning(f"No entries: {feed_info['name']}")
                continue

            for entry in feed.entries[:10]:
                article = parse_article(entry)
                if not article:
                    continue

                # Add feed name if no source
                if not article["source_name"]:
                    article["source_name"] = feed_info["name"]

                all_articles.append(article)

        except Exception as e:
            logger.error(f"Feed error {feed_info['name']}: {e}")
            continue

    logger.info(f"Total collected: {len(all_articles)} from all feeds")

    # Sort by date newest first
    all_articles.sort(
        key=lambda x: x.get("pub_dt", datetime.now(timezone.utc)),
        reverse=True
    )

    # Remove duplicates by title
    seen_titles = set()
    unique_articles = []
    for article in all_articles:
        title_key = article["title"].lower()[:60]
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_articles.append(article)

    logger.info(f"After dedup: {len(unique_articles)} articles")

    # STRATEGY: Try multiple filters in order
    # Always prefer articles WITH source URLs

    def filter_articles(articles, check_time=True,
                        check_published=True, require_url=True):
        results = []
        for a in articles:
            if check_time:
                pub_dt = a.get("pub_dt")
                if pub_dt and pub_dt < cutoff:
                    continue

            if check_published:
                url = a.get("source_url", "")
                if url and is_article_published(url):
                    continue

            if require_url:
                if not a.get("source_url"):
                    continue

            results.append(a)
            if len(results) >= count:
                break
        return results

    # Try 1: Fresh + not published + has URL (ideal)
    result = filter_articles(
        unique_articles,
        check_time=True,
        check_published=True,
        require_url=True
    )
    logger.info(f"Try 1 (ideal): {len(result)}")

    if len(result) >= count:
        result = result[:count]
        _clean_pub_dt(result)
        return result

    # Try 2: Not published + has URL (relax time)
    if len(result) < 3:
        result = filter_articles(
            unique_articles,
            check_time=False,
            check_published=True,
            require_url=True
        )
        logger.info(f"Try 2 (relax time): {len(result)}")

    if len(result) >= count:
        result = result[:count]
        _clean_pub_dt(result)
        return result

    # Try 3: Has URL only (ignore published/time)
    if len(result) < 3:
        result = filter_articles(
            unique_articles,
            check_time=False,
            check_published=False,
            require_url=True
        )
        logger.info(f"Try 3 (url only): {len(result)}")

    if len(result) >= count:
        result = result[:count]
        _clean_pub_dt(result)
        return result

    # Try 4: Absolutely anything (last resort)
    if len(result) < 3:
        logger.warning("Last resort: no URL requirement")
        result = filter_articles(
            unique_articles,
            check_time=False,
            check_published=False,
            require_url=False
        )[:count]
        logger.info(f"Try 4 (anything): {len(result)}")

    _clean_pub_dt(result)

    # Final URL report
    with_url = sum(1 for a in result if a.get("source_url"))
    without_url = len(result) - with_url
    logger.info(
        f"Final: {len(result)} articles | "
        f"with URL: {with_url} | without URL: {without_url}"
    )

    if without_url > 0:
        logger.warning(f"{without_url} articles missing URLs!")

    return result


def _clean_pub_dt(articles: list):
    """Remove internal pub_dt field."""
    for a in articles:
        a.pop("pub_dt", None)


def fetch_crypto_news(count: int = 3) -> list:
    """Fetch latest crypto news from RSS feeds."""
    all_articles = []

    for feed_info in CRYPTO_FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
            for entry in feed.entries[:5]:
                article_url = entry.get("link", "")
                title = entry.get("title", "").strip()
                if not article_url or not title:
                    continue

                summary = ""
                if hasattr(entry, "summary"):
                    import re
                    summary = re.sub(
                        r"<[^>]+>", "", entry.summary)
                    summary = re.sub(
                        r"\s+", " ", summary).strip()[:500]

                pub_dt = parse_date(entry)

                all_articles.append({
                    "title": title,
                    "summary": summary,
                    "source_name": feed_info["name"],
                    "source_url": article_url,
                    "published_at": pub_dt.strftime(
                        "%Y-%m-%dT%H:%M:%SZ"),
                    "pub_dt": pub_dt,
                })
        except Exception as e:
            logger.error(f"Crypto RSS error {feed_info['name']}: {e}")
            continue

    all_articles.sort(key=lambda x: x["pub_dt"], reverse=True)
    result = all_articles[:count]
    for a in result:
        a.pop("pub_dt", None)

    logger.info(f"Crypto RSS: {len(result)} articles")
    return result


def format_articles_for_telegram(
        articles: list, time_period: str) -> str:
    """Format RSS articles for Telegram message."""
    if not articles:
        return f"No AI & Tech news found for last {time_period}."

    now = datetime.now().strftime("%d %b %Y %H:%M")
    lines = [f"AI & Tech News (past {time_period})\n"]

    for i, article in enumerate(articles, 1):
        pub_time = ""
        if article.get("published_at"):
            try:
                dt = datetime.strptime(
                    article["published_at"],
                    "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=timezone.utc)
                pub_time = dt.strftime("%b %d, %H:%M UTC")
            except Exception:
                pub_time = ""

        source_name = article.get("source_name", "")
        source_url = article.get("source_url", "")
        title = article.get("title", "")
        summary = article.get("summary", "")

        block = f"{i}. {title}\n"
        if summary:
            block += f"{summary}\n"
        if pub_time:
            block += f"Published: {pub_time}\n"
        if source_name:
            block += f"Source: {source_name}\n"
        if source_url:
            block += f"Link: {source_url}\n"
        else:
            logger.warning(f"Article {i} has no URL: {title[:40]}")

        lines.append(block)

    lines.append(f"\nUpdated: {now}")
    return "\n".join(lines)
