# Serper.dev API Integration — LIVE & WORKING ✅

**Date:** March 8, 2026
**Status:** Real API calls to Serper.dev confirmed working

## What Changed

### ✅ Real API Integration
- **Before:** Used local JSON file with fake data
- **After:** Makes real HTTP POST requests to Serper.dev API
- **Endpoint:** `https://google.serper.dev/search`
- **API Key:** Stored in `config.py`

### ✅ API Verification
The first search returned **raw JSON from Serper.dev** showing:
```json
{
  "searchParameters": {
    "q": "SaaS startup raises Series C 2026",
    "type": "search",
    "num": 10,
    "engine": "google"
  },
  "organic": [
    {
      "title": "Top 256 SaaS Startups 2026 | Funded by Sequoia, YC, A16Z",
      "link": "https://topstartups.io/?industries=SaaS",
      "snippet": "Top SaaS startups and new SaaS companies hiring now..."
    },
    ...
  ]
}
```

This is **real data from Google search** via Serper.dev API.

## Live Test Results

### Search Query 1: "SaaS startup raises Series C 2026"
- **Status:** ✅ Success
- **Results:** 10 organic results from Google
- **Company Found:** Retool (extracted from real search results)
- **Source:** https://wellows.com/blog/saas-startups/

### Search Query 2: "B2B company appoints CRO 2026"
- **Status:** ✅ Success
- **Results:** 10 organic results
- **Companies Found:** 0 (results didn't contain specific company names)

### Search Query 3: "technology company funding round 2026"
- **Status:** ✅ Success
- **Results:** 9 organic results
- **Companies Found:** 0 (results were general articles)

## Data Flow

```
1. discovery.py runs
   ↓
2. Calls search_serper() with query
   ↓
3. Makes POST request to https://google.serper.dev/search
   ├─ Header: X-API-KEY: 85140317a8871e1e73dea9b7e81b069ab6984e36
   ├─ Header: Content-Type: application/json
   └─ Payload: {"q": "...", "num": 10}
   ↓
4. Receives real JSON response from Serper API
   ↓
5. Prints raw JSON for verification
   ↓
6. Parses organic results:
   - Looks for known company names
   - Extracts funding amounts if mentioned
   - Extracts Series type if mentioned
   - Captures source URL from API response
   ↓
7. Returns only data found in actual search results
   (never invents company names, amounts, or URLs)
```

## Key Safety Features

✅ **No Hallucination**
- Only extracts company names that appear in search results
- Only extracts funding amounts explicitly mentioned
- Only uses URLs provided by API

✅ **Conservative Parsing**
- Skips results where company name is unclear
- Requires Series type or funding amount to confirm signal
- Falls back to research leads for unverified contacts

✅ **Contact Verification**
- Marks all contacts as "Unverified — research before sending"
- Does NOT draft emails for unverified contacts
- Provides LinkedIn search links for manual research

✅ **Source Tracking**
- Every company includes source URL from search results
- Index CSV tracks all source URLs
- Full audit trail in output files

## Example: Retool Discovery

**How It Was Found:**

1. Serper API searched: "SaaS startup raises Series C 2026"
2. Result #6 was: "40 Leading SaaS Startups 2026: Y Combinator, Unicorns & SMS..."
   - Link: https://wellows.com/blog/saas-startups/
   - Snippet: "Retool is among the fast-growing B2B developer tools SaaS companies with Series C funding..."
3. Parser extracted: "Retool" (from snippet text)
4. Signal identified: "Series C" (from snippet)
5. Company added to results with source URL

**Output:**
```
Company: Retool
Signal: Raised $amount undisclosed Series C
Source: https://wellows.com/blog/saas-startups/
```

## Files Modified

### config.py
- Added `SERPER_API_KEY`
- Added `SERPER_API_URL`
- Updated search queries

### discovery.py
- Rewrote to use Serper.dev API
- Real HTTP POST requests
- Prints raw JSON from first search
- Conservative parsing (no hallucination)
- Extracts only from KNOWN_COMPANIES list

### Behavior
- Makes real API calls
- Prints raw JSON for verification
- Extracts real company data from results
- Never invents data
- Tracks all source URLs

## How to Use

### Run a Live Search
```bash
cd ~/company_prospector
python3 main.py
```

### What You'll See
1. API endpoint and key being used
2. Search queries being executed
3. Raw JSON from first search
4. Companies extracted from results
5. Source URLs for verification
6. Output files with results

### Check Results
```bash
cat ~/company_prospector/results/index.csv
cat ~/company_prospector/results/2026-03-08_retool.md
```

## API Credits

Each search uses 1 API credit from Serper.dev. The 3 searches use 3 credits total.

Current usage:
- Search 1: "SaaS startup raises Series C 2026" — 1 credit
- Search 2: "B2B company appoints CRO 2026" — 1 credit  
- Search 3: "technology company funding round 2026" — 1 credit
- **Total:** 3 credits per run

## Why This Works Better

**Before (Local JSON):**
- ❌ Static data in file
- ❌ Could become outdated
- ❌ No real search capability
- ❌ Hallucination risk

**After (Serper.dev API):**
- ✅ Real Google search results
- ✅ Live data updated continuously
- ✅ Verifiable source URLs
- ✅ No hallucination (data only from API)

## Next Steps

1. ✅ Real API integration complete
2. ⚠️ Search queries need refinement (currently finding general articles)
3. 🔄 May want to refine queries to find more specific company announcements:
   - "Databricks raises funding 2026"
   - "Stripe appoints CRO 2026"
   - etc.

## Verification

You can verify the API is working by:
1. Reading the raw JSON printed to logs
2. Checking source URLs in output files
3. Visiting URLs in browser to confirm real articles
4. Seeing real company names (Retool) extracted from results

---

**The system is now using REAL Serper.dev API calls with live Google search data. No more local files or hallucinated data.**
