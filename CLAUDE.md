# Company Prospector — Project Context for Claude

## What this project does
Daily B2B SaaS prospecting agent that:
1. Finds companies with hiring signals (AE spike, SDR spike, funding, CRO hire)
2. Identifies key contacts at those companies
3. Drafts personalized outreach emails
4. Outputs results to `results/outreach.csv`
5. Pushes results to GitHub → triggers Railway dashboard redeploy

## Stack
- **Agent**: Python (`main.py`) — runs daily via Railway cron at 3pm UTC (8am PT)
- **Dashboard**: Flask (`app.py`) + Jinja2 templates — deployed on Railway as web service
- **Data sources**: Serper.dev (web search), Greenhouse/Lever APIs (job boards)
- **Notifications**: Telegram

## Railway setup
- **Project**: diligent-vitality / production
- **Web service**: Flask dashboard (`gunicorn app:app`) — always on
- **Cron service**: `company-prospector` — runs `python3 main.py` at `0 15 * * *` (8am PT)
- **GitHub repo**: github.com/rabimoses/company-prospector (private)

## Environment variables (set on Railway cron service)
- `ANTHROPIC_API_KEY`
- `SERPER_API_KEY`
- `GH_TOKEN` — for pushing results back to GitHub after each run
- `GIT_USER_NAME`, `GIT_USER_EMAIL`
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

## Key files
- `main.py` — orchestrator: find companies → find contacts → draft emails → save CSV → git push
- `discovery.py` — finds companies via Serper (funding/CRO) + Greenhouse/Lever (AE/SDR spikes)
- `ae_sdr_boards.py` — scans job boards for hiring spikes
- `contacts.py` — finds contacts at companies
- `email_draft.py` — drafts personalized outreach emails
- `config.py` — API keys loaded from env vars
- `settings_manager.py` — reads/writes `settings.json` (user-configurable thresholds)
- `utils.py` — seen companies (90-day rolling window), logging, Telegram
- `app.py` — Flask dashboard + `/settings` GET/POST routes
- `templates/index.html` — main dashboard (company cards with signal badges)
- `templates/settings.html` — settings UI
- `results/outreach.csv` — flat CSV, one row per contact
- `seen_companies.txt` — rolling 90-day dedup list, format: `CompanyName|YYYY-MM-DD`

## Paths
All paths are relative to `Path(__file__).parent` — works on both Mac and Railway.

## Settings (configurable via /settings UI)
- Signal types to enable: ae_spike, sdr_spike, funding, cro_hire
- AE/SDR spike thresholds: min absolute roles, growth %, recent window days
- Company size filter: max total open roles (min auto-derived)
- Company blocklist: companies to always exclude
- Sender name/title, contact titles, max contacts per company

## What's done
- [x] Flask dashboard with company cards, signal badges, date selector, filter by signal type
- [x] Settings page (/settings) — all thresholds configurable via UI
- [x] Company blocklist (replaces watchlist)
- [x] 90-day rolling seen companies window
- [x] Auto git push after each agent run
- [x] Deployed on Railway (web + cron)
- [x] API keys moved to env vars (out of config.py)

## What's next
- [ ] Fix Railway deployment crash (investigate logs)
- [ ] Gmail one-click send from dashboard (SMTP with app password, env vars: GMAIL_USER, GMAIL_APP_PASSWORD)
- [ ] UI redesign: company list view first → click into company → see contacts + outreach email
- [ ] Contact discovery fix — currently most return "Contact not found"
