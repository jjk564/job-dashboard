# JobPulse 💼
> **A Privacy-First, Local Job Search & Application Copilot**

JobPulse is an autonomous, local-first dashboard designed to accelerate and automate your job search and application pipeline. Everything runs locally on your machine with a private SQLite database (`jobs.db`) — keeping your applications, resumes, notes, and credentials 100% private.

---

## 🌟 Core Features

1. **Kanban Application Pipeline**
   - Track listings visually across stages: `To Apply`, `Applied`, `Interviewing`, `Offers`, and `Archive`.
   - Filter by workplace type (Remote, Hybrid, Onsite), priority, and calculated ATS fit score.
   - Quick stage advancement buttons and deep inspection drawers.

2. **Live Multi-Board Job Aggregator & Explorer**
   - Searches across 15+ top developer, Big Tech, and startup sources:
     - **Big Tech Direct Career Portals**: **Google**, **Microsoft**, **Amazon**, **Apple**, **NVIDIA**, **Netflix**, and **Salesforce**.
     - **25+ Top Tech Company ATS Boards (Greenhouse, Ashby & Lever)**: **OpenAI**, **Anthropic**, **Stripe**, **Cloudflare**, **Databricks**, **Vercel**, **Coinbase**, **Discord**, **Reddit**, **Robinhood**, **Airbnb**, **Figma**, **GitLab**, **Ramp**, **Linear**, **Notion**, **Plaid**, **Supabase**, **Palantir**, **Scale AI**, **Duolingo**, **Twilio**, and more.
     - **SimplifyJobs Curated Feeds**: Daily updated **Entry-Level / New Grad Tech** and **Software Engineering Internship** feeds.
     - **Major Job Boards & Tech Aggregators**: **LinkedIn**, **Glassdoor**, **Indeed**, **ZipRecruiter**, **The Muse**, **We Work Remotely**, **Himalayas**, **Hacker News "Who is Hiring?"**, **Adzuna**, **RemoteOK**, **Arbeitnow**, and **Jobicy**.
   - Filter by specific platform or search across all boards simultaneously with location & mile-radius filtering.
   - One-click import directly into your Kanban pipeline with automated ATS match scoring.

3. **Smart Job URL Scraper**
   - Paste any job posting link (Greenhouse, Lever, Ashby, or general web pages).
   - Automatically extracts job title, company name, location, salary range, and requirements.

4. **ATS Fit Scoring Engine**
   - Automatically parses job descriptions against your candidate skills inventory.
   - Displays real-time fit percentage, matched skills, and highlighted missing requirements.

5. **AI & Template Document Generator**
   - **Offline Template Engine**: Instant generation of tailored cover letters, targeted resume highlights, and elevator pitches with zero external API calls.
   - **Optional LLM Integration**: Connect local Ollama (Llama 3), Google Gemini, or OpenAI with your API key for personalized deep tailoring.

6. **Application Autofill Copilot**
   - **1-Click Clipboard Palette**: Instant copy buttons for standard ATS fields (Full Name, LinkedIn, GitHub, Portfolio, Work Auth, Desired Salary, Notice Period).
   - **Assisted Browser Session**: Launches a visible browser session using Playwright to pre-fill standard application forms on Greenhouse, Lever, and Ashby.

7. **Analytics & Skills Intelligence**
   - Application funnel conversion rates (Response rate, Interview rate).
   - Real-time frequency analysis of top in-demand skills across all jobs in your pipeline.

---

## 🚀 Quick Start

### 1. Requirements
- Python 3.10+
- Node.js 18+

### 2. Launching JobPulse
Simply double-click:
```bat
start.bat
```
Or run with Python:
```bash
python start.py
```
This automatically boots the FastAPI backend (`http://127.0.0.1:8000`) and the Vite React frontend (`http://localhost:5173`) and opens the dashboard in your default browser.

### 3. Hadoku vault (secrets without `.env` files)

Secrets come from the hadoku vault at run time and live only in the process
they are handed to. You need a hadoku.me account at friend tier with a service
grant; you have grants for `jobplatform-service-key` and `resume-bot-service-key`.

**Get your credential** (once a week), from the repo root:
```bash
npx @hadoku/dev-vault@latest login
```
1. It prints a code and a `hadoku.me/account/device` link. Open it signed in
   with your passkey.
2. The first time, scan the QR code into an authenticator app.
3. Pick `jobplatform-service-key`, then approve with a passkey tap and a code
   from the app.

The command writes `.devvault.local.json` (your key, mode 600) in the checkout;
it is gitignored and must stay that way. The credential lasts 7 days; run
`login` again when it expires.

**Use it.** `.devvault.json` maps env var names to vault item names (names
only, never values). Add an entry only when the code reads that variable, then
run the command through dev-vault from the repo root:
```bash
npx @hadoku/dev-vault@latest -- python start.py
npx @hadoku/dev-vault@latest --check   # diagnoses the mapping, broker and access
```
Nothing is mapped today: the code's only env reads are `ADZUNA_APP_ID`,
`ADZUNA_APP_KEY`, `SCRAPER_PROXY_POOL` and `SCRAPER_PROXY_URL`, and none of
them are in the vault. To add one, ask the operator to store it and grant it to
`jobplatform-service-key`.

**Calling hadoku.me directly.** The credential authenticates as
`jobplatform-service-key` (service tier) when sent as the `X-User-Key` header to
`https://hadoku.me/...`, e.g. the jobplatform API at
`https://hadoku.me/jobplatform/api/*`. Treat it like a password: never commit
it, log it, or paste it anywhere.

Never map the `CLOUDFLARE_*` items for local dev: they deploy workers and push
every worker's secrets. `@wolffm/*` packages need no token outside the fleet;
install them from the public npm mirror by alias, e.g.
`"@wolffm/themes": "npm:@hadoku/themes@<version>"`.

---

## 📁 Project Structure

```
Job Dashboard/
├── backend/
│   ├── app/
│   │   ├── database.py             # Async SQLite engine
│   │   ├── models.py               # Job, Profile, Skill, Activity tables
│   │   ├── schemas.py              # Pydantic schemas
│   │   ├── main.py                 # FastAPI application & lifespan
│   │   ├── services/
│   │   │   ├── job_fetcher.py      # Public boards aggregator (RemoteOK, Arbeitnow, Jobicy)
│   │   │   ├── job_extractor.py    # URL scraper (Greenhouse, Lever, generic)
│   │   │   ├── matcher.py          # ATS keyword match scoring algorithm
│   │   │   ├── ai_generator.py     # Tailored cover letters & resume highlights
│   │   │   └── browser_assistant.py# Playwright assisted form autofill
│   │   └── routers/                # REST endpoints
│   ├── tests/                      # Pytest unit & integration test suite
│   ├── requirements.txt            # Python dependencies
│   └── run.py                      # Backend launch script
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Kanban/             # Pipeline board & cards
│   │   │   ├── JobDetails/         # Details drawer & AI Copilot
│   │   │   ├── Discovery/          # Live remote job search
│   │   │   ├── Profile/            # Profile & skills manager
│   │   │   ├── Analytics/          # Funnel & skills demand charts
│   │   │   └── Common/             # URL import & Add job modals
│   │   ├── api/                    # Typed API client
│   │   ├── App.tsx                 # Main application
│   │   └── types.ts                # TypeScript interfaces
│   ├── package.json
│   └── vite.config.ts
├── start.bat                       # 1-click Windows launcher
├── start.py                        # Cross-platform runner
└── AGENTS.md / GEMINI.md           # Workspace rules
```

---

## 🧪 Running Tests

To run the full backend test suite:
```bash
python -m pytest
```
