import json
import re
import time
import xml.etree.ElementTree as ET
import requests
from datetime import datetime


def _strip_html(html: str) -> str:
    if not html:
        return ''
    text = re.sub(r'<[^>]+>', ' ', html)
    for entity, char in [('&nbsp;', ' '), ('&amp;', '&'), ('&lt;', '<'), ('&gt;', '>'), ('&quot;', '"')]:
        text = text.replace(entity, char)
    return re.sub(r'\s+', ' ', text).strip()[:8000]


def _get(url: str):
    try:
        resp = requests.get(url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f'    HTTP error fetching {url}: {e}')
        return None


def fetch_ashby(handle: str, company_name: str) -> list:
    data = _get(f'https://api.ashbyhq.com/posting-api/job-board/{handle}?includeCompensation=true')
    if not data:
        return []
    jobs = []
    for item in data.get('jobs', []):
        loc = item.get('location') or {}
        jobs.append({
            'job_title':     item.get('title', ''),
            'company':       company_name,
            'job_url':       item.get('jobUrl', ''),
            'description':   (item.get('descriptionPlain') or _strip_html(item.get('descriptionHtml', '')))[:8000],
            'date_posted':   (item.get('publishedAt') or '')[:10],
            'location_raw':  loc.get('name', '') if isinstance(loc, dict) else str(loc),
        })
    return jobs


def fetch_greenhouse(handle: str, company_name: str) -> list:
    data = _get(f'https://boards-api.greenhouse.io/v1/boards/{handle}/jobs?content=true')
    if not data:
        return []
    jobs = []
    for item in data.get('jobs', []):
        loc = item.get('location') or {}
        jobs.append({
            'job_title':    item.get('title', ''),
            'company':      company_name,
            'job_url':      item.get('absolute_url', ''),
            'description':  _strip_html(item.get('content', ''))[:8000],
            'date_posted':  (item.get('updated_at') or '')[:10],
            'location_raw': loc.get('name', '') if isinstance(loc, dict) else str(loc),
        })
    return jobs


def fetch_lever(handle: str, company_name: str) -> list:
    data = _get(f'https://api.lever.co/v0/postings/{handle}?mode=json')
    if not isinstance(data, list):
        return []
    jobs = []
    for item in data:
        created_ms = item.get('createdAt', 0) or 0
        date_posted = datetime.utcfromtimestamp(created_ms / 1000).strftime('%Y-%m-%d') if created_ms else ''
        cats = item.get('categories') or {}
        jobs.append({
            'job_title':    item.get('text', ''),
            'company':      company_name,
            'job_url':      item.get('hostedUrl', ''),
            'description':  _strip_html(item.get('descriptionPlain') or item.get('description', ''))[:8000],
            'date_posted':  date_posted,
            'location_raw': cats.get('location', '') if isinstance(cats, dict) else '',
        })
    return jobs


def fetch_gem(handle: str, company_name: str) -> list:
    data = _get(f'https://api.gem.com/job_board/v0/{handle}/job_posts/')
    if not isinstance(data, list):
        return []
    jobs = []
    for item in data:
        loc = item.get('location') or {}
        jobs.append({
            'job_title':    item.get('title', ''),
            'company':      company_name,
            'job_url':      item.get('absolute_url', ''),
            'description':  (item.get('content_plain') or _strip_html(item.get('content', '')))[:8000],
            'date_posted':  (item.get('first_published_at') or '')[:10],
            'location_raw': loc.get('name', '') if isinstance(loc, dict) else str(loc),
        })
    return jobs


def fetch_workday(handle: str, company_name: str, seniority_keywords: list = None) -> list:
    # handle format: "{subdomain}.wd{n}/{board}"  e.g. "crowdstrike.wd5/crowdstrikecareers"
    if '/' not in handle:
        print(f'    Workday handle must be "subdomain.wdN/board", got: {handle}')
        return []

    tenant_domain, board = handle.split('/', 1)
    company_slug = tenant_domain.split('.')[0]  # "crowdstrike.wd5" → "crowdstrike"
    base = f'https://{tenant_domain}.myworkdayjobs.com'
    api  = f'{base}/wday/cxs/{company_slug}/{board}'

    # Build pre-filter search string from profile seniority keywords
    _default = ['VP', 'Director', 'Head of', 'Vice President', 'Senior Director']
    terms = seniority_keywords or _default
    search = ' OR '.join(f'"{t}"' if ' ' in t else t for t in terms)

    listings = []
    offset, limit = 0, 20
    while True:
        try:
            resp = requests.post(
                f'{api}/jobs',
                json={'limit': limit, 'offset': offset, 'searchText': search, 'appliedFacets': {}},
                headers={'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/json'},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f'    Workday listing error for {company_name}: {e}')
            break

        batch = data.get('jobPostings', [])
        if not batch:
            break
        listings.extend(batch)
        total = data.get('total', 0)
        offset += limit
        if offset >= total or offset >= 200:  # cap at 200 pre-filtered results
            break
        time.sleep(0.3)

    jobs = []
    for posting in listings:
        ext_path = posting.get('externalPath', '')
        if not ext_path:
            continue
        try:
            detail_resp = requests.get(
                f'{api}{ext_path}',
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=30,
            )
            detail_resp.raise_for_status()
            info = detail_resp.json().get('jobPostingInfo', {})
        except Exception:
            info = {}

        job_url = f'{base}/en-US/{board}{ext_path}'
        jobs.append({
            'job_title':    info.get('title') or posting.get('title', ''),
            'company':      company_name,
            'job_url':      job_url,
            'description':  _strip_html(info.get('jobDescription', ''))[:8000],
            'date_posted':  (info.get('startDate') or '')[:10],
            'location_raw': posting.get('locationsText', ''),
        })
        time.sleep(0.2)

    return jobs


def fetch_smartrecruiters(handle: str, company_name: str) -> list:
    """handle = SmartRecruiters company identifier (e.g. 'TwilioInc')"""
    list_url = f'https://api.smartrecruiters.com/v1/companies/{handle}/postings'

    listings = []
    offset, limit = 0, 100
    while True:
        data = _get(f'{list_url}?limit={limit}&offset={offset}&status=ACTIVE')
        if not data:
            break
        batch = data.get('content', [])
        if not batch:
            break
        listings.extend(batch)
        total = data.get('totalFound', 0)
        offset += limit
        if offset >= total or offset >= 500:
            break
        time.sleep(0.2)

    jobs = []
    for posting in listings[:100]:
        pid = posting.get('id', '')
        if not pid:
            continue

        loc     = posting.get('location') or {}
        city    = loc.get('city') or ''
        country = loc.get('country') or ''
        remote  = loc.get('remote') or False
        loc_str = ', '.join(p for p in [city, country] if p) or ('Remote' if remote else '')
        date_posted = (posting.get('createdon') or '')[:10]
        job_url = f'https://jobs.smartrecruiters.com/{handle}/{pid}'

        detail = _get(f'{list_url}/{pid}')
        description = ''
        if detail:
            sections = ((detail.get('jobAd') or {}).get('sections') or {})
            parts = []
            for key in ('companyDescription', 'jobDescription', 'qualifications', 'additionalInformation'):
                text = (sections.get(key) or {}).get('text') or ''
                if text:
                    parts.append(_strip_html(text))
            description = ' '.join(parts)[:8000]

        jobs.append({
            'job_title':    posting.get('name', ''),
            'company':      company_name,
            'job_url':      job_url,
            'description':  description,
            'date_posted':  date_posted,
            'location_raw': loc_str,
        })
        time.sleep(0.2)

    return jobs


def _icims_discover_urls(handle: str) -> list:
    base = f'https://{handle}.icims.com'
    _NS  = 'http://www.sitemaps.org/schemas/sitemap/0.9'

    def parse_xml(url, depth=0):
        if depth > 3:
            return []
        try:
            resp = requests.get(url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
            if not resp.ok:
                return []
            root = ET.fromstring(resp.content)
            urls = []
            for loc in root.findall(f'.//{{{_NS}}}sitemap/{{{_NS}}}loc'):
                urls.extend(parse_xml(loc.text.strip(), depth + 1))
            for loc in root.findall(f'.//{{{_NS}}}url/{{{_NS}}}loc'):
                u = loc.text.strip()
                if re.search(r'/jobs/\d+/', u):
                    urls.append(u)
            return urls
        except Exception:
            return []

    # Find sitemap via robots.txt or known paths
    sitemap_url = None
    try:
        r = requests.get(f'{base}/robots.txt', timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        if r.ok:
            for line in r.text.splitlines():
                if line.lower().startswith('sitemap:'):
                    sitemap_url = line.split(':', 1)[1].strip()
                    break
    except Exception:
        pass

    if not sitemap_url:
        for path in ['/jobs/sitemap', '/jobs/sitemap.xml', '/sitemap.xml']:
            try:
                r = requests.get(base + path, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
                if r.ok and r.text.strip().startswith('<'):
                    sitemap_url = base + path
                    break
            except Exception:
                pass

    if not sitemap_url:
        return []
    return parse_xml(sitemap_url)


def fetch_icims(handle: str, company_name: str) -> list:
    """handle = iCIMS subdomain (e.g. 'careers-twilio' for careers-twilio.icims.com)"""
    job_urls = _icims_discover_urls(handle)
    if not job_urls:
        print(f'    iCIMS: no job URLs found for {handle}')
        return []

    jobs = []
    for url in job_urls[:50]:
        try:
            resp = requests.get(url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
            if not resp.ok:
                continue
            html = resp.text

            title = date_posted = location = description = ''

            # JSON-LD structured data (most reliable source)
            ld_match = re.search(
                r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>',
                html, re.I,
            )
            if ld_match:
                try:
                    ld          = json.loads(ld_match.group(1))
                    title       = ld.get('title') or ld.get('name') or ''
                    description = _strip_html(ld.get('description') or '')[:8000]
                    date_posted = (ld.get('datePosted') or '')[:10]
                    loc_data    = ld.get('jobLocation') or {}
                    if isinstance(loc_data, list):
                        loc_data = loc_data[0] if loc_data else {}
                    addr     = loc_data.get('address') or {}
                    location = addr.get('addressLocality') or ''
                except Exception:
                    pass

            # Fallbacks for title
            if not title:
                m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
                if m:
                    title = m.group(1).strip()
            if not title:
                m = re.search(r'<title[^>]*>([^<]+)</title>', html, re.I)
                if m:
                    title = m.group(1).strip()
            if not title:
                continue

            if not description:
                description = _strip_html(html)[:8000]

            jobs.append({
                'job_title':    title,
                'company':      company_name,
                'job_url':      url,
                'description':  description,
                'date_posted':  date_posted,
                'location_raw': location,
            })
        except Exception as e:
            print(f'    iCIMS scrape error {url}: {e}')
        time.sleep(0.3)

    return jobs


def fetch_broad_search(query: str, rapidapi_key: str) -> list:
    """Search across LinkedIn/Indeed/Glassdoor via JSearch (RapidAPI)."""
    try:
        resp = requests.get(
            'https://jsearch.p.rapidapi.com/search-v2',
            headers={
                'x-rapidapi-key':  rapidapi_key,
                'x-rapidapi-host': 'jsearch.p.rapidapi.com',
            },
            params={
                'query':       query,
                'page':        '1',
                'num_pages':   '1',
                'country':     'us',
                'date_posted': 'month',
            },
            timeout=30,
        )
        if not resp.ok:
            print(f'    JSearch HTTP {resp.status_code} for "{query}": {resp.text[:200]}')
            return []
        data = resp.json()
        raw_data = data.get('data')
        if isinstance(raw_data, dict):
            raw_items = raw_data.get('jobs') or raw_data.get('results') or []
        elif isinstance(raw_data, list):
            raw_items = raw_data
        else:
            raw_items = []
        print(f'    JSearch: {len(raw_items)} results')
    except Exception as e:
        print(f'    JSearch exception for "{query}": {type(e).__name__}: {str(e)[:200]}')
        return []

    jobs = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        location = 'Remote' if item.get('job_is_remote') else ''
        # search-v2 uses job_posted_at (ISO string or epoch); extract date portion
        posted_raw = item.get('job_posted_at') or item.get('job_posted_at_datetime_utc') or ''
        posted = str(posted_raw)[:10] if posted_raw else ''

        jobs.append({
            'job_title':    item.get('job_title', ''),
            'company':      item.get('employer_name', ''),
            'job_url':      item.get('job_apply_link') or item.get('job_url', ''),
            'description':  (item.get('job_description') or '')[:8000],
            'date_posted':  posted,
            'location_raw': location,
        })

    return jobs


FETCHERS = {
    'ashby':            fetch_ashby,
    'greenhouse':       fetch_greenhouse,
    'lever':            fetch_lever,
    'gem':              fetch_gem,
    'workday':          fetch_workday,
    'smartrecruiters':  fetch_smartrecruiters,
    'icims':            fetch_icims,
}
