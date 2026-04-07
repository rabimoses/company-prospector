"""AE/SDR hiring spike detector using Greenhouse, Lever, and Ashby public APIs."""

import re
import requests
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Set
from collections import defaultdict
from utils import log_info, log_error

AE_SDR_COMPANIES = [
    # Demand gen / marketing tech
    "demandbase", "6sense", "terminus", "rollworks", "metadata",
    "outreach", "salesloft", "gong", "chorus", "clari",
    "highspot", "seismic", "showpad", "mindtickle",
    # CRM / sales tech
    "hubspot", "pipedrive", "freshsales", "insightly",
    "apollo", "zoominfo", "clearbit", "cognism", "lusha",
    # PLG / product analytics
    "amplitude", "mixpanel", "pendo", "fullstory", "heap", "logrocket",
    # Customer success
    "gainsight", "totango", "churnzero", "vitally",
    # Marketing automation
    "klaviyo", "braze", "iterable", "customerio", "appcues",
    # HR / people ops
    "lattice", "culture-amp", "leapsome", "betterworks",
    "rippling", "bamboohr", "justworks", "gusto", "namely",
    # Finance / spend
    "brex", "ramp", "airbase", "tipalti", "carta",
    # Productivity / collab
    "asana", "clickup", "notion", "loom", "monday",
    # Video / events
    "vidyard", "wistia", "goldcast", "on24",
    # Data / analytics
    "databricks", "segment", "fivetran", "dbt-labs", "airbyte",
    # Security
    "lacework", "orca-security", "axonius", "abnormal-security",
    # Other B2B SaaS
    "intercom", "drift", "qualified", "chili-piper",
    "docusign", "pandadoc", "proposify",
    "chargebee", "recurly", "zuora", "paddle",
    "partnerstack", "impact", "crossbeam",
    "workato", "zapier", "retool",
    "calendly", "typeform", "jotform",
    "webflow", "contentful", "sanity",
]

AE_KEYWORDS  = ["account executive", "account exec"]
SDR_KEYWORDS = ["sales development", "business development representative"]

# Signal thresholds
AE_MIN_ABSOLUTE  = 2    # at least 2 open AE roles
SDR_MIN_ABSOLUTE = 2    # at least 2 open SDR roles
AE_MIN_RATIO     = 0.10 # AE roles must be >=10% of total open roles
SDR_MIN_RATIO    = 0.08 # SDR roles must be >=8% of total open roles
MAX_TOTAL_ROLES  = 100  # exclude companies with too many open roles (too large)
MIN_TOTAL_ROLES  = 8    # exclude companies with too few open roles (too small/noisy)
SPIKE_GROWTH_PCT = 0.50 # >=50% more roles in recent window vs prior window
RECENT_DAYS      = 45   # recent window in days
PRIOR_DAYS       = 90   # prior window end in days

# Slug-style names to exclude — Greenhouse slugs that aren't clean company names
EXCLUDE_SLUGS = {
    "castaigroupinc", "colabsoftware", "yoodliinc", "loopreturns", "revefi",
    "levelai", "acceldata", "hellomongoose", "brainstorminc", "documocareers",
    "fulcrumpro", "playonsports", "canarytechnologies", "propelsoftware",
}


def parse_date_greenhouse(job: dict):
    """Parse first_published or updated_at from Greenhouse job."""
    from datetime import datetime, timezone
    for field in ["first_published", "updated_at"]:
        val = job.get(field)
        if val:
            try:
                return datetime.fromisoformat(val.replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
            except:
                pass
    return None


def parse_date_lever(job: dict):
    """Parse createdAt from Lever job (Unix ms timestamp)."""
    from datetime import datetime, timezone
    val = job.get("createdAt")
    if val:
        try:
            return datetime.fromtimestamp(int(val)/1000, tz=timezone.utc)
        except:
            pass
    return None


def scrape_greenhouse(company: str) -> List[Dict]:
    try:
        url = f"https://api.greenhouse.io/v1/boards/{company}/jobs"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return [{"title": j.get("title",""), "company": company, "url": j.get("absolute_url",""), "posted_at": parse_date_greenhouse(j)}
                    for j in r.json().get("jobs", []) if j.get("title")]
    except:
        pass
    return []


def scrape_lever(company: str) -> List[Dict]:
    try:
        url = f"https://api.lever.co/v0/postings/{company}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return [{"title": j.get("text",""), "company": company, "url": j.get("hostedUrl",""), "posted_at": parse_date_lever(j)}
                    for j in r.json() if j.get("text")]
    except:
        pass
    return []


def scrape_ashby(company: str) -> List[Dict]:
    """Fetch jobs from Ashby's public job board API."""
    try:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{company}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            jobs = data.get("jobPostings", [])
            return [
                {
                    "title": j.get("title", ""),
                    "company": company,
                    "url": j.get("jobUrl", f"https://jobs.ashbyhq.com/{company}"),
                    "posted_at": None,   # Ashby API doesn't expose post date easily
                }
                for j in jobs if j.get("title")
            ]
    except:
        pass
    return []


def is_ae_role(title: str) -> bool:
    t = title.lower()
    return any(k in t for k in AE_KEYWORDS)


def is_sdr_role(title: str) -> bool:
    t = title.lower()
    return any(k in t for k in SDR_KEYWORDS)


def detect_spikes(seen: Set[str], found: Set[str]) -> List[Dict]:
    """Scan company list for AE/SDR hiring spikes using ratio-based thresholds."""
    from search import web_search
    from settings_manager import get_settings
    s = get_settings()

    # Override module-level constants with saved settings
    ae_min_absolute  = s["ae_min_absolute"]
    sdr_min_absolute = s["sdr_min_absolute"]
    spike_growth_pct = s["spike_growth_pct"]
    recent_days      = s["recent_days"]
    max_total_roles  = s["max_total_roles"]
    min_total_roles  = min(ae_min_absolute, sdr_min_absolute)
    blocklist        = {c.lower() for c in s.get("blocklist_companies", [])}

    log_info("\nScanning Greenhouse, Lever, Ashby, Wellfound + Builtin for AE/SDR spikes...")

    companies = []

    # Combine seed list + dynamically discovered companies
    dynamic = discover_companies_via_serper()
    dynamic_slugs = [d["slug"] for d in dynamic]
    all_companies = list(set(AE_SDR_COMPANIES + dynamic_slugs))
    log_info(f"  Total companies to scan: {len(all_companies)} ({len(dynamic_slugs)} discovered dynamically)")

    now           = datetime.now(tz=timezone.utc)
    recent_cutoff = now - timedelta(days=recent_days)
    prior_cutoff  = now - timedelta(days=PRIOR_DAYS)
    seen_lower    = {x.lower() for x in list(seen) + list(found)}
    lock          = threading.Lock()

    def spike_str(recent, prior, total_count, label):
        pct = f"+∞%" if prior == 0 else f"+{round((recent - prior) / prior * 100)}%"
        return f"{recent} new {label} roles in last 45d (prior 45d: {prior} → now: {recent}, {pct}) | {total_count} total open {label}"

    def scan_company(company):
        """Fetch jobs for one company and return a spike result or None."""
        jobs = scrape_greenhouse(company) + scrape_lever(company) + scrape_ashby(company)
        if not jobs:
            return None

        total     = len(jobs)
        ae_jobs   = [j for j in jobs if is_ae_role(j["title"])]
        sdr_jobs  = [j for j in jobs if is_sdr_role(j["title"])]
        ae_count  = len(ae_jobs)
        sdr_count = len(sdr_jobs)

        name = company.replace("-", " ").title()

        with lock:
            if name.lower() in seen_lower:
                return None
            if company.lower() in blocklist or name.lower() in blocklist:
                log_info(f"  ⛔ BLOCKED: {name}")
                return None

        if total > max_total_roles or total < min_total_roles:
            return None
        if company.lower() in EXCLUDE_SLUGS:
            return None
        if re.search(r'\d', name) or len(name.replace(" ", "")) > 20:
            return None

        def in_recent(j): return j.get("posted_at") and j["posted_at"] >= recent_cutoff
        def in_prior(j):  return j.get("posted_at") and prior_cutoff <= j["posted_at"] < recent_cutoff

        ae_recent  = sum(1 for j in ae_jobs  if in_recent(j))
        ae_prior   = sum(1 for j in ae_jobs  if in_prior(j))
        sdr_recent = sum(1 for j in sdr_jobs if in_recent(j))
        sdr_prior  = sum(1 for j in sdr_jobs if in_prior(j))
        s_recent   = ae_recent + sdr_recent
        s_prior    = ae_prior  + sdr_prior

        ae_growth    = (ae_recent - ae_prior) / ae_prior if ae_prior > 0 else (999 if ae_recent >= ae_min_absolute else None)
        sdr_growth   = (sdr_recent - sdr_prior) / sdr_prior if sdr_prior > 0 else (999 if sdr_recent >= sdr_min_absolute else None)
        sales_growth = (s_recent - s_prior) / s_prior if s_prior > 0 else (999 if s_recent >= 3 else None)

        ae_primary      = ae_growth    is not None and ae_growth    >= spike_growth_pct and ae_recent  >= ae_min_absolute
        sdr_primary     = sdr_growth   is not None and sdr_growth   >= spike_growth_pct and sdr_recent >= sdr_min_absolute
        sales_secondary = sales_growth is not None and sales_growth >= spike_growth_pct and s_recent   >= 3

        if not ae_primary and not sdr_primary and not sales_secondary:
            return None

        if ae_primary:
            sig = spike_str(ae_recent, ae_prior, ae_count, "AE")
            if sdr_recent > 0:
                sig += f" + {sdr_recent} SDR"
            log_info(f"  ✅ AE SPIKE: {name} — {sig}")
            return {"name": name, "signal": "ae_spike", "signal_detail": sig,
                    "website": ae_jobs[0]["url"], "source_url": ae_jobs[0]["url"],
                    "source_title": f"{name} is hiring {ae_count}+ Account Executives"}
        elif sdr_primary:
            sig = spike_str(sdr_recent, sdr_prior, sdr_count, "SDR")
            log_info(f"  ✅ SDR SPIKE: {name} — {sig}")
            return {"name": name, "signal": "sdr_spike", "signal_detail": sig,
                    "website": sdr_jobs[0]["url"], "source_url": sdr_jobs[0]["url"],
                    "source_title": f"{name} is hiring {sdr_count}+ SDRs"}
        else:
            pct_str = f"+∞%" if s_prior == 0 else f"+{round((s_recent - s_prior) / s_prior * 100)}%"
            sig = f"{s_recent} new sales roles in last 45d (prior 45d: {s_prior} → now: {s_recent}, {pct_str}) — {ae_recent} AE + {sdr_recent} SDR | {ae_count+sdr_count} total open"
            log_info(f"  ✅ SALES SPIKE: {name} — {sig}")
            src = ae_jobs[0]["url"] if ae_jobs else sdr_jobs[0]["url"]
            return {"name": name, "signal": "ae_spike", "signal_detail": sig,
                    "website": src, "source_url": src,
                    "source_title": f"{name} combined sales hiring spike"}

    # Scan all companies in parallel (20 workers)
    log_info(f"  Scanning {len(all_companies)} companies in parallel (20 workers)...")
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(scan_company, c): c for c in all_companies}
        done = 0
        for future in as_completed(futures):
            done += 1
            if done % 20 == 0:
                log_info(f"  ... {done}/{len(all_companies)} scanned")
            result = future.result()
            if result:
                with lock:
                    if result["name"].lower() not in seen_lower:
                        companies.append(result)
                        seen_lower.add(result["name"].lower())
                        found.add(result["name"].lower())

    return companies


def discover_companies_via_serper() -> list:
    """Dynamically discover B2B SaaS company slugs from job boards via Tavily."""
    slugs = {}  # slug -> board type

    queries = [
        ('greenhouse', 'site:boards.greenhouse.io "account executive" "B2B SaaS"'),
        ('greenhouse', 'site:boards.greenhouse.io "account executive" software'),
        ('lever',      'site:jobs.lever.co "account executive" "B2B SaaS"'),
        ('lever',      'site:jobs.lever.co "account executive" software'),
        ('ashby',      'site:jobs.ashbyhq.com "account executive" saas'),
        ('ashby',      'site:jobs.ashbyhq.com "account executive" software'),
        ('wellfound',  'site:wellfound.com/jobs "account executive" "b2b saas"'),
        ('wellfound',  'site:wellfound.com "account executive" software startup'),
        ('builtin',    'site:builtin.com "account executive" "b2b saas"'),
        ('builtin',    'site:builtin.com "sales development representative" saas'),
    ]

    GH_RE        = re.compile(r'boards\.greenhouse\.io/([a-z0-9_\-]+)/', re.IGNORECASE)
    LEVER_RE     = re.compile(r'jobs\.lever\.co/([a-z0-9_\-]+)/', re.IGNORECASE)
    ASHBY_RE     = re.compile(r'jobs\.ashbyhq\.com/([a-z0-9_\-]+)/', re.IGNORECASE)
    WELLFOUND_RE = re.compile(r'wellfound\.com/company/([a-z0-9_\-]+)/', re.IGNORECASE)

    board_re = {
        'greenhouse': GH_RE,
        'lever':      LEVER_RE,
        'ashby':      ASHBY_RE,
        'wellfound':  WELLFOUND_RE,
        'builtin':    None,   # Builtin URLs don't expose clean slugs — used for signal only
    }

    for board, query in queries:
        try:
            data = web_search(query, num=10)
            pattern = board_re.get(board)
            if not pattern:
                continue
            for result in data.get("organic", []):
                url = result.get("link", "")
                m = pattern.search(url)
                if m:
                    slugs[m.group(1)] = board
        except:
            pass

    log_info(f"  Discovered {len(slugs)} companies dynamically via Tavily (Greenhouse, Lever, Ashby, Wellfound)")
    return [{"slug": slug, "board": board} for slug, board in slugs.items()]
