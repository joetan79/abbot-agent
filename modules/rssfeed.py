"""
RSS Feed integration for real-time AI and tech news.
Free, no API key, real-time updates.
"""

import feedparser
import logging
from datetime import datetime, timezone, timedelta
from time import mktime

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


def fetch_ai_news(hours: int = 24, count: int = 5) -> list:
    """
    Fetch latest AI and tech news from RSS feeds.
    Real-time, no API key needed, direct article URLs.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    all_articles = []

    for feed_info in AI_TECH_FEEDS:
        try:
            logger.info(f"Fetching RSS: {feed_info['name']}")
            feed = feedparser.parse(feed_info["url"])

            for entry in feed.entries:
                # Get article URL
                article_url = entry.get("link", "")
                if not article_url:
                    continue

                # Get title
                title = entry.get("title", "").strip()
                if not title:
                    continue

                # Get summary
                summary = ""
                if hasattr(entry, "summary"):
                    summary = entry.summary
                elif hasattr(entry, "description"):
                    summary = entry.description

                # Clean HTML from summary
                import re
                summary = re.sub(r"<[^>]+>", "", summary)
                summary = re.sub(r"\s+", " ", summary).strip()
                summary = summary[:500]

                # Get published date
                pub_dt = parse_date(entry)
                pub_str = pub_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

                # Skip if older than requested hours
                if pub_dt < cutoff:
                    continue

                # Check relevance for general feeds
                if not is_relevant(title, summary):
                    continue

                all_articles.append({
                    "title": title,
                    "summary": summary,
                    "source_name": feed_info["name"],
                    "source_url": article_url,
                    "published_at": pub_str,
                    "pub_dt": pub_dt,
                })

        except Exception as e:
            logger.error(f"RSS error {feed_info['name']}: {e}")
            continue

    # Sort by date, newest first
    all_articles.sort(key=lambda x: x["pub_dt"], reverse=True)

    # Remove duplicates by title similarity
    seen_titles = []
    unique_articles = []
    for article in all_articles:
        title_lower = article["title"].lower()[:50]
        if title_lower not in seen_titles:
            seen_titles.append(title_lower)
            unique_articles.append(article)

    # If not enough articles in time window, relax filter
    if len(unique_articles) < 3:
        logger.warning(
            f"Only {len(unique_articles)} articles in "
            f"last {hours}hrs - relaxing to last 72hrs"
        )
        cutoff_relaxed = datetime.now(timezone.utc) - timedelta(hours=72)
        for feed_info in AI_TECH_FEEDS[:3]:
            try:
                feed = feedparser.parse(feed_info["url"])
                for entry in feed.entries[:5]:
                    article_url = entry.get("link", "")
                    title = entry.get("title", "").strip()
                    if not article_url or not title:
                        continue
                    pub_dt = parse_date(entry)
                    if pub_dt < cutoff_relaxed:
                        continue
                    title_lower = title.lower()[:50]
                    if title_lower in seen_titles:
                        continue
                    seen_titles.append(title_lower)
                    summary = ""
                    if hasattr(entry, "summary"):
                        import re
                        summary = re.sub(
                            r"<[^>]+>", "", entry.summary)
                        summary = re.sub(
                            r"\s+", " ", summary).strip()[:500]
                    unique_articles.append({
                        "title": title,
                        "summary": summary,
                        "source_name": feed_info["name"],
                        "source_url": article_url,
                        "published_at": pub_dt.strftime(
                            "%Y-%m-%dT%H:%M:%SZ"),
                        "pub_dt": pub_dt,
                    })
            except Exception:
                continue
        unique_articles.sort(
            key=lambda x: x["pub_dt"], reverse=True)

    result = unique_articles[:count]
    # Remove pub_dt before returning (internal use only)
    for a in result:
        a.pop("pub_dt", None)

    logger.info(
        f"RSS: {len(result)} articles "
        f"(requested last {hours}hrs)"
    )
    return result


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
        return (
            f"No AI & Tech news found in the "
            f"last {time_period}. Please try again later."
        )

    now = datetime.now().strftime("%d %b %Y %H:%M")
    lines = [f"AI & Tech News (past {time_period})\n"]

    for i, article in enumerate(articles, 1):
        # Format published time
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

        block = f"{i}. {article['title']}\n"
        block += f"{article['summary']}\n"
        if pub_time:
            block += f"Published: {pub_time}\n"
        if source_name:
            block += f"Source: {source_name}\n"
        if source_url:
            block += f"Link: {source_url}\n"

        lines.append(block)

    lines.append(f"\nUpdated: {now}")
    return "\n".join(lines)
