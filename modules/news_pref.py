"""News personalisation: track which sources/topics Joe likes or skips.
Weights are applied when ranking news articles."""

import json
import logging
import os

logger = logging.getLogger(__name__)
NEWS_PREFS_FILE = "data/news_prefs.json"


def _load() -> dict:
    try:
        with open(NEWS_PREFS_FILE) as f:
            return json.load(f)
    except Exception:
        return {"sources": {}, "topics": {}}


def _save(data: dict):
    tmp = NEWS_PREFS_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, NEWS_PREFS_FILE)
    except Exception as e:
        logger.error(f"[NewsPref] Save failed: {e}")


def update_source_pref(source: str, delta: float):
    """delta: +1.0 = like, -1.0 = dislike. Weight clamped 0.1–3.0."""
    data = _load()
    current = data["sources"].get(source, 1.0)
    data["sources"][source] = max(0.1, min(3.0, current + delta))
    _save(data)
    logger.info(f"[NewsPref] source={source} weight={data['sources'][source]:.1f}")


def update_topic_pref(topic: str, delta: float):
    data = _load()
    current = data["topics"].get(topic.lower(), 1.0)
    data["topics"][topic.lower()] = max(0.1, min(3.0, current + delta))
    _save(data)


def score_article(article: dict) -> float:
    """Return a preference score for an article (higher = more preferred)."""
    data = _load()
    score = 1.0
    source = (article.get("source_domain") or article.get("source", "")).lower()
    if source:
        score *= data["sources"].get(source, 1.0)
    title = (article.get("title", "") + " " + article.get("summary", "")).lower()
    for topic, weight in data["topics"].items():
        if topic in title:
            score *= weight
    return score


def rank_articles(articles: list) -> list:
    """Sort articles by preference score (highest first)."""
    return sorted(articles, key=score_article, reverse=True)


def get_prefs_summary() -> str:
    data = _load()
    lines = []
    liked_s = {s: w for s, w in data["sources"].items() if w > 1.2}
    disliked_s = {s: w for s, w in data["sources"].items() if w < 0.8}
    liked_t = {t: w for t, w in data["topics"].items() if w > 1.2}
    disliked_t = {t: w for t, w in data["topics"].items() if w < 0.8}
    if liked_s:
        lines.append("Preferred sources: " + ", ".join(liked_s))
    if disliked_s:
        lines.append("Skipped sources: " + ", ".join(disliked_s))
    if liked_t:
        lines.append("Preferred topics: " + ", ".join(liked_t))
    if disliked_t:
        lines.append("Less interested in: " + ", ".join(disliked_t))
    return "\n".join(lines) if lines else "No news preferences set yet."


def get_pref_context() -> str:
    """For injection into news fetch system prompts."""
    summary = get_prefs_summary()
    if summary == "No news preferences set yet.":
        return ""
    return f"NEWS PREFERENCES (apply when selecting articles):\n{summary}"
