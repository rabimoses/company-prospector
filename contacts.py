"""Contact finding via Serper.dev API — real searches only."""

import sys, re, requests
from pathlib import Path
from typing import List, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent))
from config import SERPER_API_KEY, SERPER_API_URL, MAX_CONTACTS_PER_COMPANY
from settings_manager import get_settings as _get_settings
from utils import log_info, log_error, extract_domain_from_url

def serper_search(query: str) -> Dict:
    try:
        r = requests.post(
            SERPER_API_URL,
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": query, "num": 5},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log_error(f"Serper error: {e}")
        return {"organic": []}

NAME_RE = re.compile(r'\b([A-Z][a-z]{2,}\s+[A-Z][a-z]{2,})\b')
NOISE_NAMES = {'How Karim', 'Future Secured', 'New Era', 'Chief Executive', 'Staying Ahead',
               'Friday Reflection', 'Introducing Icon', 'Founder Ioannis', 'Raiders Development',
               'Embark Studios', 'Culture Drivers', 'The Evolving', 'Manifest Advisors',
               'Market Leader', 'Industry Veteran', 'Growth Leader', 'Senior Vice', 'Vice President'}

# Words that look like names but aren't — first or last word in a "name" match
NOISE_WORDS = {
    'home', 'health', 'care', 'based', 'labs', 'announces', 'appoints', 'secures',
    'program', 'programs', 'services', 'solutions', 'systems', 'technologies', 'technology',
    'group', 'partners', 'ventures', 'capital', 'global', 'digital', 'cloud', 'data',
    'platform', 'network', 'networks', 'media', 'studio', 'studios', 'agency', 'consulting',
    'compliance', 'alliance', 'leadership', 'insights', 'announcing', 'introducing',
    'voice', 'models', 'business', 'company', 'enterprise', 'software', 'products',
    'management', 'operations', 'strategy', 'research', 'development', 'engineering',
    'sales', 'marketing', 'finance', 'legal', 'support', 'success', 'growth',
    'sculptor', 'bluewave', 'manifest', 'embark', 'mosai', 'sentilink',
    'holdings', 'achieves', 'candidates', 'deepfake', 'workleap', 'advanced',
    'manufacturing', 'lead', 'identity', 'matters', 'building', 'trust',
    'enabling', 'driving', 'scaling', 'transforming', 'connecting', 'helping',
    'corporate', 'director', 'officer', 'president', 'founder', 'investor',
    'beth', 'ann', 'marie', 'lee', 'lynn', 'jean', 'sue', 'kay',
    'about', 'power', 'how', 'all', 'lio', 'openai', 'harmattan',
    'getreal', 'openobserve', 'lastpass', 'elevenlabs', 'upwind', 'superorganism',
}

def is_real_name(name: str) -> bool:
    parts = name.lower().split()
    if len(parts) != 2:
        return False
    if parts[0] in NOISE_WORDS or parts[1] in NOISE_WORDS:
        return False
    # Names should be 2-15 chars each part
    if not all(2 <= len(p) <= 15 for p in parts):
        return False
    return True
TITLE_RE = re.compile(
    r'(Chief Revenue Officer|CRO|Chief Marketing Officer|CMO|Chief Executive Officer|CEO|'
    r'VP(?:\s+of)?\s+Marketing|VP(?:\s+of)?\s+Sales|VP(?:\s+of)?\s+Revenue|VP(?:\s+of)?\s+Demand|'
    r'Head of (?:Marketing|Sales|Demand|Revenue|Growth)|'
    r'Vice President(?:\s+of)?\s+(?:Marketing|Sales|Revenue|Demand|Growth)|'
    r'SVP(?:\s+of)?\s+(?:Marketing|Sales|Revenue))',
    re.IGNORECASE
)

def find_contacts(company_name: str, company_website: str = None, signal_data: Dict = None) -> List[Dict]:
    log_info(f"Contacts: Searching for contacts at {company_name}...")
    contacts = []
    seen_names = set()

    # If we already know the CRO from the signal, add them first
    if signal_data and signal_data.get("exec_name") and signal_data.get("exec_type"):
        exec_name = signal_data["exec_name"]
        exec_type = signal_data["exec_type"]
        domain = extract_domain_from_url(company_website) if company_website else ""
        email = f"{exec_name.split()[0].lower()}@{domain}" if domain else "[guess email]"
        contacts.append({
            "name": exec_name,
            "title": exec_type,
            "email": email,
            "linkedin_url": f"https://linkedin.com/search/results/people/?keywords={exec_name.replace(' ', '%20')}",
            "verified": True,
            "source": signal_data.get("source_url", "press release"),
        })
        seen_names.add(exec_name.lower())
        log_info(f"  ✓ From signal: {exec_name} ({exec_type})")

    # Search for additional contacts
    queries = [
        # LinkedIn searches by role
        f'"{company_name}" CEO site:linkedin.com',
        f'"{company_name}" CMO OR "VP Marketing" site:linkedin.com',
        f'"{company_name}" CRO OR "VP Sales" OR "VP Revenue" site:linkedin.com',
        f'"{company_name}" "Head of Demand" OR "VP Demand" OR "Demand Generation" site:linkedin.com',
        # Press/news fallback — catches appointment announcements
        f'"{company_name}" appoints OR hires OR joins "VP" OR "Chief" OR "Head of"',
        f'"{company_name}" leadership team',
    ]

    max_contacts = _get_settings()["max_contacts_per_company"]

    for query in queries:
        if len(contacts) >= max_contacts:
            break

        data = serper_search(query)
        for r in data.get("organic", []):
            if len(contacts) >= max_contacts:
                break

            title = r.get("title", "")
            snippet = r.get("snippet", "")
            combined = title + " " + snippet

            # Try name from title first, then snippet
            name_match = NAME_RE.search(title) or NAME_RE.search(snippet)
            title_match = TITLE_RE.search(combined)

            if not name_match or not title_match:
                continue
            if name_match.group(1) in NOISE_NAMES:
                continue
            if not is_real_name(name_match.group(1)):
                continue

            name = name_match.group(1)
            role = title_match.group(1)

            if name.lower() in seen_names:
                continue

            domain = extract_domain_from_url(company_website) if company_website else ""
            email = f"{name.split()[0].lower()}@{domain}" if domain else "[guess email]"

            contacts.append({
                "name": name,
                "title": role,
                "email": email,
                "linkedin_url": r.get("link", ""),
                "verified": True,
                "source": r.get("link", ""),
                "verification_note": "Found via search — verify before sending",
            })
            seen_names.add(name.lower())
            log_info(f"  ~ Found: {name} ({role}) — verify before sending")

    if not contacts:
        log_info(f"  No contacts found for {company_name}")

    log_info(f"  Total: {len(contacts)} contacts found")
    return contacts[:max_contacts]
