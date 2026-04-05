"""AE/SDR hiring spike detector using Greenhouse and Lever public APIs."""

import requests
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


def is_ae_role(title: str) -> bool:
    t = title.lower()
    return any(k in t for k in AE_KEYWORDS)


def is_sdr_role(title: str) -> bool:
    t = title.lower()
    return any(k in t for k in SDR_KEYWORDS)


def detect_spikes(seen: Set[str], found: Set[str]) -> List[Dict]:
    """Scan company list for AE/SDR hiring spikes using ratio-based thresholds."""
    from config import SERPER_API_KEY
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

    log_info("\nScanning Greenhouse + Lever for AE/SDR spikes...")

    companies = []

    # Combine seed list + dynamically discovered companies
    dynamic = discover_companies_via_serper(SERPER_API_KEY)
    dynamic_slugs = [d["slug"] for d in dynamic]
    all_companies = list(set(AE_SDR_COMPANIES + dynamic_slugs))
    log_info(f"  Total companies to scan: {len(all_companies)} ({len(dynamic_slugs)} discovered dynamically)")

    for company in all_companies:
        jobs = scrape_greenhouse(company) + scrape_lever(company)
        if not jobs:
            continue

        total     = len(jobs)
        ae_jobs   = [j for j in jobs if is_ae_role(j["title"])]
        sdr_jobs  = [j for j in jobs if is_sdr_role(j["title"])]
        ae_count  = len(ae_jobs)
        sdr_count = len(sdr_jobs)
        ae_ratio  = ae_count / total
        sdr_ratio = sdr_count / total

        name = company.replace("-", " ").title()
        if name.lower() in {x.lower() for x in list(seen) + list(found)}:
            continue
        if company.lower() in blocklist or name.lower() in blocklist:
            log_info(f"  ⛔ BLOCKED: {name}")
            continue

        # Skip if company is too large or too small
        if total > max_total_roles or total < min_total_roles:
            continue

        # Skip known slug-style names
        if company.lower() in EXCLUDE_SLUGS:
            continue

        # Skip slug-style names (contain digits or look like URLs)
        import re
        if re.search(r'\d', name) or len(name.replace(" ", "")) > 20:
            continue

        # Split into recent (0-45d) and prior (46-90d) windows
        from datetime import datetime, timezone, timedelta
        now = datetime.now(tz=timezone.utc)
        recent_cutoff = now - timedelta(days=recent_days)
        prior_cutoff  = now - timedelta(days=PRIOR_DAYS)

        def in_recent(j): return j.get("posted_at") and j["posted_at"] >= recent_cutoff
        def in_prior(j):  return j.get("posted_at") and prior_cutoff <= j["posted_at"] < recent_cutoff

        ae_recent_count  = sum(1 for j in ae_jobs  if in_recent(j))
        ae_prior_count   = sum(1 for j in ae_jobs  if in_prior(j))
        sdr_recent_count = sum(1 for j in sdr_jobs if in_recent(j))
        sdr_prior_count  = sum(1 for j in sdr_jobs if in_prior(j))
        sales_recent     = ae_recent_count + sdr_recent_count
        sales_prior      = ae_prior_count  + sdr_prior_count

        ae_growth    = (ae_recent_count - ae_prior_count) / ae_prior_count if ae_prior_count > 0 else (999 if ae_recent_count >= ae_min_absolute else None)
        sdr_growth   = (sdr_recent_count - sdr_prior_count) / sdr_prior_count if sdr_prior_count > 0 else (999 if sdr_recent_count >= sdr_min_absolute else None)
        sales_growth = (sales_recent - sales_prior) / sales_prior if sales_prior > 0 else (999 if sales_recent >= 3 else None)

        ae_primary      = ae_growth    is not None and ae_growth    >= spike_growth_pct and ae_recent_count    >= ae_min_absolute
        sdr_primary     = sdr_growth   is not None and sdr_growth   >= spike_growth_pct and sdr_recent_count   >= sdr_min_absolute
        sales_secondary = sales_growth is not None and sales_growth >= spike_growth_pct and sales_recent >= 3

        if not ae_primary and not sdr_primary and not sales_secondary:
            continue

        if ae_primary:
            g = "new push (0 prior)" if ae_prior_count == 0 else f"+{round(ae_growth*100)}% vs prior 45d"
            signal_str = f"{ae_recent_count} new AE roles in last 45d ({g}) | {ae_count} total open AE"
            if sdr_recent_count > 0:
                signal_str += f" + {sdr_recent_count} SDR"
            log_info(f"  ✅ AE SPIKE: {name} — {signal_str}")
            companies.append({
                "name": name,
                "signal": "ae_spike",
                "signal_detail": signal_str,
                "website": ae_jobs[0]["url"],
                "source_url": ae_jobs[0]["url"],
                "source_title": f"{name} is hiring {ae_count}+ Account Executives",
            })
            found.add(name.lower())

        elif sdr_primary and name.lower() not in found:
            g = "new push (0 prior)" if sdr_prior_count == 0 else f"+{round(sdr_growth*100)}% vs prior 45d"
            signal_str = f"{sdr_recent_count} new SDR roles in last 45d ({g}) | {sdr_count} total open SDR"
            log_info(f"  ✅ SDR SPIKE: {name} — {signal_str}")
            companies.append({
                "name": name,
                "signal": "sdr_spike",
                "signal_detail": signal_str,
                "website": sdr_jobs[0]["url"],
                "source_url": sdr_jobs[0]["url"],
                "source_title": f"{name} is hiring {sdr_count}+ SDRs",
            })
            found.add(name.lower())

        elif sales_secondary and name.lower() not in found:
            g = "new push (0 prior)" if sales_prior == 0 else f"+{round(sales_growth*100)}% vs prior 45d"
            signal_str = f"{sales_recent} new sales roles in last 45d ({g}) — {ae_recent_count} AE + {sdr_recent_count} SDR | {ae_count+sdr_count} total open"
            log_info(f"  ✅ SALES SPIKE: {name} — {signal_str}")
            companies.append({
                "name": name,
                "signal": "ae_spike",
                "signal_detail": signal_str,
                "website": ae_jobs[0]["url"] if ae_jobs else sdr_jobs[0]["url"],
                "source_url": ae_jobs[0]["url"] if ae_jobs else sdr_jobs[0]["url"],
                "source_title": f"{name} combined sales hiring spike",
            })
            found.add(name.lower())

    return companies


def discover_companies_via_serper(serper_api_key: str) -> list:
    """Dynamically discover B2B SaaS company slugs from Greenhouse/Lever via Serper."""
    import requests
    slugs = {}  # slug -> board type

    queries = [
        ('greenhouse', 'site:boards.greenhouse.io "account executive" "B2B SaaS"'),
        ('greenhouse', 'site:boards.greenhouse.io "account executive" "series B" OR "series C"'),
        ('greenhouse', 'site:boards.greenhouse.io "account executive" software'),
        ('lever',      'site:jobs.lever.co "account executive" "B2B SaaS"'),
        ('lever',      'site:jobs.lever.co "account executive" "series B" OR "series C"'),
        ('lever',      'site:jobs.lever.co "account executive" software'),
    ]

    import re
    GH_RE   = re.compile(r'boards\.greenhouse\.io/([a-z0-9_\-]+)/', re.IGNORECASE)
    LEVER_RE = re.compile(r'jobs\.lever\.co/([a-z0-9_\-]+)/', re.IGNORECASE)

    for board, query in queries:
        try:
            r = requests.post(
                'https://google.serper.dev/search',
                headers={"X-API-KEY": serper_api_key, "Content-Type": "application/json"},
                json={"q": query, "num": 10},
                timeout=10,
            )
            for result in r.json().get("organic", []):
                url = result.get("link", "")
                if board == "greenhouse":
                    m = GH_RE.search(url)
                    if m:
                        slugs[m.group(1)] = "greenhouse"
                else:
                    m = LEVER_RE.search(url)
                    if m:
                        slugs[m.group(1)] = "lever"
        except:
            pass

    log_info(f"  Discovered {len(slugs)} companies dynamically via Serper")
    return [{"slug": slug, "board": board} for slug, board in slugs.items()]
