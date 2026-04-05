import csv
import os
from datetime import date
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash
from settings_manager import get_settings, save_settings

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "prospector-dev-key")

CSV_PATH = Path(__file__).parent / "results" / "outreach.csv"

SIGNAL_LABELS = {
    "ae_spike": "AE Spike",
    "sdr_spike": "SDR Spike",
    "funding": "Funding",
    "cro_hire": "CRO Hire",
    "vp_hire": "VP Hire",
    "expansion": "Expansion",
}

SIGNAL_COLORS = {
    "ae_spike": "#60a5fa",
    "sdr_spike": "#a78bfa",
    "funding": "#34d399",
    "cro_hire": "#fbbf24",
    "vp_hire": "#fbbf24",
    "expansion": "#22d3ee",
}


def load_rows():
    if not CSV_PATH.exists():
        return []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def group_companies(rows, filter_date=None, filter_signal=None):
    companies = {}
    for row in rows:
        if filter_date and row["date"] != filter_date:
            continue
        if filter_signal and row["signal"] != filter_signal:
            continue
        name = row["company"]
        if name not in companies:
            companies[name] = {
                "name": name,
                "date": row["date"],
                "signal": row["signal"],
                "signal_label": SIGNAL_LABELS.get(row["signal"], row["signal"]),
                "signal_color": SIGNAL_COLORS.get(row["signal"], "#6b7280"),
                "signal_detail": row["signal_detail"],
                "source_url": row["source_url"],
                "verify_linkedin": row.get("verify_demand_gen_linkedin", ""),
                "contacts": [],
            }
        contact_name = row.get("contact_name", "")
        if contact_name and contact_name != "Contact not found":
            companies[name]["contacts"].append({
                "name": contact_name,
                "title": row.get("contact_title", ""),
                "email": row.get("contact_email", ""),
                "email_subject": row.get("email_subject", ""),
                "email_body": row.get("email_body", ""),
                "li_note": row.get("li_note", ""),
            })
    return list(companies.values())


@app.route("/")
def index():
    rows = load_rows()
    today = date.today().isoformat()

    # Dates available
    all_dates = sorted({r["date"] for r in rows}, reverse=True)
    all_signals = sorted({r["signal"] for r in rows if r["signal"]})

    # Default to most recent date
    selected_date = all_dates[0] if all_dates else today
    companies = group_companies(rows, filter_date=selected_date)

    return render_template(
        "index.html",
        companies=companies,
        all_dates=all_dates,
        all_signals=all_signals,
        selected_date=selected_date,
        signal_labels=SIGNAL_LABELS,
        total=len(companies),
    )


@app.route("/date/<run_date>")
def by_date(run_date):
    rows = load_rows()
    all_dates = sorted({r["date"] for r in rows}, reverse=True)
    all_signals = sorted({r["signal"] for r in rows if r["signal"]})
    companies = group_companies(rows, filter_date=run_date)
    return render_template(
        "index.html",
        companies=companies,
        all_dates=all_dates,
        all_signals=all_signals,
        selected_date=run_date,
        signal_labels=SIGNAL_LABELS,
        total=len(companies),
    )


@app.route("/settings", methods=["GET"])
def settings_page():
    s = get_settings()
    return render_template("settings.html", s=s)


@app.route("/settings", methods=["POST"])
def settings_save():
    f = request.form
    s = get_settings()

    # Signals enabled
    s["signals_enabled"] = f.getlist("signals_enabled")

    # Numeric thresholds
    for key in ("ae_min_absolute", "sdr_min_absolute", "max_total_roles"):
        try:
            s[key] = int(f.get(key, s[key]))
        except (ValueError, TypeError):
            pass
    for key in ("spike_growth_pct",):
        try:
            s[key] = round(float(f.get(key, s[key] * 100)) / 100, 4)
        except (ValueError, TypeError):
            pass
    try:
        s["recent_days"] = int(f.get("recent_days", s["recent_days"]))
    except (ValueError, TypeError):
        pass
    try:
        s["max_contacts_per_company"] = int(f.get("max_contacts_per_company", s["max_contacts_per_company"]))
    except (ValueError, TypeError):
        pass

    # Text fields
    s["sender_name"] = f.get("sender_name", s["sender_name"]).strip()
    s["sender_title"] = f.get("sender_title", s["sender_title"]).strip()

    # List fields (one item per line)
    titles_raw = f.get("contact_titles", "")
    s["contact_titles"] = [t.strip() for t in titles_raw.splitlines() if t.strip()]

    blocklist_raw = f.get("blocklist_companies", "")
    s["blocklist_companies"] = [w.strip().lower() for w in blocklist_raw.splitlines() if w.strip()]

    save_settings(s)
    flash("Settings saved.")
    return redirect(url_for("settings_page"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
