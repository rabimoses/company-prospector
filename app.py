import csv
import json
import os
import subprocess
import threading
from datetime import date, datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request, redirect, url_for, flash
from settings_manager import get_settings, save_settings

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "prospector-dev-key")

BASE_DIR   = Path(__file__).parent
CSV_PATH   = BASE_DIR / "results" / "outreach.csv"
RUN_LOG    = BASE_DIR / "results" / ".run_log.txt"
RUN_STATE  = BASE_DIR / "results" / ".run_state.json"

SIGNAL_LABELS = {
    "ae_spike":  "AE Spike",
    "sdr_spike": "SDR Spike",
    "funding":   "Funding",
    "cro_hire":  "CRO Hire",
    "vp_hire":   "VP Hire",
    "expansion": "Expansion",
}

SIGNAL_COLORS = {
    "ae_spike":  "#60a5fa",
    "sdr_spike": "#a78bfa",
    "funding":   "#34d399",
    "cro_hire":  "#fbbf24",
    "vp_hire":   "#fbbf24",
    "expansion": "#22d3ee",
}

# ── run-state helpers ──────────────────────────────────────────────────────────

def _get_run_state() -> dict:
    try:
        return json.loads(RUN_STATE.read_text()) if RUN_STATE.exists() else {}
    except Exception:
        return {}

def _save_run_state(state: dict):
    RUN_STATE.parent.mkdir(parents=True, exist_ok=True)
    RUN_STATE.write_text(json.dumps(state))

# Progress milestones: (log substring, pct)
_MILESTONES = [
    ("Starting prospecting run",  5),
    ("SERPER.DEV LIVE SEARCH",   10),
    ("Scanning Greenhouse",       25),
    ("Total companies to scan",   38),
    ("TOTAL:",                    52),
    ("Processing ",               58),
    ("Drafting",                  70),
    ("Updated outreach.csv",      85),
    ("Telegram notification",     93),
    ("Pushed ",                  100),
]

def _estimate_progress(log_lines: list) -> int:
    text = "\n".join(log_lines)
    pct = 0
    for substring, val in _MILESTONES:
        if substring in text:
            pct = val
    return pct

def _parse_summary(log_text: str) -> str:
    for line in log_text.splitlines():
        if "Summary:" in line:
            return line.split("Summary:")[-1].strip()
    return ""

def _run_agent_thread():
    _save_run_state({"running": True, "started_at": datetime.utcnow().isoformat()})
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    try:
        with open(RUN_LOG, "w") as log_f:
            proc = subprocess.Popen(
                ["python3", str(BASE_DIR / "main.py")],
                stdout=log_f, stderr=subprocess.STDOUT,
                cwd=str(BASE_DIR), env=env,
            )
            proc.wait()
        log_text = RUN_LOG.read_text(errors="replace")
        summary  = _parse_summary(log_text)
        error    = "" if proc.returncode == 0 else f"Exit code {proc.returncode}"
        _save_run_state({
            "running": False,
            "finished_at": datetime.utcnow().isoformat(),
            "summary": summary,
            "error": error,
        })
    except Exception as e:
        _save_run_state({"running": False, "error": str(e)})

def _apply_settings_from_form(f):
    s = get_settings()
    s["signals_enabled"] = f.getlist("signals_enabled")
    for key in ("ae_min_absolute", "sdr_min_absolute", "max_total_roles", "recent_days",
                "max_contacts_per_company"):
        try:
            s[key] = int(f.get(key, s[key]))
        except (ValueError, TypeError):
            pass
    try:
        s["spike_growth_pct"] = round(float(f.get("spike_growth_pct", s["spike_growth_pct"] * 100)) / 100, 4)
    except (ValueError, TypeError):
        pass
    s["sender_name"]  = f.get("sender_name",  s["sender_name"]).strip()
    s["sender_title"] = f.get("sender_title", s["sender_title"]).strip()
    titles_raw   = f.get("contact_titles", "")
    s["contact_titles"] = [t.strip() for t in titles_raw.splitlines() if t.strip()]
    blocklist_raw = f.get("blocklist_companies", "")
    s["blocklist_companies"] = [w.strip().lower() for w in blocklist_raw.splitlines() if w.strip()]
    save_settings(s)

# ── routes ─────────────────────────────────────────────────────────────────────

def load_rows():
    if not CSV_PATH.exists():
        return []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def group_companies(rows, filter_date=None):
    companies = {}
    for row in rows:
        if filter_date and row.get("date") != filter_date:
            continue
        name = row["company"]
        if name not in companies:
            companies[name] = {
                "name": name,
                "date": row.get("date", ""),
                "signal": row.get("signal", ""),
                "signal_label": SIGNAL_LABELS.get(row.get("signal", ""), row.get("signal", "")),
                "signal_color": SIGNAL_COLORS.get(row.get("signal", ""), "#6b7280"),
                "signal_detail": row.get("signal_detail", ""),
                "source_url": row.get("source_url", ""),
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
    rows       = load_rows()
    today      = date.today().isoformat()
    all_dates  = sorted({r["date"] for r in rows}, reverse=True)
    all_signals = sorted({r["signal"] for r in rows if r.get("signal")})
    selected   = all_dates[0] if all_dates else today
    companies  = group_companies(rows, filter_date=selected)
    return render_template("index.html",
        companies=companies, all_dates=all_dates, all_signals=all_signals,
        selected_date=selected, signal_labels=SIGNAL_LABELS,
        total=len(companies), s=get_settings(),
        run_state=_get_run_state(),
    )


@app.route("/date/<run_date>")
def by_date(run_date):
    rows        = load_rows()
    all_dates   = sorted({r["date"] for r in rows}, reverse=True)
    all_signals = sorted({r["signal"] for r in rows if r.get("signal")})
    companies   = group_companies(rows, filter_date=run_date)
    return render_template("index.html",
        companies=companies, all_dates=all_dates, all_signals=all_signals,
        selected_date=run_date, signal_labels=SIGNAL_LABELS,
        total=len(companies), s=get_settings(),
        run_state=_get_run_state(),
    )


@app.route("/run", methods=["POST"])
def run_agent():
    state = _get_run_state()
    if state.get("running"):
        return jsonify({"error": "Already running"}), 409
    _apply_settings_from_form(request.form)
    threading.Thread(target=_run_agent_thread, daemon=True).start()
    return jsonify({"started": True})


@app.route("/run/status")
def run_status():
    state = _get_run_state()
    log_lines = []
    if RUN_LOG.exists():
        raw = RUN_LOG.read_text(errors="replace").splitlines()
        # Strip timestamp prefix for display
        log_lines = [
            l.split("] ", 1)[-1] if "] " in l else l
            for l in raw if l.strip()
        ]
    progress = 100 if not state.get("running") and state.get("finished_at") else _estimate_progress(log_lines)
    return jsonify({
        "running":  state.get("running", False),
        "progress": progress,
        "log_tail": log_lines[-18:],
        "summary":  state.get("summary", ""),
        "error":    state.get("error", ""),
        "finished": bool(state.get("finished_at") and not state.get("running")),
    })


@app.route("/settings", methods=["GET"])
def settings_page():
    s = get_settings()
    return render_template("settings.html", s=s)


@app.route("/settings", methods=["POST"])
def settings_save():
    _apply_settings_from_form(request.form)
    flash("Settings saved.")
    return redirect(url_for("settings_page"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
