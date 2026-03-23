"""
NewsAPI integration for fresh real-time news.
Free tier: 100 requests/day at newsapi.org
"""

import os
import httpx
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

logger = logging.getLogger(__name__)

NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "")
NEWSAPI_URL = "https://newsapi.org/v2/everything"


def fetch_ai_news(hours: int = 24, count: int = 5) -> list:
    """
    Fetch latest AI and tech news from NewsAPI.
    Free tier works best without strict from-date filter.
    We fetch latest articles and filter by date ourselves.
    """
    if not NEWSAPI_KEY:
        logger.error("NEWSAPI_KEY not set in .env")
        return []

    try:
        response = httpx.get(
            NEWSAPI_URL,
            params={
                "q": (
                    "artificial intelligence OR "
                    "OpenAI OR Anthropic OR Claude OR "
                    "ChatGPT OR machine learning OR "
                    "large language model OR AI agent OR "
                    "NVIDIA AI OR Google AI OR Microsoft AI"
                ),
                "sortBy": "publishedAt",
                "language": "en",
                "pageSize": 20,
                "apiKey": NEWSAPI_KEY,
            },
            timeout=15,
            headers={"User-Agent": "ABbot/1.0"},
        )

        data = response.json()

        if data.get("status") != "ok":
            logger.error(f"NewsAPI error: {data.get('message')}")
            return []

        from datetime import datetime, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        def parse_article(item):
            if item.get("title") == "[Removed]":
                return None
            if not item.get("title") or not item.get("description"):
                return None
            if not item.get("url"):
                return None
            return {
                "title": item["title"],
                "summary": item.get("description", ""),
                "source_name": item.get("source", {}).get("name", ""),
                "source_url": item.get("url", ""),
                "published_at": item.get("publishedAt", ""),
                "content": item.get("content", ""),
            }

        all_items = data.get("articles", [])

        # First try: strict time filter
        articles = []
        for item in all_items:
            article = parse_article(item)
            if not article:
                continue
            pub_str = article["published_at"]
            if pub_str:
                try:
                    pub_dt = datetime.strptime(
                        pub_str, "%Y-%m-%dT%H:%M:%SZ"
                    ).replace(tzinfo=timezone.utc)
                    if pub_dt < cutoff:
                        continue
                except Exception:
                    pass
            articles.append(article)
            if len(articles) >= count:
                break

        # Fallback: if too few results relax time filter
        if len(articles) < 3:
            logger.warning(
                f"Only {len(articles)} articles in last "
                f"{hours}hrs - relaxing time filter"
            )
            articles = []
            for item in all_items:
                article = parse_article(item)
                if article:
                    articles.append(article)
                if len(articles) >= count:
                    break

        logger.info(
            f"NewsAPI returned {len(articles)} articles "
            f"(requested last {hours}hrs)"
        )
        return articles

    except Exception as e:
        logger.error(f"NewsAPI fetch error: {e}", exc_info=True)
        return []


def fetch_crypto_news(count: int = 3) -> list:
    if not NEWSAPI_KEY:
        return []
    try:
        response = httpx.get(
            NEWSAPI_URL,
            params={
                "q": (
                    "Bitcoin OR Ethereum OR Solana OR "
                    "cryptocurrency OR crypto OR BTC OR ETH"
                ),
                "sortBy": "publishedAt",
                "language": "en",
                "pageSize": count * 2,
                "apiKey": NEWSAPI_KEY,
            },
            timeout=15,
            headers={"User-Agent": "ABbot/1.0"},
        )
        data = response.json()
        if data.get("status") != "ok":
            logger.error(f"NewsAPI crypto: {data.get('message')}")
            return []
        articles = []
        for item in data.get("articles", []):
            if item.get("title") == "[Removed]":
                continue
            if not item.get("title") or not item.get("description"):
                continue
            articles.append({
                "title": item["title"],
                "summary": item.get("description", ""),
                "source_name": item.get(
                    "source", {}).get("name", ""),
                "source_url": item.get("url", ""),
                "published_at": item.get("publishedAt", ""),
            })
            if len(articles) >= count:
                break
        logger.info(f"NewsAPI crypto: {len(articles)} articles")
        return articles
    except Exception as e:
        logger.error(f"NewsAPI crypto error: {e}")
        return []


def format_articles_for_telegram(articles: list, time_period: str) -> str:
    """Format NewsAPI articles for Telegram message."""
    if not articles:
        return "No recent news found."

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
                )
                pub_time = dt.strftime("%b %d, %H:%M")
            except Exception:
                pub_time = ""

        source_name = article.get("source_name", "")
        source_url = article.get("source_url", "")

        # Build article block
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
