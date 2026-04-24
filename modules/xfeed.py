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
from modules.rssfeed import clean_text

logger = logging.getLogger(__name__)

RSSHUB_INSTANCES = [
    "https://rsshub.app",
    "https://rsshub.rssforever.com",
    "https://hub.slarker.me",
    "https://rsshub.nn.ci",
]

X_ACCOUNTS = [
    # US Major Labs
    "OpenAI",
    "AnthropicAI",
    "GoogleDeepMind",
    "MetaAI",
    "xai",
    "NVIDIAAl",
    "MSFTResearch",
    "IBMResearch",
    "CohereAI",
    "MistralAI",
    # Key Researchers
    "sama",
    "karpathy",
    "ylecun",
    "demishassabis",
    "ilyasut",
    "drjimfan",
    # Asian Labs
    "deepseek_ai",
    "Alibaba_Qwen",
    "01AI_Yi",
    "SamsungAILab",
    # Other Global
    "TIIuae",
    "huggingface",
    "StabilityAI",
    "EleutherAI",
]

X_KEYWORDS = [
    "AI model release 2026",
    "LLM benchmark new",
    "open source AI model",
    "DeepSeek new model",
    "Qwen model release",
    "AI research breakthrough",
    "foundation model launch",
    "AGI announcement",
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

                title = clean_text(getattr(entry, "title", "") or "")
                summary = clean_text(getattr(entry, "summary", title) or title)
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


def fetch_x_posts(hours=24, count=10):
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


def format_x_posts_for_telegram(posts):
    if not posts:
        return "❌ No recent X posts found."

    lines = ["*AI Pulse & Updates*\n"]
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


def get_xfeed_search_prompt():
    """Build a date-stamped search prompt so Claude only returns today/yesterday's news."""
    from datetime import datetime, timezone, timedelta
    today_str = datetime.now(timezone.utc).strftime("%B %d, %Y")
    yesterday_str = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%B %d, %Y")
    return f"""Today is {today_str}. Search the web for AI news published TODAY or YESTERDAY ({yesterday_str}) only.

Find announcements published on {today_str} or {yesterday_str} from:
OpenAI, Anthropic, Google DeepMind, Meta AI, Microsoft AI, NVIDIA, DeepSeek, Alibaba Qwen, Mistral AI, xAI, Hugging Face, Cohere, Stability AI, TII UAE, Samsung AI, Baidu.

STRICT RULES:
- Only include articles with a clear publication date of {today_str} or {yesterday_str}
- Do NOT include anything from before {yesterday_str}
- Do NOT include general overviews or roundups from previous weeks
- Do NOT make up or hallucinate URLs — only use URLs you actually found
- If you find fewer than 3 genuine recent items, return only what is real

For each item found, use EXACTLY this format:
SOURCE: (lab or company name only)
TITLE: (headline only, no lab name prefix)
URL: (direct link to the announcement or article)
DATE: (exact date like {datetime.now(timezone.utc).strftime("%Y-%m-%d")})
WHY: (one sentence why this matters)

Separate each item with a blank line. Maximum 10 items."""


# Keep for backward-compat imports; callers should prefer get_xfeed_search_prompt()
XFEED_SEARCH_PROMPT = get_xfeed_search_prompt()


def parse_claude_news_response(raw, max_age_days=3):
    """
    Parse plain-text Claude search response into structured post dicts.
    Filters out old articles, section headers, and duplicates.
    """
    import re
    from datetime import datetime, timezone, timedelta

    if not raw or len(raw.strip()) < 50:
        return []

    today = datetime.now(timezone.utc)
    cutoff_date = today - timedelta(days=max_age_days)

    known_labs = [
        "OpenAI", "Anthropic", "Google DeepMind", "DeepMind",
        "Meta AI", "Meta", "Microsoft", "NVIDIA", "DeepSeek",
        "Alibaba", "Qwen", "Mistral", "xAI", "Cohere",
        "Hugging Face", "Stability AI", "TII", "IBM",
        "Samsung", "Baidu", "ByteDance", "01.AI", "EleutherAI",
        "Inflection", "Writer", "SenseTime", "Zhipu", "KAIST",
        "NAVER", "Google", "Apple", "Amazon", "Tesla",
        "Nature", "Stanford", "MIT", "Berkeley", "Oxford",
        "Scale AI", "Runway", "Midjourney", "Perplexity",
    ]

    junk_patterns = [
        r'latest ai news',
        r'past \d+ hours',
        r'here are',
        r'following.*found',
        r'search result',
        r'^\d+\s*$',
        r'^(january|february|march|april|may|june|july|august|september|october|november|december)',
        r'no (new|recent|significant)',
        r'i (found|searched|looked)',
        r'based on',
        r'as of',
        r'update[sd]? from',
    ]

    def is_junk(text):
        t = text.lower().strip()
        if len(t) < 15:
            return True
        for pattern in junk_patterns:
            if re.search(pattern, t, re.IGNORECASE):
                return True
        return False

    def parse_date_str(date_str):
        if not date_str:
            return None
        s = date_str.strip()
        formats = [
            '%Y-%m-%d', '%B %d, %Y', '%b %d, %Y',
            '%d %B %Y', '%d %b %Y', '%B %Y', '%b %Y',
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(s[:20], fmt)
                return dt.replace(tzinfo=timezone.utc)
            except:
                continue
        if any(word in s.lower() for word in ['late', 'early', 'mid', 'recent']):
            return None
        return None

    def is_too_old(date_str):
        dt = parse_date_str(date_str)
        if dt is None:
            return True
        # Month-only date (day=1, no day digit in string): accept only current month
        if dt.day == 1 and not re.search(r'\b\d{1,2}[,\s]', date_str.strip()):
            return not (dt.year == today.year and dt.month == today.month)
        return dt < cutoff_date

    blocks = re.split(r'\n(?=\d+[\.\)]\s|\-\s*SOURCE:)', raw)
    if len(blocks) <= 1:
        blocks = raw.split('\n\n')

    posts = []
    seen_titles = []

    for block in blocks:
        if not block.strip():
            continue

        source_m = re.search(r'SOURCE:\s*(.+?)(?:\n|$)', block, re.IGNORECASE)
        title_m  = re.search(r'TITLE:\s*(.+?)(?:\n|$)', block, re.IGNORECASE)
        url_m    = re.search(r'URL:\s*(https?://\S+)', block, re.IGNORECASE)
        date_m   = re.search(r'DATE:\s*(.+?)(?:\n|$)', block, re.IGNORECASE)
        why_m    = re.search(r'WHY:\s*(.+?)(?:\n|$)', block, re.IGNORECASE)

        if not title_m:
            lines = [l.strip() for l in block.strip().split('\n')
                     if l.strip() and not l.strip().startswith(('SOURCE:', 'URL:', 'DATE:', 'WHY:', '-'))]
            if lines:
                candidate = re.sub(r'^\d+[\.\)]\s*', '', lines[0]).strip()
                if candidate:
                    class _M:
                        def __init__(self, v): self._v = v
                        def group(self, x): return self._v
                    title_m = _M(candidate)

        if not title_m:
            continue

        raw_title = clean_text(title_m.group(1).strip())

        if is_junk(raw_title):
            continue

        date_str = date_m.group(1).strip() if date_m else ''
        if date_str and is_too_old(date_str):
            logger.debug(f"xfeed: skipping old article: {date_str} | {raw_title[:40]}")
            continue

        if source_m:
            src_candidate = source_m.group(1).strip()
            if src_candidate.lower() not in ('ai lab', 'unknown', '', 'various', 'multiple'):
                source = src_candidate
            else:
                source = None
        else:
            source = None

        if not source:
            for lab in known_labs:
                if lab.lower() in raw_title.lower():
                    source = lab
                    break
            if not source:
                source = "AI Research"

        clean_title = re.sub(
            r'^' + re.escape(source) + r'\s*[-:–]\s*',
            '', raw_title, flags=re.IGNORECASE
        ).strip()
        title = clean_title if len(clean_title) > 10 else raw_title

        if is_junk(title):
            continue

        title_lower = title.lower()
        is_dup = False
        for seen in seen_titles:
            words_new  = set(title_lower.split())
            words_seen = set(seen.split())
            if words_new and words_seen:
                overlap = len(words_new & words_seen) / max(len(words_new), len(words_seen))
                if overlap > 0.55:
                    is_dup = True
                    break
        if is_dup:
            continue

        seen_titles.append(title_lower)

        url     = url_m.group(1).strip() if url_m else ""
        summary = clean_text(why_m.group(1).strip())[:250] if why_m else ""
        pub_date = today.strftime("%Y-%m-%d") if not date_str else (
            date_str[:10] if len(date_str) >= 10 else today.strftime("%Y-%m-%d")
        )

        posts.append({
            "title":     title[:200],
            "summary":   summary,
            "url":       url,
            "source":    source,
            "published": pub_date,
        })

    return posts[:10]
