import os
import sys
import json
import re
import anthropic
from sheets import get_client, ensure_setup, load_profile

PROMPT = """You are helping a job seeker set up automated job board search queries.

Based on their scoring profile below, generate 8-10 search query strings optimized for job board search engines (LinkedIn, Indeed, Glassdoor).

PROFILE:
Background: {background}
Seniority Level: {seniority_keywords}
Target Functions: {target_functions}
Keywords: {keywords}

Requirements:
- Each query combines a seniority level + a specific role type or function
- Write them as natural job title searches — the way a recruiter would title the role
- Vary the combinations — don't repeat the same words in every query
- Specific enough to filter noise, broad enough to surface relevant roles
- Think about how these roles are actually titled at companies (e.g. "Head of Revenue Operations" not "GTM Ops Leader")
- Do NOT include location — the system handles that separately

Output ONLY a valid JSON array of strings, no explanation, no markdown:
["query 1", "query 2", ...]"""


def main():
    api_key   = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    sheets_id = os.environ.get('GOOGLE_SHEETS_ID', '').strip()

    if not api_key or not sheets_id:
        print('ERROR: ANTHROPIC_API_KEY and GOOGLE_SHEETS_ID must be set')
        sys.exit(1)

    sheets_client = get_client()
    ensure_setup(sheets_client, sheets_id)
    profile = load_profile(sheets_client, sheets_id)

    if not profile.get('background'):
        print('ERROR: No profile found in Config - Profile tab.')
        print('Run the Build Scoring Profile workflow first (Step 5 in the README).')
        sys.exit(1)

    print('Reading profile from Google Sheets...')
    print(f'  Background: {profile.get("background", "")[:80]}...')

    print('\nGenerating search terms with Claude...')
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=1024,
        messages=[{
            'role': 'user',
            'content': PROMPT.format(
                background=profile.get('background', ''),
                seniority_keywords=profile.get('seniority_keywords', ''),
                target_functions=profile.get('target_functions', ''),
                keywords=profile.get('keywords', ''),
            ),
        }],
    )

    text = response.content[0].text
    match = re.search(r'\[[\s\S]*\]', text)
    if not match:
        print('ERROR: Could not parse Claude response')
        print(text)
        sys.exit(1)

    try:
        queries = json.loads(match.group())
    except json.JSONDecodeError as e:
        print(f'ERROR: Invalid JSON in Claude response: {e}')
        print(text)
        sys.exit(1)

    print(f'\nGenerated {len(queries)} search queries:')
    for q in queries:
        print(f'  - {q}')

    sheet = sheets_client.open_by_key(sheets_id)
    ws    = sheet.worksheet('Config - Search Terms')
    ws.clear()
    rows  = [['Query', 'Active']] + [[q, 'Y'] for q in queries]
    ws.update(rows, value_input_option='RAW')

    print('\nWritten to Config - Search Terms tab.')
    print('Open your sheet and review the queries — set Active = N for any you want to skip,')
    print('or add your own rows at any time.')


if __name__ == '__main__':
    main()
