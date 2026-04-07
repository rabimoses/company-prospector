"""Contact finding via Serper.dev + Claude extraction."""

import json
import re
import sys
from pathlib import Path
from typing import List, Dict

sys.path.insert(0, str(Path(__file__).parent))
from config import ANTHROPIC_API_KEY
from search import web_search
from settings_manager import get_settings as _get_settings
from utils import log_info, log_error, extract_domain_from_url


def _claude_extract_contacts(company_name: str, search_results: list, max_contacts: int) -> List[Dict]:
    """Use Claude to extract (name, title) pairs from search result snippets."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        # Build a condensed text block from all search snippets
        snippets = []
        for r in search_results:
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            if title or snippet:
                snippets.append(f"- {title}: {snippet}")
        if not snippets:
            return []

        text_block = "\n".join(snippets[:30])  # cap at 30 results

        prompt = f"""You are extracting executive contacts from search result snippets about the company "{company_name}".

Search results:
{text_block}

Extract up to {max_contacts} real people who work at {company_name} in senior sales, marketing, or revenue roles.
Target titles: CRO, Chief Revenue Officer, CMO, Chief Marketing Officer, VP Marketing, VP Sales, VP Demand Generation, Head of Demand Generation, Head of Marketing, Head of Revenue, Director of Demand Generation, SVP Marketing, SVP Sales, CEO, Co-Founder.

Rules:
- Only include people who clearly work at {company_name} (not a different company)
- Only include people with a clearly identified title from the target list above
- Do NOT invent or guess names — only include names explicitly mentioned in the snippets
- Return ONLY a JSON array, no other text

Format:
[
  {{"name": "First Last", "title": "exact title from snippet"}},
  ...
]

If no valid contacts found, return: []"""

        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        # Extract JSON array from response
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except Exception as e:
        log_error(f"Claude extraction error: {e}")
    return []


def find_contacts(company_name: str, company_website: str = None, signal_data: Dict = None) -> List[Dict]:
    log_info(f"Contacts: Searching for contacts at {company_name}...")
    contacts = []
    seen_names = set()
    max_contacts = _get_settings()["max_contacts_per_company"]
    domain = extract_domain_from_url(company_website) if company_website else ""

    # If we already know the exec from the signal, add them first
    if signal_data and signal_data.get("exec_name") and signal_data.get("exec_type"):
        exec_name = signal_data["exec_name"]
        exec_type = signal_data["exec_type"]
        email = _guess_email(exec_name, domain)
        contacts.append({
            "name": exec_name,
            "title": exec_type,
            "email": email,
            "linkedin_url": f"https://linkedin.com/search/results/people/?keywords={exec_name.replace(' ', '%20')}+{company_name.replace(' ', '%20')}",
            "verified": True,
            "source": signal_data.get("source_url", "press release"),
        })
        seen_names.add(exec_name.lower())
        log_info(f"  ✓ From signal: {exec_name} ({exec_type})")

    if len(contacts) >= max_contacts:
        return contacts[:max_contacts]

    # Collect all search results then extract with Claude in one pass
    all_results = []

    queries = [
        # Press releases / news — most reliable source
        f'"{company_name}" "VP of Marketing" OR CMO OR "Chief Marketing Officer" appointed OR hired OR joins',
        f'"{company_name}" "VP of Sales" OR CRO OR "Chief Revenue Officer" appointed OR hired OR joins',
        f'"{company_name}" "Head of Demand" OR "Demand Generation" OR "Revenue Marketing" hired OR joins OR named',
        f'"{company_name}" "VP Sales" OR "VP Marketing" OR "Head of Marketing" site:linkedin.com/in',
        # Company's own website — team/about page often lists execs
        f'site:{domain} team OR leadership OR "about us"' if domain else None,
        # Crunchbase / Craft — reliable exec data
        f'"{company_name}" leadership team site:crunchbase.com OR site:craft.co',
        # General exec announcement
        f'"{company_name}" executive team revenue marketing leadership 2024 OR 2025',
    ]

    for query in queries:
        if not query:
            continue
        try:
            data = web_search(query, num=5)
            results = data.get("organic", [])
            all_results.extend(results)
        except Exception as e:
            log_error(f"Search error for '{query}': {e}")

    # Use Claude to extract contacts from all results at once
    if all_results:
        remaining = max_contacts - len(contacts)
        extracted = _claude_extract_contacts(company_name, all_results, remaining)
        for c in extracted:
            name = c.get("name", "").strip()
            title = c.get("title", "").strip()
            if not name or not title:
                continue
            if name.lower() in seen_names:
                continue
            email = _guess_email(name, domain)
            contacts.append({
                "name": name,
                "title": title,
                "email": email,
                "linkedin_url": f"https://linkedin.com/search/results/people/?keywords={name.replace(' ', '%20')}+{company_name.replace(' ', '%20')}",
                "verified": False,
                "source": "web search",
                "verification_note": "Found via search — verify before sending",
            })
            seen_names.add(name.lower())
            log_info(f"  ~ Found: {name} ({title})")
            if len(contacts) >= max_contacts:
                break

    if not contacts:
        log_info(f"  No contacts found for {company_name}")

    log_info(f"  Total: {len(contacts)} contacts found")
    return contacts[:max_contacts]


def _guess_email(name: str, domain: str) -> str:
    """Guess the most common email format for a person at a company."""
    if not domain:
        return ""
    parts = name.lower().split()
    if len(parts) < 2:
        return f"{parts[0]}@{domain}" if parts else ""
    first, last = parts[0], parts[-1]
    # Most common B2B SaaS format is first@domain or first.last@domain
    return f"{first}.{last}@{domain}"
