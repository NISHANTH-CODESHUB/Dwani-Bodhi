"""Scoring of kiosk responses: voice (ECCL / passage, speech queue) and taps (synchronous)."""

from __future__ import annotations

import logging
import zlib
from datetime import timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..jobs.queue import enqueue
from ..models import Blob, Child, Classroom, Response, School
from ..speech.acoustic import SimulatedBackend, SimulatedUtterance, get_acoustic_model
from ..speech.audio import decode_to_16k_mono, signal_quality, trim_silence
from ..speech.calibration import load_eccl_config
from ..speech.eccl import UNSURE, score_word
from ..speech.passage import PassageConfig, score_passage
from ..storage import get_store
from .common import pack, utcnow

log = logging.getLogger(__name__)


def region_for_child(db: Session, child: Child) -> str:
    room = db.get(Classroom, child.classroom_id)
    if room and room.region_profile:
        return room.region_profile
    school = db.get(School, room.school_id) if room else None
    return school.region_profile if school else "standard"


def score_tap(r: Response) -> None:
    """Tap items are scored at sync time (no model needed)."""
    cp = pack()
    item = cp.items.get(r.item_id)
    chosen = str(r.payload.get("chosen", ""))
    if item is None:
        r.status, r.verdict = "error", {"error": "unknown item"}
        return
    if "question_id" in r.payload:  # passage comprehension question
        q = next((q for q in item.questions if q.id == r.payload["question_id"]), None)
        correct = q is not None and chosen == q.answer
        r.verdict = {"correct": correct, "chosen": chosen}
    else:
        opt = next((o for o in item.options if o.value == chosen), None)
        correct = chosen == (item.answer or "")
        r.verdict = {"correct": correct, "chosen": chosen, "probe": opt.probe if (opt and not correct) else None}
    r.confidence, r.status, r.scored_at = 1.0, "scored", utcnow()


def score_voice(db: Session, response_id: str) -> None:
    s = get_settings()
    r = db.get(Response, response_id)
    if r is None or r.status not in ("pending", "error"):
        return
    cp = pack()
    item = cp.items.get(r.item_id)
    child = db.get(Child, r.child_id)
    blob = db.scalar(select(Blob).where(Blob.response_id == r.id, Blob.kind == "audio", Blob.deleted_at.is_(None)))
    sim = r.payload.get("simulated_utterance")
    if s.speech_backend == "review" and blob is not None:
        # No acoustic model on this host: the teacher listens and confirms (1 tap) in the review queue.
        _to_teacher(db, r, blob, "teacher review")
        return
    model = get_acoustic_model()
    simulated = isinstance(model, SimulatedBackend)
    if item is None or child is None or (blob is None and not (simulated and sim is not None)):
        r.status, r.verdict = "error", {"error": "missing item/child/audio"}
        if blob is not None:
            _retire_audio(db, blob)
        db.commit()
        return
    if simulated:
        # Dev/demo path only: the simulated backend synthesises posteriors for a declared utterance.
        if not (s.allow_simulated_audio and sim is not None):
            _to_teacher(db, r, blob, "no acoustic model configured")
            return
        model.say(SimulatedUtterance(str(sim), seed=zlib.crc32(r.id.encode()) & 0xFFFF))
        wave = np.zeros(16000, dtype=np.float32)
        q = None
    else:
        wave = decode_to_16k_mono(get_store(db).get(blob.key))
        q = signal_quality(wave)
        if not q.scorable:
            r.status, r.confidence, r.scored_at = "unsure", 0.0, utcnow()
            r.verdict = {"status": UNSURE, "detail": "poor audio", "quality": q.__dict__}
            _retire_audio(db, blob, keep=True)
            db.commit()
            return
    log_probs = model.log_probs(trim_silence(wave))
    profile = cp.regions.get(region_for_child(db, child))
    if item.type == "passage":
        v = score_passage(log_probs, item.text or "", model, profile, PassageConfig(eccl=load_eccl_config())).to_dict()
        conf = max(0.0, 1.0 - 2 * (v["unsure"] / max(1, v["attempted"])))
        status = "scored" if v["attempted"] else "unsure"
    else:
        wv = score_word(log_probs, item.text or "", model, profile, load_eccl_config())
        v, conf = wv.to_dict(), wv.confidence
        status = "unsure" if wv.status in ("UNSURE", "OTHER", "NO_SPEECH") else "scored"
    if q is not None:
        v["quality"] = {"snr_db": round(q.snr_db, 1), "duration_s": round(q.duration_s, 2)}
    r.verdict, r.confidence, r.status, r.scored_at = v, conf, status, utcnow()
    if blob is not None:
        _retire_audio(db, blob, keep=status == "unsure")
    db.commit()
    enqueue(db, "update_learner", {"child_id": r.child_id}, dedupe_key=f"learner:{r.child_id}", delay_s=2)
    db.commit()


def _to_teacher(db: Session, r: Response, blob: Blob | None, detail: str) -> None:
    """Send a recording to the teacher's confirm queue. The clip is kept only for the review window."""
    r.status, r.confidence, r.scored_at = "unsure", 0.0, utcnow()
    r.verdict = {"status": UNSURE, "detail": detail}
    if blob is not None:
        _retire_audio(db, blob, keep=True)
    db.commit()


def _retire_audio(db: Session, blob: Blob, keep: bool = False) -> None:
    """Privacy by design: raw audio is deleted right after scoring. UNSURE clips are kept only until the
    teacher's 'listen' review window closes (max 7 days), then purged by the purge job."""
    s = get_settings()
    if keep:
        blob.delete_after = utcnow() + timedelta(days=7)
        return
    if s.audio_retention_hours > 0:
        blob.delete_after = utcnow() + timedelta(hours=s.audio_retention_hours)
        return
    get_store(db).delete(blob.key)
    blob.deleted_at = utcnow()


def purge_expired_blobs(db: Session) -> int:
    rows = db.scalars(select(Blob).where(Blob.deleted_at.is_(None), Blob.delete_after.is_not(None),
                                         Blob.delete_after <= utcnow())).all()
    for b in rows:
        get_store(db).delete(b.key)
        b.deleted_at = utcnow()
    db.commit()
    return len(rows)
