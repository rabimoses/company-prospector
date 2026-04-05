"""Utility functions for prospector."""

import os
import sys
from pathlib import Path
from datetime import datetime
import requests
from typing import Set, Optional


SEEN_EXPIRY_DAYS = 90


def load_seen_companies() -> Set[str]:
    """Load seen companies, dropping entries older than SEEN_EXPIRY_DAYS."""
    from datetime import date, timedelta
    seen_file = Path.home() / "company_prospector" / "seen_companies.txt"

    if not seen_file.exists():
        return set()

    cutoff = date.today() - timedelta(days=SEEN_EXPIRY_DAYS)
    names = set()
    try:
        with open(seen_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if '|' in line:
                    name, date_str = line.rsplit('|', 1)
                    try:
                        seen_date = date.fromisoformat(date_str.strip())
                        if seen_date >= cutoff:
                            names.add(name.strip())
                    except ValueError:
                        names.add(name.strip())  # malformed date — keep it
                else:
                    # Legacy format (no date) — keep but will get a date on next save
                    names.add(line)
    except Exception as e:
        log_error(f"Error loading seen companies: {e}")
    return names


def save_seen_companies(companies: Set[str]) -> None:
    """Save seen companies with today's date, preserving existing dates."""
    from datetime import date, timedelta
    seen_file = Path.home() / "company_prospector" / "seen_companies.txt"
    cutoff = date.today() - timedelta(days=SEEN_EXPIRY_DAYS)
    today = date.today().isoformat()

    # Load existing dated entries
    existing: dict[str, str] = {}
    if seen_file.exists():
        try:
            with open(seen_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    if '|' in line:
                        name, date_str = line.rsplit('|', 1)
                        existing[name.strip()] = date_str.strip()
                    else:
                        existing[line] = today
        except Exception as e:
            log_error(f"Error reading seen companies for save: {e}")

    # Merge: new companies get today's date; existing keep their date
    for name in companies:
        if name not in existing:
            existing[name] = today

    # Write back, dropping expired entries
    try:
        with open(seen_file, 'w') as f:
            for name, date_str in sorted(existing.items()):
                try:
                    if date.fromisoformat(date_str) >= cutoff:
                        f.write(f"{name}|{date_str}\n")
                except ValueError:
                    f.write(f"{name}|{today}\n")
    except Exception as e:
        log_error(f"Error saving seen companies: {e}")


def send_telegram_notification(message: str) -> bool:
    """Send notification to Telegram."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        log_error("Telegram credentials not set (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)")
        return False
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": True
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            log_info("Telegram notification sent")
            return True
        else:
            log_error(f"Telegram API error: {response.status_code}")
            return False
    except Exception as e:
        log_error(f"Error sending Telegram notification: {e}")
        return False


def log_info(message: str) -> None:
    """Log info message."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")
    
    # Also write to log file
    try:
        log_file = Path.home() / ".prospector_logs" / "output.log"
        with open(log_file, 'a') as f:
            f.write(f"[{timestamp}] {message}\n")
    except:
        pass


def log_error(message: str) -> None:
    """Log error message."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] ERROR: {message}", file=sys.stderr)
    
    # Also write to error log file
    try:
        log_file = Path.home() / ".prospector_logs" / "error.log"
        with open(log_file, 'a') as f:
            f.write(f"[{timestamp}] ERROR: {message}\n")
    except:
        pass


def extract_domain_from_url(url: str) -> Optional[str]:
    """Extract domain from URL."""
    if not url:
        return None
    
    # Remove protocol
    if "://" in url:
        url = url.split("://")[1]
    
    # Remove path
    if "/" in url:
        url = url.split("/")[0]
    
    # Remove www
    if url.startswith("www."):
        url = url[4:]
    
    return url


def guess_email_format(company_domain: str, first_name: str, last_name: str) -> str:
    """Guess email format for a contact."""
    # Try common patterns
    candidates = [
        f"{first_name.lower()}@{company_domain}",
        f"{first_name.lower()}.{last_name.lower()}@{company_domain}",
        f"{first_name[0].lower()}{last_name.lower()}@{company_domain}",
    ]
    
    return candidates[0]  # Return first guess


def web_search_tool(query: str, count: int = 5) -> list:
    """
    Perform real web search using available search infrastructure.
    
    This is designed to be called from discovery.py and returns results
    in the format: [{"title": "...", "url": "...", "snippet": "..."}]
    
    In a sandboxed environment, this would call the OpenClaw web_search tool.
    Here we provide a fallback that can be integrated with:
    1. Brave Search API (via BRAVE_SEARCH_API_KEY env var)
    2. OpenClaw gateway (via OPENCLAW_GATEWAY_URL/TOKEN)
    3. Other search providers
    """
    import os
    
    # Try Brave Search API first
    brave_key = os.getenv("BRAVE_SEARCH_API_KEY")
    if brave_key:
        try:
            return _search_brave(query, count, brave_key)
        except Exception as e:
            log_error(f"Brave search failed: {e}")
    
    # Try OpenClaw Gateway
    gateway_url = os.getenv("OPENCLAW_GATEWAY_URL")
    gateway_token = os.getenv("OPENCLAW_GATEWAY_TOKEN")
    if gateway_url and gateway_token:
        try:
            return _search_gateway(query, count, gateway_url, gateway_token)
        except Exception as e:
            log_error(f"Gateway search failed: {e}")
    
    # Fallback: no search available
    log_error("No search API configured. Set BRAVE_SEARCH_API_KEY or OPENCLAW_GATEWAY_URL/TOKEN")
    return []


def _search_brave(query: str, count: int, api_key: str) -> list:
    """Search using Brave Search API."""
    import requests
    
    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {"Accept": "application/json", "X-Subscription-Token": api_key}
    params = {"q": query, "count": count, "freshness": "pw"}  # pw = past week
    
    response = requests.get(url, headers=headers, params=params, timeout=10)
    response.raise_for_status()
    
    data = response.json()
    results = []
    
    for item in data.get("web", {}).get("results", []):
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("description", ""),
        })
    
    return results


def _search_gateway(query: str, count: int, gateway_url: str, gateway_token: str) -> list:
    """Search using OpenClaw Gateway."""
    import requests
    
    url = f"{gateway_url}/api/search"
    headers = {"Authorization": f"Bearer {gateway_token}"}
    payload = {"query": query, "count": count}
    
    response = requests.post(url, json=payload, headers=headers, timeout=10)
    response.raise_for_status()
    
    data = response.json()
    return data.get("results", [])
