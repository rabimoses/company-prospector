"""Email drafting module with verification awareness."""

import sys
from pathlib import Path
from typing import List, Dict

sys.path.insert(0, str(Path(__file__).parent))
from config import EMAIL_SIGNATURE, get_sender_info
from utils import log_info


def draft_emails(company_data: Dict, contacts: List[Dict]) -> List[Dict]:
    """
    Draft personalized outreach emails for each contact.
    
    Rules:
    - Subject line references specific signal (funding, CRO, etc.)
    - Opening line mentions trigger naturally
    - Body positions Jacob as demand gen expert
    - Asks for 20-minute conversation, not job
    - Tone: peer-to-peer, confident
    - Length: 5-7 sentences max
    
    Skip unverified contacts (they need research first).
    """
    emails = []
    
    company_name = company_data.get("name", "Unknown")
    signal = company_data.get("signal", "growth")
    signal_detail = company_data.get("signal_detail", "")
    
    for contact in contacts:
        # Skip unverified contacts — they need research first
        if not contact.get("verified", False):
            log_info(f"  Skipping unverified contact: {contact.get('name')} (needs research)")
            continue
        
        email = draft_email_for_contact(company_data, contact)
        if email:
            emails.append(email)
    
    return emails


def draft_email_for_contact(company_data: Dict, contact: Dict) -> Dict:
    """Draft a personalized email for a specific VERIFIED contact."""
    sender_name, sender_title = get_sender_info()

    company_name = company_data.get("name", "Unknown")
    signal = company_data.get("signal", "growth")
    signal_detail = company_data.get("signal_detail", "")
    contact_name = contact.get("name", "Unknown")
    contact_title = contact.get("title", "Unknown")
    
    # Extract first name from contact name
    first_name = contact_name.split()[0] if " " in contact_name else contact_name
    
    # Generate subject line based on signal
    if signal == "cro_hire":
        subject = f"Welcome to {company_name}, {first_name}"
    elif signal == "funding":
        subject = f"Congrats on the funding, {first_name}"
    elif signal == "cmo_hire":
        subject = f"Congrats on the new role, {first_name}"
    elif signal == "exec_hire":
        subject = f"Welcome to {company_name}, {first_name}"
    elif signal == "ae_spike":
        subject = f"Saw {company_name} is scaling its sales team, {first_name}"
    elif signal == "sdr_spike":
        subject = f"Saw {company_name} is building out its SDR team, {first_name}"
    else:
        subject = f"Connecting with {company_name}"
    
    # Generate opening based on signal and recipient role
    exec_name = company_data.get("exec_name", "")
    is_new_exec = exec_name and first_name.lower() in exec_name.lower()

    if signal == "cro_hire":
        if is_new_exec:
            opening = f"Congrats on the new role, {first_name} — saw the announcement and wanted to reach out before your inbox fills up."
        elif "cmo" in contact_title.lower() or "marketing" in contact_title.lower():
            opening = f"I noticed {company_name} just brought on a new CRO — often a signal that pipeline and demand gen become top priorities. Wanted to reach out."
        else:
            opening = f"I saw {company_name} recently appointed a new CRO and wanted to connect while the team is thinking about go-to-market."
    elif signal == "funding":
        opening = f"Congrats on the recent funding, {first_name} — saw the announcement and wanted to reach out while the momentum is fresh."
    elif signal == "cmo_hire":
        if is_new_exec:
            opening = f"Congrats on the new role, {first_name} — saw the announcement and wanted to reach out before your calendar fills up."
        else:
            opening = f"I noticed {company_name} just brought on a new CMO — usually a signal that demand gen strategy gets revisited quickly. Wanted to connect."
    elif signal == "exec_hire":
        opening = f"Welcome to {company_name}, {first_name}. I noticed your recent appointment and wanted to connect."
    elif signal == "ae_spike":
        opening = f"I noticed {company_name} is actively expanding its AE team — usually a strong signal that pipeline and demand gen are about to become top priorities. Wanted to reach out while the timing is right."
    elif signal == "sdr_spike":
        opening = f"I noticed {company_name} is building out its SDR team — a clear sign that top-of-funnel investment is accelerating. Wanted to connect while the timing is right."
    else:
        opening = f"I came across {company_name} and thought it'd be worth connecting."
    
    # Generate body
    body = f"""{opening}

I lead demand generation strategy for B2B SaaS companies, and I've spent the last several years building pipeline engines that actually move revenue. When teams are scaling like {company_name}, there's typically a moment when demand gen strategy becomes critical — and I thought it might be worth a quick conversation.

No pitch, no process — just 20 minutes to explore if there's a fit. Would you be open to that?

Best,
{sender_name}"""
    
    # LinkedIn connection note (300 char limit)
    if signal == "cro_hire":
        if is_new_exec:
            li_note = f"Congrats on the new role at {company_name}, {first_name}. I lead demand gen for B2B SaaS companies and would love to connect."
        else:
            li_note = f"Hi {first_name} — saw {company_name} just brought on a new CRO. I specialize in demand gen for scaling B2B SaaS teams. Would love to connect."
    elif signal == "cmo_hire":
        if is_new_exec:
            li_note = f"Congrats on the new role at {company_name}, {first_name}. I specialize in demand gen for B2B SaaS and would love to connect early."
        else:
            li_note = f"Hi {first_name} — saw {company_name} just brought on a new CMO. I build demand gen engines for scaling SaaS teams. Would love to connect."
    elif signal == "funding":
        li_note = f"Congrats on the recent funding, {first_name}. I build demand gen engines for B2B SaaS companies at your stage. Would love to connect."
    elif signal == "ae_spike":
        li_note = f"Hi {first_name} — noticed {company_name} is scaling its AE team. I build demand gen engines for B2B SaaS companies at this stage. Would love to connect."
    elif signal == "sdr_spike":
        li_note = f"Hi {first_name} — noticed {company_name} is expanding its SDR team. I specialize in demand gen for scaling B2B SaaS teams. Would love to connect."
    else:
        li_note = f"Hi {first_name} — I lead demand gen strategy for B2B SaaS companies and thought it'd be worth connecting."

    # Trim to 300 chars if needed
    if len(li_note) > 300:
        li_note = li_note[:297] + "..."

    return {
        "subject": subject,
        "body": body,
        "li_note": li_note,
        "contact_name": contact_name,
        "contact_title": contact_title,
        "contact_email": contact.get("email", "N/A"),
    }
