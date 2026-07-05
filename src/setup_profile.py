import os
import sys
import json
import re
import anthropic
from sheets import get_client, ensure_setup

SETUP_PROMPT = """You are helping set up an automated job search screening system.
Based on the resume and sample job descriptions provided, generate a scoring profile.

RESUME:
{resume}

SAMPLE JOB DESCRIPTIONS:
{jobs}

Generate a profile with these exact fields. Be specific and concrete — generic anchors and keywords produce poor screening results.

Output ONLY a valid JSON object with these exact keys:
{{
  "background": "2-3 sentences describing this person's seniority level, professional background, and what they do. Be specific (e.g. VP-level, GTM/product ops, B2B SaaS).",
  "anchors": "4-6 architectural anchors — specific, distinctive things this person does that are hard for others to claim, separated by |  e.g. Built GTM motion from 0 to $50M ARR | Designed product-led growth strategy across enterprise segments",
  "keywords": "15-20 keywords that signal a strong fit when they appear in a job posting, comma-separated e.g. go-to-market strategy, revenue operations, sales velocity, GTM orchestration",
  "negative_signals": "5-8 things that look right on the surface but signal poor fit, separated by | e.g. Pure sales quota role with no strategy component | Individual contributor with no team scope",
  "comp_target": ""
}}

Infer anchors from specific accomplishments described in the resume, not generic role descriptions.
Infer negative signals from the close-but-not-quite job examples — what makes those not quite right?"""


def _read_file(path):
    try:
        with open(path, encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


def _read_stdin(label):
    print(f'\n{label}')
    print('Paste below. Type END on its own line when done:\n')
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == 'END':
            break
        lines.append(line)
    return '\n'.join(lines).strip()


def main():
    api_key   = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    sheets_id = os.environ.get('GOOGLE_SHEETS_ID', '').strip()

    if not api_key or not sheets_id:
        print('ERROR: ANTHROPIC_API_KEY and GOOGLE_SHEETS_ID must be set')
        sys.exit(1)

    # File mode (GitHub Actions) falls back to interactive (local)
    resume = _read_file('setup/resume.txt')
    jobs   = _read_file('setup/sample_jobs.txt')

    if not resume:
        resume = _read_stdin('RESUME — paste your full resume:')
    if not jobs:
        jobs = _read_stdin(
            'SAMPLE JOB DESCRIPTIONS — paste 3-5 postings '
            '(2-3 strong fits and 1-2 close-but-not-quite):'
        )

    if not resume or not jobs:
        print('ERROR: Both resume and sample job descriptions are required')
        sys.exit(1)

    print('\nGenerating scoring profile with Claude...')
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=2048,
        messages=[{
            'role': 'user',
            'content': SETUP_PROMPT.format(resume=resume[:15000], jobs=jobs[:20000]),
        }],
    )

    text = response.content[0].text
    match = re.search(r'\{[\s\S]*\}', text)
    if not match:
        print('ERROR: Could not parse Claude response')
        print(text)
        sys.exit(1)

    try:
        profile = json.loads(match.group())
    except json.JSONDecodeError as e:
        print(f'ERROR: Invalid JSON in Claude response: {e}')
        print(text)
        sys.exit(1)

    print('\nGenerated profile:')
    for key, val in profile.items():
        display = (val[:120] + '...') if len(str(val)) > 120 else val
        print(f'  {key}: {display}')

    print('\nWriting to Google Sheets...')
    sheets_client = get_client()
    ensure_setup(sheets_client, sheets_id)

    sheet = sheets_client.open_by_key(sheets_id)
    ws = sheet.worksheet('Config - Profile')
    ws.clear()
    ws.update(
        [
            ['Field', 'Value'],
            ['Background',       profile.get('background', '')],
            ['Anchors',          profile.get('anchors', '')],
            ['Keywords',         profile.get('keywords', '')],
            ['Negative Signals', profile.get('negative_signals', '')],
            ['Comp Target',      ''],
            ['Score Threshold',  '6'],
        ],
        value_input_option='RAW',
    )

    print('Done. Profile written to Config - Profile tab.')
    print('\nNext steps:')
    print('  1. Open your Google Sheet → Config - Profile and review the output')
    print('  2. Optionally fill in the Comp Target row (e.g. $300K-$400K OTE) — leave blank to skip compensation filtering')
    print('  3. Delete setup/resume.txt and setup/sample_jobs.txt from your repo')
    print('  4. You are ready to run your first scan')


if __name__ == '__main__':
    main()
