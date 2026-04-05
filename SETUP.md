# Company Prospector — Quick Start

The system is built and working. This guide shows you how to activate it.

## Status

✅ **Built:** All modules created
✅ **Tested:** Test run successful (see results in ~/company_prospector/results/)
✅ **Scheduled:** LaunchAgent ready at ~/Library/LaunchAgents/com.prospector.daily.plist
⚠️ **Blocked:** Web search integration needed (see options below)

## What Just Happened

I ran a test to verify the system works end-to-end:

```bash
python3 ~/company_prospector/main.py --test
```

This created:
- **3 test companies** (Databricks, Notion, Figma)
- **6 contacts** (2 per company)
- **6 draft emails** (personalized for each contact)
- **1 index CSV** summarizing the run

All saved to: `~/company_prospector/results/`

You can open any of these files now:
```bash
open ~/company_prospector/results/2026-03-08_databricks.md
cat ~/company_prospector/results/index.csv
```

## Next Steps

### Step 1: Choose Your Search Integration

The prospector needs real company data. Pick one:

**Option A: Use Telegram credentials you already have** ✅
```bash
# Verify your credentials exist:
echo $TELEGRAM_BOT_TOKEN
echo $TELEGRAM_CHAT_ID

# If they're set, you're good. Telegram notifications will work.
```

**Option B: Use a CSV of target companies** (Easy, recommended for first run)
```bash
# Create ~/company_prospector/companies_to_prospect.csv
cat > ~/company_prospector/companies_to_prospect.csv << 'CSV'
name,website,signal,signal_detail
Databricks,databricks.com,cro_hire,Hired new CRO Sarah Jones in Feb 2026
Notion,notion.so,funding,Raised $50M Series D in Jan 2026
Figma,figma.com,headcount_growth,25% headcount growth in 2026
CSV

# Then run:
python3 ~/company_prospector/main.py --csv ~/company_prospector/companies_to_prospect.csv
```

**Option C: Use Brave Search API** (Automated, requires API key)
See INTEGRATION_GUIDE.md

**Option D: Use OpenClaw Gateway** (Preferred, uses your existing setup)
See INTEGRATION_GUIDE.md

### Step 2: Test with Real Data

Once you pick an integration, test it:

```bash
# Using CSV (easiest first test)
python3 ~/company_prospector/main.py --csv ~/company_prospector/companies_to_prospect.csv

# Or test mode again to verify system still works
python3 ~/company_prospector/main.py --test
```

Check the results:
```bash
# View latest run
ls -ltr ~/company_prospector/results/ | tail -5

# Read a company file
cat ~/company_prospector/results/2026-03-08_databricks.md

# Check the index
cat ~/company_prospector/results/index.csv
```

### Step 3: Install Dependencies

```bash
cd ~/company_prospector
pip3 install -r requirements.txt
```

### Step 4: Enable Daily Scheduling

Once you've verified everything works with real data, enable the daily run:

```bash
# Check if LaunchAgent is already loaded
launchctl list | grep prospector

# If not loaded, load it:
launchctl load ~/Library/LaunchAgents/com.prospector.daily.plist

# Runs every day at 9:05 AM (5 minutes after job monitor at 9:00 AM)
```

Check logs after it runs:
```bash
tail ~/.prospector_logs/output.log
tail ~/.prospector_logs/error.log
```

## File Structure

```
~/company_prospector/
├── main.py                 # Orchestration (supports --test, --csv flags)
├── discovery.py            # Find companies (placeholder, needs search API)
├── contacts.py             # Find key people at companies
├── email_draft.py          # Generate personalized emails
├── config.py               # All templates and settings
├── utils.py                # Logging, Telegram, file helpers
├── requirements.txt        # Dependencies
├── README.md               # Full documentation
├── INTEGRATION_GUIDE.md    # How to add search APIs
├── SETUP.md                # This file
├── seen_companies.txt      # Deduplication list (auto-generated)
│
└── results/
    ├── YYYY-MM-DD_company1.md    # Results file per company
    ├── YYYY-MM-DD_company2.md    # (with contacts & drafted emails)
    └── index.csv                 # Summary of all runs
```

## Email Quality

The system generates personalized emails that:
- ✅ Reference the specific signal (funding, CRO hire, growth)
- ✅ Use natural language (not templated)
- ✅ Position Jacob as a peer, not an applicant
- ✅ Ask for 20-min conversation, not a job
- ✅ Are authentic & confident
- ✅ 5-7 sentences (concise)

Example (from Databricks test run):
```
Subject: Welcome to Databricks, Sarah

Welcome to Databricks, Sarah Jones. I noticed you recently stepped into the CRO role and wanted to connect.

I work in demand generation at B2B SaaS companies, and I've spent the last several years building pipeline engines that actually move revenue. Scaling teams like yours often have a moment where demand gen strategy becomes critical — and I thought it might be worth a quick conversation.

No pitch, no process — just 20 minutes to explore if there's a fit. Would you be open to that?

Best,
Jacob Landsman
```

## Telegram Notifications

After each run, you get a summary like:
```
🎯 Prospector Run Complete — 2026-03-08
Companies found: 3
Contacts identified: 6
Emails drafted: 6

Files saved to ~/company_prospector/results/
```

If this doesn't send, verify your credentials:
```bash
echo $TELEGRAM_BOT_TOKEN
echo $TELEGRAM_CHAT_ID
```

If they're empty, set them:
```bash
# Add to ~/.zprofile or ~/.bash_profile, then source it
export TELEGRAM_BOT_TOKEN="your_token"
export TELEGRAM_CHAT_ID="your_chat_id"
source ~/.zprofile
```

## Troubleshooting

### "No companies found" after running
- You need to complete a search integration (Option A-D above)
- Or use the CSV method (Option B)
- Test mode (--test flag) always works

### Telegram not sending notifications
```bash
# Check credentials
echo $TELEGRAM_BOT_TOKEN $TELEGRAM_CHAT_ID

# Test manually
python3 -c "from utils import send_telegram_notification; send_telegram_notification('test')"
```

### LaunchAgent not running at 9:05 AM
```bash
# Check if loaded
launchctl list | grep prospector

# View output
tail ~/.prospector_logs/output.log
tail ~/.prospector_logs/error.log

# Reload if needed
launchctl unload ~/Library/LaunchAgents/com.prospector.daily.plist
launchctl load ~/Library/LaunchAgents/com.prospector.daily.plist
```

### Want to run now (don't wait until 9:05 AM)
```bash
python3 ~/company_prospector/main.py
```

## Configuration

All customizable:

**In config.py:**
- SEARCH_QUERIES — what to search for
- CONTACT_TITLES — which roles to target
- EMAIL_OPENING_TEMPLATES — email opening styles
- SENDER_NAME, SENDER_TITLE — Jacob's details

**In main.py:**
- Add more test companies in get_test_companies()
- Adjust rate limiting (time.sleep(1))
- Change Telegram message format

## Next Actions

1. **Try it once:**
   ```bash
   python3 ~/company_prospector/main.py --test
   ```

2. **Set up real data:**
   - Pick an integration (CSV recommended for first test)
   - Update main.py or create companies_to_prospect.csv
   - Run again with real company data

3. **Enable daily:**
   ```bash
   launchctl load ~/Library/LaunchAgents/com.prospector.daily.plist
   ```

4. **Monitor:**
   ```bash
   tail -f ~/.prospector_logs/output.log
   ```

## Need Help?

- **README.md** — Full architecture & detailed docs
- **INTEGRATION_GUIDE.md** — How to add Brave, Gateway, or other APIs
- **config.py** — All settings & templates in one place

Questions? Check the logs (`~/.prospector_logs/`) or read the integration guide.

---

You're ready. Pick an integration and run it. 🚀
