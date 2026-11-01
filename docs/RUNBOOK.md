# Operations runbook

## First deployment (pilot VM, Ubuntu 24.04, Indian region)
1. Install Docker, then clone the repo and `cp .env.example .env`. Set strong `JWT_SECRET`, `PHONE_PEPPER`,
   `POSTGRES_PASSWORD`, `SITE_ADDRESS` (domain with DNS pointing at the VM) and `ANTHROPIC_API_KEY`.
   Set `SPEECH_BACKEND=wav2vec2` and `ALLOW_SIMULATED_AUDIO=false`.
2. `docker compose up -d --build`. The API runs `alembic upgrade head` on start; Caddy obtains TLS automatically.
3. The first speech-worker start downloads the acoustic model into `/data/hf`. Watch it with
   `docker compose logs -f worker-speech`.
4. Teachers create their own accounts, schools and classes in the app (*New teacher? Create an account*);
   nobody approves them. A forgotten PIN: `docker compose exec api python -m app.cli reset-pin --phone 98xxxxxxxx`
   (prints a new PIN once). Every PIN must pass the policy in `security.pin_problem`.
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
- Database: move to managed Postgres; add a read replica for reporting.
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

## Vercel deployment

See README → Deployment → Option A. Operational notes:
- Logs: Vercel → Project → *Logs* (filter `api/index`). A start-up `RuntimeError` names the missing setting
  (`JWT_SECRET`, `PHONE_PEPPER`, a Postgres `DATABASE_URL`).
- Migrations run on the first cold start after a deploy (Postgres advisory lock; concurrent starts wait).
- Daily maintenance (`/v1/cron/tick`, 03:00 IST): purges expired media, recovers stale jobs, builds weekly
  Action Cards. Needs `CRON_SECRET`. Trigger by hand: `curl -H "Authorization: Bearer $CRON_SECRET" https://<app>/v1/cron/tick`.
- Queued work is visible at `/health` (`queued`, `failed_jobs`).
- Fresh start: run `python -m app.cli reset-data --yes` locally with `DATABASE_URL` set to the Neon URL.
