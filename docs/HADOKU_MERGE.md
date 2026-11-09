# Unifying JobPulse with hadoku.me/jobplatform

This branch (`hadoku-merge`) makes this repo's UI the one hadoku.me serves at
`/jobplatform/`. It keeps JobPulse's UI, moves it onto the hadoku jobplatform
API, and adds the features that so far exist only in hadoku-jobplatform's UI.

## What stays where

| Piece | Lives in | Why |
|---|---|---|
| UI (this `frontend/`) | **this repo** | JobPulse's UI is the product |
| API, D1 database, scoring, migrations | hadoku-jobplatform `worker/` | deploys from WolffM CI; holds production data |
| Scrapers | hadoku-scrape + hadoku-scrapers-collab | run on the scraper host with its proxies |
| FastAPI backend (`backend/`) | **retired** at the end of this branch | its data becomes per-user rows in D1 |

The UI calls `https://hadoku.me/jobplatform/api/*` with the visitor's own
hadoku.me session, so every user sees their own pipeline, profiles and
documents. No shared service key in the browser, ever.

## How each backend call moves

| JobPulse call (`/api/...`) | hadoku jobplatform API | Notes |
|---|---|---|
| `GET /jobs` (pipeline) | `GET /pipeline` | status names map below |
| `GET/PATCH /jobs/:id` | `GET /jobs/:id`, `PUT /jobs/:id/state`, `PATCH /jobs/:id/tracking` | ids are strings (`greenhouse_123`) |
| `POST /jobs` (add by hand) | `POST /jobs/import` with `manual` | shown only to people tracking it |
| `DELETE /jobs/:id` | `DELETE /jobs/:id/state` | the posting stays in the shared corpus |
| `POST /jobs/:id/activities` | `POST /jobs/:id/events` | note / interview / contact / follow_up |
| `POST /jobs/:id/check-status`, `check-all-status` | posting freshness from the nightly scrape | *worker change: expose `last_seen_at` / closed* |
| `GET /discovery/search` | `GET /jobs` (profile, near, workplace, min_salary) | *worker change: server-side keyword search* |
| `POST /discovery/import-url` | `POST /jobs/import` | |
| `GET/PUT /profile` | `GET/PUT /applicant-profile` | *worker change: work authorization, desired salary, notice period* |
| `/profile/skills` | profile `stack` | *worker change: a per-user skills list* |
| `/search-profiles` CRUD | `/profiles` CRUD | same model (track + levels) |
| `/directives` | `GET /directives` | |
| `/assistant/:id/match` | — | *worker change: matched / missing skills per posting* |
| `/assistant/:id/generate`, `application-kit` | `POST /jobs/:id/resume`, `/cover-letter`, `/application-extras` | |
| `/assistant/:id/mint-packet` | `POST /jobs/:id/packet-link` | |
| `/assistant/:id/autofill-payload` | `GET /jobs/:id/fill-packet` | the Fill extension replaces `launch-browser` |
| `/scraper/match-companies` | `POST /companies/match`, `/companies/probe`, profile companies | |
| `/scraper/trigger`, `/scraper/sync-corpus` | **removed** | the scraper runs nightly from directives |
| `/analytics/metrics` | `GET /insights` | |

Status names: `TO_APPLY` ↔ `saved`/`interested`, `APPLIED` ↔ `applied`,
`INTERVIEWING` ↔ `interviewing`, `OFFER` ↔ `offered`, `REJECTED` ↔ `rejected`,
`ARCHIVED` ↔ `dismissed`.

## Features only hadoku-jobplatform's UI has today

To bring in: the application queue (approve before the runner submits),
packets, unanswered form questions, ATS verification codes, up/down votes
on postings, the Fill extension download, hiding a company, and Quick copy.

## Phases

0. **Dev harness**: `npm run dev` proxies `/jobplatform/api` and `/session` to
   hadoku.me; `?apiKey=` signs the dev page in once, as hadoku-jobplatform's
   harness does. React 19, the version hadoku.me provides.
1. **API layer**: `src/api/hadoku.ts` with typed calls and the mappings above;
   the pipeline (Kanban + drawer) moves first.
2. **Worker changes** in hadoku-jobplatform for the rows marked above.
3. **Discovery, profile, analytics** onto the API.
4. **Port the hadoku-only features.**
5. **Host-safe build**: React, `@wolffm/themes` and the logger come from
   hadoku.me's import map; Tailwind's reset scoped to the app root; no global
   `html`/`body` styles; first load under hadoku.me's 54.7 kB gzip budget.
6. **Switch hadoku.me** to this UI; retire `backend/`.
