"""Isolated Tavily web-search tool with bounded, safe failure behavior."""

import logging
import os
from pathlib import Path
import time
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


logger = logging.getLogger(__name__)


class WebSearchError(RuntimeError):
    pass


def _result(item: dict, rank: int) -> dict:
    url = item.get("url", "")
    return {
        "title": item.get("title", ""),
        "url": url,
        "snippet": item.get("content", "")[:1000],
        "content": item.get("content", "")[:2000],
        "source": url.split("/")[2] if "://" in url else "unknown",
        "published_date": item.get("published_date"),
        "rank": rank,
        "relevance": item.get("score"),
        "search_timestamp": datetime.now(timezone.utc).isoformat(),
    }


def web_search(query: str, max_results: int | None = None) -> dict:
    """Search Tavily without exposing credentials or trusting page instructions."""
    started = time.perf_counter()
    api_key = os.getenv("WEB_SEARCH_API_KEY", "").strip()
    provider = os.getenv("WEB_SEARCH_PROVIDER", "tavily").lower()
    limit = min(max(int(max_results or os.getenv("WEB_SEARCH_MAX_RESULTS", "5")), 1), 10)

    if not api_key:
        return {
            "ok": False,
            "provider": provider,
            "error": "Web search is not configured. Set WEB_SEARCH_API_KEY to enable it.",
            "results": [],
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    if provider != "tavily":
        return {"ok": False, "provider": provider, "error": f"Unsupported web search provider: {provider}.", "results": []}

    payload = {
        "api_key": api_key,
        "query": query[:500],
        "search_depth": os.getenv("WEB_SEARCH_DEPTH", "basic"),
        "max_results": limit,
        "include_answer": False,
        "include_raw_content": False,
    }
    retries = min(max(int(os.getenv("WEB_SEARCH_RETRIES", "1")), 0), 3)
    last_error = None
    for attempt in range(retries + 1):
        try:
            with httpx.Client(timeout=float(os.getenv("WEB_SEARCH_TIMEOUT_SECONDS", "8"))) as client:
                response = client.post("https://api.tavily.com/search", json=payload)
            if response.status_code == 429:
                raise WebSearchError("Web search rate limit reached.")
            response.raise_for_status()
            data = response.json()
            results = [_result(item, index) for index, item in enumerate(data.get("results", [])[:limit], start=1)]
            return {
                "ok": True,
                "provider": provider,
                "results": results,
                "error": None if results else "No web results found.",
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            }
        except (httpx.TimeoutException, httpx.HTTPError, WebSearchError, ValueError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(0.2 * (attempt + 1))
                continue
            logger.warning("Web search failed provider=%s reason=%s", provider, type(exc).__name__)

    return {
        "ok": False,
        "provider": provider,
        "error": str(last_error),
        "results": [],
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def format_web_context(results: list[dict]) -> str:
    if not results:
        return "No external web evidence was available."
    return "\n\n".join(
        f"[Web source {item['rank']} | {item['source']} | {item.get('published_date') or 'date unavailable'}]\n"
        f"Title: {item['title']}\nURL: {item['url']}\nContent: {item['content']}"
        for item in results
    )