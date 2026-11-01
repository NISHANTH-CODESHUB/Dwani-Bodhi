"""Weekly Action Card: class summary → (Claude Opus | template) card → re-check registration (N5)."""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..content.pack import ContentPack
from ..content.schema import Activity
from ..learner.misconceptions import CONFIRMED, SUSPECTED
from ..llm import card as llm_card
from ..llm.client import LLMUnavailable
from ..models import ActionCard, Child, LearnerAux, MisconceptionState, Recheck, Response
from .catalog import describe
from .common import iso_week, pack, today

log = logging.getLogger(__name__)
MIN_GROUP = 3


def _examples(db: Session, child_ids: list[str], mis_id: str, limit: int = 4) -> list[str]:
    out: list[str] = []
    rows = db.scalars(select(Response).where(Response.child_id.in_(child_ids), Response.status.in_(["scored", "confirmed"]))
                      .order_by(Response.created_at.desc()).limit(400)).all()
    for r in rows:
        v = r.verdict or {}
        ex = None
        if mis_id.startswith("READ_") and v.get("rule") == mis_id[5:] and v.get("produced"):
            ex = f"{v.get('target')} → {v.get('produced')}"
        elif r.item_type == "slate" and mis_id in (v.get("matching_bugs") or []):
            ex = f"{v['a']}{v['op']}{v['b']}={v['answer']}"
        if ex and ex not in out:
            out.append(ex)
        if len(out) >= limit:
            break
    return out


def _candidates(cp: ContentPack, domain: str, rung: str, top: list[tuple[str, int]], blocking: list[str]) -> list[str]:
    """Rank activities by how many children's confirmed/suspected confusions they target (weighted by
    child count), then by blocking skills, then by level fit. The top confusion dominates the choice."""
    scored = []
    for a in cp.activities.values():
        if a.domain != domain:
            continue
        targets = set(a.targets)
        s = 0.0
        for rank, (mid, n) in enumerate(top):
            tags = set(describe(mid)["tags"]) | {mid}
            if tags & targets:
                s += 3.0 * n * (1.0 if rank == 0 else 0.5)
        s += 1.0 * len(set(blocking) & targets) + (0.5 if rung in a.levels else 0.0)
        if s > 0:
            scored.append((s, a.id))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [aid for _, aid in scored[:4]]


def _n_children_hi(n: int) -> str:
    """'1 child' / '5 children'."""
    return f"{n} child" if n == 1 else f"{n} children"


def build_summary(db: Session, classroom_id: str) -> tuple[dict, dict[str, list[str]]]:
    cp = pack()
    kids = db.scalars(select(Child).where(Child.classroom_id == classroom_id, Child.deleted_at.is_(None),
                                          Child.consent_status == "granted")).all()
    members: dict[str, list[str]] = defaultdict(list)
    blocking: dict[str, Counter] = defaultdict(Counter)
    rung_name: dict[str, str] = {}
    for c in kids:
        aux = db.get(LearnerAux, c.id)
        for dom, lv in ((aux.levels if aux else {}) or {}).items():
            key = f"{dom}:{lv['rung_id']}"
            members[key].append(c.id)
            rung_name[key] = lv["name_hi"]
            blocking[key].update(lv.get("blocking_skills", []))
    # Merge tiny groups up the ladder (TaRL groups need a workable size): a small group joins the next
    # level; a small top group joins the level below it.
    for dom in cp.graph.ladders:
        order = ["beginner"] + [r.id for r in cp.graph.ladders[dom]]
        keys = [f"{dom}:{r}" for r in order if f"{dom}:{r}" in members]
        kept: list[str] = []
        for i, k in enumerate(keys):
            if len(members[k]) < MIN_GROUP and i + 1 < len(keys):
                nxt = keys[i + 1]
                members[nxt] = members.pop(k) + members[nxt]
                blocking[nxt].update(blocking.pop(k, Counter()))
            else:
                kept.append(k)
        if len(kept) > 1 and len(members[kept[-1]]) < MIN_GROUP:
            last, prev = kept[-1], kept[-2]
            members[prev].extend(members.pop(last))
            blocking[prev].update(blocking.pop(last, Counter()))
    groups = []
    for key, ids in sorted(members.items()):
        dom, rung = key.split(":")
        mis, sure = Counter(), Counter()
        for row in db.scalars(select(MisconceptionState).where(MisconceptionState.child_id.in_(ids),
                                                              MisconceptionState.status.in_([CONFIRMED, SUSPECTED]))):
            if describe(row.mis_id)["domain"] == dom:
                mis[row.mis_id] += 1
                sure[row.mis_id] += row.status == CONFIRMED
        # Confirmed evidence ranks first; suspected-only confusions are still worth an activity.
        top = sorted(mis.items(), key=lambda t: (-sure[t[0]], -t[1], t[0]))[:3]
        groups.append({
            "key": key, "domain": dom, "level_id": rung, "level_name_hi": rung_name.get(key, rung),
            "n_children": len(ids),
            "top_confusions": [{"id": m, "n_children": n, "n_confirmed": sure[m], "n_suspected": n - sure[m],
                                "description_hi": describe(m)["description_hi"],
                                "examples": _examples(db, ids, m)} for m, n in top],
            "blocking_skills": [s for s, _ in blocking[key].most_common(3)],
            "candidate_activities": _candidates(cp, dom, rung, top, [s for s, _ in blocking[key].most_common(3)]),
        })
    last = _last_week_outcomes(db, classroom_id)
    return {"n_children": len(kids), "groups": groups, "last_week": last}, dict(members)


def _last_week_outcomes(db: Session, classroom_id: str) -> dict:
    rows = db.scalars(select(Recheck).join(Child, Child.id == Recheck.child_id)
                      .where(Child.classroom_id == classroom_id, Recheck.outcome.is_not(None))).all()
    c = Counter(r.outcome for r in rows)
    return {"resolved": c.get("resolved", 0), "improved": c.get("improved", 0), "persists": c.get("persists", 0)}


def why_hi(t: dict) -> str:
    """Evidence sentence that never states a suspected confusion as fact."""
    sure, maybe = t.get("n_confirmed", t["n_children"]), t.get("n_suspected", 0)
    desc = t["description_hi"].rstrip("।. ")
    if sure and maybe:
        return f"Confirmed in {_n_children_hi(sure)}: {desc}. Possibly also in {_n_children_hi(maybe)} — we will check next week."
    if sure:
        return f"Confirmed in {_n_children_hi(sure)}: {desc}."
    return f"Possibly in {_n_children_hi(maybe)} (still being checked): {desc}."


def template_card(summary: dict, activities: dict[str, Activity]) -> llm_card.CardOut:
    groups = []
    for g in summary["groups"]:
        if not g["candidate_activities"]:
            continue
        act = activities[g["candidate_activities"][0]]
        if g["top_confusions"]:
            t = g["top_confusions"][0]
            why = why_hi(t)
            ex = t["examples"]
        else:
            why = f"{_n_children_hi(g['n_children'])} at level '{g['level_name_hi']}'"
            ex = []
        groups.append(llm_card.CardGroup(group_key=g["key"], activity_id=act.id, title_hi=act.title_hi, why_hi=why,
                                         steps_hi=[s.hi for s in act.steps], example_items=ex))
    return llm_card.CardOut(headline_hi="This week's plan — 10 minutes for each group",
                            groups=groups, teacher_tip_hi="A little practice every day makes a big difference. Well done!")


def generate_card(db: Session, classroom_id: str, day: date | None = None, force: bool = False) -> ActionCard:
    day = day or today()
    week = iso_week(day)
    existing = db.scalar(select(ActionCard).where(ActionCard.classroom_id == classroom_id, ActionCard.week == week))
    if existing and not force:
        return existing
    cp = pack()
    summary, members = build_summary(db, classroom_id)
    source, model = "template", None
    try:
        out = llm_card.generate(db, summary, cp.activities, ref=classroom_id)
        errs = llm_card.validate(out, summary, cp.activities)
        if errs:  # one retry with the validator's findings (GUIDE §9.3), then the template
            log.warning("card validation failed, retrying once: %s", errs)
            out = llm_card.generate(db, summary, cp.activities, ref=classroom_id, fix=errs)
            errs = llm_card.validate(out, summary, cp.activities)
        if errs:
            log.warning("card validation failed: %s", errs)
            raise LLMUnavailable("; ".join(errs))
        source, model = "llm", get_settings().model_card
    except LLMUnavailable:
        out = template_card(summary, cp.activities)
    card = out.model_dump()
    if existing:
        existing.card, existing.summary, existing.source, existing.model = card, summary, source, model
        row = existing
    else:
        row = ActionCard(classroom_id=classroom_id, week=week, card=card, summary=summary, source=source, model=model)
        db.add(row)
    try:
        db.flush()
    except IntegrityError:
        # Another request/worker wrote this week's card while ours was being generated: use theirs.
        db.rollback()
        other = db.scalar(select(ActionCard).where(ActionCard.classroom_id == classroom_id, ActionCard.week == week))
        if other is None:
            raise
        return other
    _register_rechecks(db, row, out, members, day)
    db.commit()
    return row


def _register_rechecks(db: Session, row: ActionCard, out: llm_card.CardOut, members: dict, day: date) -> None:
    cp = pack()
    due = day + timedelta(days=14)
    for g in out.groups:
        act = cp.activities.get(g.activity_id)
        if act is None:
            continue
        for cid in members.get(g.group_key, []):
            targets = []
            for ms in db.scalars(select(MisconceptionState).where(
                    MisconceptionState.child_id == cid, MisconceptionState.status == CONFIRMED)):
                tags = set(describe(ms.mis_id)["tags"]) | {ms.mis_id}
                if tags & set(act.targets):
                    targets.append((ms.mis_id, ms.alpha / (ms.alpha + ms.beta)))
            for tid, base in targets:
                exists = db.scalar(select(Recheck.id).where(Recheck.child_id == cid, Recheck.target_id == tid,
                                                            Recheck.outcome.is_(None)))
                if exists:
                    continue
                db.add(Recheck(child_id=cid, target_id=tid, activity_id=act.id, card_id=row.id, baseline=base, due=due))
                aux = db.get(LearnerAux, cid)
                if aux is not None:
                    aux.recheck = sorted(set(aux.recheck or []) | {tid})


def efficacy(db: Session, classroom_ids: list[str] | None = None) -> list[dict]:
    """Resolution rate per (activity, misconception) — the evidence engine of N5."""
    q = select(Recheck).where(Recheck.outcome.is_not(None))
    if classroom_ids is not None:
        q = q.join(Child, Child.id == Recheck.child_id).where(Child.classroom_id.in_(classroom_ids))
    agg: dict = defaultdict(Counter)
    for r in db.scalars(q):
        agg[(r.activity_id, r.target_id)][r.outcome] += 1
    out = []
    for (aid, tid), c in agg.items():
        n = sum(c.values())
        out.append({"activity_id": aid, "target_id": tid, "n": n, "resolved": c["resolved"],
                    "improved": c["improved"], "persists": c["persists"],
                    "resolution_rate": round(c["resolved"] / n, 3) if n else None})
    return sorted(out, key=lambda d: -d["n"])

