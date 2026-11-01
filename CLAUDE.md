# Dhwani-Bodhi — rules for the AI builder

- Design spec: `docs/GUIDE.md` (sections 6–13). Decisions log: `docs/DECISIONS.md` — add a line for every design choice.
- Backend: Python 3.11, FastAPI, SQLAlchemy 2, Alembic, pytest (`services/api`). Frontend: React+TS+Vite PWA, Vitest (`apps/web`).
- Run `cd services/api && .venv/Scripts/python -m pytest -q` before declaring any backend change done. Never leave failing tests.
- Schema changes: edit `app/models.py`, then `alembic revision --autogenerate -m "..."` and check the generated file.
- NEVER send child names, audio, faces, or school identifiers to any external API. The server stores child UUIDs only.
- Reading scoring is deterministic (ECCL, `app/speech/eccl.py`). Do not use an LLM for it.
- No misconception may be recorded without symbolic reproduction (`app/diagnosis/verify.py`) or ECCL evidence.
- Claude models: `claude-opus-5-5` (cards, explanations, hypotheses), `claude-sonnet-5-5` / `claude-haiku-5-5` (slates; pick by eval).
  Always go through `app/llm/client.py` (logging, cost, budget guard, offline fallback). Use structured outputs.
- Action Cards may only select activities from `content/packs/*/activities`. New activities need pedagogy-lead review.
- Content changes: edit YAML under `content/packs/hi-IN`; regenerate maths items with `tools/gen_math_items.py`; the pack must validate.
- All UI strings in Hindi; large touch targets; everything must work offline on a 2 GB Android phone.
- Keep pure logic (speech/, diagnosis/, learner/) free of DB and HTTP code so it stays unit-testable.
