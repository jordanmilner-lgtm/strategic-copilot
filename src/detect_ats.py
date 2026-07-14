import re
import time
import requests
import yaml
from store import COMPANIES_PATH

HEADERS = {'User-Agent': 'Mozilla/5.0'}

ASHBY_RE      = re.compile(r'jobs\.ashbyhq\.com/([a-z0-9][a-z0-9-]*)')
GREENHOUSE_RE = re.compile(r'(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/([a-z0-9][a-z0-9-]*)')
LEVER_RE      = re.compile(r'jobs\.lever\.co/([a-z0-9][a-z0-9-]*)')
GEM_RE        = re.compile(r'jobs\.gem\.com/([a-z0-9][a-z0-9-]*)')


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
        time.sleep(0.2)

    # Pass 2: scrape the company's careers page for ATS links
    return _scrape_careers_page(company_name)


def main():
    with open(COMPANIES_PATH, encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}
    companies = data.get('companies', [])

    if not companies:
        print('config/companies.yml is empty — add company names first')
        return

    detected = 0
    skipped  = 0
    failed   = []
    changed  = False

    for c in companies:
        if not isinstance(c, dict):
            continue
        name   = str(c.get('name', '') or '').strip()
        ats    = str(c.get('ats', '') or '').strip()
        handle = str(c.get('handle', '') or '').strip()

        if not name:
            continue

        if ats and handle:
            print(f'  {name}: already set ({ats}/{handle}) — skipping')
            skipped += 1
            continue

        print(f'  {name}: detecting...', end=' ', flush=True)
        found_ats, found_handle = detect_ats(name)

        if found_ats:
            c['ats'] = found_ats
            c['handle'] = found_handle
            c.setdefault('active', 'Y')
            changed = True
            print(f'{found_ats}/{found_handle}')
            detected += 1
        else:
            print('not found — fill in manually')
            failed.append(name)

    if changed:
        with open(COMPANIES_PATH, 'w', encoding='utf-8') as f:
            yaml.safe_dump({'companies': companies}, f, sort_keys=False, allow_unicode=True, width=100)

    print(f'\n{"="*40}')
    print(f'Detected:  {detected}')
    print(f'Skipped:   {skipped} (already set)')
    print(f'Not found: {len(failed)}')

    if failed:
        print('\nThese companies could not be detected automatically.')
        print('They may use Workday, iCIMS, or another ATS not supported by this system.')
        print('Or their job board handle does not match their company name.')
        print('Check Section A in the README to look up their handle manually:')
        for name in failed:
            print(f'  - {name}')


if __name__ == '__main__':
    main()
