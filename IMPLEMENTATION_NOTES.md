# Implementation Notes

## Status: Framework Complete, Web Integration Pending

The prospecting agent framework is built and ready. The following components need real web search and contact discovery integration:

## Integration Checklist

### 1. Web Search for Company Discovery (`discovery.py`)

**What's needed:**
- Real web search results for funding announcements
- TechCrunch, CrunchBase parsing
- News aggregation for CRO hires
- LinkedIn growth tracking

**How to implement:**
1. Use OpenClaw's `web_search` tool to find companies
2. Parse results for signals (funding amount, round type, CRO name, headcount)
3. Extract company name, website, and signal details

**Example queries:**
```
"B2B SaaS Series B funding 2026"
"B2B SaaS Series C funding 2026"
site:techcrunch.com "raises" "SaaS" 2026
```

### 2. Contact Discovery (`contacts.py`)

**What's needed:**
- LinkedIn search for specific titles at each company
- Company website scraping for contact pages
- Email address verification or guessing

**How to implement:**
1. Search LinkedIn for "[company] CRO site:linkedin.com"
2. Parse LinkedIn profile URLs and names
3. Try to find email on company website (contact page, team page)
4. Guess email format (firstname@domain, firstname.lastname@domain)
5. Optionally verify with Hunter.io or similar

**Example searches:**
```
"[company] CRO site:linkedin.com"
"[company] CMO"
"[company] VP Marketing"
```

### 3. Email Draft Template Refinement

**Status:** ✅ Complete and ready to test

Current templates:
- Funding signal → "Congrats on the [amount] [round]"
- CRO hire → "Welcome to [company], [name]"
- Headcount growth → "Impressive scaling"

**To refine:**
1. Test with real contacts
2. Track open rates and reply rates
3. Adjust tone/length based on feedback
4. A/B test different subject lines

## Architecture

### Data Flow
```
Web Search → Company Discovery → Contact Finding → Email Drafting → Results
    ↓             ↓                   ↓                 ↓            ↓
SEARCH_QUERIES  COMPANY DATA    CONTACTS LIST    EMAIL OBJECT    FILE + TELEGRAM
```

### Deduplication
- `seen_companies.txt` prevents re-processing the same companies
- Checked before contact discovery
- Updated after successful email drafting

### Logging
- `~/.prospector_logs/output.log` — all run details
- `~/.prospector_logs/error.log` — errors and warnings
- Appended to on each run

## Testing Strategy

1. **Mock run** — Test with hard-coded companies and contacts
2. **Limited search** — Run discovery with 1–2 queries, verify results
3. **Full run** — Run with all queries, capture results
4. **Email verification** — Check email format and content
5. **Production** — Deploy LaunchAgent and monitor daily runs

## Performance Considerations

- **Rate limiting:** 2-second delays between company processing (respect crawlers)
- **Search results:** Limited to 5 per query to reduce noise
- **Contacts per company:** Max 5 to focus on key decision-makers
- **Timeout:** 10 seconds for web requests

## Dependencies

```
requests>=2.31.0          # Web requests
beautifulsoup4>=4.12.0    # HTML parsing
```

## Future Enhancements

1. **CRM Integration** — Save contacts to Salesforce/HubSpot
2. **Email Tracking** — Track opens/clicks via Mixpanel
3. **Response Handling** — Auto-follow-up based on replies
4. **Personalization** — Add company-specific data (funding amount, growth metrics)
5. **Scoring** — Rank companies by likelihood-to-convert
6. **Analytics** — Dashboard of run metrics, reply rates, etc.

## Troubleshooting

**No companies found:**
- Check search queries in config.py
- Verify web connectivity
- Review error.log for API failures

**No contacts found:**
- LinkedIn search may be rate-limited
- Try company website scraping
- Email guessing is fallback

**Telegram not working:**
- Check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars
- Verify bot has access to chat
- Review error.log for API errors

**LaunchAgent not running:**
- Check plist is loaded: `launchctl list | grep prospector`
- Check logs: `tail ~/.prospector_logs/output.log`
- Verify Python path: `which python3`
