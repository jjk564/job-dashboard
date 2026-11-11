# JobPulse 💼
> **A job search and application copilot, running on hadoku**

JobPulse is the job-search app at **[hadoku.me/jobpulse](https://hadoku.me/jobpulse/)**.
Sign in to hadoku.me and everything is yours: your pipeline, search profiles,
documents and applications live in hadoku's database under your account, on
every device.

This repo is its UI. The data and the work behind it come from hadoku:

| Piece | Where it lives |
|---|---|
| This UI (`frontend/`) | this repo |
| The API, the database, scoring | [hadoku-jobplatform](https://github.com/WolffM/hadoku-jobplatform)'s worker, at `hadoku.me/jobplatform/api` |
| Job discovery | hadoku's scraper: the Greenhouse, Ashby and Lever boards of every company on anyone's search profile, nightly, plus RemoteOK and Remotive |
| Tailored résumés, cover letters, packets | hadoku's résumé service |
| Filling application forms | hadoku's form runner (you approve before anything is sent), or the hadoku Fill extension in your own browser |

How the UI moved onto hadoku, call by call: [docs/HADOKU_MERGE.md](docs/HADOKU_MERGE.md).

---

## 🌟 Features

1. **Kanban pipeline**: To Apply, Applied, Interviewing, Offers and Archive,
   with priority, notes, a follow-up date, a contact and an activity timeline
   per posting. Postings their board no longer lists are flagged from the
   nightly scrape.
2. **Discover**: keyword search over hadoku's corpus with location + radius,
   minimum pay, US-only, track and source filters. Add to Pipeline tracks the
   posting itself.
3. **Import a URL**, or add a posting by hand (shown only to people tracking it).
4. **ATS match**: the skills a posting names against your skills list:
   matched, missing, a score.
5. **Documents**: a tailored résumé, a cover letter (formal or conversational),
   screening answers, intro email and talking points, and a shareable packet
   page + PDF.
6. **Applications**: queue a posting for hadoku's form runner, approve each
   filled form before it is submitted, and answer the questions forms asked
   once (reused on every later form).
7. **Search profiles**: keywords, IC/manager track and levels, workplace,
   location and radius, pay floor, and target companies, whose boards
   hadoku scrapes nightly.
8. **Analytics**: your funnel, response and interview rates, the skills your
   pipeline asks for, and its workplace mix.

---

## 🛠 Development

Requires Node 22+.

```bash
cd frontend
npm ci
npm run dev        # http://localhost:5173
```

The dev server proxies `/jobplatform/api` and `/session` to hadoku.me, so it
runs against the real API. Sign the dev page in once with your own hadoku key:
`http://localhost:5173/?apiKey=<your key>`. It is exchanged for the same
session cookie hadoku.me uses and leaves the URL straight away.

Use **your own** key here. The credential `npx @hadoku/dev-vault login`
gives this repo authenticates as the shared `jobplatform-service-key`
identity, not as you, so the dev page would show that identity's (empty)
pipeline. That credential is for scripts; see
[hadoku.me/docs/contributing](https://hadoku.me/docs/contributing/).

```bash
npm run build      # standalone build (dist/)
npm run build:lib  # the bundle hadoku.me mounts (dist-lib/)
npm run lint:css   # every color must be a @wolffm/themes token
```

### How it reaches hadoku.me

`npm run build:lib` builds `src/entry.tsx` (`mount` / `unmount`) with React,
`@wolffm/themes`, `@wolffm/task-ui-components` and the logger left to
hadoku.me's import map. Nothing in it styles the host page: Tailwind's reset
and every utility are scoped to `.job-platform-container`.

hadoku-jobplatform publishes it as `@wolffm/jobpulse` from the exact commit in
its `jobpulse/source.json`, building it on a GitHub-hosted runner with no
secrets. Moving that pin is what deploys a change here to hadoku.me; ask
there when `main` has something to ship.

---

## 📁 Project Structure

```
frontend/
├── src/
│   ├── api/
│   │   ├── hadoku.ts      # transport + shape mappings for the hadoku API
│   │   └── client.ts      # the calls the components use
│   ├── components/        # Kanban, Discovery, Applications, Profile, Analytics, drawer
│   ├── entry.tsx          # mount/unmount: what hadoku.me loads
│   └── main.tsx           # the standalone dev page (and ?apiKey= sign-in)
├── vite.config.ts         # dev server + hadoku.me proxy
├── vite.lib.config.ts     # the hadoku.me bundle
└── tailwind.config.js     # theme tokens; everything scoped to the app root
docs/HADOKU_MERGE.md       # how each old backend call maps onto hadoku
```
