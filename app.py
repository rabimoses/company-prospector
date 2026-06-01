import csv
import json
import os
import signal
import subprocess
import sys
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
    "series_a":  "Series A",
    "ae_spike":  "AE Spike",
    "sdr_spike": "SDR Spike",
    "funding":   "Funding",
    "cro_hire":  "CRO Hire",
    "vp_hire":   "VP Hire",
    "expansion": "Expansion",
}

SIGNAL_COLORS = {
    "series_a":  "#f97316",
    "ae_spike":  "#60a5fa",
    "sdr_spike": "#a78bfa",
    "funding":   "#34d399",
    "cro_hire":  "#fbbf24",
    "vp_hire":   "#fbbf24",
    "expansion": "#22d3ee",
}

# ── run-state helpers ──────────────────────────────────────────────────────────

_current_proc: subprocess.Popen | None = None
_proc_lock = threading.Lock()

def _get_run_state() -> dict:
    try:
        return json.loads(RUN_STATE.read_text()) if RUN_STATE.exists() else {}
    except Exception:
        return {}

def _save_run_state(state: dict):
    RUN_STATE.parent.mkdir(parents=True, exist_ok=True)
    RUN_STATE.write_text(json.dumps(state))

def _estimate_progress(log_lines: list) -> int:
    """Progress tied to what's actually visible in the results list.
    Stays 0 until the first CSV write; then scales with processing.
    Phase 2 board scan progress comes from '... X/Y scanned' log lines."""
    import re
    text = "\n".join(log_lines)

    if "Pushed " in text:
        return 100

    # Phase 2 board scan in progress — scale 65→90% based on scan progress
    board_scan_started = "companies in parallel" in text
    if board_scan_started:
        scan_matches = list(re.finditer(r'\.\.\.?\s*(\d+)/(\d+)\s*scanned', text))
        if scan_matches:
            last = scan_matches[-1]
            done, total = int(last.group(1)), int(last.group(2))
            pct = 65 + int((done / total) * 25) if total > 0 else 65
            return min(pct, 90)
        return 65  # scan started but no progress logged yet

    # Count how many pre-writes have happened (one per phase batch)
    pre_writes = list(re.finditer(r"Pre-wrote (\d+) discovered companies", text))
    if not pre_writes:
        return 0  # Nothing written yet — stopping shows nothing

    # Total companies discovered across all phases
    total_discovered = sum(int(m.group(1)) for m in pre_writes)
    if total_discovered == 0:
        return 0

    # Count fully-processed companies
    writes = text.count("Updated outreach.csv")

    # Phase 1 done = 15%, scale 15→65% as Phase 1 companies are processed
    pct = 15 + int((writes / total_discovered) * 50)
    return min(pct, 65)

def _parse_summary(log_text: str) -> str:
    for line in log_text.splitlines():
        if "Summary:" in line:
            return line.split("Summary:")[-1].strip()
    return ""

def _run_agent_thread():
    global _current_proc
    # Clear the log BEFORE marking as running so stale progress from the
    # previous run is never shown during the first few polls of the new run.
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    RUN_LOG.write_text("")
    _save_run_state({"running": True, "started_at": datetime.utcnow().isoformat()})
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    try:
        with open(RUN_LOG, "w") as log_f:
            with _proc_lock:
                proc = subprocess.Popen(
                    [sys.executable, str(BASE_DIR / "main.py")],
                    stdout=log_f, stderr=subprocess.STDOUT,
                    cwd=str(BASE_DIR), env=env,
                    start_new_session=True,  # own process group so we can kill all children
                )
                _current_proc = proc
            proc.wait()
        with _proc_lock:
            _current_proc = None
        log_text = RUN_LOG.read_text(errors="replace")
        summary  = _parse_summary(log_text)
        error    = "" if proc.returncode == 0 else (
            "Stopped by user." if proc.returncode in (-9, -15) else f"Exit code {proc.returncode}"
        )
        _save_run_state({
            "running": False,
            "finished_at": datetime.utcnow().isoformat(),
            "summary": summary,
            "error": error,
        })
    except Exception as e:
        with _proc_lock:
            _current_proc = None
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
            # Derive company website: use stored value or fall back to name-based guess
            stored_website = row.get("company_website", "")
            if not stored_website:
                slug = name.lower().replace(" ", "").replace(",", "").replace(".", "")
                stored_website = f"https://{slug}.com"
            companies[name] = {
                "name": name,
                "date": row.get("date", ""),
                "signal": row.get("signal", ""),
                "signal_label": SIGNAL_LABELS.get(row.get("signal", ""), row.get("signal", "")),
                "signal_color": SIGNAL_COLORS.get(row.get("signal", ""), "#6b7280"),
                "signal_detail": row.get("signal_detail", ""),
                "source_url": row.get("source_url", ""),
                "company_website": stored_website,
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


@app.route("/reset", methods=["POST"])
def reset_data():
    header = "date,company,company_website,signal,signal_detail,verify_demand_gen_linkedin,contact_name,contact_title,contact_email,email_subject,email_body,li_note,source_url"
    open(OUTREACH_CSV, "w").write(header + "\n")
    open(INDEX_CSV, "w").close()
    open(SEEN_FILE, "w").close()
    return jsonify({"status": "ok", "message": "reset complete"})

@app.route("/")
def index():
    rows        = load_rows()
    all_dates   = sorted({r["date"] for r in rows}, reverse=True)
    all_signals = sorted({r["signal"] for r in rows if r.get("signal")})
    # Default to most recent date so fresh run results are shown immediately
    default_date = all_dates[0] if all_dates else None
    companies    = group_companies(rows, filter_date=default_date)
    companies    = sorted(companies, key=lambda c: c["date"], reverse=True)
    return render_template("index.html",
        companies=companies, all_dates=all_dates, all_signals=all_signals,
        selected_date=default_date, signal_labels=SIGNAL_LABELS,
        total=len(companies), s=get_settings(),
        run_state=_get_run_state(),
    )


@app.route("/date/<run_date>")
def by_date(run_date):
    rows        = load_rows()
    all_dates   = sorted({r["date"] for r in rows}, reverse=True)
    all_signals = sorted({r["signal"] for r in rows if r.get("signal")})
    if run_date == "all":
        companies = group_companies(rows, filter_date=None)
        companies = sorted(companies, key=lambda c: c["date"], reverse=True)
        selected  = None
    else:
        companies = group_companies(rows, filter_date=run_date)
        selected  = run_date
    return render_template("index.html",
        companies=companies, all_dates=all_dates, all_signals=all_signals,
        selected_date=selected, signal_labels=SIGNAL_LABELS,
        total=len(companies), s=get_settings(),
        run_state=_get_run_state(),
    )


@app.route("/cron", methods=["GET", "POST"])
def cron_trigger():
    """Called by cron-job.org daily. Protected by CRON_SECRET env var."""
    secret = os.environ.get("CRON_SECRET", "")
    if secret and request.args.get("secret") != secret:
        return jsonify({"error": "unauthorized"}), 401
    state = _get_run_state()
    if state.get("running"):
        return jsonify({"status": "already running"}), 200
    threading.Thread(target=_run_agent_thread, daemon=True).start()
    return jsonify({"status": "started"}), 200


@app.route("/run", methods=["POST"])
def run_agent():
    state = _get_run_state()
    if state.get("running"):
        return jsonify({"error": "Already running"}), 409
    _apply_settings_from_form(request.form)
    threading.Thread(target=_run_agent_thread, daemon=True).start()
    return jsonify({"started": True})


@app.route("/run/stop", methods=["POST"])
def stop_agent():
    global _current_proc
    with _proc_lock:
        proc = _current_proc
    if proc and proc.poll() is None:
        try:
            # Kill the entire process group (catches child processes too)
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
    # Force state to stopped immediately so UI updates right away
    _save_run_state({
        "running": False,
        "finished_at": datetime.utcnow().isoformat(),
        "error": "Stopped by user.",
    })
    return jsonify({"stopped": True})


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


@app.route("/logs")
def view_logs():
    """Show the full raw log from the last run — useful for debugging."""
    log_text = RUN_LOG.read_text(errors="replace") if RUN_LOG.exists() else "(no log file)"
    state = _get_run_state()
    return f"<pre style='font-family:monospace;font-size:12px;white-space:pre-wrap'><b>Run state:</b> {json.dumps(state, indent=2)}\n\n<b>Log:</b>\n{log_text}</pre>"


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
