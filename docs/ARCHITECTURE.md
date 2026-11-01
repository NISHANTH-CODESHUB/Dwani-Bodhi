# Architecture

```
Phone (PWA, offline-first)                         Server (India region)                         Claude API
┌──────────────────────────┐   HTTPS batch sync   ┌──────────────────────────────────┐  crops + de-identified JSON
│ Kiosk · Teacher app      │ ───────────────────► │ API (FastAPI, stateless, N reps) │ ─────────────────────────►
│ Dexie: roster WITH names │  UUIDs only, idempot.│  /v1/sync → blobs + job queue     │
│ plans, items, queue      │ ◄─────────────────── │ Workers (scale per queue):        │
│ VAD, discontinue rules   │  plans, cards, today │  speech  ECCL (Wav2Vec2-CTC)      │
└──────────────────────────┘                      │  vision  ArUco crop → Claude → bug│
                                                  │  learner BKT/Beta/levels/plans    │
                                                  │  llm     Action Cards, discovery  │
                                                  │ Postgres · S3-compatible blobs    │
                                                  └──────────────────────────────────┘
```

## Request/data flow
1. The phone records a session offline against a cached plan and stores responses and audio in IndexedDB.
2. `POST /v1/sync` (multipart, idempotent by client UUIDs):
   - tap responses are scored immediately
   - voice responses enqueue `score_voice`
   - slate photos enqueue `process_slate`
3. **Speech worker:** decodes audio (PyAV) → quality gate → acoustic log-probs → ECCL / passage scoring →
   verdict + calibrated confidence → audio deleted → `update_learner` enqueued.
4. **Vision worker:** ArUco detection → homography crop per slate → Claude transcription
   (expectation-constrained) → `verify()` against the bug grammar → low confidence goes to the teacher
   confirm queue.
5. **Learner worker:**
   - applies scored responses in order (BKT soft evidence, Beta misconceptions, speech-variant control)
   - updates TaRL levels and closes re-checks
   - writes the next offline session plan
6. **Scheduler tick:**
   - purges expired media
   - recovers stale jobs
   - generates the week's Action Card per active classroom (Claude Opus, or a template fallback)
   - registers re-checks

## Scaling path
| Load | Topology |
|---|---|
| Pilot (≤50 schools) | One VM, `docker compose` |
| District (≈2k schools) | Managed Postgres, S3 bucket (Indian region), 2–4 API replicas, 4–8 CPU speech workers |
| State (≈50k schools) | Kubernetes; speech workers on GPU nodes (one model load serves many jobs); Postgres read replicas for reporting; partition `response` by month |

Rough arithmetic:
- 1M children × 2.5 audio-minutes/week ≈ 2.5M audio-minutes/week.
- At a real-time factor of ~0.15 on CPU that is ~40 vCPUs.
- Queues are independent, so each tier scales on its own signal (queue depth on `/metrics`).

## Module map (`services/api/app`)
| Module | Responsibility | Depends on |
|---|---|---|
| `speech/` | Devanagari, mutations, CTC, ECCL, passage/WCPM, dialect profiles, calibration | numpy (torch only in `acoustic.Wav2Vec2Backend`) |
| `diagnosis/` | Procedure grammar, bug library, verification, item generator | pure |
| `learner/` | BKT, misconceptions, graph, levels, scheduler, planner, state | pure |
| `content/` | Pack schema and loader | pydantic, yaml |
| `llm/` | Claude client (cost, budget, fallback), slate, card, explain, hypotheses | anthropic SDK |
| `vision/` | ArUco detection, rectification, enhancement, ID cards | OpenCV |
| `services/` | Orchestration with the DB | all of the above |
| `api/` | HTTP surface, auth, scoping | services |
| `jobs/` | Queue and worker | services |
