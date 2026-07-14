# Strategic Copilot

An automated job search pipeline for anyone actively looking for their next role. Every weekday morning it scans your target companies' job boards, scores each posting against your profile using Claude AI, and publishes only the relevant roles to a job board hosted on GitHub Pages. You open your board over breakfast and your shortlist is ready. No coding required to set up or run.

Everything lives in this repo: config in `config/`, results in `data/`, and the board at `index.html` — no Google Sheets, no service accounts, no external database.

**What it costs to run:** $0 infrastructure (GitHub Actions and Pages are free). Anthropic API usage runs roughly $0.50–$2/month at steady state for 20–30 companies. The first week is higher while the system learns which jobs it's already seen — after that, only genuinely new postings that match your title and location filters get scored, typically 5–15 jobs per day.

---

## How it works

```
config/companies.yml  ─┐
config/profile.yml    ─┤→  daily GitHub Action  →  data/jobs.json  →  GitHub Pages board
data/scored_urls.json ─┘   (fetch → filter → score)   (committed)      (index.html)
```

- `config/companies.yml` — your target companies and their ATS handles
- `config/profile.yml` — your scoring profile (background, anchors, keywords, filters)
- `data/jobs.json` — every qualifying role found so far (the board reads this)
- `data/scored_urls.json` — dedup cache so nothing is scored (and billed) twice

---

## Setup — overview

1. Fork this repo and enable Actions
2. Add one secret: `ANTHROPIC_API_KEY`
3. Enable GitHub Pages
4. Build your scoring profile
5. Add your target companies and detect their ATS handles
6. Run your first scan

The whole process takes about 15–20 minutes.

**Prefer a guided setup?** Open [claude.ai](https://claude.ai) and paste:

> I'm setting up an automated job search pipeline using GitHub Actions. The repo is at https://github.com/jordanmilner-lgtm/strategic-copilot — walk me through the setup, and help me find ATS job board handles for my target companies.

---

## Step 1: Fork this repo

1. Create a free account at [github.com](https://github.com) if you don't have one
2. Go to this repo and click **Fork** (top right) → **Create fork**
3. **Enable GitHub Actions on your fork** — GitHub disables Actions by default on forks. Go to the **Actions** tab and click **I understand my workflows, go ahead and enable them**. Without this, the scan never runs.
4. Visibility: your profile and target list are visible in a **Public** repo — and GitHub Pages requires Public on the free plan. If you want the repo Private, you'll need GitHub Pro for Pages, or read results from `data/jobs.json` directly on GitHub instead.

## Step 2: Add your API key

1. Go to [console.anthropic.com](https://console.anthropic.com) → **API Keys** → **Create Key** → copy the key (starts with `sk-ant-`)
2. In your fork: **Settings → Secrets and variables → Actions → New repository secret**
3. Name: `ANTHROPIC_API_KEY`, value: the key. Done — this is the only secret.

## Step 3: Enable GitHub Pages

1. In your fork: **Settings → Pages**
2. Under "Build and deployment", set **Source: Deploy from a branch**, branch **main**, folder **/ (root)** → **Save**
3. Your board will be live at `https://YOUR-USERNAME.github.io/strategic-copilot/` within a minute or two (empty until the first scan runs)

## Step 4: Build your scoring profile

You provide your resume and a handful of sample postings; Claude generates `config/profile.yml`.

1. In your fork, click **Add file → Create new file**, name it `setup/resume.txt`, paste your full resume, commit.
2. Repeat for `setup/sample_jobs.txt` — paste 3–5 job postings: 2–3 strong fits AND 1–2 close-but-not-quite. The contrast is what teaches Claude your real criteria.
3. **Actions** tab → **Build Scoring Profile** → **Run workflow**. It commits `config/profile.yml` in ~30 seconds.
4. Review `config/profile.yml` and tweak anything that looks off. Optionally set `comp_target` (e.g. `$300K-$400K OTE`) — leave blank to skip comp filtering.
5. Delete `setup/resume.txt` and `setup/sample_jobs.txt` (open each file → trash icon → commit).

**Score threshold:** `score_threshold` defaults to 6 ("interesting but not obvious"). Raise to 7 for less noise, lower to 5 if you're missing roles.

**Filter fields** — these control which titles even reach the AI scorer (keeping costs low):

| Field | What it does | Example |
|---|---|---|
| `location` | Geography filter | `US only`, `Remote only`, `Any` |
| `seniority_keywords` | Title must contain one | `director, vp, head of, principal` |
| `target_functions` | Title must also contain one | `gtm, sales, strategy, operations` |
| `exclude_functions` | Title must NOT contain any | `engineer, legal, finance, recruiter` |

## Step 5: Add your target companies

Edit `config/companies.yml` (on GitHub: open the file → pencil icon → commit). Aim for 20–30 companies.

The easy way: add just names —

```yaml
companies:
  - name: Anthropic
  - name: Figma
  - name: Ramp
```

— then run the **Detect Company ATS** workflow (Actions tab). It finds each company's ATS platform and handle, verifies them against the live APIs, and commits the result. Companies it can't detect are listed in the run log; fill those in manually using [Section A](#section-a-finding-a-companys-ats-handle) below, or ask Claude to look them up.

A fully specified entry looks like:

```yaml
  - name: CrowdStrike
    ats: workday
    handle: crowdstrike.wd5/crowdstrikecareers
    active: Y
```

**Supported ATS platforms:** Ashby, Greenhouse, Lever, Gem, Workday — the majority of tech and growth-stage companies.
**Unsupported:** iCIMS, Taleo, Comeet, SmartRecruiters, SAP SuccessFactors (no public APIs) — watch those manually or via Google Alerts.

**Think in tiers** when building the list: 8–12 dream companies, 10–15 strong fits, 5–10 worth watching. The system treats them identically, but tiering helps you prioritize what comes back.

## Step 6: Run your first scan

**Actions** tab → **Strategic Copilot Daily Scan** → **Run workflow**.

- First run takes 15–45 minutes (every current job gets scored once) and costs more than usual; from day two only new postings are scored.
- When it finishes, it commits `data/jobs.json` and your board at `https://YOUR-USERNAME.github.io/strategic-copilot/` shows the results — sortable by fit score, filterable by company and search text.
- After that it runs automatically every weekday at 11:23 AM UTC (7:23 AM Eastern). No action needed.

---

## Daily use

Open your Pages board each morning. Columns to focus on:

- **Fit** (1–10) — your primary filter; sort by it
- **Why it fits** — Claude's two-sentence strategic thesis
- **abstract fit** badge — a genuine mandate match, not just keyword overlap

The board links each title straight to the posting.

## Managing companies

- **Add:** new entry in `config/companies.yml` (name alone + run Detect Company ATS, or fully specified). Next scan picks it up.
- **Pause:** set `active: N`. **Remove:** delete the entry.
- **Non-standard titles** (e.g. Palantir uses "Lead" not "Director"): set `seniority_override: 'lead, head of'` on that company.

## Adjusting your profile

Edit `config/profile.yml` any time; changes apply on the next scan. After the first week, paste over- and under-scored examples into Claude and ask what to adjust — a few targeted refinements beat perfecting it upfront.

---

## Troubleshooting

**"Board is empty after the scan"**
Check the Actions log (completed run → job → expand steps):
- Title filter blocking everything — check the "After filters" count
- All jobs already in `data/scored_urls.json` — expected after the first run
- Threshold too high — try `score_threshold: '5'` temporarily

**"The scan failed"**
- Verify the `ANTHROPIC_API_KEY` secret is set and your Anthropic account has billing enabled
- If the commit step failed: Settings → Actions → General → Workflow permissions → **Read and write permissions**

**"Page shows 404"**
Pages can take a couple of minutes after the first enable. Confirm Settings → Pages shows the site URL and source is main / root.

**"Duplicate jobs"**
`data/scored_urls.json` is the dedup cache. If deleted, the next run re-scores everything (higher cost, no data loss).

**"A company's handle isn't working"**
Test the API URL in your browser (below). If it errors, re-derive the handle from the company's careers page.

---

## Section A: Finding a company's ATS handle

1. Go to the company's careers page and click a job posting; look at the URL:
   - **Ashby:** `jobs.ashbyhq.com/HANDLE/job-id`
   - **Greenhouse:** `boards.greenhouse.io/HANDLE/jobs/job-id`
   - **Lever:** `jobs.lever.co/HANDLE/job-id`
   - **Gem:** `jobs.gem.com/HANDLE/job-id`
   - **Workday:** `https://SUBDOMAIN.wdN.myworkdayjobs.com/BOARD` → handle is `SUBDOMAIN.wdN/BOARD` (e.g. `crowdstrike.wd5/crowdstrikecareers`)
2. If the URL matches none of these, the ATS is unsupported.

**Quick check** — paste in your browser, replacing HANDLE; JSON back means it's right:
- Ashby: `https://api.ashbyhq.com/posting-api/job-board/HANDLE`
- Greenhouse: `https://boards-api.greenhouse.io/v1/boards/HANDLE/jobs`
- Lever: `https://api.lever.co/v0/postings/HANDLE?mode=json`
- Gem: `https://api.gem.com/job_board/v0/HANDLE/job_posts/`

---

*Built with Claude Code.*
