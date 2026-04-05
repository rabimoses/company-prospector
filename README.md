# Company Prospector Agent

B2B SaaS prospecting agent for finding companies with growth signals (funding, new CRO, headcount growth) and drafting personalized outreach emails.

## Architecture

- **main.py** — Orchestration, saves results, sends Telegram notifications
- **discovery.py** — Finds companies with growth signals via web search
- **contacts.py** — Finds key contacts at each company
- **email_draft.py** — Generates personalized outreach emails
- **config.py** — Configuration and templates
- **utils.py** — Logging, Telegram, file management

## Setup

### 1. Install Dependencies

```bash
cd ~/company_prospector
pip3 install -r requirements.txt
```

### 2. Configure Web Search

The prospector needs web search to function. You have three options:

#### Option A: Brave Search API (Recommended)
```bash
export BRAVE_SEARCH_API_KEY="your_api_key_here"
```
Get a key at: https://api.search.brave.com

#### Option B: OpenClaw Integration (Preferred for this setup)
Create a wrapper that calls OpenClaw's web_search tool:
```bash
# Edit discovery.py to use the OpenClaw gateway
# See integration instructions below
```

#### Option C: Manual CSV
Provide ~/company_prospector/companies_to_prospect.csv with pre-found companies

### 3. Telegram Credentials

The prospector uses Telegram bot credentials already configured in ~/job_monitor/config.py

Set environment variables:
```bash
export TELEGRAM_BOT_TOKEN="your_token"
export TELEGRAM_CHAT_ID="your_chat_id"
```

### 4. Test Run

```bash
cd ~/company_prospector
python3 main.py
```

## OpenClaw Integration

To use OpenClaw's web_search and web_fetch tools, create a gateway wrapper:

```bash
# Install openclaw CLI (if not already done)
npm install -g openclaw

# Set gateway credentials
export OPENCLAW_GATEWAY_URL="http://localhost:8765"
export OPENCLAW_GATEWAY_TOKEN="your_token"

# Then update discovery.py to call the gateway API
```

## Daily Scheduling

The LaunchAgent is already set up at:
```
~/Library/LaunchAgents/com.prospector.daily.plist
```

Runs at **9:05 AM daily** (5 minutes after job monitor at 9:00 AM)

Check status:
```bash
launchctl list | grep prospector
```

View logs:
```bash
tail -f ~/.prospector_logs/output.log
tail -f ~/.prospector_logs/error.log
```

## Output Structure

Results saved to `~/company_prospector/results/`:

### Per-Company Files
```
results/2026-03-08_companyname.md
```

Contains:
- Signal type and details
- Contacts (name, title, LinkedIn, email)
- Drafted emails (subject + body)

### Index
```
results/index.csv
```

CSV summary of all processed companies

### Deduplication
```
~/company_prospector/seen_companies.txt
```

List of companies already processed (prevents duplicate emails)

## Email Quality Notes

The draft emails follow these rules:
- **Subject** references specific signal (e.g., "Congrats on Series C")
- **Opening** naturally mentions the trigger (not generic)
- **Body** positions Jacob as demand gen expert
- **Call-to-action** asks for 20-min conversation, not a job
- **Tone** peer-to-peer, confident, authentic
- **Length** 5-7 sentences max
- **Framing** offers expertise + wants to connect (not "I'm looking for work")

## Troubleshooting

### No companies found
- Check if search API is configured
- Try manual CSV input (Option C above)
- Verify search queries are returning results

### Telegram not sending
```bash
# Verify credentials are set
echo $TELEGRAM_BOT_TOKEN
echo $TELEGRAM_CHAT_ID

# Test send manually
python3 -c "from utils import send_telegram_notification; send_telegram_notification('Test')"
```

### LaunchAgent not running
```bash
# Check if loaded
launchctl list | grep prospector

# Reload if needed
launchctl unload ~/Library/LaunchAgents/com.prospector.daily.plist
launchctl load ~/Library/LaunchAgents/com.prospector.daily.plist

# Check logs
cat ~/.prospector_logs/error.log
```

## Next Steps

1. [ ] Configure web search API (Option A, B, or C)
2. [ ] Test with `python3 main.py`
3. [ ] Verify results in ~/company_prospector/results/
4. [ ] Check Telegram notifications work
5. [ ] Monitor LaunchAgent logs for first scheduled run

## Customization

All templates and signals are in `config.py` — easy to adjust:
- SEARCH_QUERIES — add/modify search terms
- CONTACT_TITLES — adjust who to look for
- EMAIL_OPENING_TEMPLATES — customize message styles
