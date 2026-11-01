"""Persist/restore LearnerState and apply scored responses (guide §8)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..content.pack import ContentPack
from ..content.schema import TAP_TYPES
from ..learner.levels import assign_level
from ..learner.misconceptions import CONFIRMED, RESOLVED, BetaState
from ..learner.planner import plan_session
from ..learner.state import LearnerState
from ..models import Child, LearnerAux, MisconceptionState, Plan, Recheck, Response, SkillState
from .common import as_utc, pack, utcnow


def load_state(db: Session, child: Child, cp: ContentPack | None = None) -> LearnerState:
    cp = cp or pack()
    st = LearnerState(child_id=child.id, grade=child.grade)
    for row in db.scalars(select(SkillState).where(SkillState.child_id == child.id)):
        st.skills[row.skill_id] = row.p
        st.n_obs[row.skill_id] = row.n_obs
    for row in db.scalars(select(MisconceptionState).where(MisconceptionState.child_id == child.id)):
        st.misconceptions[row.mis_id] = BetaState(row.alpha, row.beta, row.was_confirmed, row.verified or 0.0)
    aux = db.get(LearnerAux, child.id)
    if aux:
        st.speech_variants = set(aux.speech_variants or [])
        st.recheck = set(aux.recheck or [])
        st.wcpm_history = [tuple(x) for x in (aux.wcpm_history or [])]
        st.sounding_out_count = aux.sounding_out_count or 0
        st.last_updated = as_utc(aux.last_updated)
    st.ensure(cp.graph)
    return st


def save_state(db: Session, st: LearnerState, cp: ContentPack, assessed_on: date | None = None) -> dict:
    now = utcnow()
    for sid, p in st.skills.items():
        row = db.get(SkillState, (st.child_id, sid))
        if row is None:
            db.add(SkillState(child_id=st.child_id, skill_id=sid, p=p, n_obs=st.n_obs.get(sid, 0), updated_at=now))
        else:
            row.p, row.n_obs, row.updated_at = p, st.n_obs.get(sid, 0), now
    for mid, m in st.misconceptions.items():
        row = db.get(MisconceptionState, (st.child_id, mid))
        status = m.status
        if row is None:
            row = MisconceptionState(child_id=st.child_id, mis_id=mid, alpha=m.alpha, beta=m.beta)
            db.add(row)
        if status == CONFIRMED and row.first_confirmed_at is None:
            row.first_confirmed_at = now
        if status == RESOLVED and row.resolved_at is None:
            row.resolved_at = now
        row.alpha, row.beta, row.was_confirmed, row.status, row.updated_at = m.alpha, m.beta, m.was_confirmed, status, now
        row.verified = m.verified
    levels = {dom: assign_level(cp.graph, st.skills, dom).to_dict() for dom in cp.graph.ladders}
    aux = db.get(LearnerAux, st.child_id)
    if aux is None:
        aux = LearnerAux(child_id=st.child_id)
        db.add(aux)
    aux.speech_variants = sorted(st.speech_variants)
    aux.recheck = sorted(st.recheck)
    aux.wcpm_history = [list(x) for x in st.wcpm_history][-20:]
    aux.sounding_out_count = st.sounding_out_count
    aux.levels = levels
    aux.last_updated = st.last_updated or now
    if assessed_on:
        aux.last_assessed = assessed_on
    return levels


def apply_response(st: LearnerState, r: Response, cp: ContentPack) -> None:
    item = cp.items.get(r.item_id)
    if item is None or r.verdict is None:
        return
    v = r.verdict
    if r.item_type in ("akshara", "word", "nonword"):
        st.observe_reading_word(cp.graph, v, item.skills, item.probes)
    elif r.item_type == "repeat":
        st.observe_reading_word(cp.graph, v, item.skills, item.probes, control=True)
    elif r.item_type == "passage":
        if "question_id" in r.payload:  # comprehension answer to the passage's question
            st.observe_tap(cp.graph, ["L11"], bool(v.get("correct")))
        else:
            bench = cp.benchmarks.wcpm_by_grade.get(st.grade, 45)
            st.observe_passage(cp.graph, v, bench, item.skills)
    elif r.item_type in TAP_TYPES:
        st.observe_tap(cp.graph, item.skills, bool(v.get("correct")), v.get("probe"))
    elif r.item_type == "slate":
        st.observe_slate(cp.graph, v, item.skills, float(r.confidence or 1.0))


def update_child(db: Session, child_id: str) -> dict | None:
    """Apply all scored-but-unapplied responses in order, refresh levels, rechecks and next plan."""
    cp = pack()
    # Row lock (Postgres): two learner workers for the same child would otherwise both start from the same
    # state and the last commit would silently drop the other's evidence. SQLite ignores FOR UPDATE.
    child = db.scalar(select(Child).where(Child.id == child_id).with_for_update())
    if child is None or child.deleted_at is not None:  # never re-create state for an erased child
        return None
    st = load_state(db, child, cp)
    st.advance_time(utcnow())
    rows = db.scalars(
        select(Response).where(Response.child_id == child_id, Response.applied.is_(False),
                               Response.status.in_(["scored", "confirmed"]))
        .order_by(Response.created_at)
    ).all()
    touched: set[str] = set()
    for r in rows:
        apply_response(st, r, cp)
        r.applied = True
        item = cp.items.get(r.item_id)
        if item:
            touched.update(item.skills)
            touched.update(item.probes)
    st.recheck -= {s for s in touched if s in st.recheck and st.n_obs.get(s, 0) > 0}
    levels = save_state(db, st, cp, assessed_on=utcnow().date() if rows else None)
    _update_rechecks(db, st)
    plan = plan_session(st, cp, last_seen=_last_seen(db, child_id))
    db.add(Plan(child_id=child_id, plan=plan.to_dict()))
    db.commit()
    return {"levels": levels, "applied": len(rows)}


def _last_seen(db: Session, child_id: str) -> dict:
    out: dict = {}
    for item_id, created in db.execute(
        select(Response.item_id, Response.created_at).where(Response.child_id == child_id)
    ):
        d = as_utc(created).date()
        if item_id not in out or d > out[item_id]:
            out[item_id] = d
    return out


def _update_rechecks(db: Session, st: LearnerState) -> None:
    """N5: close re-checks whose target has new evidence and record the outcome."""
    open_rows = db.scalars(select(Recheck).where(Recheck.child_id == st.child_id, Recheck.outcome.is_(None))).all()
    for rc in open_rows:
        if rc.target_id in st.misconceptions:
            m = st.misconceptions[rc.target_id]
            rc.latest = m.mean
            if m.status == RESOLVED or m.mean < 0.3:
                rc.outcome, rc.closed_at = "resolved", utcnow()
            elif m.mean < rc.baseline - 0.1:
                rc.outcome = None  # improving; keep open until due
        elif rc.target_id in st.skills:
            rc.latest = st.skills[rc.target_id]
            if rc.latest >= 0.8:
                rc.outcome, rc.closed_at = "resolved", utcnow()
        if rc.outcome is None and rc.due < utcnow().date():
            improved = rc.latest is not None and (
                rc.latest < rc.baseline - 0.1 if rc.target_id in st.misconceptions else rc.latest > rc.baseline + 0.1)
            rc.outcome, rc.closed_at = ("improved" if improved else "persists"), utcnow()
