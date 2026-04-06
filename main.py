#!/usr/bin/env python3
"""
B2B SaaS Prospecting Agent
Finds companies with growth signals, identifies key contacts, drafts outreach emails.
Real web search integration with verified sources and contact verification status.
"""

import os
import sys
import json
import csv
import argparse
from datetime import datetime
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    load_seen_companies,
    save_seen_companies,
    send_telegram_notification,
    log_error,
    log_info,
)
from discovery import find_companies
from contacts import find_contacts
from email_draft import draft_emails


def main():
    """Main prospecting run."""
    parser = argparse.ArgumentParser(description="B2B SaaS Prospector — Real Companies, Verified Sources")
    parser.add_argument("--test", action="store_true", help="Run in test mode with mock data")
    parser.add_argument("--csv", type=str, help="Load companies from CSV file")
    args = parser.parse_args()
    
    start_time = datetime.now()
    run_date = start_time.strftime("%Y-%m-%d")
    
    log_info(f"Starting prospecting run at {start_time}")
    if args.test:
        log_info("Running in TEST MODE with mock data")
    
    # Ensure output directories exist
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    
    # Load seen companies to avoid duplicates
    seen_companies = load_seen_companies()
    log_info(f"Loaded {len(seen_companies)} previously seen companies")
    
    # Get companies to process
    if args.test:
        companies = get_test_companies(seen_companies)
        log_info("Using TEST MODE data (3 mock companies)")
    elif args.csv:
        companies = load_companies_from_csv(args.csv, seen_companies)
    else:
        companies = find_companies(seen_companies)
    
    if not companies:
        message = (
            f"🎯 Prospector Run — {run_date}\n"
            f"Companies found: 0\n"
            f"Contacts identified: 0\n"
            f"Emails drafted: 0\n\n"
            f"No new qualifying companies found."
        )
        log_info("No new companies found")
        send_telegram_notification(message)
        return
    
    log_info(f"Processing {len(companies)} companies...")
    
    # Process each company
    total_contacts = 0
    total_emails = 0
    total_unverified = 0
    index_data = []
    
    for company_data in companies:
        company_name = company_data.get("name")
        log_info(f"Processing {company_name}...")
        
        try:
            # Find contacts at company
            if args.test:
                contacts = get_test_contacts(company_name)
            else:
                # Use company domain, not source URL
                source_url = company_data.get("website", "")
                company_domain = company_data.get("domain", "")
                contacts = find_contacts(
                    company_name,
                    company_domain or (company_name.lower().replace(" ", "") + ".com"),
                    company_data
                )
            
            if not contacts:
                contacts = [{"name": "Contact not found", "title": "N/A", "email": "N/A", "verified": False}]
                log_info(f"  No contacts found for {company_name}")
            else:
                verified = sum(1 for c in contacts if c.get("verified", False))
                unverified = len(contacts) - verified
                log_info(f"  Found {len(contacts)} contacts: {verified} verified, {unverified} unverified")
                total_unverified += unverified
            
            # Draft emails for verified contacts only
            emails = draft_emails(company_data, contacts)
            log_info(f"  Drafting {len(emails)} emails (only for verified contacts)")
            
            # Save results file
            result_file = save_company_results(
                company_name,
                company_data,
                contacts,
                emails,
                run_date
            )
            
            # Add to index
            verified_count = sum(1 for c in contacts if c.get("verified", False))
            index_data.append({
                "date": run_date,
                "company": company_name,
                "signal": company_data.get("signal"),
                "signal_detail": company_data.get("signal_detail", ""),
                "contacts_found": verified_count,
                "contacts_unverified": len(contacts) - verified_count,
                "emails_drafted": len(emails),
                "source_url": company_data.get("source_url", ""),
                "file_path": str(result_file)
            })
            
            total_contacts += len(contacts)
            total_emails += len(emails)
            
            # Mark as seen
            seen_companies.add(company_name)
            
            # Rate limit
            time.sleep(1)
            
        except Exception as e:
            log_error(f"Error processing {company_name}: {e}")
            continue
    
    # Update seen companies file
    save_seen_companies(seen_companies)
    
    # Update index CSV
    update_index_csv(index_data)
    update_contacts_csv(index_data)
    
    # Send Telegram notification
    message = (
        f"🎯 Prospector Run Complete — {run_date}\n"
        f"Companies found: {len(companies)}\n"
        f"Verified contacts: {total_emails}\n"
        f"Unverified contacts: {total_unverified}\n"
        f"Emails drafted: {total_emails}\n\n"
        f"Files saved to ~/company_prospector/results/"
    )
    send_telegram_notification(message)
    
    elapsed = (datetime.now() - start_time).total_seconds()
    log_info(f"Run complete in {elapsed:.1f}s")
    log_info(f"Summary: {len(companies)} companies, {total_contacts} total contacts ({total_emails} verified, {total_unverified} unverified), {total_emails} emails drafted")

    # Push updated results to git so Railway redeploys the dashboard
    push_results_to_git(run_date)


def push_results_to_git(run_date):
    """Push results to GitHub via REST API — no git binary required."""
    import base64
    import requests as req

    gh_token = os.environ.get("GH_TOKEN", "")
    gh_repo  = os.environ.get("GH_REPO", "")  # e.g. "rabimoses/company-prospector"

    if not gh_token or not gh_repo:
        log_error("GH_TOKEN or GH_REPO not set — skipping git push")
        return

    repo_dir = Path(__file__).parent
    headers = {
        "Authorization": f"token {gh_token}",
        "Accept": "application/vnd.github.v3+json",
    }
    api_base = f"https://api.github.com/repos/{gh_repo}/contents"

    # Collect files to push
    files_to_push = ["results/outreach.csv", "results/index.csv", "seen_companies.txt"]
    for md in (repo_dir / "results").glob(f"{run_date}_*.md"):
        files_to_push.append(str(md.relative_to(repo_dir)))

    pushed = 0
    for rel_path in files_to_push:
        local_path = repo_dir / rel_path
        if not local_path.exists():
            continue

        content_b64 = base64.b64encode(local_path.read_bytes()).decode()

        # Get current SHA (needed for updates)
        sha = None
        r = req.get(f"{api_base}/{rel_path}", headers=headers, timeout=10)
        if r.status_code == 200:
            sha = r.json().get("sha")

        payload = {
            "message": f"prospector run {run_date}",
            "content": content_b64,
        }
        if sha:
            payload["sha"] = sha

        r = req.put(f"{api_base}/{rel_path}", json=payload, headers=headers, timeout=30)
        if r.status_code in (200, 201):
            pushed += 1
        else:
            log_error(f"GitHub API error pushing {rel_path}: {r.status_code} {r.text[:200]}")

    if pushed:
        log_info(f"Pushed {pushed} files to GitHub via API — Railway will redeploy")


def get_test_companies(seen):
    """Return mock companies for testing."""
    test_companies = [
        {
            "name": "Databricks",
            "website": "databricks.com",
            "signal": "funding",
            "signal_detail": "Raised $12B Series G in February 2026",
            "source_url": "https://techcrunch.com/2026/02/15/databricks-raises-12b-series-g/",
        },
        {
            "name": "Notion",
            "website": "notion.so",
            "signal": "cro_hire",
            "signal_detail": "Appointed Priya Sharma as VP Marketing in February 2026",
            "source_url": "https://notion.com/press/priya-sharma-vp-marketing/",
        },
        {
            "name": "Figma",
            "website": "figma.com",
            "signal": "funding",
            "signal_detail": "Raised $200M Series E in March 2026",
            "source_url": "https://techcrunch.com/2026/03/01/figma-funding-round-2026/",
        },
    ]
    
    return [c for c in test_companies if c["name"] not in seen]


def get_test_contacts(company_name):
    """Return mock contacts for testing."""
    test_contacts = {
        "Databricks": [
            {
                "name": "Sarah Chen",
                "title": "Chief Revenue Officer",
                "email": "sarah.chen@databricks.com",
                "linkedin_url": "https://linkedin.com/in/sarahchen",
                "verified": True,
                "source": "Databricks PR - February 2026"
            }
        ],
        "Notion": [
            {
                "name": "Priya Sharma",
                "title": "VP Marketing",
                "email": "priya.sharma@notion.so",
                "linkedin_url": "https://linkedin.com/in/priyasharma",
                "verified": True,
                "source": "Notion Press - February 2026"
            }
        ],
        "Figma": [
            {
                "name": "Mike Rodriguez",
                "title": "Chief Marketing Officer",
                "email": "mike.rodriguez@figma.com",
                "linkedin_url": "https://linkedin.com/in/mikerodriguez",
                "verified": True,
                "source": "Figma LinkedIn - March 2026"
            }
        ],
    }
    
    return test_contacts.get(company_name, [])


def load_companies_from_csv(csv_path, seen):
    """Load companies from CSV file."""
    companies = []
    csv_file = Path(csv_path)
    
    if not csv_file.exists():
        log_error(f"CSV file not found: {csv_path}")
        return []
    
    try:
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("name") not in seen:
                    companies.append({
                        "name": row.get("name"),
                        "website": row.get("website"),
                        "signal": row.get("signal"),
                        "signal_detail": row.get("signal_detail"),
                        "source_url": row.get("source_url", ""),
                    })
        
        log_info(f"Loaded {len(companies)} companies from {csv_path}")
        return companies
    
    except Exception as e:
        log_error(f"Error loading CSV: {e}")
        return []


def save_company_results(company_name, company_data, contacts, emails, run_date):
    """Save company results to markdown file with verification status."""
    results_dir = Path(__file__).parent / "results"

    safe_name = company_name.lower().replace(" ", "_").replace(".", "")[:30]
    filename = f"{run_date}_{safe_name}.md"
    filepath = results_dir / filename
    
    # Build markdown content
    content = f"""# {company_name}

**Signal:** {company_data.get('signal', 'N/A')}
**Detail:** {company_data.get('signal_detail', 'N/A')}
**Date Found:** {run_date}
**Website:** {company_data.get('website', 'N/A')}
**Source:** [{company_data.get('source', 'Unknown')}]({company_data.get('source_url', '#')})

## Contacts

| Name | Title | LinkedIn | Email | Status |
|------|-------|----------|-------|--------|
"""
    
    for contact in contacts:
        linkedin = contact.get('linkedin_url', 'N/A')
        if linkedin and linkedin != 'N/A':
            linkedin = f"[Link]({linkedin})"
        email = contact.get('email', 'N/A')
        
        # Status: Verified or Unverified
        if contact.get('verified', False):
            status = f"✓ Verified ({contact.get('source', 'Unknown')})"
        else:
            note = contact.get('verification_note', 'Research needed')
            status = f"⚠️ Unverified — {note}"
        
        content += f"| {contact.get('name', 'N/A')} | {contact.get('title', 'N/A')} | {linkedin} | {email} | {status} |\n"
    
    content += "\n## Outreach Emails\n"
    
    if emails:
        for i, email in enumerate(emails, 1):
            content += f"\n### Email {i}\n\n"
            content += f"**To:** {email.get('contact_name', 'Unknown')} ({email.get('contact_title', 'N/A')})\n\n"
            content += f"**Subject:** {email.get('subject', 'N/A')}\n\n"
            content += f"**Body:**\n\n{email.get('body', 'N/A')}\n\n**LI Note:** {email.get('li_note', '')}\n"
    else:
        content += "\n*No emails drafted — all contacts require further research and verification.*\n"
    
    # Write file
    filepath.write_text(content)
    log_info(f"  Saved results to {filename}")
    
    return filepath


def update_contacts_csv(index_data):
    """Write flat contacts CSV — one row per contact with email body."""
    results_dir = Path(__file__).parent / "results"
    csv_path = results_dir / "outreach.csv"

    # Load existing rows excluding today's companies (will rewrite them)
    existing_rows = []
    today_companies = {r["company"] for r in index_data}
    if csv_path.exists():
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            existing_rows = [r for r in reader if r["company"] not in today_companies]

    # Parse each company's markdown file for contacts and emails
    new_rows = []
    for entry in index_data:
        company = entry["company"]
        signal = entry["signal"]
        source_url = entry["source_url"]
        md_path = Path(entry["file_path"])
        if not md_path.exists():
            continue

        md = md_path.read_text()

        # Extract contacts from markdown table
        contacts = []
        in_table = False
        for line in md.splitlines():
            if "| Name |" in line:
                in_table = True
                continue
            if in_table and line.startswith("|---"):
                continue
            if in_table and line.startswith("|"):
                parts = [p.strip() for p in line.split("|")[1:-1]]
                if len(parts) >= 4:
                    contacts.append({
                        "name": parts[0],
                        "title": parts[1],
                        "email": parts[3],
                    })
            elif in_table and not line.startswith("|"):
                in_table = False

        # Extract emails from markdown
        emails = {}
        current_contact = None
        current_subject = None
        current_li_note = ""
        current_body_lines = []
        in_body = False
        for line in md.splitlines():
            if line.startswith("### Email"):
                if current_contact and current_subject:
                    emails[current_contact] = {
                        "subject": current_subject,
                        "body": " ".join(current_body_lines).strip(),
                        "li_note": current_li_note
                    }
                current_contact = None
                current_subject = None
                current_li_note = ""
                current_body_lines = []
                in_body = False
            elif line.startswith("**To:**"):
                current_contact = line.replace("**To:**", "").strip().split("(")[0].strip()
            elif line.startswith("**Subject:**"):
                current_subject = line.replace("**Subject:**", "").strip()
            elif line.startswith("**LI Note:**"):
                current_li_note = line.replace("**LI Note:**", "").strip()
                in_body = False
            elif line.startswith("**Body:**"):
                in_body = True
            elif in_body and line.strip():
                current_body_lines.append(line.strip())

        if current_contact and current_subject:
            emails[current_contact] = {
                "subject": current_subject,
                "body": " ".join(current_body_lines).strip(),
                "li_note": current_li_note
            }

        for contact in contacts:
            name = contact["name"]
            email_data = emails.get(name, {})
            new_rows.append({
                "date": entry.get("date", ""),
                "company": company,
                "signal": signal,
                "signal_detail": entry.get("signal_detail", ""),
                "source_url": source_url,
                "contact_name": name,
                "contact_title": contact["title"],
                "contact_email": contact["email"],
                "email_subject": email_data.get("subject", ""),
                "email_body": email_data.get("body", ""),
                "li_note": email_data.get("li_note", ""),
                "verify_demand_gen_linkedin": f"https://www.linkedin.com/search/results/people/?keywords=demand+generation+{company.replace(chr(32), '+')}&origin=GLOBAL_SEARCH_HEADER",
            })

    all_rows = existing_rows + new_rows
    fieldnames = ["date", "company", "signal", "signal_detail", "verify_demand_gen_linkedin", "contact_name", "contact_title", "contact_email", "email_subject", "email_body", "li_note", "source_url"]
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    log_info(f"Updated outreach.csv with {len(new_rows)} contact rows")


def update_index_csv(index_data):
    """Update or create index CSV."""
    results_dir = Path(__file__).parent / "results"
    csv_path = results_dir / "index.csv"
    
    existing_data = []
    if csv_path.exists():
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            existing_data = list(reader)
    
    # Deduplicate: new data overrides existing entries for same company+date
    existing_keys = {(r["date"], r["company"]) for r in index_data}
    existing_data = [r for r in existing_data if (r["date"], r["company"]) not in existing_keys]
    all_data = existing_data + index_data
    
    fieldnames = ["date", "company", "signal", "signal_detail", "contacts_found", "contacts_unverified", "emails_drafted", "source_url", "file_path"]
    with open(csv_path, 'w') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(all_data)
    
    log_info(f"Updated index.csv with {len(index_data)} entries")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log_error(f"Fatal error: {e}")
        sys.exit(1)
