# Operations runbook

## First deployment (pilot VM, Ubuntu 24.04, Indian region)
1. Install Docker, then clone the repo and `cp .env.example .env`. Set strong `JWT_SECRET`, `PHONE_PEPPER`,
   `POSTGRES_PASSWORD`, `SITE_ADDRESS` (domain with DNS pointing at the VM) and `ANTHROPIC_API_KEY`.
   Set `SPEECH_BACKEND=wav2vec2` and `ALLOW_SIMULATED_AUDIO=false`.
2. `docker compose up -d --build`. The API runs `alembic upgrade head` on start; Caddy obtains TLS automatically.
3. The first speech-worker start downloads the acoustic model into `/data/hf`. Watch it with
   `docker compose logs -f worker-speech`.
4. Create the org tree, schools, classrooms and users via `/v1/admin/*` (see `/docs`) with an admin account.
   Bootstrap the first admin with
   `docker compose exec api python -m app.cli create-admin --phone 98xxxxxxxx`. It prints a generated 8-digit PIN once; hand it over in person. `POST /v1/admin/users` without a `pin` also returns a generated one, and every PIN must pass the policy in `security.pin_problem`.
5. Print ID cards: `python tools/make_aruco_cards.py --from 1 --to 48`.

## Daily checks
- `GET /health`:
  - `queued` per queue should drain within minutes
  - `failed_jobs` should be 0 (inspect the `job.last_error` column)
  - `llm_spend_usd_total`
- `GET /metrics`: Prometheus gauges per queue/status. Alert if speech queue depth > 500 for 15 min.

## Scaling
- Speech backlog: `docker compose up -d --scale worker-speech=N`, or move to GPU nodes (`SPEECH_DEVICE=cuda`).
- API latency: increase `API_WORKERS` or the number of replicas behind a load balancer (the API is stateless).
- Database: move to managed Postgres; add a read replica for the admin dashboards.
- Media: switch `BLOB_BACKEND=s3` (bucket in an Indian region, SSE on).

## Backups
- Nightly `pg_dump | gzip` to encrypted object storage; keep 30 days. Audio is deliberately not backed up.

## Model / prompt changes
- Any change to `MODEL_*`, prompts in `app/llm/`, or ECCL thresholds must re-run `eval/` and beat or equal the
  current report before deploy. Calibration: `eval/run_reading_eval.py --fit eval/calibration.json`, then
  set `ECCL_CALIBRATION`.

## Incidents
- Claude outage or budget hit: the system automatically falls back to template cards and teacher-read slates. No action needed.
- Speech model failure: responses stay `pending` and are retried with backoff; fix, then restart the workers.
- Data-deletion request: `DELETE /v1/children/{id}` from the teacher app.
