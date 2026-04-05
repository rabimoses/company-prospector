# Integration Guide: Prospector + OpenClaw

## Problem

The prospector runs as a standalone Python script via LaunchAgent. It can't directly call OpenClaw tools, but it needs web search to discover companies.

## Solutions

### Solution 1: OpenClaw Gateway Integration (Recommended)

The prospector can call the OpenClaw Gateway API to use your web_search tool.

#### Setup

1. Get your Gateway URL and token:
```bash
# From your OpenClaw setup
echo $OPENCLAW_GATEWAY_URL
echo $OPENCLAW_GATEWAY_TOKEN
```

2. Export them as environment variables:
```bash
# Add to ~/.zprofile or ~/.bash_profile
export OPENCLAW_GATEWAY_URL="http://localhost:8765"
export OPENCLAW_GATEWAY_TOKEN="your_token_here"
```

3. Update `discovery.py` to use the gateway:

```python
import os
import requests

def web_search(query: str, count: int = 3) -> List[Dict]:
    """Search using OpenClaw Gateway."""
    gateway_url = os.getenv("OPENCLAW_GATEWAY_URL")
    gateway_token = os.getenv("OPENCLAW_GATEWAY_TOKEN")
    
    if not gateway_url or not gateway_token:
        log_error("Gateway not configured. Set OPENCLAW_GATEWAY_URL and OPENCLAW_GATEWAY_TOKEN")
        return []
    
    url = f"{gateway_url}/api/search"
    headers = {"Authorization": f"Bearer {gateway_token}"}
    payload = {"query": query, "count": count}
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()["results"]
        else:
            log_error(f"Gateway error: {response.status_code}")
            return []
    except Exception as e:
        log_error(f"Gateway request failed: {e}")
        return []
```

### Solution 2: Brave Search API

Use Brave Search for real-time web results.

#### Setup

1. Get a Brave Search API key:
   - Go to https://api.search.brave.com
   - Create account, get API key

2. Export it:
```bash
export BRAVE_SEARCH_API_KEY="your_api_key"
```

3. Install Brave Search Python client:
```bash
pip3 install braveapi
```

4. Update `discovery.py`:

```python
import os
from braveapi import Brave

def web_search(query: str, count: int = 3) -> List[Dict]:
    """Search using Brave Search API."""
    api_key = os.getenv("BRAVE_SEARCH_API_KEY")
    if not api_key:
        log_error("BRAVE_SEARCH_API_KEY not set")
        return []
    
    try:
        brave = Brave(api_key)
        response = brave.search(q=query, count=count)
        
        results = []
        for result in response.get("web", {}).get("results", []):
            results.append({
                "title": result.get("title"),
                "url": result.get("url"),
                "snippet": result.get("snippet"),
            })
        return results
    except Exception as e:
        log_error(f"Brave search failed: {e}")
        return []
```

### Solution 3: Manual Input + CSV

Don't use automated search — provide a CSV of pre-screened companies.

Create `~/company_prospector/companies_to_prospect.csv`:
```csv
name,website,signal,signal_detail
Databricks,databricks.com,cro_hire,Hired new CRO Sarah Jones in Feb 2026
Notion,notion.so,funding,Raised $50M Series D in Jan 2026
```

Then update `main.py` to load from CSV instead of discovery.py.

## Testing Without Search API

Use the provided test mode:

```bash
# Run with mock data to test the full pipeline
python3 main.py --test
```

This will:
- Create mock companies
- Find mock contacts
- Draft sample emails
- Save everything to results/

Useful for verifying the system works before enabling live search.

## Which Solution?

| Option | Pros | Cons |
|--------|------|------|
| **Gateway** | Uses existing OpenClaw setup | Requires Gateway running |
| **Brave** | Simple, reliable, real-time | Costs $$$, needs API key |
| **Manual CSV** | No cost, full control | Not automated, slower |
| **Test Mode** | Free, no setup | Mock data only |

**Recommendation:** Start with **Solution 3 (manual CSV)** to get the system working end-to-end, then add automated search once you've verified the process works.

## Telegram Notification Setup

The prospector sends summaries via Telegram. Your credentials are already configured:

```bash
# Should already be set from job_monitor
echo $TELEGRAM_BOT_TOKEN
echo $TELEGRAM_CHAT_ID
```

If not set:
```bash
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"
```

Get these from:
- Bot: BotFather on Telegram (@BotFather) → /newbot
- Chat ID: Send message to bot, then: `curl https://api.telegram.org/bot<TOKEN>/getUpdates`

## Debugging

Check logs after each run:
```bash
tail -100 ~/.prospector_logs/output.log
tail -100 ~/.prospector_logs/error.log
```

Test Telegram manually:
```bash
python3 -c "from utils import send_telegram_notification; send_telegram_notification('Test message')"
```

Test search integration:
```python
python3 << 'PYTHON'
from discovery import web_search
results = web_search("B2B SaaS Series C funding 2026")
print(f"Found {len(results)} results")
for r in results[:3]:
    print(f"  {r.get('title')}")
PYTHON
```

## Next: Make It Work

1. Pick a solution above (recommend: **Manual CSV**)
2. Implement the integration
3. Run `python3 main.py`
4. Check results in `~/company_prospector/results/`
5. Enable LaunchAgent once verified: `launchctl load ~/Library/LaunchAgents/com.prospector.daily.plist`

Questions? Check the logs.
