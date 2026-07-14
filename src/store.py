"""File-based storage: config lives in config/*.yml, results in data/*.json.

Replaces the former Google Sheets backend. All paths are relative to the
repo root so the scripts work both locally and in GitHub Actions.
"""
import json
import os
from datetime import datetime, timezone

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

COMPANIES_PATH   = os.path.join(ROOT, 'config', 'companies.yml')
PROFILE_PATH     = os.path.join(ROOT, 'config', 'profile.yml')
JOBS_PATH        = os.path.join(ROOT, 'data', 'jobs.json')
SCORED_URLS_PATH = os.path.join(ROOT, 'data', 'scored_urls.json')

RESULTS_HEADERS = [
    'Job Title', 'Company', 'Job URL', 'Source Lane', 'Date Posted', 'Days Since Posted',
    'Fit Score', 'Abstract Fit Flag', 'Scope Flag', 'Comp Signal',
    'Corporate Bottleneck', 'Strategic Thesis', 'Status',
]


def _read_yaml(path):
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def _read_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')


def load_companies() -> list:
    """Active companies as dicts with the same keys main.py already uses."""
    data = _read_yaml(COMPANIES_PATH)
    companies = []
    for c in data.get('companies', []):
        if not isinstance(c, dict):
            continue
        if str(c.get('active', 'Y')).strip().upper() in ('N', 'FALSE', 'NO'):
            continue
        companies.append({
            'Company Name':       str(c.get('name', '')).strip(),
            'ATS Type':           str(c.get('ats', '')).strip(),
            'ATS Handle':         str(c.get('handle', '')).strip(),
            'Seniority Override': str(c.get('seniority_override', '') or '').strip(),
        })
    return companies


def load_profile() -> dict:
    profile = _read_yaml(PROFILE_PATH)
    return {k: str(v).strip() for k, v in profile.items() if v is not None and str(v).strip()}


def save_profile(profile: dict):
    os.makedirs(os.path.dirname(PROFILE_PATH), exist_ok=True)
    with open(PROFILE_PATH, 'w', encoding='utf-8') as f:
        yaml.safe_dump(profile, f, sort_keys=False, allow_unicode=True, width=100)


def read_seen_urls() -> set:
    return set(_read_json(SCORED_URLS_PATH, []))


def append_scored_urls(urls: list):
    if not urls:
        return
    seen = _read_json(SCORED_URLS_PATH, [])
    known = set(seen)
    seen.extend(u for u in urls if u not in known)
    _write_json(SCORED_URLS_PATH, seen)


def append_results(jobs: list):
    """Merge newly qualifying jobs into data/jobs.json (newest first)."""
    if not jobs:
        return
    data = _read_json(JOBS_PATH, {'generated_at': None, 'jobs': []})
    existing_urls = {j.get('Job URL') for j in data.get('jobs', [])}
    new_rows = [
        {h: job.get(h, '') for h in RESULTS_HEADERS}
        for job in jobs
        if job.get('Job URL') not in existing_urls
    ]
    data['jobs'] = new_rows + data.get('jobs', [])
    data['generated_at'] = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    _write_json(JOBS_PATH, data)
