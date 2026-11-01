"""Offline-first batch sync (guide §5.2, §11.2). Idempotent: every object carries a client UUID, so a
phone can safely retry a partially-failed upload over a flaky 2G link."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import AfterValidator, BaseModel, Field, ValidationError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from ..db import get_db
from ..jobs.queue import enqueue
from ..models import AssessmentSession, Blob, Child, Plan, Response, SlatePhoto
from ..security import Principal, can_access_classroom, current_principal
from ..services.common import pack
from ..services.scoring import score_tap
from ..storage import get_store, sha256

log = logging.getLogger("sync")
router = APIRouter(prefix="/v1", tags=["sync"])

MAX_AUDIO_BYTES = 2_000_000
MAX_IMAGE_BYTES = 6_000_000
MAX_MANIFEST_BYTES = 2_000_000
MAX_REQUEST_BYTES = 64_000_000  # the phone sends <= 5 MB batches; anything far larger is not our client
MAX_PARTS = 400
AUDIO_MIME = {"audio/webm", "audio/ogg", "audio/mp4", "audio/wav", "audio/x-wav", "audio/mpeg", "audio/aac"}
IMAGE_MIME = {"image/jpeg", "image/png", "image/webp"}
# Client ids become database keys and blob paths, so they must be real UUIDs (no "..", "/", NUL, ...).
# Phones send local offsets (+05:30); SQLite drops offsets on storage, so store everything as UTC.
UtcDatetime = Annotated[datetime, AfterValidator(lambda d: d.astimezone(UTC) if d.tzinfo else d.replace(tzinfo=UTC))]
UUID_RE = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


class ResponseIn(BaseModel):
    id: str = Field(pattern=UUID_RE)
    item_id: str = Field(min_length=1, max_length=64)
    modality: Literal["voice", "tap"]
    payload: dict = Field(default_factory=dict)
    created_at: UtcDatetime
    audio_part: str | None = Field(None, max_length=64)  # name of the multipart file field holding the audio


class SessionIn(BaseModel):
    id: str = Field(pattern=UUID_RE)
    child_id: str = Field(pattern=UUID_RE)
    classroom_id: str = Field(pattern=UUID_RE)
    started_at: UtcDatetime
    ended_at: UtcDatetime | None = None
    plan_id: str | None = Field(None, max_length=36)
    discontinued: bool = False
    responses: list[ResponseIn] = Field(default_factory=list, max_length=200)


class SlateProblemIn(BaseModel):
    item_id: str = Field(min_length=1, max_length=64)
    a: int = Field(ge=0, le=100_000)
    b: int = Field(ge=0, le=100_000)
    op: Literal["+", "-"]


class SlatePhotoIn(BaseModel):
    id: str = Field(pattern=UUID_RE)
    classroom_id: str = Field(pattern=UUID_RE)
    taken_at: UtcDatetime
    problems: list[SlateProblemIn] = Field(max_length=50)
    image_part: str = Field(max_length=64)


class Manifest(BaseModel):
    device_id: str | None = Field(None, max_length=64)
    sessions: list[SessionIn] = Field(default_factory=list, max_length=200)
    slate_photos: list[SlatePhotoIn] = Field(default_factory=list, max_length=50)


class MediaProblem(Exception):
    """A single bad file: reject that one object, keep the rest of the batch."""


def _media(files: dict[str, UploadFile], blobs: dict[str, bytes], name: str | None,
           allowed: set[str], limit: int) -> tuple[bytes, str] | None:
    if not name or name not in files:
        return None
    mime = (files[name].content_type or "").split(";")[0].strip()
    if mime not in allowed:
        raise MediaProblem(f"unsupported media type {mime}")
    data = blobs[name]
    if len(data) > limit:
        raise MediaProblem("file too large")
    return (data, mime) if data else None


@router.post("/sync")
async def sync(request: Request, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_REQUEST_BYTES:
        raise HTTPException(413, "sync batch too large")
    form = await request.form(max_files=MAX_PARTS, max_fields=MAX_PARTS)
    raw = form.get("manifest")
    if raw is None:
        raise HTTPException(422, "manifest field required")
    try:
        text = raw if isinstance(raw, str) else (await raw.read(MAX_MANIFEST_BYTES + 1)).decode()
        if len(text) > MAX_MANIFEST_BYTES:
            raise HTTPException(413, "manifest too large")
        manifest = Manifest.model_validate(json.loads(text))
    except (ValidationError, json.JSONDecodeError, UnicodeDecodeError) as e:
        raise HTTPException(422, f"bad manifest: {e}") from e

    # Read only the parts the manifest refers to, capped just above the largest per-kind limit.
    wanted = {r.audio_part for s in manifest.sessions for r in s.responses if r.audio_part}
    wanted |= {ph.image_part for ph in manifest.slate_photos}
    files = {k: v for k, v in form.multi_items() if k in wanted and isinstance(v, UploadFile)}
    blobs = {k: await f.read(MAX_IMAGE_BYTES + 1) for k, f in files.items()}
    # DB and blob-store calls block (boto3 for S3): run them off the event loop so other requests proceed.
    return await run_in_threadpool(_apply, manifest, files, blobs, p, db)


def _apply(manifest: Manifest, files: dict[str, UploadFile], blobs: dict[str, bytes], p: Principal,
           db: Session) -> dict:
    cp = pack()
    store = get_store()
    accepted: dict[str, list[str]] = {"sessions": [], "responses": [], "slate_photos": []}
    duplicates: list[str] = []
    rejected: list[dict] = []
    children_touched: set[str] = set()
    written: list[str] = []  # blob keys stored by this request: removed again if the commit fails

    try:
        for s in manifest.sessions:
            child = db.get(Child, s.child_id)
            if (child is None or child.deleted_at is not None or child.classroom_id != s.classroom_id
                    or not can_access_classroom(db, p, s.classroom_id)):
                rejected.append({"id": s.id, "reason": "unknown child or no access"})
                continue
            if child.consent_status != "granted":
                rejected.append({"id": s.id, "reason": "no parental consent recorded"})
                continue
            existing = db.get(AssessmentSession, s.id)
            if existing is not None and existing.child_id != s.child_id:
                rejected.append({"id": s.id, "reason": "session id already used"})
                continue
            if existing is None:
                db.add(AssessmentSession(id=s.id, child_id=s.child_id, classroom_id=s.classroom_id,
                                         device_id=manifest.device_id, started_at=s.started_at,
                                         ended_at=s.ended_at, plan_id=s.plan_id, content_version=cp.version,
                                         discontinued=s.discontinued))
                accepted["sessions"].append(s.id)
                if s.plan_id and (plan := db.get(Plan, s.plan_id)):
                    plan.consumed = True
            for r in s.responses:
                if db.get(Response, r.id):
                    duplicates.append(r.id)
                    continue
                item = cp.items.get(r.item_id)
                if item is None:
                    rejected.append({"id": r.id, "reason": f"unknown item {r.item_id}"})
                    continue
                audio = None
                if r.modality == "voice":
                    try:
                        audio = _media(files, blobs, r.audio_part, AUDIO_MIME, MAX_AUDIO_BYTES)
                    except MediaProblem as e:
                        rejected.append({"id": r.id, "reason": str(e)})
                        continue
                    if audio is None and "simulated_utterance" not in r.payload:
                        # Never "accepted": the phone would then delete its only copy of the recording.
                        rejected.append({"id": r.id, "reason": "audio missing"})
                        continue
                resp = Response(id=r.id, session_id=s.id, child_id=s.child_id, item_id=r.item_id,
                                item_type=item.type, modality=r.modality, payload=r.payload,
                                created_at=r.created_at, content_version=cp.version)
                db.add(resp)
                if r.modality == "tap":
                    score_tap(resp)
                    children_touched.add(s.child_id)
                else:
                    if audio:
                        data, mime = audio
                        key = f"audio/{s.classroom_id}/{s.child_id}/{r.id}"
                        store.put(key, data, mime)
                        written.append(key)
                        db.add(Blob(kind="audio", response_id=r.id, key=key, mime=mime, size=len(data),
                                    sha256=sha256(data)))
                    db.flush()
                    enqueue(db, "score_voice", {"response_id": r.id}, dedupe_key=f"voice:{r.id}")
                accepted["responses"].append(r.id)

        for ph in manifest.slate_photos:
            if not can_access_classroom(db, p, ph.classroom_id):
                rejected.append({"id": ph.id, "reason": "no access"})
                continue
            if db.get(SlatePhoto, ph.id):
                duplicates.append(ph.id)
                continue
            try:
                img = _media(files, blobs, ph.image_part, IMAGE_MIME, MAX_IMAGE_BYTES)
            except MediaProblem as e:
                rejected.append({"id": ph.id, "reason": str(e)})
                continue
            if img is None:
                rejected.append({"id": ph.id, "reason": "image missing"})
                continue
            data, mime = img
            key = f"slates/{ph.classroom_id}/{ph.id}/photo"
            store.put(key, data, mime)
            written.append(key)
            db.add(SlatePhoto(id=ph.id, classroom_id=ph.classroom_id, taken_at=ph.taken_at,
                              problems=[x.model_dump() for x in ph.problems]))
            db.add(Blob(kind="slate_photo", slate_photo_id=ph.id, key=key, mime=mime, size=len(data),
                        sha256=sha256(data)))
            db.flush()
            enqueue(db, "process_slate", {"photo_id": ph.id}, dedupe_key=f"slate:{ph.id}")
            accepted["slate_photos"].append(ph.id)

        for cid in children_touched:
            enqueue(db, "update_learner", {"child_id": cid}, dedupe_key=f"learner:{cid}", delay_s=2)
        db.commit()
    except Exception:
        db.rollback()
        for key in written:  # no DB row points at these files any more: never leave child audio orphaned
            try:
                store.delete(key)
            except Exception:  # best effort; the original error is what matters
                log.warning("could not remove orphaned blob %s", key, exc_info=True)
        raise
    return {"accepted": accepted, "duplicates": duplicates, "rejected": rejected, "content_version": cp.version}
