"""Slate photo pipeline: ArUco crop → Claude transcription → symbolic bug verification (guide §6.2)."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..diagnosis.verify import verify
from ..jobs.queue import enqueue
from ..llm import slate as llm_slate
from ..llm.client import LLMUnavailable
from ..models import Blob, Child, Response, SlatePhoto
from ..storage import get_store, sha256
from ..vision.slates import detect_and_crop
from .common import utcnow

log = logging.getLogger(__name__)
CONFIRM_BELOW = 0.75  # answer confidence below this → teacher 1-tap confirm queue


def process_slate(db: Session, photo_id: str) -> dict:
    photo = db.get(SlatePhoto, photo_id)
    if photo is None:
        return {"error": "missing photo"}
    blob = db.scalar(select(Blob).where(Blob.slate_photo_id == photo_id, Blob.kind == "slate_photo"))
    if blob is None:
        photo.status = "error"
        db.commit()
        return {"error": "missing blob"}
    crops, meta = detect_and_crop(get_store(db).get(blob.key))
    children = {c.aruco_slot: c for c in db.scalars(select(Child).where(
        Child.classroom_id == photo.classroom_id, Child.deleted_at.is_(None)))}
    problems = [{"problem_id": f"p{i + 1}", **p} for i, p in enumerate(photo.problems)]
    result = {"markers": meta["markers"], "slates": []}
    touched: set[str] = set()
    for crop in crops:
        child = children.get(crop.marker_id)
        entry = {"marker": crop.marker_id, "child_id": child.id if child else None, "usable": crop.usable}
        result["slates"].append(entry)
        if child is None or child.consent_status != "granted":
            entry["skipped"] = "no consented child for this marker"
            continue
        key = f"slates/{photo.classroom_id}/{photo_id}/{crop.marker_id}.jpg"
        get_store(db).put(key, crop.jpeg, "image/jpeg")
        db.add(Blob(kind="slate_crop", slate_photo_id=photo_id, key=key, mime="image/jpeg",
                    size=len(crop.jpeg), sha256=sha256(crop.jpeg),
                    delete_after=utcnow() + timedelta(days=get_settings().slate_crop_retention_days)))
        reading = None
        if crop.usable:
            try:
                reading = llm_slate.transcribe(db, crop.jpeg, "image/jpeg", problems, ref=photo_id)
            except LLMUnavailable as e:
                entry["llm"] = str(e)
        by_pid = {p.problem_id: p for p in reading.problems} if reading else {}
        for p in problems:
            pr = by_pid.get(p["problem_id"])
            rid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{photo_id}/{crop.marker_id}/{p['problem_id']}"))
            if db.get(Response, rid):
                continue
            payload = {"slate_photo_id": photo_id, "crop_key": key, "problem": p,
                       "transcription": pr.model_dump() if pr else None}
            r = Response(id=rid, child_id=child.id, item_id=p["item_id"], item_type="slate", modality="slate",
                         payload=payload, created_at=photo.taken_at)
            if pr is None:  # no model / unusable crop → teacher reads the crop and types the answer
                r.status, r.verdict, r.confidence = "unsure", {"status": "NEEDS_READING"}, 0.0
            else:
                v = verify(p["a"], p["b"], p["op"], pr.child_answer).to_dict()
                conf = llm_slate.answer_confidence(pr)
                r.verdict, r.confidence = v, conf
                r.status = "scored" if conf >= CONFIRM_BELOW and v["status"] != "ILLEGIBLE" else "unsure"
                r.scored_at = utcnow()
            db.add(r)
            touched.add(child.id)
    photo.status, photo.result = "done", result
    # Privacy (GUIDE §13.1): the full classroom photo may show faces. Only per-child answer crops are kept.
    get_store(db).delete(blob.key)
    blob.deleted_at = utcnow()
    db.commit()
    for cid in touched:
        enqueue(db, "update_learner", {"child_id": cid}, dedupe_key=f"learner:{cid}", delay_s=2)
    db.commit()
    return result


def confirm_slate_answer(r: Response, answer: str | None) -> None:
    p = r.payload["problem"]
    r.verdict = verify(p["a"], p["b"], p["op"], answer).to_dict()
    r.confidence, r.status, r.scored_at = 1.0, "confirmed", utcnow()
