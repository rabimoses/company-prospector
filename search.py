"""
Unified search utility — Tavily Search API backend.
Returns results in normalised format: {"organic": [{"title","link","snippet"}]}
"""

import os
import requests
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from utils import log_error

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
TAVILY_URL     = "https://api.tavily.com/search"


def web_search(query: str, num: int = 10,
               include_domains: list = None, days: int = None) -> dict:
    """Search the web and return {organic: [{title, link, snippet}]}.

    Args:
        query:          Search query. Do NOT include site: or after: operators —
                        use include_domains / days instead (Tavily native params).
        num:            Max results to return (up to 20).
        include_domains: Restrict results to these domains, e.g. ["techcrunch.com"]
        days:           Only return results from the last N days.
    """
    if not TAVILY_API_KEY:
        log_error("TAVILY_API_KEY not set")
        return {"organic": []}

    payload = {
        "api_key":      TAVILY_API_KEY,
        "query":        query,
        "num_results":  min(num, 20),
        "search_depth": "basic",
    }
    if include_domains:
        payload["include_domains"] = include_domains
    if days:
        payload["days"] = days

    try:
        r = requests.post(TAVILY_URL, json=payload, timeout=15)
        if not r.ok:
            log_error(f"Tavily search error: {r.status_code} — {r.text[:200]}")
            return {"organic": []}

        data = r.json()
        results = data.get("results", [])

        # Normalise to Serper-compatible format
        organic = [
            {
                "title":   item.get("title", ""),
                "link":    item.get("url", ""),
                "snippet": item.get("content", ""),
            }
            for item in results
        ]
        return {"organic": organic}

    except Exception as e:
        log_error(f"Tavily search error: {e}")
        return {"organic": []}
