"""
News fetcher: combines RSS feeds (free, unlimited) with NewsAPI (free tier).
Returns a list of article dicts: {title, summary, source, url}
"""
import httpx
import feedparser
from config.settings import NEWS_API_KEY

# Free RSS feeds — no API key needed
RSS_FEEDS = {
    "ai_tech": [
        "https://techcrunch.com/feed/",
        "https://feeds.feedburner.com/venturebeat/SZYF",  # VentureBeat AI
        "https://www.wired.com/feed/rss",
    ],
    "finance": [
        "https://feeds.content.dowjones.io/public/rss/mw_topstories",  # MarketWatch
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",       # CNBC Top News
        "https://finance.yahoo.com/news/rssindex",
    ],
    "business": [
        "https://feeds.bloomberg.com/markets/news.rss",
        "https://www.ft.com/rss/home",
    ],
}

MAX_PER_FEED = 3
MAX_SUMMARY_WORDS = 80


def _truncate(text: str, max_words: int = MAX_SUMMARY_WORDS) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "..."


def fetch_rss(category: str) -> list[dict]:
    articles = []
    feeds = RSS_FEEDS.get(category, [])
    for feed_url in feeds:
        try:
            parsed = feedparser.parse(feed_url)
            for entry in parsed.entries[:MAX_PER_FEED]:
                summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
                articles.append({
                    "title": entry.get("title", ""),
                    "summary": _truncate(summary),
                    "source": parsed.feed.get("title", feed_url),
                    "url": entry.get("link", ""),
                })
        except Exception:
            continue
    return articles


def fetch_newsapi(query: str, page_size: int = 10) -> list[dict]:
    """Fetch from NewsAPI free tier. Falls back gracefully if key missing."""
    if not NEWS_API_KEY:
        return []
    try:
        resp = httpx.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": query,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": page_size,
                "apiKey": NEWS_API_KEY,
            },
            timeout=10,
        )
        data = resp.json()
        articles = []
        for a in data.get("articles", []):
            articles.append({
                "title": a.get("title", ""),
                "summary": _truncate(a.get("description") or a.get("content") or ""),
                "source": a.get("source", {}).get("name", ""),
                "url": a.get("url", ""),
            })
        return articles
    except Exception:
        return []


def fetch_daily_news() -> list[dict]:
    """
    Main entry point: fetch all relevant news for the daily brief.
    Returns combined list (RSS + NewsAPI), deduped by title.
    """
    articles = []
    articles += fetch_rss("ai_tech")
    articles += fetch_rss("finance")
    articles += fetch_rss("business")
    articles += fetch_newsapi("AI artificial intelligence OR stock market OR startup", page_size=8)

    # Dedupe by title (case-insensitive)
    seen = set()
    unique = []
    for a in articles:
        key = a["title"].lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(a)

    return unique[:30]  # Cap at 30 articles to keep Claude input manageable


def format_articles_for_claude(articles: list[dict]) -> str:
    lines = []
    for i, a in enumerate(articles, 1):
        lines.append(f"{i}. [{a['source']}] {a['title']}\n   {a['summary']}")
    return "\n\n".join(lines)
