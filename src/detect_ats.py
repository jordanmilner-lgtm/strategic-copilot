import os
import re
import sys
import time
import requests
import gspread
from sheets import get_client, ensure_setup

HEADERS = {'User-Agent': 'Mozilla/5.0'}

ASHBY_RE           = re.compile(r'jobs\.ashbyhq\.com/([a-z0-9][a-z0-9-]*)')
GREENHOUSE_RE      = re.compile(r'(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/([a-z0-9][a-z0-9-]*)')
LEVER_RE           = re.compile(r'jobs\.lever\.co/([a-z0-9][a-z0-9-]*)')
GEM_RE             = re.compile(r'jobs\.gem\.com/([a-z0-9][a-z0-9-]*)')
SMARTRECRUITERS_RE = re.compile(r'jobs\.smartrecruiters\.com/([A-Za-z0-9][A-Za-z0-9-]*)')
ICIMS_RE           = re.compile(r'https?://([a-z0-9][a-z0-9-]*)\.icims\.com')


def _get(url):
    try:
        r = requests.get(url, timeout=10, headers=HEADERS, allow_redirects=True)
        if r.ok:
            return r
    except Exception:
        pass
    return None


def _check_ashby(handle):
    r = _get(f'https://api.ashbyhq.com/posting-api/job-board/{handle}')
    if not r:
        return False
    try:
        return 'jobs' in r.json()
    except Exception:
        return False


def _check_greenhouse(handle):
    r = _get(f'https://boards-api.greenhouse.io/v1/boards/{handle}/jobs')
    if not r:
        return False
    try:
        return 'jobs' in r.json()
    except Exception:
        return False


def _check_lever(handle):
    r = _get(f'https://api.lever.co/v0/postings/{handle}?mode=json')
    if not r:
        return False
    try:
        return isinstance(r.json(), list)
    except Exception:
        return False


def _check_gem(handle):
    r = _get(f'https://api.gem.com/job_board/v0/{handle}/job_posts/')
    if not r:
        return False
    try:
        return isinstance(r.json(), list)
    except Exception:
        return False


def _check_smartrecruiters(handle):
    r = _get(f'https://api.smartrecruiters.com/v1/companies/{handle}/postings?limit=1&status=ACTIVE')
    if not r:
        return False
    try:
        return 'content' in r.json()
    except Exception:
        return False


def _check_icims(handle):
    r = _get(f'https://{handle}.icims.com/jobs/search')
    return r is not None


def _scrape_careers_page(company_name):
    """Fetch the company's careers page and look for ATS links in the HTML."""
    base = re.sub(r'[^a-z0-9]', '', company_name.lower())
    domains = [f'{base}.com', f'{base}.io', f'{base}.ai']

    for domain in domains:
        for path in ['/careers', '/jobs', '/about/careers']:
            r = _get(f'https://www.{domain}{path}')
            if not r:
                r = _get(f'https://{domain}{path}')
            if not r:
                continue

            html = r.text

            m = ASHBY_RE.search(html)
            if m and _check_ashby(m.group(1)):
                return 'ashby', m.group(1)

            m = GREENHOUSE_RE.search(html)
            if m and _check_greenhouse(m.group(1)):
                return 'greenhouse', m.group(1)

            m = LEVER_RE.search(html)
            if m and _check_lever(m.group(1)):
                return 'lever', m.group(1)

            m = GEM_RE.search(html)
            if m and _check_gem(m.group(1)):
                return 'gem', m.group(1)

            m = SMARTRECRUITERS_RE.search(html)
            if m and _check_smartrecruiters(m.group(1)):
                return 'smartrecruiters', m.group(1)

            m = ICIMS_RE.search(html)
            if m and _check_icims(m.group(1)):
                return 'icims', m.group(1)

            time.sleep(0.2)

    return None, None


def detect_ats(company_name):
    base = company_name.lower().strip()
    base = re.sub(r'[^a-z0-9 ]', '', base)

    candidates = []
    if ' ' in base:
        candidates.append(base.replace(' ', '-'))
        candidates.append(base.replace(' ', ''))
    else:
        candidates.append(base)

    # Pass 1: try direct API handle matching
    for handle in candidates:
        if not handle:
            continue
        if _check_ashby(handle):
            return 'ashby', handle
        if _check_greenhouse(handle):
            return 'greenhouse', handle
        if _check_lever(handle):
            return 'lever', handle
        if _check_gem(handle):
            return 'gem', handle
        if _check_smartrecruiters(handle):
            return 'smartrecruiters', handle
        time.sleep(0.2)

    # Pass 2: scrape the company's careers page for ATS links
    return _scrape_careers_page(company_name)


def main():
    sheets_id = os.environ.get('GOOGLE_SHEETS_ID', '').strip()
    if not sheets_id:
        print('ERROR: GOOGLE_SHEETS_ID must be set')
        sys.exit(1)

    client = get_client()
    ensure_setup(client, sheets_id)

    sheet  = client.open_by_key(sheets_id)
    ws     = sheet.worksheet('Config - Companies')
    rows   = ws.get_all_values()

    if not rows:
        print('Config - Companies tab is empty — add company names first')
        return

    headers = rows[0]
    try:
        name_col   = headers.index('Company Name')
        ats_col    = headers.index('ATS Type')
        handle_col = headers.index('ATS Handle')
    except ValueError as e:
        print(f'ERROR: Missing expected column: {e}')
        sys.exit(1)

    detected = 0
    skipped  = 0
    failed   = []
    cells    = []

    for i, row in enumerate(rows[1:], start=2):
        while len(row) <= max(name_col, ats_col, handle_col):
            row.append('')

        name   = row[name_col].strip()
        ats    = row[ats_col].strip()
        handle = row[handle_col].strip()

        if not name:
            continue

        if ats and handle:
            print(f'  {name}: already set ({ats}/{handle}) — skipping')
            skipped += 1
            continue

        print(f'  {name}: detecting...', end=' ', flush=True)
        found_ats, found_handle = detect_ats(name)

        if found_ats:
            cells.append(gspread.Cell(i, ats_col + 1,    found_ats))
            cells.append(gspread.Cell(i, handle_col + 1, found_handle))
            print(f'{found_ats}/{found_handle}')
            detected += 1
        else:
            print('not found — fill in manually')
            failed.append(name)

    if cells:
        ws.update_cells(cells, value_input_option='RAW')

    print(f'\n{"="*40}')
    print(f'Detected:  {detected}')
    print(f'Skipped:   {skipped} (already set)')
    print(f'Not found: {len(failed)}')

    if failed:
        print('\nThese companies could not be detected automatically.')
        print('They may use Workday or another ATS not supported by this system.')
        print('Or their job board handle does not match their company name.')
        print('Check Section A in the README to look up their handle manually:')
        for name in failed:
            print(f'  - {name}')


if __name__ == '__main__':
    main()
