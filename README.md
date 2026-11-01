<div align="center">

# 🔊 Dhwani-Bodhi · ध्वनि-बोधि

### See *why* a child is stuck, not just *that* they are

**Learning visibility at the misconception level for foundational literacy and numeracy (FLN) in Indian classrooms.**

[![CI](https://github.com/NISHANTH-CODESHUB/Dwani-Bodhi/actions/workflows/ci.yml/badge.svg)](https://github.com/NISHANTH-CODESHUB/Dwani-Bodhi/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React_18-PWA-61DAFB?logo=react&logoColor=black)
![Claude](https://img.shields.io/badge/Claude-Opus_%7C_Sonnet-D97757)
![Offline-first](https://img.shields.io/badge/Offline--first-2GB_Android-success)

*ShikshaNext × Anthropic · AI for Foundational Learning Hackathon 2026 · Challenge 2: Learning-Level Visibility*

</div>

---

## 💡 The idea in one paragraph

Most assessment tools tell a teacher that **30 children are behind**. Dhwani-Bodhi tells her that
**9 of them read ी as ि**, how confident the system is, which **10-minute activity** fixes it, and, the
following week, **whether it worked**.

It listens to children read aloud and reads photos of their slate maths. It works out the specific
**misconception** behind each mistake and turns that into a short weekly **Action Card** for the teacher.
Everything runs on a cheap Android phone, offline, in Hindi.

```
   Diagnose ──────────► Decide ──────────► Do ──────────► Detect
   voice + slate        learner model      Monday         targeted re-checks
   → exact bug          + who to assess    Action Card    → did it work?
        ▲                                                     │
        └─────────────────────────────────────────────────────┘
```

---

## 📑 Table of contents

- [Why this matters](#-why-this-matters)
- [The five novelties](#-the-five-novelties)
- [Who uses it](#-who-uses-it)
- [Architecture](#️-architecture)
- [Tech stack](#-tech-stack)
- [Repository layout](#-repository-layout)
- [Quick start (local)](#-quick-start-local)
- [Configuration](#️-configuration)
- [Running modes](#-running-modes)
- [Testing](#-testing)
- [Evaluation](#-evaluation)
- [Deployment](#-deployment)
- [Privacy & child safety](#-privacy--child-safety)
- [Documentation](#-documentation)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🎯 Why this matters

- Millions of children in Grades 1–3 can't yet read a simple word or do two-digit subtraction.
- Teachers have 40+ children and no time for one-on-one assessment.
- Existing dashboards stop at "below grade level", which tells a teacher *who* to help but not *what to do*.

Dhwani-Bodhi closes that gap. Each verdict is explainable, comes with a confidence level, and maps to
an activity that has been vetted by a pedagogy reviewer.

---

## ✨ The five novelties

| # | Novelty | What it does | Where |
|---|---|---|---|
| **N1** | **ECCL reading scoring**<br/>*Expectation-Constrained Confusion Lattice* | Compares the CTC likelihood of the correct reading with a lattice of *pedagogical* mis-readings (क↔ख, ि↔ी, ब↔व, dropped matras, dropped nasals, split conjuncts). The error type falls out by construction. It tolerates dialect variation, and a listen-and-repeat control separates speech difficulty from decoding difficulty. Fully deterministic, with no LLM in the loop. | `services/api/app/speech/eccl.py` |
| **N2** | **Neuro-symbolic slate diagnosis** | ArUco ID cards → rectified per-child slate crops → Claude Vision transcribes *what the child wrote* → a procedure grammar must **reproduce the exact wrong answer** before a misconception is recorded. Answers it can't explain feed a *Claude proposes → executor verifies → human approves* discovery loop. | `app/diagnosis/`, `app/services/slates.py` |
| **N3** | **Diagnostic item engineering + adaptive plans** | Items are generated so that **every bug predicts a different answer**. Sessions are planned by expected information gain. | `app/diagnosis/itemgen.py`, `app/learner/planner.py` |
| **N4** | **Uncertainty-honest learner model** | BKT with soft evidence and asymmetric prerequisite propagation. Misconceptions use a Beta-Binomial model and are confirmed only after ≥2 reproductions. Includes TaRL level ladders, abstention when unsure, and a "who to assess today" scheduler that fits the teacher's time budget. | `app/learner/` |
| **N5** | **Closed loop with evidence** | The Monday Action Card picks **only vetted activities** (written by Claude Opus or a deterministic template), registers targeted re-checks, and measures resolution rates for each activity × misconception pair. | `app/services/cards.py` |

---

## 👥 Who uses it

| Role | What they get |
|---|---|
| 🧒 **Student** | A friendly Hindi **kiosk** with a mascot (*Cheenu*). Children read aloud and tap answers. They never see scores, and every session ends on a success. |
| 👩‍🏫 **Teacher** | Class roster, slate capture, weekly **Action Card**, per-child profiles with explanations, a 1-tap confirm queue for uncertain verdicts, student activity timelines, and printable ArUco ID cards. |
| 🏛️ **Admin** | A state → district → block → cluster → school → class hierarchy, account approvals, notifications, KPIs, level distributions and activity charts. Admins see only their own part of the hierarchy, and students appear by register number (`STU-<year>-<seq>`), never by name. |

---

## 🏗️ Architecture

```
Phone (PWA, offline-first)                       Server (India region)                        Claude API
┌──────────────────────────┐   HTTPS batch sync  ┌──────────────────────────────────┐  crops + de-identified JSON
│ Kiosk · Teacher · Admin  │ ──────────────────► │ API (FastAPI, stateless, N reps) │ ─────────────────────────►
│ Dexie: roster WITH names │ UUIDs only, idempot.│  /v1/sync → blobs + job queue    │
│ plans, items, queue      │ ◄────────────────── │ Workers (scale per queue):       │
│ VAD, discontinue rules   │ plans, cards, today │  speech  ECCL (Wav2Vec2-CTC)     │
└──────────────────────────┘                     │  vision  ArUco crop → Claude → bug│
                                                 │  learner BKT/Beta/levels/plans   │
                                                 │  llm     Action Cards, discovery │
                                                 │ Postgres · S3-compatible blobs   │
                                                 └──────────────────────────────────┘
```

**Data flow**

1. The phone runs a session **offline** against a cached plan and stores responses and audio in IndexedDB.
2. `POST /v1/sync` (idempotent): tap answers are scored immediately, voice answers go to the `speech`
   queue, and slate photos go to the `vision` queue.
3. **Speech worker:** decode → quality gate → acoustic log-probs → ECCL → calibrated verdict → **audio deleted**.
4. **Vision worker:** ArUco → homography crop → Claude transcription → `verify()` against the bug grammar.
   Low-confidence results go to the teacher's confirm queue.
5. **Learner worker:** updates BKT, misconceptions and levels, closes re-checks, and writes the next offline plan.
6. **Scheduler:** purges media, recovers stale jobs, and generates each active classroom's weekly Action Card.

Full details: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## 🧰 Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18 · TypeScript · Vite · `vite-plugin-pwa` (Workbox) · Dexie (IndexedDB) · Vitest |
| Backend | Python 3.11 · FastAPI · SQLAlchemy 2 · Alembic · Pydantic v2 · DB-backed job queue |
| Speech | Wav2Vec2-CTC ([EkStep Vakyansh Hindi](https://huggingface.co/Harveenchadha/vakyansh-wav2vec2-hindi-him-4200), MIT) · PyAV · NumPy |
| Vision | OpenCV (ArUco markers, homography rectification) |
| AI | Anthropic Claude: **Opus** (cards, explanations, hypotheses), **Sonnet / Haiku** (slate reading) |
| Data | PostgreSQL 16 (prod) / SQLite (dev) · local disk or S3-compatible blob storage |
| Deploy | Docker Compose · Caddy (automatic TLS) · GitHub Actions CI |

---

## 📂 Repository layout

```
dhwani-bodhi/
├── apps/web/                  # Offline-first PWA: child kiosk, teacher app, admin dashboard
│   └── src/
│       ├── kiosk/             #   child-facing reading & tap activities (Cheenu mascot)
│       ├── teacher/           #   roster, slate capture, Action Card, profiles, confirm queue
│       ├── admin/             #   hierarchy, approvals, dashboards
│       ├── lib/               #   offline sync, IndexedDB, audio/VAD, TTS, auth
│       └── i18n/hi.ts         #   all UI strings (Hindi)
├── services/api/              # FastAPI backend + workers
│   ├── app/
│   │   ├── speech/            #   ECCL, Devanagari mutations, CTC, passage/WCPM, dialects
│   │   ├── diagnosis/         #   procedure grammar, bug library, verifier, item generator
│   │   ├── learner/           #   BKT, misconceptions, skill graph, levels, scheduler, planner
│   │   ├── vision/            #   ArUco detection, rectification, ID cards
│   │   ├── llm/               #   Claude client (cost log, budget guard, offline fallback)
│   │   ├── services/          #   orchestration with the DB
│   │   ├── api/               #   HTTP routes, auth, scoping
│   │   └── jobs/              #   queue + worker + scheduler
│   ├── migrations/            #   Alembic migrations
│   └── tests/                 #   pytest suites (unit, e2e, privacy, migrations)
├── content/packs/hi-IN/       # Hindi content pack: skill graph, items, activities, dialect regions
├── eval/                      # Reading + slate evaluation harnesses, calibration
├── tools/                     # Maths item generator, ArUco card maker, dev launcher
├── infra/                     # Dockerfiles + Caddyfile
├── docs/                      # Design guide, architecture, privacy, runbook, user guide
└── docker-compose.yml         # Postgres + API + speech workers + worker + Caddy
```

**Content pack (`hi-IN`):** a 22-node skill graph mapped to NIPUN Bharat, 177 diagnostic items,
30 vetted classroom activities, and regional dialect profiles.

---

## 🚀 Quick start (local)

### Prerequisites
- **Python 3.11+**
- **Node.js 22+** and npm
- Git
- *(Optional)* an Anthropic API key. The system works fully offline without one.

### 1. Clone

```bash
git clone https://github.com/NISHANTH-CODESHUB/Dwani-Bodhi.git
cd Dwani-Bodhi
cp .env.example .env
```

### 2. Backend (API + worker)

```bash
cd services/api
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -e ".[dev]"

python -m app.demo                       # seed a demo classroom through the real pipeline
uvicorn app.main:app --reload            # API → http://localhost:8000/docs
```

In a **second terminal**, start the background worker:

```bash
cd services/api && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
python -m app.jobs.worker --scheduler          # scoring, learner model, Claude jobs
```

### 3. Frontend (third terminal)

```bash
cd apps/web
npm install
npm run dev                  # → http://localhost:5173 (proxies /v1 to :8000)
# npm run dev -- --mode demo # adds a "simulate" box on voice items, so no microphone is needed
```

> **Windows shortcut:** `tools/run-dev.ps1` starts everything at once.

### 4. Log in

- `python -m app.demo` creates a **teacher** and an **admin** account with random phone numbers and strong
  random PINs. They are printed once and saved to the git-ignored `data/demo-credentials.txt`.
  Rotate them with `python -m app.demo --reset-credentials`.
- On a **fresh database**, the app asks you to create the top-level admin first. That admin then builds the
  hierarchy and creates or approves the other accounts.

👉 Step-by-step usage: [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) (also in the app under **मेनू → उपयोग गाइड**).

---

## ⚙️ Configuration

All settings live in `.env` (see [`.env.example`](.env.example)). The main ones:

| Variable | Purpose | Default |
|---|---|---|
| `APP_ENV` | `dev` or `prod` (prod refuses dev secrets) | `dev` |
| `DATABASE_URL` | Postgres URL; SQLite is used in dev if unset | SQLite |
| `JWT_SECRET`, `PHONE_PEPPER` | Auth secrets: **generate long random values** | — |
| `ANTHROPIC_API_KEY` | Enables Claude features (optional) | empty |
| `LLM_MODE` | `auto` / offline behaviour | `auto` |
| `MODEL_SLATE` / `MODEL_CARD` / `MODEL_EXPLAIN` / `MODEL_HYPOTHESIS` | Claude model per task | Sonnet 5.5 / Opus 5.5 |
| `DAILY_LLM_BUDGET_USD` | Hard daily cap on Claude spend | `5` |
| `SPEECH_BACKEND` | `wav2vec2` (real) or `simulated` (demos/tests only) | `simulated` |
| `SPEECH_MODEL_ID` | Hugging Face acoustic model | Vakyansh Hindi |
| `BLOB_BACKEND` | `local` or `s3` (use an Indian region) | `local` |
| `AUDIO_RETENTION_HOURS` | Raw audio retention after scoring | `0` |
| `SLATE_CROP_RETENTION_DAYS` | Retention for per-child slate crops | `30` |
| `ADMIN_SELF_SIGNUP` | Admin sign-ups active immediately (`false` = needs approval) | `true` |

---

## 🔀 Running modes

| Mode | How | Behaviour |
|---|---|---|
| **Fully offline / no key** | leave `ANTHROPIC_API_KEY` empty | Action Cards come from deterministic templates, and slates go to the teacher's 1-tap confirm queue. |
| **With Claude** | set `ANTHROPIC_API_KEY` | Claude reads slates and writes cards and explanations. Every call is logged with its cost and capped by `DAILY_LLM_BUDGET_USD`. |
| **Real speech scoring** | `pip install -e ".[speech]"` and `SPEECH_BACKEND=wav2vec2` | Wav2Vec2-CTC acoustic scoring. The `simulated` backend is for demos and tests only and is **refused in production**. |

---

## 🧪 Testing

```bash
# Backend: algorithms, API end-to-end, privacy, hierarchy, migrations
cd services/api && pytest -q

# Frontend: sync core, audio, PIN policy, TTS, kiosk runner, image utils
cd apps/web && npm test

# Type-check + production build
cd apps/web && npm run build
```

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs on every push and pull request. It runs
Ruff, pytest, validates the content pack, applies the Alembic migrations, and runs the Vitest suite and
the production build.

---

## 📊 Evaluation

```bash
python eval/run_reading_eval.py --manifest eval/datasets/dr1/manifest.csv --fit eval/calibration.json
python eval/run_slate_eval.py   --labels   eval/datasets/ds1/labels.json --model claude-haiku-5-5
python eval/smoke_speech_model.py          # real-model smoke test (loads Vakyansh, checks coverage + RTF)
```

> ⚠️ `--simulate` / `--synthetic` modes only check that the pipeline runs. **They are not accuracy claims.**
> Real numbers come from the planted-error and consented-child datasets described in
> [`docs/GUIDE.md`](docs/GUIDE.md) §14.

---

## 🌐 Deployment

**Pilot setup: one VM in an Indian cloud region**

```bash
cp .env.example .env    # set POSTGRES_PASSWORD, JWT_SECRET, PHONE_PEPPER, SITE_ADDRESS, ANTHROPIC_API_KEY
docker compose up -d --build
docker compose up -d --scale worker-speech=3    # scale speech scoring horizontally
```

| Scale | Topology |
|---|---|
| Pilot (≤ 50 schools) | One VM, `docker compose` |
| District (≈ 2k schools) | Managed Postgres, S3 (India), 2–4 API replicas, 4–8 CPU speech workers |
| State (≈ 50k schools) | Kubernetes, GPU speech workers, Postgres read replicas, monthly partitions |

Backups, monitoring and scaling: [`docs/RUNBOOK.md`](docs/RUNBOOK.md).

---

## 🔒 Privacy & child safety

Designed for India's **DPDP Act 2023**, with verifiable parental consent.

- 🧒 **Child names never leave the phone.** The server stores only UUIDs, grade and register number.
- 🎙️ **Raw audio is deleted right after scoring.**
- 🖼️ **No faces to AI.** Slates are cropped by ArUco geometry before any API call, and full classroom photos are deleted.
- 🤖 **Claude sees only cropped slates and de-identified JSON.** Explanations use a `{{child}}` placeholder that the phone fills in locally.
- ✅ **Consent is enforced at sync.** Sessions for children without granted consent are rejected.
- 🗑️ **Right to erasure.** `DELETE /v1/children/{id}` removes every trace of the child.
- 🔐 PBKDF2-hashed PINs with a guessability policy, lockout, HMAC-peppered phone numbers, JWT and TLS.
- 🌱 **Child wellbeing:** no scores shown to children, sessions end on a success, no facial recognition, no third-party analytics.

Full policy: [`docs/PRIVACY.md`](docs/PRIVACY.md).

---

## 📚 Documentation

| Document | Contents |
|---|---|
| [`docs/GUIDE.md`](docs/GUIDE.md) | The full design guide: problem, landscape, the five novelties in depth, evaluation plan |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System design, data flow, scaling path, module map |
| [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) | How teachers and admins use the app day to day |
| [`docs/PRIVACY.md`](docs/PRIVACY.md) | DPDP compliance and child-safety measures |
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | Operations: deploy, scale, back up, monitor |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Log of design decisions |
| [`docs/STATUS.md`](docs/STATUS.md) | Current build status and verification evidence |

---

## 🤝 Contributing

Contributions are welcome, especially from teachers, FLN pedagogy experts, and speakers of Hindi dialects.

1. Fork the repo and create a branch: `git checkout -b feature/my-change`
2. Keep pure logic (`speech/`, `diagnosis/`, `learner/`) free of DB and HTTP code.
3. **Ground rules:**
   - Reading scoring stays deterministic (ECCL). No LLM in that path.
   - No misconception is recorded without symbolic reproduction or ECCL evidence.
   - Action Cards may only use activities from `content/packs/*/activities`. New activities need pedagogy review.
   - Never send child names, audio, faces or school identifiers to an external API.
   - All UI strings are in Hindi, touch targets are large, and everything must work offline on a 2 GB phone.
4. Run `pytest` and `npm test`, then open a pull request.

---

## 📄 License

Released under the **[Apache License 2.0](LICENSE)** as an open-source **digital public good**.

<div align="center">

**Made with ❤️ for every child learning to read and count**

*ध्वनि (sound) + बोधि (understanding): understanding through sound*

</div>
