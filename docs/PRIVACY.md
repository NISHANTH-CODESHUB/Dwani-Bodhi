# Privacy, safety and compliance (DPDP Act 2023)

Designed for full compliance with verifiable parental consent, whatever exemptions the DPDP Rules may
allow (⚠️ verify current commencement status and educational-institution exemptions with counsel).

| Principle | Implementation | Code |
|---|---|---|
| Consent | Sync rejects any session for a child without `consent_status = granted` | `api/sync.py` |
| Minimisation | Server stores child UUID, grade, ID-card slot, optional gender (fairness reporting). **Names exist only in the phone's IndexedDB.** | `models.Child` |
| No names to AI | Explanations use the `{{child}}` placeholder; the phone substitutes the name locally | `llm/explain.py` |
| No faces to AI | Slates are cropped by ArUco geometry and the marker is blanked before any API call | `vision/slates.py` |
| No classroom photos kept | The full slate photo is deleted as soon as crops exist; crops expire after `SLATE_CROP_RETENTION_DAYS` (default 30) | `services/slates.py` |
| Storage limitation | Raw audio deleted immediately after scoring; UNSURE clips kept ≤ 7 days for teacher review, then purged | `services/scoring.py` |
| Erasure | `DELETE /v1/children/{id}` removes responses, states, plans, sessions, re-checks, audio, slate crops, child-scoped jobs and cost-log references | `api/classroom.py` |
| Purpose limitation | Classroom endpoints: only the class teacher (there is no admin role). The server never holds names; students are shown by register number | `security.can_access_classroom`, `services/reports.py` |
| Security | 6–12 digit PINs with a guessability policy, forced change of weak PINs, PIN change revokes all sessions, lockout after 5 wrong tries, PBKDF2 PINs, HMAC-peppered phone numbers, JWT, TLS (Caddy), encrypted S3 objects, prod refuses dev secrets | `security.py`, `main.py` |
| Location | Deploy DB and blobs in an Indian region; Claude receives only de-identified content | `docker-compose.yml` |
| Fairness | Dialect tolerance profiles; listen-and-repeat control; eval reports accuracy by group | `speech/regions.py`, `eval/` |

Child wellbeing:
- no scores are shown to children
- sessions end on a success item
- no free-speech collection
- no facial recognition
- no third-party analytics
