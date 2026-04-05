"""Central settings — reads/writes settings.json, falls back to defaults."""

import json
from pathlib import Path

SETTINGS_FILE = Path(__file__).parent / "settings.json"

DEFAULTS = {
    # Which signal types to run
    "signals_enabled": ["ae_spike", "sdr_spike", "funding", "cro_hire"],

    # AE/SDR spike thresholds
    "ae_min_absolute": 2,
    "sdr_min_absolute": 2,
    "spike_growth_pct": 0.50,
    "recent_days": 45,

    # Company size filter (min is auto-derived from spike thresholds)
    "max_total_roles": 100,

    # Email / sender
    "sender_name": "Jacob Landsman",
    "sender_title": "Demand Generation Leader",
    "max_contacts_per_company": 5,
    "contact_titles": [
        "CRO", "Chief Revenue Officer",
        "CMO", "Chief Marketing Officer",
        "CEO", "Co-Founder",
        "VP Marketing", "VP Demand Generation",
    ],

    # Companies to exclude from all results (blocklist)
    "blocklist_companies": [],
}


def get_settings() -> dict:
    if not SETTINGS_FILE.exists():
        return DEFAULTS.copy()
    with open(SETTINGS_FILE, encoding="utf-8") as f:
        saved = json.load(f)
    merged = DEFAULTS.copy()
    merged.update(saved)
    return merged


def save_settings(settings: dict) -> None:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
