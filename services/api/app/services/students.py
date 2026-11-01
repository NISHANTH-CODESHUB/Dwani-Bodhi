"""Student register numbers and activity read models (teacher + admin dashboards).

Names never reach the server: a student is identified here by the register number (and the class ID-card
number). Statistics are computed with grouped queries, so a page costs a fixed number of queries.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Date, case, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..learner.misconceptions import CONFIRMED
from ..models import (
    AssessmentSession,
    Child,
    Classroom,
    ClassroomTeacher,
    LearnerAux,
    MisconceptionState,
    Response,
    School,
    User,
)
from .common import as_utc, pack

REGISTER_RE = re.compile(r"^STU-(\d{4})-(\d{5,})$")
LITERACY_TYPES = {"akshara", "word", "nonword", "repeat", "passage"}
PASSAGE_PASS_ACCURACY = 0.85  # a passage read with >= 85% words correct counts as a correct attempt


# ------------------------------------------------------------------------------ register numbers
def format_register_no(year: int, seq: int) -> str:
    return f"STU-{year}-{seq:05d}"


def next_register_no(db: Session, year: int) -> str:
    """Next free number for `year` (sequence restarts each year). Unique constraint + retry handles races."""
    prefix = f"STU-{year}-"
    seqs = [int(m.group(2)) for (r,) in db.execute(select(Child.register_no).where(Child.register_no.like(prefix + "%")))
            if r and (m := REGISTER_RE.match(r))]
    return format_register_no(year, max(seqs, default=0) + 1)


def assign_register_no(db: Session, child: Child, attempts: int = 5) -> str:
    """Give `child` a permanent register number (no-op if it has one). Uses a savepoint per try, so a
    concurrent insert of the same number only retries this step, never the caller's transaction."""
    if child.register_no:
        return child.register_no
    year = as_utc(child.created_at or datetime.now(UTC)).year
    for _ in range(attempts):
        candidate = next_register_no(db, year)
        try:
            with db.begin_nested():
                child.register_no = candidate
                db.flush()
            return candidate
        except IntegrityError:
            child.register_no = None
    raise RuntimeError("could not allocate a register number")


def backfill_register_numbers(db: Session) -> int:
    kids = db.scalars(select(Child).where(Child.register_no.is_(None)).order_by(Child.created_at, Child.id)).all()
    for c in kids:
        assign_register_no(db, c)
    return len(kids)


# ------------------------------------------------------------------------------ outcomes
def outcome(r: Response) -> str:
    """correct | incorrect | unsure | pending | error — one comparable result per response type."""
    if r.status in ("pending", "error", "unsure"):
        return r.status
    v = r.verdict or {}
    if "status" in v:  # reading items, slates (ECCL / procedure verification)
        return "correct" if v["status"] == "CORRECT" else "incorrect" if v["status"] in ("ERROR", "BUG", "WRONG") else "unsure"
    if r.item_type == "passage" and "accuracy" in v:
        return "correct" if (v.get("accuracy") or 0) >= PASSAGE_PASS_ACCURACY else "incorrect"
    if isinstance(v.get("correct"), bool):  # tap items
        return "correct" if v["correct"] else "incorrect"
    return "unsure"


def domain_of(item_type: str) -> str:
    return "literacy" if item_type in LITERACY_TYPES else "numeracy"


def _accuracy(c: int, i: int) -> float | None:
    return round(c / (c + i), 3) if c + i else None


def _iso(d: datetime | date | None) -> str | None:
    if d is None:
        return None
    return as_utc(d).isoformat() if isinstance(d, datetime) else d.isoformat()


def _now() -> datetime:
    return datetime.now(UTC)


def _level(lv: dict, domain: str) -> dict | None:
    x = (lv or {}).get(domain)
    return {"rung_id": x.get("rung_id"), "name": x.get("name_en") or x.get("name_hi"), "certain": x.get("certain")} \
        if x else None


# ------------------------------------------------------------------------------ student rows
def student_rows(db: Session, kids: list[Child]) -> list[dict]:
    """One summary row per student (fixed number of queries for any number of students)."""
    if not kids:
        return []
    ids = [c.id for c in kids]
    week_ago = _now() - timedelta(days=7)
    sess = {cid: (n, n7, last) for cid, n, n7, last in db.execute(
        select(AssessmentSession.child_id, func.count(),
               func.sum(case((AssessmentSession.started_at >= week_ago, 1), else_=0)),
               func.max(func.coalesce(AssessmentSession.ended_at, AssessmentSession.started_at)))
        .where(AssessmentSession.child_id.in_(ids)).group_by(AssessmentSession.child_id))}
    tally: dict[str, Counter] = defaultdict(Counter)
    last_resp: dict[str, datetime] = {}
    for r in db.scalars(select(Response).where(Response.child_id.in_(ids))):
        tally[r.child_id][outcome(r)] += 1
        if r.created_at and (r.child_id not in last_resp or as_utc(r.created_at) > last_resp[r.child_id]):
            last_resp[r.child_id] = as_utc(r.created_at)
    aux = {a.child_id: a for a in db.scalars(select(LearnerAux).where(LearnerAux.child_id.in_(ids)))}
    confusions = dict(db.execute(select(MisconceptionState.child_id, func.count()).where(
        MisconceptionState.child_id.in_(ids), MisconceptionState.status == CONFIRMED)
        .group_by(MisconceptionState.child_id)).all())
    rooms = {c.classroom_id for c in kids}
    room_info = {rid: (rname, sname) for rid, rname, sname in db.execute(
        select(Classroom.id, Classroom.name, School.name).join(School, Classroom.school_id == School.id)
        .where(Classroom.id.in_(rooms)))}
    teachers: dict[str, list[str]] = defaultdict(list)
    for rid, name in db.execute(select(ClassroomTeacher.classroom_id, User.display_name)
                                .join(User, User.id == ClassroomTeacher.user_id)
                                .where(ClassroomTeacher.classroom_id.in_(rooms), User.active.is_(True))):
        teachers[rid].append(name)
    out = []
    for c in kids:
        n, n7, last = sess.get(c.id, (0, 0, None))
        t = tally.get(c.id, Counter())
        lv = (aux[c.id].levels if c.id in aux else {}) or {}
        last_active = max([d for d in (as_utc(last) if last else None, last_resp.get(c.id)) if d], default=None)
        rname, sname = room_info.get(c.classroom_id, (None, None))
        out.append({
            "id": c.id, "register_no": c.register_no, "grade": c.grade, "aruco_slot": c.aruco_slot,
            "consent": c.consent_status, "classroom_id": c.classroom_id, "classroom": rname, "school": sname,
            "teachers": sorted(teachers.get(c.classroom_id, [])),
            "sessions": int(n or 0), "sessions_7d": int(n7 or 0), "responses": sum(t.values()),
            "correct": t["correct"], "incorrect": t["incorrect"], "to_review": t["unsure"],
            "accuracy": _accuracy(t["correct"], t["incorrect"]),
            "last_active": _iso(last_active),
            "last_assessed": _iso(aux[c.id].last_assessed) if c.id in aux and aux[c.id].last_assessed else None,
            "literacy": _level(lv, "literacy"), "numeracy": _level(lv, "numeracy"),
            "confirmed_confusions": int(confusions.get(c.id, 0)),
            "created_at": _iso(c.created_at),
        })
    return out


def _day(db: Session, col):
    """Calendar day (UTC) of a timestamp column. SQLite's CAST(... AS DATE) would keep only the year."""
    return func.date(col) if db.get_bind().dialect.name == "sqlite" else cast(col, Date)


def _daily(db: Session, child_ids: list[str] | None, room_ids: list[str] | None, days: int) -> list[dict]:
    """Sessions and answers per day for the last `days` days (zero-filled, oldest first)."""
    start = (_now() - timedelta(days=days - 1)).date()
    since = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
    sday, rday = _day(db, AssessmentSession.started_at), _day(db, Response.created_at)
    sq = select(sday, func.count()).where(AssessmentSession.started_at >= since)
    rq = select(rday, func.count()).where(Response.created_at >= since)
    if child_ids is not None:
        sq, rq = sq.where(AssessmentSession.child_id.in_(child_ids)), rq.where(Response.child_id.in_(child_ids))
    if room_ids is not None:
        sq = sq.where(AssessmentSession.classroom_id.in_(room_ids))
        rq = rq.where(Response.child_id.in_(select(Child.id).where(Child.classroom_id.in_(room_ids))))
    s = {str(d)[:10]: n for d, n in db.execute(sq.group_by(sday))}
    r = {str(d)[:10]: n for d, n in db.execute(rq.group_by(rday))}
    days_list = [(start + timedelta(days=i)).isoformat() for i in range(days)]
    return [{"day": d, "sessions": int(s.get(d, 0)), "answers": int(r.get(d, 0))} for d in days_list]


# ------------------------------------------------------------------------------ one student
def _item_label(r: Response) -> str:
    item = pack().items.get(r.item_id)
    prob = (r.payload or {}).get("problem")
    if r.item_type == "slate" and isinstance(prob, dict):
        return f"{prob.get('a')} {prob.get('op')} {prob.get('b')}"
    if item is None:
        return r.item_id
    if item.type == "slate" and item.a is not None:
        return f"{item.a} {item.op} {item.b}"
    text = item.text or item.prompt_hi or r.item_id
    return text if len(text) <= 60 else text[:57] + "…"


def _detail(r: Response) -> str | None:
    v = r.verdict or {}
    if r.item_type == "passage" and "wcpm" in v:
        return f"{round(v['wcpm'])} words/min, {round(100 * (v.get('accuracy') or 0))}% correct"
    if r.item_type == "slate":
        ans = (r.payload or {}).get("answer") or v.get("answer")
        return f"wrote {ans}" if ans not in (None, "") else None
    if v.get("rule"):
        return str(v["rule"])
    if "chosen" in v and v.get("correct") is False:
        return f"chose {v['chosen']}"
    return None


def child_activity(db: Session, child: Child, max_sessions: int = 30) -> dict:
    row = student_rows(db, [child])[0]
    responses = db.scalars(select(Response).where(Response.child_id == child.id)
                           .order_by(Response.created_at.desc())).all()
    by_session: dict[str | None, list[Response]] = defaultdict(list)
    for r in responses:
        by_session[r.session_id].append(r)
    by_domain: dict[str, Counter] = defaultdict(Counter)
    for r in responses:
        by_domain[domain_of(r.item_type)][outcome(r)] += 1

    def entry(r: Response) -> dict:
        return {"id": r.id, "item_id": r.item_id, "type": r.item_type, "domain": domain_of(r.item_type),
                "label": _item_label(r), "outcome": outcome(r), "detail": _detail(r), "at": _iso(r.created_at)}

    timeline = []
    sessions = db.scalars(select(AssessmentSession).where(AssessmentSession.child_id == child.id)
                          .order_by(AssessmentSession.started_at.desc()).limit(max_sessions)).all()
    for s in sessions:
        rs = sorted(by_session.get(s.id, []), key=lambda r: as_utc(r.created_at) if r.created_at else _now())
        t = Counter(outcome(r) for r in rs)
        dur = (as_utc(s.ended_at) - as_utc(s.started_at)).total_seconds() if s.ended_at and s.started_at else None
        timeline.append({"kind": "session", "id": s.id, "at": _iso(s.started_at), "ended_at": _iso(s.ended_at),
                         "duration_s": round(dur) if dur and dur > 0 else None, "discontinued": s.discontinued,
                         "answers": len(rs), "correct": t["correct"], "incorrect": t["incorrect"],
                         "to_review": t["unsure"], "waiting": t["pending"],
                         "accuracy": _accuracy(t["correct"], t["incorrect"]), "items": [entry(r) for r in rs]})
    # Slate answers come from the teacher's class photo, not a kiosk session: one group per day.
    slates: dict[str, list[Response]] = defaultdict(list)
    for r in by_session.get(None, []):
        slates[as_utc(r.created_at).date().isoformat() if r.created_at else "unknown"].append(r)
    for day, rs in slates.items():
        t = Counter(outcome(r) for r in rs)
        timeline.append({"kind": "slate", "id": f"slate-{day}", "at": _iso(min(as_utc(r.created_at) for r in rs))
                         if all(r.created_at for r in rs) else None, "ended_at": None, "duration_s": None,
                         "discontinued": False, "answers": len(rs), "correct": t["correct"],
                         "incorrect": t["incorrect"], "to_review": t["unsure"], "waiting": t["pending"],
                         "accuracy": _accuracy(t["correct"], t["incorrect"]), "items": [entry(r) for r in rs]})
    timeline.sort(key=lambda e: e["at"] or "", reverse=True)
    return {
        "student": row,
        "domains": {d: {"correct": by_domain[d]["correct"], "incorrect": by_domain[d]["incorrect"],
                        "to_review": by_domain[d]["unsure"],
                        "accuracy": _accuracy(by_domain[d]["correct"], by_domain[d]["incorrect"])}
                    for d in ("literacy", "numeracy")},
        "daily": _daily(db, [child.id], None, 30),
        "timeline": timeline[:max_sessions],
    }


# ------------------------------------------------------------------------------ one classroom
def classroom_activity(db: Session, classroom_id: str) -> dict:
    kids = db.scalars(select(Child).where(Child.classroom_id == classroom_id, Child.deleted_at.is_(None))
                      .order_by(Child.aruco_slot)).all()
    rows = student_rows(db, kids)
    daily = _daily(db, None, [classroom_id], 14)
    c = sum(r["correct"] for r in rows)
    i = sum(r["incorrect"] for r in rows)
    return {
        "totals": {"students": len(rows), "consented": sum(r["consent"] == "granted" for r in rows),
                   "assessed": sum(1 for r in rows if r["last_assessed"]),
                   "active_7d": sum(1 for r in rows if r["sessions_7d"]),
                   "sessions_14d": sum(d["sessions"] for d in daily), "answers_14d": sum(d["answers"] for d in daily),
                   "accuracy": _accuracy(c, i), "to_review": sum(r["to_review"] for r in rows)},
        "daily": daily,
        "students": rows,
    }


# ------------------------------------------------------------------------------ admin views
def scoped_rooms(db: Session, scope: set[str] | None) -> list[tuple[Classroom, School]]:
    q = select(Classroom, School).join(School, Classroom.school_id == School.id).order_by(School.name, Classroom.name)
    if scope is not None:
        q = q.where(School.org_unit_id.in_(scope))
    return [(r, s) for r, s in db.execute(q)]


def scoped_teachers(db: Session, scope: set[str] | None, room_ids: list[str]) -> list[User]:
    """Teachers of the rooms in scope, plus (unlinked) teachers placed in a unit of the scope."""
    linked = select(ClassroomTeacher.user_id).where(ClassroomTeacher.classroom_id.in_(room_ids))
    q = select(User).where(User.role == "teacher")
    if scope is not None:
        q = q.where(User.id.in_(linked) | User.org_unit_id.in_(scope))
    return list(db.scalars(q.order_by(User.display_name)))


def teacher_rows(db: Session, teachers: list[User], rooms: list[tuple[Classroom, School]]) -> list[dict]:
    if not teachers:
        return []
    room_ids = [r.id for r, _ in rooms]
    info = {r.id: (r.name, s.name) for r, s in rooms}
    links: dict[str, list[str]] = defaultdict(list)
    for rid, uid in db.execute(select(ClassroomTeacher.classroom_id, ClassroomTeacher.user_id)
                               .where(ClassroomTeacher.user_id.in_([t.id for t in teachers]))):
        links[uid].append(rid)
    students = dict(db.execute(select(Child.classroom_id, func.count()).where(
        Child.classroom_id.in_(room_ids), Child.deleted_at.is_(None)).group_by(Child.classroom_id)).all())
    now = _now()
    agg = {rid: (n7, n30, last) for rid, n7, n30, last in db.execute(
        select(AssessmentSession.classroom_id,
               func.sum(case((AssessmentSession.started_at >= now - timedelta(days=7), 1), else_=0)),
               func.sum(case((AssessmentSession.started_at >= now - timedelta(days=30), 1), else_=0)),
               func.max(AssessmentSession.started_at))
        .where(AssessmentSession.classroom_id.in_(room_ids)).group_by(AssessmentSession.classroom_id))}
    out = []
    for t in teachers:
        mine = links.get(t.id, [])
        lasts = [as_utc(agg[r][2]) for r in mine if r in agg and agg[r][2]]
        out.append({
            "id": t.id, "display_name": t.display_name, "active": t.active, "pending": t.pending,
            "last_login_at": _iso(t.last_login_at), "created_at": _iso(t.created_at),
            "classes": [{"id": r, "name": info.get(r, ("?", "?"))[0], "school": info.get(r, ("?", "?"))[1]}
                        for r in mine],
            "students": sum(int(students.get(r, 0)) for r in mine),
            "sessions_7d": sum(int(agg[r][0] or 0) for r in mine if r in agg),
            "sessions_30d": sum(int(agg[r][1] or 0) for r in mine if r in agg),
            "last_active": _iso(max(lasts)) if lasts else None,
        })
    return out


def admin_dashboard(db: Session, scope: set[str] | None) -> dict:
    rooms = scoped_rooms(db, scope)
    room_ids = [r.id for r, _ in rooms]
    schools = {s.id for _, s in rooms}
    if scope is not None:
        schools |= set(db.scalars(select(School.id).where(School.org_unit_id.in_(scope))))
    else:
        schools = set(db.scalars(select(School.id)))
    teachers = scoped_teachers(db, scope, room_ids)
    kid_ids = list(db.scalars(select(Child.id).where(Child.classroom_id.in_(room_ids), Child.deleted_at.is_(None))))
    now = _now()

    def count_sessions(days: int) -> int:
        return int(db.scalar(select(func.count()).select_from(AssessmentSession).where(
            AssessmentSession.classroom_id.in_(room_ids), AssessmentSession.started_at >= now - timedelta(days=days)))
            or 0)

    lit, num = Counter(), Counter()
    assessed = 0
    for a in db.scalars(select(LearnerAux).where(LearnerAux.child_id.in_(kid_ids))):
        lv = a.levels or {}
        if a.last_assessed:
            assessed += 1
        for dom, ctr in (("literacy", lit), ("numeracy", num)):
            x = lv.get(dom)
            if x:
                ctr[(x.get("rung_index", -1), x.get("name_en") or x.get("rung_id"))] += 1
    unassessed = len(kid_ids) - assessed
    info = {r.id: (r.name, s.name) for r, s in rooms}
    reg = dict(db.execute(select(Child.id, Child.register_no).where(Child.id.in_(kid_ids))).all())
    recent = []
    for s in db.scalars(select(AssessmentSession).where(AssessmentSession.classroom_id.in_(room_ids))
                        .order_by(AssessmentSession.started_at.desc()).limit(12)):
        recent.append({"session_id": s.id, "student_id": s.child_id, "register_no": reg.get(s.child_id),
                       "classroom": info.get(s.classroom_id, ("?", "?"))[0],
                       "school": info.get(s.classroom_id, ("?", "?"))[1], "at": _iso(s.started_at)})
    answers = {sid: n for sid, n in db.execute(select(Response.session_id, func.count()).where(
        Response.session_id.in_([e["session_id"] for e in recent])).group_by(Response.session_id))}
    for e in recent:
        e["answers"] = int(answers.get(e["session_id"], 0))
    rows = teacher_rows(db, teachers, rooms)
    rows.sort(key=lambda t: (-t["sessions_7d"], t["display_name"]))

    def dist(ctr: Counter) -> list[dict]:
        out = [{"level": name, "n": n} for (_, name), n in sorted(ctr.items())]
        return out + ([{"level": "Not assessed yet", "n": unassessed}] if unassessed > 0 else [])

    return {
        "totals": {
            "schools": len(schools), "classrooms": len(rooms),
            "teachers": sum(1 for t in teachers if t.active and not t.pending),
            "teachers_pending": sum(1 for t in teachers if t.pending),
            "students": len(kid_ids), "students_assessed": assessed,
            "sessions_7d": count_sessions(7), "sessions_30d": count_sessions(30),
        },
        "daily": _daily(db, None, room_ids, 14),
        "levels": {"literacy": dist(lit), "numeracy": dist(num)},
        "teachers": rows,
        "recent": recent,
    }


def admin_students(db: Session, scope: set[str] | None, *, school_id: str | None = None,
                   classroom_id: str | None = None, grade: int | None = None, consent: str | None = None,
                   q: str | None = None, limit: int = 50, offset: int = 0) -> dict:
    rooms = scoped_rooms(db, scope)
    room_ids = [r.id for r, s in rooms if (not school_id or s.id == school_id) and (not classroom_id or r.id == classroom_id)]
    query = select(Child).where(Child.classroom_id.in_(room_ids), Child.deleted_at.is_(None))
    if grade:
        query = query.where(Child.grade == grade)
    if consent:
        query = query.where(Child.consent_status == consent)
    if q:
        query = query.where(Child.register_no.ilike(f"%{q.strip()}%"))
    total = int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    kids = db.scalars(query.order_by(Child.register_no, Child.id).limit(limit).offset(offset)).all()
    return {"total": total, "limit": limit, "offset": offset, "students": student_rows(db, list(kids)),
            "schools": [{"id": i, "name": n} for i, n in sorted({(s.id, s.name) for _, s in rooms}, key=lambda x: x[1])],
            "classrooms": [{"id": r.id, "name": r.name, "school_id": s.id, "school": s.name} for r, s in rooms]}
