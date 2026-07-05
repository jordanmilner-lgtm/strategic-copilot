import json
import re
import time
import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


def _build_prompt(job: dict, profile: dict) -> str:
    anchors  = '\n'.join(f'- {a.strip()}' for a in profile.get('anchors', '').split('|') if a.strip())
    keywords = profile.get('keywords', '')
    neg      = '\n'.join(f'- {s.strip()}' for s in profile.get('negative_signals', '').split('|') if s.strip())
    comp     = profile.get('comp_target', 'not specified')

    comp_line = f'IN_RANGE (likely {comp}) | BELOW_RANGE | NOT_LISTED' if comp and comp != 'not specified' else 'NOT_LISTED (compensation not specified — do not penalize)'

    return f"""You are the Automated Screening Node for Jordan Milner's executive job search engine.

Analyze this job posting and output ONLY a valid JSON object. No markdown fences, no explanation, no other text.

Job Title: {job['job_title']}
Company: {job['company']}
Job URL: {job['job_url']}
Date Posted: {job['date_posted']}

Job Description:
{job['description']}

CANDIDATE PROFILE:
{profile.get('background', '')}

Architectural strengths:
{anchors}

KEYWORD TRIGGERS (boost score toward 8–10 when present):
{keywords}

SCORING SCALE — fit_score must be an integer from 1 to 10. Do not exceed 10.
- 9-10: VP/Director/Head of role with mandate squarely in GTM Strategy, Product Operations, Value Engineering, Business Transformation, AI Transformation, or Digital Transformation — at a B2B SaaS/Cloud/AI company OR any organization where the transformation mandate is GTM/Sales/RevOps-focused and the candidate's cloud/enterprise background directly applies.
- 7-8: VP/Director/Head of role in adjacent strategic function (Revenue Operations, Sales Strategy, Customer Strategy, AI Strategy & Operations) at a relevant company; OR a strong AI/digital transformation role where the mandate is enterprise-wide process redesign.
- 5-6: Promising but scope is unclear, slightly below target level, or a stretch.
- 3-4: Adjacent function or below-target level. Unlikely strong match.
- 1-2: Wrong function, wrong level, or wrong industry.

STRONG NEGATIVE SIGNALS — each one meaningfully pushes the score down toward 1-4:
{neg}

SCOPE PARAMETERS:
MATCH — title is VP, Senior Director, Director, or Head of AND reports to C-suite or VP+
BELOW — Manager, IC, or unclear seniority
UNCLEAR — reporting structure not mentioned

ABSTRACT FIT FLAG — answer YES or NO only:
YES: Role is VP/Director/Head of level AND mandate maps directly to GTM Strategy, Product Operations, Value Engineering, Business/AI/Digital Transformation, or Strategic Operations AND the candidate's cloud/enterprise/GTM background directly applies.
NO: Anything else — adjacent function, IC-level, or mixed signals.

COMPENSATION:
{comp_line}

Output ONLY this JSON, nothing else:
{{
  "job_title": "exact title from posting",
  "company": "company name",
  "job_url": "{job['job_url']}",
  "date_posted": "{job['date_posted']}",
  "fit_score": 5,
  "abstract_fit_flag": "YES",
  "scope_flag": "MATCH",
  "comp_signal": "NOT_LISTED",
  "inferred_corporate_bottleneck": "one sentence: what business pain is this role solving",
  "strategic_alignment_thesis": "two sentences: why candidate is or is not a strong fit"
}}"""


def _parse(text: str, job_url: str) -> dict:
    match = re.search(r'\{[\s\S]*\}', text)
    if not match:
        return {'Job URL': job_url, 'Fit Score': 0}
    try:
        p = json.loads(match.group())
    except json.JSONDecodeError:
        return {'Job URL': job_url, 'Fit Score': 0}

    fit_flag  = 'YES' if (p.get('abstract_fit_flag') or '').upper() == 'YES' else 'NO'
    raw_comp  = (p.get('comp_signal') or '').upper()
    comp      = 'IN_RANGE' if raw_comp == 'IN_RANGE' else ('BELOW_RANGE' if raw_comp == 'BELOW_RANGE' else 'NOT_LISTED')

    return {
        'Job Title':            p.get('job_title', ''),
        'Company':              p.get('company', ''),
        'Job URL':              p.get('job_url') or job_url,
        'Source Lane':          'Lane 1 - Target',
        'Date Posted':          p.get('date_posted', ''),
        'Fit Score':            int(p.get('fit_score', 0) or 0),
        'Abstract Fit Flag':    fit_flag,
        'Scope Flag':           p.get('scope_flag', ''),
        'Comp Signal':          comp,
        'Corporate Bottleneck': p.get('inferred_corporate_bottleneck', ''),
        'Strategic Thesis':     p.get('strategic_alignment_thesis', ''),
        'Status':               'New',
    }


def score_jobs(jobs: list, profile: dict, api_key: str) -> list:
    client = anthropic.Anthropic(api_key=api_key)
    results = []

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=5, max=60),
        retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.APIConnectionError)),
        reraise=True,
    )
    def _call(prompt: str) -> str:
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=1024,
            messages=[{'role': 'user', 'content': prompt}],
        )
        return msg.content[0].text

    for i, job in enumerate(jobs):
        url = job.get('job_url', '')
        try:
            text = _call(_build_prompt(job, profile))
            results.append(_parse(text, url))
        except Exception as e:
            print(f'    Scoring error for {url}: {e}')
            results.append({'Job URL': url, 'Fit Score': 0})

        if i < len(jobs) - 1:
            time.sleep(0.3)

    return results
