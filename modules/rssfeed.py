"""
RSS Feed integration for real-time AI and tech news.
Free, no API key, real-time updates.
"""

import re
import time
import email.utils
import feedparser
import logging
import httpx
from datetime import datetime, timezone, timedelta
from modules.utils import is_article_published, mark_article_published


def extract_og_image(url: str) -> str | None:
    """
    Fetch og:image meta tag from article URL.
    Zero Claude tokens. One HTTP GET per new article. 4s timeout max.
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; ABbot/1.0; +https://abai.cloud)"}
        r = httpx.get(url, timeout=4, follow_redirects=True, headers=headers)
        if r.status_code != 200:
            return None
        html = r.text
        if 'og:image' not in html:
            return None
        start = html.find('property="og:image"')
        if start == -1:
            start = html.find("property='og:image'")
        if start == -1:
            return None
        content_start = html.find('content="', start)
        if content_start == -1:
            content_start = html.find("content='", start)
            if content_start == -1:
                return None
            quote_char = "'"
        else:
            quote_char = '"'
        content_start += len('content=') + 1
        content_end = html.find(quote_char, content_start)
        if content_end == -1:
            return None
        image_url = html[content_start:content_end].strip()
        if not image_url.startswith("http") or len(image_url) > 500:
            return None
        return image_url
    except Exception:
        return None


def get_source_domain(url: str) -> str:
    """Extract bare domain from URL. e.g. 'https://techcrunch.com/...' → 'techcrunch.com'"""
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""

logger = logging.getLogger(__name__)

# High-frequency primary feeds — post daily, used in all tiers
AI_TECH_FEEDS = [
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
        "name": "Reuters Tech",
        "url": "https://feeds.reuters.com/reuters/technologyNews",
        "category": "AI & Tech",
        "priority": 1,
    },
    {
        "name": "ZDNet AI",
        "url": "https://www.zdnet.com/topic/artificial-intelligence/rss.xml",
        "category": "AI & Tech",
        "priority": 2,
    },
    {
        "name": "Bloomberg Tech",
        "url": "https://feeds.bloomberg.com/technology/news.rss",
        "category": "AI Business",
        "priority": 2,
    },
    {
        "name": "AI News",
        "url": "https://www.artificialintelligence-news.com/feed/",
        "category": "AI & Tech",
        "priority": 1,
    },
    {
        "name": "InfoQ AI",
        "url": "https://feed.infoq.com/",
        "category": "AI & Tech",
        "priority": 2,
    },
]

# Low-frequency research feeds — post infrequently, used ONLY in Tier 3 (72hr window)
RESEARCH_FEEDS = [
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
        "name": "MIT Tech Review",
        "url": "https://www.technologyreview.com/feed/",
        "category": "AI Research",
        "priority": 1,
    },
    {
        "name": "The Batch",
        "url": "https://www.deeplearning.ai/the-batch/feed/",
        "category": "AI Research",
        "priority": 2,
    },
    {
        "name": "Towards Data Science",
        "url": "https://towardsdatascience.com/feed",
        "category": "AI Research",
        "priority": 3,
    },
    {
        "name": "Synced AI",
        "url": "https://syncedreview.com/feed/",
        "category": "AI Research",
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


def parse_article(item,
                  feed_name: str = "",
                  feed_category: str = "AI & Tech") -> dict | None:
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

    # Get source name — fall back to feed_name
    source_name = ""
    if hasattr(item, "source"):
        src = item.source
        if isinstance(src, dict):
            source_name = src.get("title", src.get("name", ""))
        elif hasattr(src, "title"):
            source_name = src.title
    if not source_name and feed_name:
        source_name = feed_name

    pub_dt = parse_date(item)
    has_date = pub_dt is not None
    pub_str = pub_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if pub_dt else ""

    # Auto-categorize, fall back to feed_category
    category = auto_categorize(title, summary)
    if category == "AI & Tech" and feed_category and feed_category != "AI & Tech":
        category = feed_category

    article = {
        "title": title,
        "summary": summary,
        "source_name": source_name,
        "source_url": source_url,
        "published_at": pub_str,
        "pub_dt": pub_dt,
        "has_date": has_date,
        "category": category,
    }

    logger.debug(
        f"Parsed: {title[:40]} | "
        f"url: {source_url[:60] or 'MISSING'}"
    )

    return article


def fetch_ai_news(hours: int = 24, count: int = 5) -> list:
    """
    Fetch AI and tech news with STRICT rules:
    - Primary: last {hours}hrs only
    - Extended: last 72hrs only if primary has < count articles
    - Hard cutoff: NEVER older than 72hrs (no exceptions)
    - Never repeat published articles
    - Research feeds only in extended tiers
    """
    from modules.utils import is_article_published

    now = datetime.now(timezone.utc)
    primary_cutoff = now - timedelta(hours=hours)
    hard_cutoff    = now - timedelta(hours=72)

    logger.info(
        f"News fetch | window: {hours}hrs | "
        f"primary: {primary_cutoff.strftime('%d %b %H:%M UTC')} | "
        f"hard limit: {hard_cutoff.strftime('%d %b %H:%M UTC')}"
    )

    # ─────────────────────────────────────────────
    # COLLECT from primary feeds
    # ─────────────────────────────────────────────
    primary_raw = []
    for feed_info in AI_TECH_FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
            if not feed.entries:
                logger.debug(f"Empty feed: {feed_info['name']}")
                continue
            for entry in feed.entries[:15]:
                article = parse_article(
                    entry,
                    feed_info["name"],
                    feed_info.get("category", "AI & Tech")
                )
                if article:
                    primary_raw.append(article)
        except Exception as e:
            logger.error(f"Feed error {feed_info['name']}: {e}")

    logger.info(f"Primary feeds collected: {len(primary_raw)}")

    # ─────────────────────────────────────────────
    # COLLECT from research feeds
    # ─────────────────────────────────────────────
    research_raw = []
    for feed_info in RESEARCH_FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
            if not feed.entries:
                continue
            for entry in feed.entries[:10]:
                article = parse_article(
                    entry,
                    feed_info["name"],
                    feed_info.get("category", "AI Research")
                )
                if article:
                    research_raw.append(article)
        except Exception as e:
            logger.error(f"Research feed error {feed_info['name']}: {e}")

    logger.info(f"Research feeds collected: {len(research_raw)}")

    # ─────────────────────────────────────────────
    # Add relevance scores
    # ─────────────────────────────────────────────
    for article in primary_raw + research_raw:
        article["relevance_score"] = calculate_relevance_score(
            article["title"], article["summary"]
        )

    # ─────────────────────────────────────────────
    # HARD FILTER — applied to ALL articles, no exceptions
    # Rejects:
    #   1. No valid date (unknown age = unsafe)
    #   2. Older than 72hr hard cutoff
    #   3. Already published (duplicate check)
    # ─────────────────────────────────────────────
    def hard_filter(articles: list, label: str = "") -> list:
        kept = []
        rejected_no_date  = 0
        rejected_old      = 0
        rejected_dup      = 0

        for a in articles:
            pub_dt   = a.get("pub_dt")
            has_date = a.get("has_date", False)
            title    = a.get("title", "")[:50]
            url      = a.get("source_url", "")

            # Rule 1: Must have a valid date
            if not has_date or pub_dt is None:
                rejected_no_date += 1
                logger.debug(f"REJECT no-date: {title}")
                continue

            # Rule 2: Must be within 72hr hard cutoff
            if pub_dt < hard_cutoff:
                rejected_old += 1
                age_days = (now - pub_dt).total_seconds() / 86400
                logger.debug(f"REJECT too old ({age_days:.1f}d): {title}")
                continue

            # Rule 3: Must not already be published
            if url and is_article_published(url):
                rejected_dup += 1
                logger.debug(f"REJECT duplicate: {title}")
                continue

            kept.append(a)

        if label:
            logger.info(
                f"Hard filter [{label}]: kept={len(kept)} | "
                f"no_date={rejected_no_date} | "
                f"old={rejected_old} | dup={rejected_dup}"
            )

        return kept

    primary_filtered  = hard_filter(primary_raw,  "primary")
    research_filtered = hard_filter(research_raw, "research")

    total_rejected = (
        len(primary_raw)  - len(primary_filtered) +
        len(research_raw) - len(research_filtered)
    )
    if total_rejected > 0:
        logger.warning(
            f"Hard filter rejected {total_rejected} articles total"
        )

    # ─────────────────────────────────────────────
    # Deduplication by title
    # ─────────────────────────────────────────────
    def dedup(articles: list) -> list:
        seen, result = set(), []
        for a in articles:
            key = a["title"].lower().strip()[:60]
            if key not in seen:
                seen.add(key)
                result.append(a)
        return result

    primary_filtered  = dedup(primary_filtered)
    research_filtered = dedup(research_filtered)

    # ─────────────────────────────────────────────
    # Sort by relevance + recency
    # ─────────────────────────────────────────────
    def smart_sort(articles: list) -> list:
        return sorted(
            articles,
            key=lambda x: (
                x.get("relevance_score", 0),
                x.get("pub_dt") or datetime.min.replace(tzinfo=timezone.utc)
            ),
            reverse=True
        )

    primary_filtered  = smart_sort(primary_filtered)
    research_filtered = smart_sort(research_filtered)

    # ─────────────────────────────────────────────
    # Separate by time window (post hard-filter)
    # ─────────────────────────────────────────────
    primary_fresh    = [a for a in primary_filtered
                        if a["pub_dt"] >= primary_cutoff]
    primary_extended = [a for a in primary_filtered
                        if a["pub_dt"] < primary_cutoff]
    research_fresh   = [a for a in research_filtered
                        if a["pub_dt"] >= primary_cutoff]
    research_extended = [a for a in research_filtered
                         if a["pub_dt"] < primary_cutoff]

    logger.info(
        f"Categorized: "
        f"primary_fresh={len(primary_fresh)} "
        f"primary_extended={len(primary_extended)} "
        f"research_fresh={len(research_fresh)} "
        f"research_extended={len(research_extended)}"
    )

    # ─────────────────────────────────────────────
    # Build result using tiered approach
    # ─────────────────────────────────────────────
    result     = []
    seen_titles = set()

    def add_articles(pool: list, label: str, need_url: bool = True) -> int:
        added = 0
        for a in pool:
            if len(result) >= count:
                break
            key = a["title"].lower()[:60]
            if key in seen_titles:
                continue
            if need_url and not a.get("source_url"):
                continue
            # Fetch og:image AFTER dedup — only for articles we will publish
            url = a.get("source_url", "")
            if url:
                a["image_url"] = extract_og_image(url)
                a["source_domain"] = get_source_domain(url)
            else:
                a["image_url"] = None
                a["source_domain"] = ""
            result.append(a)
            seen_titles.add(key)
            added += 1
        if added > 0:
            logger.info(
                f"Added {added} from {label} | total: {len(result)}/{count}"
            )
        return added

    # TIER 1: Primary feeds, primary window, with URL
    add_articles(primary_fresh,
                 f"primary fresh ({hours}hrs)", need_url=True)
    if len(result) >= count:
        _log_final(result, hours, now)
        _clean_pub_dt(result)
        return result

    # TIER 2: Research feeds, primary window, with URL
    add_articles(research_fresh,
                 f"research fresh ({hours}hrs)", need_url=True)
    if len(result) >= count:
        _log_final(result, hours, now)
        _clean_pub_dt(result)
        return result

    # Not enough in primary window — extend to 72hrs
    if len(result) < count:
        logger.warning(
            f"Only {len(result)} articles in last {hours}hrs. "
            f"Extending window to 72hrs."
        )

    # TIER 3: Primary feeds, extended window (up to 72hrs), with URL
    add_articles(primary_extended,
                 "primary extended (72hrs)", need_url=True)
    if len(result) >= count:
        _log_final(result, hours, now)
        _clean_pub_dt(result)
        return result

    # TIER 4: Research feeds, extended window (up to 72hrs), with URL
    add_articles(research_extended,
                 "research extended (72hrs)", need_url=True)
    if len(result) >= count:
        _log_final(result, hours, now)
        _clean_pub_dt(result)
        return result

    # TIER 5: Last resort — relax URL requirement, still within 72hrs
    if len(result) < 3:
        logger.warning("Very few articles. Relaxing URL requirement.")
        all_filtered = dedup(smart_sort(primary_filtered + research_filtered))
        add_articles(all_filtered, "any (no url req)", need_url=False)

    _log_final(result, hours, now)
    _clean_pub_dt(result)
    return result


def _log_final(articles: list, hours: int, now: datetime):
    """Log final article selection; error on any 72hr violation."""
    logger.info(f"=== FINAL: {len(articles)} articles ===")
    violations = 0
    hard_cutoff = now - timedelta(hours=72)
    for i, a in enumerate(articles, 1):
        pub_dt = a.get("pub_dt")
        url    = "URL:OK" if a.get("source_url") else "URL:MISSING"
        if pub_dt:
            age_hrs  = (now - pub_dt).total_seconds() / 3600
            age_days = age_hrs / 24
            if pub_dt < hard_cutoff:
                status = f"VIOLATION {age_days:.1f}days!"
                violations += 1
            elif age_hrs <= hours:
                status = f"FRESH {age_hrs:.1f}hrs"
            else:
                status = f"EXTENDED {age_hrs:.1f}hrs"
        else:
            status = "NO-DATE"
        logger.info(f"  {i}. [{status}] [{url}] {a['title'][:50]}")
    if violations > 0:
        logger.error(
            f"CRITICAL: {violations} articles violated 72hr hard cutoff!"
        )
    else:
        logger.info("All articles within 72hr limit")


def _clean_pub_dt(articles: list):
    """Remove internal-only fields before returning to caller."""
    for a in articles:
        a.pop("pub_dt", None)
        a.pop("has_date", None)
        a.pop("is_research", None)


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
            f"for last {time_period}. "
            f"Will retry next schedule."
        )

    now = datetime.now(timezone.utc)

    # Find actual date range of articles
    dates = []
    for a in articles:
        pub = a.get("published_at", "")
        if pub:
            try:
                dt = datetime.strptime(
                    pub, "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=timezone.utc)
                dates.append(dt)
            except Exception:
                pass

    if dates:
        oldest = min(dates)
        newest = max(dates)
        age_range = (
            f"{oldest.strftime('%d %b %H:%M')} - "
            f"{newest.strftime('%d %b %H:%M UTC')}"
        )
    else:
        age_range = "Date unknown"

    # Count categories
    categories = {}
    for a in articles:
        cat = a.get("category", "AI & Tech")
        categories[cat] = categories.get(cat, 0) + 1
    cat_summary = " | ".join(
        f"{c}:{n}" for c, n in categories.items()
    )

    lines = [
        f"AI & Tech News",
        f"Window: last {time_period} | Coverage: {age_range}",
        f"Topics: {cat_summary}",
        "─" * 35,
        "",
    ]

    for i, article in enumerate(articles, 1):
        pub = article.get("published_at", "")
        pub_display = ""

        if pub:
            try:
                dt = datetime.strptime(
                    pub, "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=timezone.utc)
                age_hrs = (now - dt).total_seconds() / 3600

                if age_hrs < 1:
                    age_str = f"{int(age_hrs * 60)}min ago"
                elif age_hrs < 24:
                    age_str = f"{age_hrs:.1f}hrs ago"
                else:
                    age_str = f"{int(age_hrs / 24)}d ago"
                pub_display = (
                    f"{dt.strftime('%d %b %H:%M')} ({age_str})"
                )
            except Exception:
                pub_display = pub[:16]

        source_name = article.get("source_name", "")
        source_url = article.get("source_url", "")
        title = article.get("title", "")
        summary = article.get("summary", "")
        category = article.get("category", "AI & Tech")

        block = f"{i}. {title}\n"
        block += f"[{category}]"
        if pub_display:
            block += f" • {pub_display}"
        if source_name:
            block += f" • {source_name}"
        block += "\n"

        if summary:
            short = summary[:180]
            if len(summary) > 180:
                short += "..."
            block += f"{short}\n"

        # CRITICAL - never skip source link
        if source_url:
            block += f"Link: {source_url}\n"
        else:
            logger.warning(
                f"No URL for article {i}: {title[:50]}"
            )

        lines.append(block)

    with_url = sum(1 for a in articles if a.get("source_url"))
    lines.append(
        "─" * 35 + "\n"
        f"{len(articles)} stories | {with_url} with links"
    )

    return "\n".join(lines)
