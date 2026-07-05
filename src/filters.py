from datetime import datetime, timedelta

NON_US = [
    'united kingdom', 'london', 'england', 'scotland', 'ireland', 'edinburgh', 'manchester',
    'germany', 'berlin', 'munich', 'frankfurt', 'hamburg',
    'france', 'paris', 'lyon',
    'netherlands', 'amsterdam', 'sweden', 'stockholm',
    'spain', 'madrid', 'barcelona', 'italy', 'milan', 'rome',
    'switzerland', 'zurich', 'geneva',
    'india', 'bangalore', 'bengaluru', 'mumbai', 'delhi', 'hyderabad', 'pune', 'chennai', 'gurgaon',
    'singapore', 'hong kong', 'australia', 'sydney', 'melbourne',
    'japan', 'tokyo', 'china', 'beijing', 'shanghai',
    'canada', 'toronto', 'vancouver', 'montreal',
    'israel', 'tel aviv', 'poland', 'warsaw', 'krakow',
    'brazil', 'sao paulo', 'mexico city',
    'emea', 'apac', 'latam', 'europe', 'asia pacific', 'asia-pacific', ', uk', '- uk',
]

SENIORITY = [
    'head of', 'vp ', 'vp,', 'vice president', 'director', 'chief',
    'principal', 'managing director', 'general manager',
]

SKIP_FUNCTIONS = [
    'engineer', 'devops', 'backend', 'frontend', 'fullstack', 'full-stack', 'qa ', 'sre ',
    'design', 'scientist', 'researcher', ' research', ' legal', 'counsel', 'attorney',
    'compliance', 'governance', 'regulatory', 'finance', 'financial', 'treasury',
    'accounting', 'controllership', 'procurement', 'tax ', 'compensation', 'benefits',
    'recruiter', 'recruiting', 'talent acquisition', 'brand ', 'content director',
    'creative director', 'communications', 'public relation', 'cybersecurity',
    'information security', 'security operation', 'supply chain', 'logistics',
    'facilities', 'real estate', 'data science', 'machine learning', 'clinical', 'medical',
]

TARGET_FUNCTIONS = [
    'gtm', 'go-to-market', 'go to market', 'sales', 'revenue', 'commercial',
    'product ops', 'product operations', 'product strategy', 'business ops',
    'business operations', 'business development', 'operations', ' ops', 'strategy',
    'strategic', 'transformation', 'enablement', 'customer success', 'customer experience',
    'partnerships', 'alliances', 'biz dev', 'ai strategy', 'ai lead', 'enterprise',
    'growth', 'chief of staff', 'value', 'market', 'field ',
]


def is_too_old(job: dict, days: int = 30) -> bool:
    date_str = (job.get('date_posted') or '')[:10]
    if not date_str:
        return False
    try:
        return datetime.strptime(date_str, '%Y-%m-%d') < datetime.utcnow() - timedelta(days=days)
    except ValueError:
        return False


def _is_non_us(loc: str) -> bool:
    if not loc:
        return False
    loc = loc.strip().lower()
    if 'remote' in loc:
        return False
    last_three = loc[-3:]
    if len(last_three) == 3 and last_three[0] == ' ' and last_three[1:].isalpha() and last_three != ' us':
        return True
    return any(k in loc for k in NON_US)


def passes_title_filter(job: dict) -> bool:
    title = (job.get('job_title') or '').lower()
    loc   = (job.get('location_raw') or '').strip().lower()

    if _is_non_us(loc):
        return False

    has_seniority = any(s in title for s in SENIORITY)
    has_skip      = any(s in title for s in SKIP_FUNCTIONS)
    has_target    = any(f in title for f in TARGET_FUNCTIONS)

    return has_seniority and not has_skip and has_target
