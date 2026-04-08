"""
RSS Feed integration for real-time AI and tech news.
Free, no API key, real-time updates.
"""

import re
import time
import email.utils
import feedparser
import logging
from datetime import datetime, timezone, timedelta
from modules.utils import is_article_published, mark_article_published

logger = logging.getLogger(__name__)

# Top AI and Tech RSS feeds
AI_TECH_FEEDS = [
    # Original feeds
    {
        "name": "TechCrunch AI",
        "url": "https://techcrunch.com/category/artificial-intelligence/feed/",
        "category": "AI & Tech",
        "priority": 1,
    },
    {
        "name": "The Verge AI",
        "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
        "category": "AI & Tech",
        "priority": 1,
    },
    {
        "name": "VentureBeat AI",
        "url": "https://venturebeat.com/category/ai/feed/",
        "category": "AI & Tech",
        "priority": 1,
    },
    {
        "name": "Ars Technica",
        "url": "https://feeds.arstechnica.com/arstechnica/index",
        "category": "AI & Tech",
        "priority": 2,
    },
    {
        "name": "MIT Tech Review",
        "url": "https://www.technologyreview.com/feed/",
        "category": "AI Research",
        "priority": 1,
    },
    {
        "name": "ZDNet AI",
        "url": "https://www.zdnet.com/topic/artificial-intelligence/rss.xml",
        "category": "AI & Tech",
        "priority": 2,
    },
    # New high quality feeds
    {
        "name": "Google AI Blog",
        "url": "https://blog.research.google/feeds/posts/default",
        "category": "AI Research",
        "priority": 1,
    },
    {
        "name": "OpenAI News",
        "url": "https://openai.com/news/rss.xml",
        "category": "AI Models",
        "priority": 1,
    },
    {
        "name": "Hugging Face Blog",
        "url": "https://huggingface.co/blog/feed.xml",
        "category": "AI Research",
        "priority": 1,
    },
    {
        "name": "Bloomberg Tech",
        "url": "https://feeds.bloomberg.com/technology/news.rss",
        "category": "AI Business",
        "priority": 2,
    },
    {
        "name": "Synced AI",
        "url": "https://syncedreview.com/feed/",
        "category": "AI Research",
        "priority": 2,
    },
    {
        "name": "AI News",
        "url": "https://www.artificialintelligence-news.com/feed/",
        "category": "AI & Tech",
        "priority": 1,
    },
    {
        "name": "Towards Data Science",
        "url": "https://towardsdatascience.com/feed",
        "category": "AI Research",
        "priority": 3,
    },
    {
        "name": "InfoQ AI",
        "url": "https://feed.infoq.com/",
        "category": "AI & Tech",
        "priority": 2,
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

# Keywords to filter AI/tech relevant articles (legacy — kept for compatibility)
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


def calculate_relevance_score(title: str, summary: str) -> int:
    """
    Score article relevance 0-100.
    Higher = more relevant to AI & Tech.
    """
    text = (title + " " + summary).lower()
    score = 0

    # Tier 1 - Core AI topics (high value)
    tier1_keywords = [
        "artificial intelligence", "machine learning",
        "large language model", "llm", "neural network",
        "deep learning", "generative ai", "gen ai",
        "foundation model", "transformer",
    ]
    for kw in tier1_keywords:
        if kw in text:
            score += 15

    # Tier 2 - AI companies & products (high value)
    tier2_keywords = [
        "openai", "anthropic", "claude", "chatgpt",
        "gpt-4", "gpt-5", "gemini", "copilot",
        "nvidia", "deepmind", "meta ai", "llama",
        "mistral", "groq", "perplexity", "midjourney",
        "stable diffusion", "dall-e", "sora",
    ]
    for kw in tier2_keywords:
        if kw in text:
            score += 12

    # Tier 3 - Tech topics (medium value)
    tier3_keywords = [
        "robotics", "automation", "autonomous",
        "computer vision", "natural language",
        "reinforcement learning", "ai agent",
        "multimodal", "benchmark", "dataset",
        "open source", "microsoft", "google",
        "apple", "amazon", "tesla ai",
    ]
    for kw in tier3_keywords:
        if kw in text:
            score += 8

    # Tier 4 - General tech (lower value)
    tier4_keywords = [
        "startup", "funding", "venture", "billion",
        "launch", "release", "update", "version",
        "software", "cloud", "data", "algorithm",
        "chip", "semiconductor", "quantum",
    ]
    for kw in tier4_keywords:
        if kw in text:
            score += 4

    # Boost for title matches (more important)
    title_lower = title.lower()
    for kw in tier1_keywords + tier2_keywords:
        if kw in title_lower:
            score += 10  # title bonus

    # Penalty for non-tech content
    penalty_keywords = [
        "sports", "football", "celebrity",
        "fashion", "cooking", "travel",
        "weather forecast", "horoscope",
    ]
    for kw in penalty_keywords:
        if kw in text:
            score -= 20

    return max(0, min(100, score))


def is_relevant(title: str, summary: str, min_score: int = 8) -> bool:
    """Check if article meets minimum relevance."""
    score = calculate_relevance_score(title, summary)
    return score >= min_score


def auto_categorize(title: str, summary: str) -> str:
    """Auto-assign category based on content."""
    text = (title + " " + summary).lower()

    # Check categories in priority order
    if any(kw in text for kw in [
        "gpt", "claude", "gemini", "llama",
        "model release", "new model", "llm release",
        "foundation model", "language model"
    ]):
        return "AI Models"

    if any(kw in text for kw in [
        "funding", "raises", "billion", "million",
        "acquisition", "merger", "ipo", "valuation",
        "investment", "startup", "venture"
    ]):
        return "AI Business"

    if any(kw in text for kw in [
        "regulation", "policy", "law", "ban",
        "congress", "european", "gdpr", "act",
        "government", "senate", "safety"
    ]):
        return "AI Policy"

    if any(kw in text for kw in [
        "research", "paper", "study", "benchmark",
        "arxiv", "university", "lab", "experiment",
        "breakthrough", "discovery", "published"
    ]):
        return "AI Research"

    if any(kw in text for kw in [
        "robot", "autonomous", "self-driving",
        "drone", "automation", "manufacturing"
    ]):
        return "Robotics"

    if any(kw in text for kw in [
        "nvidia", "chip", "gpu", "hardware",
        "semiconductor", "processor", "compute"
    ]):
        return "AI Hardware"

    return "AI & Tech"  # default


def meets_quality_standards(article: dict) -> bool:
    """
    Check article meets minimum quality bar.
    Returns True if article should be included.
    """
    title = article.get("title", "")
    summary = article.get("summary", "")

    # Title must be meaningful length
    if len(title) < 20:
        logger.debug(f"Too short title: {title}")
        return False

    # Summary must have substance
    if len(summary) < 50:
        logger.debug(f"Too short summary: {title[:40]}")
        return False

    # Skip pure listicles/clickbait
    clickbait_patterns = [
        "you won't believe",
        "this one trick",
        "doctors hate",
        "click here",
    ]
    title_lower = title.lower()
    for pattern in clickbait_patterns:
        if pattern in title_lower:
            return False

    # Must have minimum relevance
    score = calculate_relevance_score(title, summary)
    if score < 5:
        logger.debug(f"Low relevance ({score}): {title[:40]}")
        return False

    return True


def parse_date(entry) -> datetime | None:
    """
    Parse RSS entry date accurately.
    Returns None if date cannot be determined.
    NEVER falls back to datetime.now() — that would make
    undated articles always pass the time filter.
    """
    now = datetime.now(timezone.utc)
    one_year_ago = now - timedelta(days=365)
    one_day_future = now + timedelta(days=1)

    # Try feedparser's pre-parsed time structs first (most reliable)
    for attr in ["published_parsed", "updated_parsed", "created_parsed"]:
        val = getattr(entry, attr, None)
        if val is None and isinstance(entry, dict):
            val = entry.get(attr)

        if val is not None:
            try:
                timestamp = time.mktime(val)
                dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                if one_year_ago <= dt <= one_day_future:
                    return dt
                else:
                    logger.debug(f"Date out of range: {dt}")
            except Exception as e:
                logger.debug(f"Date parse error for {attr}: {e}")
                continue

    # Try string date fields
    date_strings = []
    for attr in ["published", "updated", "created", "date"]:
        val = getattr(entry, attr, None)
        if val is None and isinstance(entry, dict):
            val = entry.get(attr)
        if val and isinstance(val, str):
            date_strings.append(val.strip())

    for date_str in date_strings:
        if not date_str:
            continue

        dt = None

        # Try email/RFC 2822 format (most common in RSS)
        # e.g. "Mon, 07 Apr 2026 10:30:00 +0800"
        try:
            parsed = email.utils.parsedate_to_datetime(date_str)
            dt = parsed.astimezone(timezone.utc)
        except Exception:
            pass

        # Try ISO 8601 formats
        if dt is None:
            iso_formats = [
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S.%f%z",
                "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
            ]
            for fmt in iso_formats:
                try:
                    dt = datetime.strptime(date_str[:len(fmt) + 5], fmt)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    else:
                        dt = dt.astimezone(timezone.utc)
                    break
                except Exception:
                    continue

        if dt is not None:
            if one_year_ago <= dt <= one_day_future:
                return dt
            else:
                logger.debug(f"Date string out of range: {date_str} -> {dt}")

    # Could not determine date
    logger.debug(
        f"Could not parse date for: "
        f"{getattr(entry, 'title', 'unknown')[:50]}"
    )
    return None  # NEVER return datetime.now()


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
    pub_str = pub_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if pub_dt else ""

    article = {
        "title": title,
        "summary": summary,
        "source_name": source_name,
        "source_url": source_url,
        "published_at": pub_str,
        "pub_dt": pub_dt,
        "category": auto_categorize(title, summary),
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

                # Quality filter
                if not meets_quality_standards(article):
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

    # Add relevance scores
    for article in unique_articles:
        article["relevance_score"] = calculate_relevance_score(
            article["title"],
            article["summary"]
        )

    # Sort by relevance score first, then date
    unique_articles.sort(
        key=lambda x: (
            x.get("relevance_score", 0),
            x.get("pub_dt", datetime.now(timezone.utc))
        ),
        reverse=True
    )

    if unique_articles:
        logger.info(
            f"Top article score: "
            f"{unique_articles[0].get('relevance_score', 0)}"
        )

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


def check_feed_health() -> dict:
    """Check which RSS feeds are responding."""
    results = {}
    for feed_info in AI_TECH_FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
            count = len(feed.entries)
            results[feed_info["name"]] = {
                "status": "ok" if count > 0 else "empty",
                "entries": count,
            }
        except Exception as e:
            results[feed_info["name"]] = {
                "status": "error",
                "error": str(e),
            }
    return results


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
                        "%Y-%m-%dT%H:%M:%SZ") if pub_dt else "",
                    "pub_dt": pub_dt,
                })
        except Exception as e:
            logger.error(f"Crypto RSS error {feed_info['name']}: {e}")
            continue

    all_articles.sort(
        key=lambda x: x["pub_dt"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True
    )
    result = all_articles[:count]
    for a in result:
        a.pop("pub_dt", None)

    logger.info(f"Crypto RSS: {len(result)} articles")
    return result


def format_articles_for_telegram(
        articles: list,
        time_period: str) -> str:
    """Format RSS articles for Telegram message."""
    if not articles:
        return (
            f"No AI & Tech news found "
            f"for last {time_period}."
        )

    now = datetime.now().strftime("%d %b %Y %H:%M")

    # Count categories
    categories = {}
    for a in articles:
        cat = a.get("category", "AI & Tech")
        categories[cat] = categories.get(cat, 0) + 1

    cat_summary = " | ".join(
        f"{cat}: {count}"
        for cat, count in categories.items()
    )

    lines = [
        f"AI & Tech News — {now}",
        f"Period: past {time_period}",
        f"Topics: {cat_summary}",
        "─" * 30,
        "",
    ]

    for i, article in enumerate(articles, 1):
        pub_time = ""
        if article.get("published_at"):
            try:
                dt = datetime.strptime(
                    article["published_at"],
                    "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=timezone.utc)
                pub_time = dt.strftime("%b %d, %H:%M")
            except Exception:
                pub_time = ""

        source_name = article.get("source_name", "")
        source_url = article.get("source_url", "")
        title = article.get("title", "")
        summary = article.get("summary", "")
        category = article.get("category", "AI & Tech")

        block = f"{i}. {title}\n"
        block += f"[{category}]"
        if pub_time:
            block += f" • {pub_time}"
        if source_name:
            block += f" • {source_name}"
        block += "\n"
        if summary:
            short_summary = summary[:200]
            if len(summary) > 200:
                short_summary += "..."
            block += f"{short_summary}\n"

        # NEVER skip this - source link is critical
        if source_url:
            block += f"Link: {source_url}\n"
        else:
            logger.warning(
                f"MISSING URL for article {i}: "
                f"{title[:50]}"
            )

        lines.append(block)

    # Summary stats
    with_url = sum(
        1 for a in articles
        if a.get("source_url")
    )
    lines.append(
        "─" * 30 + "\n"
        f"{len(articles)} stories | "
        f"{with_url} with source links"
    )

    return "\n".join(lines)
