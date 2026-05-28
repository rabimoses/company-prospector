"""Discovery via Serper.dev API — real searches, no hallucination."""

import sys, json, re, requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Set

sys.path.insert(0, str(Path(__file__).parent))
from config import ANTHROPIC_API_KEY
from search import web_search
from utils import log_info, log_error
from ae_sdr_boards import detect_spikes

def get_search_queries():
    """Return list of (kind, query, include_domains, days) tuples for Tavily.
    Using press release domains for funding — BusinessWire/PRNewswire publish
    dated announcements that Tavily's recency filter works reliably on,
    unlike TechCrunch which returns old articles regardless of days= param."""
    pr_domains = ["businesswire.com", "prnewswire.com"]
    return [
        ("series_a", "raises Series A SaaS software",               pr_domains, 90),
        ("series_a", "raises Series A B2B software platform",       pr_domains, 90),
        ("series_a", "Series A funding round SaaS",                 pr_domains, 90),
        ("series_a", "closes Series A B2B software",                pr_domains, 90),
        ("funding",  "raises Series B SaaS software",               pr_domains, 90),
        ("funding", "raises Series C SaaS software",          pr_domains, 90),
        ("funding", "raises Series B B2B software platform",  pr_domains, 90),
        ("funding", "raises Series C B2B software platform",  pr_domains, 90),
        ("cro",     "appointed CRO OR Chief Revenue Officer SaaS", ["businesswire.com"], 60),
        ("cro",     "appoints Chief Revenue Officer",               ["prnewswire.com"],  60),
    ]

AE_SDR_QUERIES = [
    ("ae_spike",  '"account executive" "B2B SaaS" site:linkedin.com/jobs'),
    ("ae_spike",  '"account executive" site:greenhouse.io'),
    ("ae_spike",  '"account executive" site:lever.co'),
    ("ae_spike",  '"account executive" site:wellfound.com/jobs'),
    ("sdr_spike", '"sales development representative" site:greenhouse.io'),
    ("sdr_spike", '"sales development representative" site:lever.co'),
    ("sdr_spike", '"sales development representative" site:wellfound.com/jobs'),
]

AE_SPIKE_THRESHOLD  = 2
SDR_SPIKE_THRESHOLD = 2

# ─── money normaliser: "$55 million" → "$55M", "$2 billion" → "$2B" ──────────
def normalise_amount(raw: str) -> str:
    raw = raw.strip()
    m = re.match(r'\$?([\d\.]+)\s*(million|billion|[MBmb])', raw, re.I)
    if not m:
        return raw
    num  = m.group(1)
    unit = 'B' if m.group(2).lower().startswith('b') else 'M'
    return f"${num}{unit}"

# ─── helpers shared by both phases ────────────────────────────────────────────
def _settings():
    from settings_manager import get_settings
    return get_settings()

def _filter_and_dedupe(companies: List[Dict], blocklist: set) -> List[Dict]:
    """Keyword filter + Claude B2B SaaS confirmation + deduplication."""
    filtered = []
    for c in companies:
        if not is_likely_b2b_saas(c):
            log_info(f"  🚫 FILTERED (keyword, non-SaaS): {c['name']}")
            continue
        if c["name"].lower() in blocklist:
            log_info(f"  ⛔ BLOCKED: {c['name']}")
            continue
        filtered.append(c)
    filtered = claude_saas_filter(filtered)
    return dedupe(filtered)


# ─── Phase 1: fast web signals (funding / CRO hires) ─────────────────────────
def find_signal_companies(seen: Set[str], found: Set[str] = None) -> List[Dict]:
    """Search Tavily for funding rounds and CRO hires. Fast (~30s)."""
    s = _settings()
    signals_enabled = s["signals_enabled"]
    blocklist = {c.lower() for c in s.get("blocklist_companies", [])}
    if found is None:
        found = set()

    log_info("="*80)
    log_info("PHASE 1 — Web signals (funding / CRO hires)")
    log_info("="*80)

    companies = []
    for kind, query, domains, days in get_search_queries():
        log_info(f"\n{'─'*60}")
        log_info(f"QUERY: {query} | domains={domains} | last {days}d")
        log_info(f"{'─'*60}")

        data = serper_search(query, domains=domains, days=days)
        results = data.get("organic", [])
        log_info(f"  {len(results)} results\n")
        for i, r in enumerate(results, 1):
            print(f"  [{i}] {r.get('title','')}")
            print(f"      {r.get('snippet','')[:120]}")
            print(f"      {r.get('link','')}")
        print()
        log_info("PARSING:")

        signal_type = "series_a" if kind == "series_a" else ("funding" if kind == "funding" else "cro_hire")
        if signal_type not in signals_enabled:
            if not (signal_type == "series_a" and "funding" in signals_enabled):
                log_info(f"  ⏭ SKIPPED (disabled): {signal_type}")
                continue
        if kind == "series_a":
            batch = parse_funding(results, seen, found, force_signal="series_a")
        elif kind == "funding":
            batch = parse_funding(results, seen, found)
        else:
            batch = parse_cro(results, seen, found)
        companies.extend(batch)
        found.update(c["name"] for c in batch)

    companies = _filter_and_dedupe(companies, blocklist)
    log_info(f"\nPhase 1 complete — {len(companies)} signal companies")
    return companies


# ─── Phase 2: AE/SDR spike detection (slow board scan) ───────────────────────
def find_spike_companies(seen: Set[str], found: Set[str] = None) -> List[Dict]:
    """Scan Greenhouse + Lever boards for AE/SDR hiring spikes. Slow (~5 min)."""
    s = _settings()
    signals_enabled = s["signals_enabled"]
    blocklist = {c.lower() for c in s.get("blocklist_companies", [])}
    if found is None:
        found = set()

    if "ae_spike" not in signals_enabled and "sdr_spike" not in signals_enabled:
        log_info("  ⏭ SKIPPED AE/SDR spikes (disabled in settings)")
        return []

    log_info("="*80)
    log_info("PHASE 2 — AE/SDR hiring spikes (job board scan)")
    log_info("="*80)

    spike_batch = detect_spikes(seen, found)
    companies = _filter_and_dedupe(spike_batch, blocklist)
    log_info(f"\nPhase 2 complete — {len(companies)} spike companies")
    return companies


# ─── Legacy wrapper (kept for compatibility) ──────────────────────────────────
def find_companies(seen: Set[str]) -> List[Dict]:
    found: Set[str] = set()
    phase1 = find_signal_companies(seen, found)
    found.update(c["name"] for c in phase1)
    phase2 = find_spike_companies(seen, found)
    all_companies = dedupe(phase1 + phase2)
    log_info(f"\n{'='*80}")
    log_info(f"TOTAL: {len(all_companies)} companies found")
    log_info("="*80)
    return all_companies


# ─── search call ──────────────────────────────────────────────────────────────
def serper_search(query: str, domains: list = None, days: int = None) -> Dict:
    return web_search(query, num=10, include_domains=domains, days=days)


# ─── funding parser ───────────────────────────────────────────────────────────
# Patterns (case-insensitive):
#   [Company] raises/raised $XM/X million
#   [Company] announces $XM Series X
FUND_RE = re.compile(
    r'^([A-Z][A-Za-z0-9\s\.\-]+?)\s+'
    r'(?:raises|raised|announces|bags|secures|closes|lands|nabs)\s+'
    r'(\$[\d\.]+\s*(?:million|billion|[MB]))',
    re.IGNORECASE
)
SERIES_RE = re.compile(r'Series\s+([A-G][+]?)', re.IGNORECASE)

def is_recent_url(url, months=12):
    """Return True if URL date is within the last N months, or if no date found."""
    from datetime import datetime, timedelta
    import re
    m = re.search(r'/(\d{4})/(\d{2})/(\d{2})/', url)
    if not m:
        return True  # no date in URL, allow it
    try:
        article_date = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        cutoff = datetime.now() - timedelta(days=months*30)
        return article_date >= cutoff
    except:
        return True

def _parse_amount_millions(a):
    import re
    m = re.match(r"\$?([\d\.]+)\s*([MB])", a.strip(), re.I)
    if not m: return -1
    return float(m.group(1)) * (1000 if m.group(2).upper()=="B" else 1)

def parse_funding(results, seen, found, force_signal=None):
    companies = []
    for r in results:
        title   = r.get("title", "")
        snippet = r.get("snippet", "")
        url     = r.get("link", "")
        combined = title + " " + snippet

        if not is_recent_url(url):
            log_info(f"  ❌ SKIP (too old): {title[:70]}")
            continue

        m = FUND_RE.search(combined)
        if not m:
            log_info(f"  ❌ SKIP (no funding pattern): {title[:70]}")
            continue

        name   = clean_name(m.group(1))
        amount = normalise_amount(m.group(2))
        series = SERIES_RE.search(combined)
        series_label = f"Series {series.group(1)}" if series else "funding round"

        noise_words = {'today', 'yesterday', 'recently', 'now', 'just', 'new', 'the', 'has', 'this', 'that', 'its', 'their', 'our', 'your'}
        if not name or name.lower() in noise_words or name.lower() in {x.lower() for x in list(seen)+list(found)}:
            log_info(f"  ❌ SKIP (seen/invalid): {name}")
            continue

        log_info(f"  ✅ EXTRACTED: {name} — {amount} {series_label}")
        log_info(f"               Source: {url}")
        if force_signal == "series_a":
            am = _parse_amount_millions(amount)
            if am > 0 and not (5 <= am <= 50):
                log_info(f"  ❌ SKIP (amount out of Series A range): {name}")
                continue
            sig = "series_a"
        else:
            am = _parse_amount_millions(amount)
            is_a = bool(series and series.group(1).upper() == "A") and (am < 0 or 5 <= am <= 50)
            sig = "series_a" if is_a else "funding"
        companies.append({
            "name": name,
            "signal": sig,
            "signal_detail": f"Raised {amount} {series_label}",
            "website": url,
            "source_url": url,
            "source_title": title,
        })

    return companies


# ─── CRO/CMO parser ───────────────────────────────────────────────────────────
# Patterns (case-insensitive):
#   [Company] appoints/names [Name] as CRO/Chief Revenue Officer
#   [Company] appoints [Adj] [Name] as …  (e.g. "Industry Veteran John Smith")
APPT_RE = re.compile(
    r'([\w][A-Za-z0-9\s\.\-]+?)\s+(?:appoints|names|hires|announced the appointment of)\s+(?:[A-Za-z0-9]+\s+){0,5}([A-Z][a-zA-Z\']+\s+[A-Z][a-zA-Z\']+)\s+as\s+(CRO|CMO|Chief Revenue Officer|Chief Marketing Officer)',
    re.IGNORECASE
)
# Second pass for "and X as CRO" in same headline (e.g. Mosai)
APPT_RE2 = re.compile(
    r'and\s+([A-Z][a-zA-Z]+\s+[A-Z][a-zA-Z]+)\s+as\s+(CRO|CMO|Chief Revenue Officer|Chief Marketing Officer)',
    re.IGNORECASE
)
NOISE_TAIL = re.compile(r'\s+(today|yesterday|now|recently|just|officially|formally)$', re.IGNORECASE)

def normalize_title(t):
    """Expand truncated Serper titles so regex can match."""
    t = t.strip()
    # Skip normalization if title already has the full title
    if re.search(r'Chief Revenue Officer|Chief Marketing Officer|\bCRO\b|\bCMO\b', t, re.IGNORECASE):
        return t
    # Only replace truncation at END of string
    t = re.sub(r'as\s+Chief\s*\.\.\.$', 'as Chief Revenue Officer', t, flags=re.IGNORECASE)
    t = re.sub(r'as\s+C\.\.\.$', 'as Chief Revenue Officer', t, flags=re.IGNORECASE)
    t = re.sub(r'\bas\s+\.\.\.$', 'as Chief Revenue Officer', t, flags=re.IGNORECASE)
    return t

def parse_cro(results, seen, found):
    companies = []
    for r in results:
        title   = r.get("title", "")
        snippet = r.get("snippet", "")
        url     = r.get("link", "")
        combined = title + " " + snippet

        if not is_recent_url(url):
            log_info(f"  ❌ SKIP (too old): {title[:70]}")
            continue

        m = APPT_RE.search(normalize_title(title)) or APPT_RE.search(snippet)
        if not m:
            # Try second pass for "and X as CRO" pattern (e.g. Mosai)
            m2 = APPT_RE2.search(combined)
            if m2:
                # Extract company from first APPT_RE match without CRO requirement
                company_re = re.compile(r'([\w][A-Za-z0-9\s\.\-]+?)\s+(?:appoints|names|hires)', re.IGNORECASE)
                cm = company_re.search(combined)
                if cm:
                    name = NOISE_TAIL.sub("", clean_name(cm.group(1))).strip()
                    exec_name = m2.group(1).strip()
                    exec_type = "CRO" if "revenue" in m2.group(2).lower() or m2.group(2).upper() == "CRO" else "CMO"
                    noise_words = {'today', 'yesterday', 'recently', 'now', 'just', 'new', 'the', 'has', 'this', 'that', 'its', 'their', 'our', 'your'}
                    if not name or name.lower() in noise_words or name.lower() in {x.lower() for x in list(seen)+list(found)}:
                        log_info(f"  ❌ SKIP (seen/invalid): {name}")
                        continue
                    log_info(f"  ✅ EXTRACTED: {name} — appointed {exec_name} as {exec_type}")
                    found.add(name)
                    companies.append({"name": name, "exec_name": exec_name, "exec_type": exec_type, "url": url, "signal": "cro_hire", "signal_detail": f"Appointed {exec_name} as {exec_type}", "source_url": url, "source_title": title})
                    continue
            log_info(f"  ❌ SKIP (no appt pattern): {title[:70]}")
            continue

        name      = NOISE_TAIL.sub("", clean_name(m.group(1))).strip()
        exec_name = m.group(2).strip()
        exec_type = m.group(3).strip().upper()
        is_cmo = "marketing" in exec_type.lower() or exec_type.upper() == "CMO"
        exec_type = "CMO" if is_cmo else "CRO"
        signal_type = "cmo_hire" if is_cmo else "cro_hire"

        noise_words = {'today', 'yesterday', 'recently', 'now', 'just', 'new', 'the', 'has', 'this', 'that', 'its', 'their', 'our', 'your'}
        if not name or name.lower() in noise_words or name.lower() in {x.lower() for x in list(seen)+list(found)}:
            log_info(f"  ❌ SKIP (seen/invalid): {name}")
            continue

        if name.lower() in {x.lower() for x in list(found)}:
            log_info(f"  ❌ SKIP (duplicate): {name}")
            continue
        log_info(f"  ✅ EXTRACTED: {name} — appointed {exec_name} as {exec_type}")
        log_info(f"               Source: {url}")
        found.add(name.lower())
        companies.append({
            "name": name,
            "signal": signal_type,
            "signal_detail": f"Appointed {exec_name} as {exec_type}",
            "website": url,
            "source_url": url,
            "source_title": title,
            "exec_name": exec_name,
            "exec_type": exec_type,
        })

    return companies


# ─── AE/SDR spike parser ─────────────────────────────────────────────────────
def parse_ae_sdr_spike(results, kind, seen, found):
    """Group results by company — flag if 3+ AE or 3+ SDR roles found."""
    from collections import defaultdict
    company_jobs = defaultdict(list)

    GREENHOUSE_RE = re.compile(r'greenhouse\.io/([a-z0-9_\-]+)/', re.IGNORECASE)
    LEVER_RE      = re.compile(r'jobs\.lever\.co/([a-z0-9_\-]+)/', re.IGNORECASE)
    LINKEDIN_RE   = re.compile(r'linkedin\.com/jobs/view/[^/]+-at-([a-z0-9\-]+)-\d', re.IGNORECASE)
    BRAVADO_RE    = re.compile(r'bravado\.co/jobs/([a-z0-9_\-]+)/', re.IGNORECASE)
    WELLFOUND_RE  = re.compile(r'wellfound\.com/company/([a-z0-9_\-]+)/', re.IGNORECASE)
    TITLE_CO_RE   = re.compile(r'^(.+?)\s+(?:is hiring|hiring|–|-)\s', re.IGNORECASE)

    for r in results:
        title   = r.get("title", "")
        url     = r.get("link", "")

        company = None
        for pattern in [GREENHOUSE_RE, LEVER_RE, BRAVADO_RE, WELLFOUND_RE]:
            m = pattern.search(url)
            if m:
                company = m.group(1).replace("-", " ").replace("_", " ").title()
                break
        if not company:
            m = LINKEDIN_RE.search(url)
            if m:
                company = m.group(1).replace("-", " ").title()
        if not company:
            m = TITLE_CO_RE.search(title)
            if m:
                company = clean_name(m.group(1))
        if not company:
            continue

        # Skip if extracted "company" is clearly a job title
        job_title_words = {'account', 'executive', 'sales', 'development',
                           'representative', 'manager', 'director', 'engineer'}
        if sum(1 for w in company.lower().split() if w in job_title_words) >= 2:
            continue

        company_jobs[company].append({"title": title, "url": url})

    threshold  = AE_SPIKE_THRESHOLD if kind == "ae_spike" else SDR_SPIKE_THRESHOLD
    role_label = "Account Executive" if kind == "ae_spike" else "SDR"
    signal_type = kind

    companies = []
    for company, jobs in company_jobs.items():
        if len(jobs) < threshold:
            continue
        if company.lower() in {x.lower() for x in list(seen) + list(found)}:
            log_info(f"  ❌ SKIP (seen): {company}")
            continue
        log_info(f"  ✅ EXTRACTED: {company} — {len(jobs)} open {role_label} roles (spike)")
        companies.append({
            "name": company,
            "signal": signal_type,
            "signal_detail": f"{len(jobs)}+ open {role_label} roles — hiring spike detected",
            "website": jobs[0]["url"],
            "source_url": jobs[0]["url"],
            "source_title": jobs[0]["title"],
        })
        found.add(company)

    return companies


# ─── helpers ─────────────────────────────────────────────────────────────────
def clean_name(raw: str) -> str:
    # Strip trailing noise words that leaked into the capture group
    noise = r'\s+(raises|raised|announces|bags|secures|appoints|names|hires).*$'
    name = re.sub(noise, '', raw, flags=re.IGNORECASE).strip().rstrip('.,;:-')
    # Strip leading descriptors like "Consumer-focused privacy company Cloaked"
    # If last word is capitalized and rest look like descriptors, keep last word
    parts = name.split()
    if len(parts) > 2:
        # Find last capitalized word that could be a company name
        desc_words = {'company', 'startup', 'platform', 'provider', 'solution',
                      'focused', 'based', 'backed', 'funded', 'led', 'driven'}
        if any(w.lower() in desc_words for w in parts[:-1]):
            name = parts[-1]
    # Drop if looks like a sentence fragment (> 5 words)
    if len(name.split()) > 5:
        return ""
    return name


def claude_saas_filter(companies: list) -> list:
    """Use Claude to confirm each company is a B2B SaaS business. Batches all in one call."""
    if not companies or not ANTHROPIC_API_KEY:
        return companies

    # Build a compact list for Claude to evaluate
    company_list = "\n".join(
        f"{i+1}. {c['name']} — {c.get('signal_detail', '')} | source: {c.get('source_title', '')}"
        for i, c in enumerate(companies)
    )

    prompt = f"""You are a B2B SaaS classifier. For each company below, reply with just the number and YES or NO.

A company qualifies as B2B SaaS if it sells software subscriptions to businesses (not consumers, not hardware, not services/consulting, not crypto/DeFi, not defense/aerospace, not biotech/pharma, not a VC/fund).

{company_list}

Reply in this exact format, one per line:
1. YES
2. NO
etc."""

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5",
                "max_tokens": 256,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=20,
        )
        r.raise_for_status()
        response_text = r.json()["content"][0]["text"]

        # Parse YES/NO answers
        kept = []
        for line in response_text.strip().splitlines():
            line = line.strip()
            m = re.match(r'^(\d+)\.\s*(YES|NO)', line, re.IGNORECASE)
            if m:
                idx = int(m.group(1)) - 1
                verdict = m.group(2).upper()
                if 0 <= idx < len(companies):
                    if verdict == "YES":
                        kept.append(companies[idx])
                    else:
                        log_info(f"  🚫 FILTERED (Claude, non-SaaS): {companies[idx]['name']}")

        # Fallback: if parsing failed, return original list
        if not kept and len(companies) > 0:
            log_info("  ⚠️ Claude SaaS filter parse failed — keeping all companies")
            return companies

        log_info(f"  🤖 Claude SaaS filter: {len(kept)}/{len(companies)} passed")
        return kept

    except Exception as e:
        log_error(f"Claude SaaS filter error: {e} — skipping filter")
        return companies


NON_SAAS_KEYWORDS = {
    'beverage', 'food', 'drink', 'restaurant', 'retail', 'fashion', 'apparel',
    'defense', 'defence', 'military', 'aerospace', 'weapon',
    'real estate', 'construction', 'mining', 'oil', 'gas',
    'pharmaceutical', 'biotech', 'medical device', 'hospital',
    'hardware', 'semiconductor', 'manufacturing',
    'maritime', 'shipping', 'trucking',
    'beverage', 'tractor', 'food delivery', 'swish', 'harmattan', 'idmworks', 'insight assurance',
    'world labs', 'research lab', 'research institute',
    'solar', 'renewable', 'utility',
}


def is_likely_b2b_saas(company: dict) -> bool:
    NON_SAAS_KEYWORDS = {
        'beverage', 'food', 'drink', 'restaurant', 'retail', 'fashion', 'apparel',
        'defense', 'defence', 'military', 'aerospace', 'weapon',
        'real estate', 'construction', 'mining', 'oil', 'gas',
        'pharmaceutical', 'biotech', 'medical device', 'hospital',
        'hardware', 'semiconductor', 'manufacturing',
        'maritime', 'shipping', 'trucking',
    'beverage', 'tractor', 'food delivery', 'swish', 'harmattan', 'idmworks', 'insight assurance',
    'world labs', 'research lab', 'research institute',
        'solar', 'renewable', 'utility',
    }
    text = (company.get("name", "") + " " + company.get("signal_detail", "") + " " + company.get("source_title", "")).lower()
    for kw in NON_SAAS_KEYWORDS:
        if kw in text:
            return False
    return True

def dedupe(companies):
    seen, out = set(), []
    for c in companies:
        k = c["name"].lower()
        if k not in seen:
            seen.add(k)
            out.append(c)
    return out
