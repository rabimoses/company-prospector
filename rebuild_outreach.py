import csv, re

def make_li_note(company, signal, first_name):
    if signal == "cro_hire":
        note = f"Hi {first_name} — saw {company} just brought on a new CRO. I specialize in demand gen for scaling B2B SaaS teams. Would love to connect."
    elif signal == "funding":
        note = f"Congrats on the recent funding, {first_name}. I build demand gen engines for B2B SaaS companies at your stage. Would love to connect."
    else:
        note = f"Hi {first_name} — I lead demand gen strategy for B2B SaaS companies and thought it'd be worth connecting."
    return note[:297] + "..." if len(note) > 300 else note
from pathlib import Path

results_dir = Path.home() / "company_prospector" / "results"
md_files = sorted(results_dir.glob("2026-03-09_*.md"))
rows = []

for md_path in md_files:
    md = md_path.read_text()
    company = md_path.stem.replace("2026-03-09_", "").replace("_", " ").title()
    signal = ""
    source_url = ""
    for line in md.splitlines():
        if line.startswith("**Signal:**"):
            signal = line.replace("**Signal:**", "").strip()
        if line.startswith("**Source:**"):
            m = re.search(r'\((https?://[^\)]+)\)', line)
            if m:
                source_url = m.group(1)
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
                contacts.append({"name": parts[0], "title": parts[1], "email": parts[3]})
        elif in_table and not line.startswith("|"):
            in_table = False
    emails = {}
    current_contact = current_subject = None
    current_body_lines = []
    in_body = False
    for line in md.splitlines():
        if line.startswith("### Email"):
            if current_contact and current_subject:
                emails[current_contact] = {"subject": current_subject, "body": " ".join(current_body_lines).strip()}
            current_contact = current_subject = None
            current_body_lines = []
            in_body = False
        elif line.startswith("**To:**"):
            current_contact = line.replace("**To:**", "").strip().split("(")[0].strip()
        elif line.startswith("**Subject:**"):
            current_subject = line.replace("**Subject:**", "").strip()
        elif line.startswith("**Body:**"):
            in_body = True
        elif in_body and line.strip():
            current_body_lines.append(line.strip())
    if current_contact and current_subject:
        emails[current_contact] = {"subject": current_subject, "body": " ".join(current_body_lines).strip()}
    for contact in contacts:
        name = contact["name"]
        email_data = emails.get(name, {})
        rows.append({
            "company": company,
            "signal": signal,
            "verify_demand_gen_linkedin": f"https://www.linkedin.com/search/results/people/?keywords=demand+generation+{company.replace(' ', '+')}",
            "contact_name": name,
            "contact_title": contact["title"],
            "contact_email": contact["email"],
            "email_subject": email_data.get("subject", ""),
            "email_body": email_data.get("body", ""),
            "li_note": make_li_note(company, signal, name.split()[0]),
            "source_url": source_url,
        })

fieldnames = ["company", "signal", "verify_demand_gen_linkedin", "contact_name", "contact_title", "contact_email", "email_subject", "email_body", "li_note", "source_url"]
with open(results_dir / "outreach.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
print(f"SUCCESS: {len(rows)} rows written")
