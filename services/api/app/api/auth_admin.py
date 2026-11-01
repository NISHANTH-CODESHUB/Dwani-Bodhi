"""Login and administrative setup (org units, schools, classrooms, users)."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..diagnosis.bugs import DEFAULT_LIBRARY
from ..models import BugProposal, Classroom, ClassroomTeacher, Notification, OrgUnit, School, User
from ..security import (
    ORG_KINDS,
    PIN_CHANGE_SCOPE,
    Principal,
    admin_scope,
    approvers_for,
    burn_pin_check,
    can_manage_user,
    current_principal,
    generate_pin,
    hash_phone,
    hash_pin,
    in_scope,
    issue_token,
    pin_change_principal,
    pin_problem,
    require_role,
    user_org_units,
    verify_pin,
)
from ..services.common import pack
from ..services.discovery import load_approved_bugs
from ..services.notify import ACCOUNT_APPROVED, ADMIN_JOINED, SIGNUP_REQUEST, notify, resolve

router = APIRouter(prefix="/v1", tags=["auth & admin"])


class LoginIn(BaseModel):
    phone: str = Field(min_length=6, max_length=20)
    pin: str = Field(min_length=4, max_length=12)


def _classrooms_for(db: Session, user: User) -> list[dict]:
    if user.role == "teacher":
        ids = db.scalars(select(ClassroomTeacher.classroom_id).where(ClassroomTeacher.user_id == user.id)).all()
        rooms = db.scalars(select(Classroom).where(Classroom.id.in_(ids))).all()
    else:
        rooms = []
    out = []
    for r in rooms:
        s = db.get(School, r.school_id)
        out.append({"id": r.id, "name": r.name, "grades": r.grades, "school": s.name if s else None,
                    "region_profile": r.region_profile or (s.region_profile if s else "standard"),
                    "daily_kiosk_budget_min": r.daily_kiosk_budget_min})
    return out


# PINs are short, so each phone gets MAX_FAILS tries per LOCK_SECONDS window (login and PIN change).
# Per-process memory: enough for the single-API-container pilot; use Redis if the API is scaled out.
MAX_FAILS, LOCK_SECONDS = 5, 15 * 60
_fails: dict[str, list[float]] = {}


def _check_lock(key: str, limit: int = MAX_FAILS) -> list[float]:
    now = time.monotonic()
    recent = [t for t in _fails.get(key, []) if now - t < LOCK_SECONDS]
    if len(recent) >= limit:
        raise HTTPException(429, "too many wrong PINs; try again in 15 minutes")
    return recent


def _record_fail(key: str, recent: list[float]) -> None:
    _fails[key] = recent + [time.monotonic()]


def _user_out(user: User) -> dict:
    return {"id": user.id, "role": user.role, "display_name": user.display_name, "org_unit_id": user.org_unit_id}


# Per phone across all clients, a looser cap: stops distributed guessing without letting one stranger
# lock a teacher out of her own phone number (the tight limit above is per phone *and* client address).
MAX_FAILS_PER_PHONE = 20


@router.post("/auth/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)) -> dict:
    ph = hash_phone(body.phone)
    client = request.client.host if request.client else "?"
    key, phone_key = f"login:{ph}:{client}", f"login:{ph}"
    recent = _check_lock(key)
    phone_recent = _check_lock(phone_key, MAX_FAILS_PER_PHONE)
    user = db.scalar(select(User).where(User.phone_hash == ph))
    if user is None:
        burn_pin_check(body.pin)  # same cost as a wrong PIN, so timing does not reveal registered phones
    if user is None or not verify_pin(body.pin, user.pin_hash) or not (user.active or user.pending):
        _record_fail(key, recent)
        _record_fail(phone_key, phone_recent)
        raise HTTPException(401, "wrong phone or PIN")
    _fails.pop(key, None)
    _fails.pop(phone_key, None)
    if user.pending:
        raise HTTPException(403, "Your account is waiting for approval by your admin. Please try again later.")
    user.last_login_at = datetime.now(UTC)
    db.commit()
    weak = pin_problem(body.pin, body.phone)
    if weak:  # e.g. an old 4-digit PIN: the only thing this session may do is set a strong one
        return {"token": issue_token(user, scope=PIN_CHANGE_SCOPE), "user": _user_out(user), "classrooms": [],
                "pin_change_required": True, "pin_problem": weak}
    return {"token": issue_token(user), "user": _user_out(user), "classrooms": _classrooms_for(db, user),
            "pin_change_required": False}


class OpenIn(BaseModel):
    role: Literal["teacher", "admin"] = "teacher"


@router.post("/auth/open")
def open_session(body: OpenIn, db: Session = Depends(get_db)) -> dict:
    """AUTH_DISABLED (dev/demo only): sign in as the first active user of `role`, no phone or PIN."""
    if not get_settings().auth_disabled:
        raise HTTPException(404, "not found")
    user = db.scalar(select(User).where(User.role == body.role, User.active.is_(True)).order_by(User.created_at))
    if user is None:
        raise HTTPException(404, f"no active {body.role} user; run `python -m app.demo` first")
    return {"token": issue_token(user), "user": _user_out(user), "classrooms": _classrooms_for(db, user),
            "pin_change_required": False}


class PinChangeIn(BaseModel):
    current_pin: str = Field(min_length=4, max_length=12)
    new_pin: str = Field(min_length=1, max_length=12)
    phone: str | None = Field(None, max_length=20, description="optional: lets the server reject phone-derived PINs")


@router.post("/auth/pin")
def change_pin(body: PinChangeIn, p: Principal = Depends(pin_change_principal), db: Session = Depends(get_db)) -> dict:
    """Change the PIN. Ends every other session (all older tokens are rejected) and returns a fresh token."""
    user = p.user
    key = f"pinchange:{user.id}"
    recent = _check_lock(key)
    if not verify_pin(body.current_pin, user.pin_hash):
        _record_fail(key, recent)  # 400, not 401: a typo must not look like an expired session
        raise HTTPException(400, "The current PIN is wrong.")
    phone = body.phone if body.phone and hash_phone(body.phone) == user.phone_hash else None
    problem = pin_problem(body.new_pin, phone)
    if problem:
        raise HTTPException(422, problem)
    if body.new_pin == body.current_pin:
        raise HTTPException(422, "The new PIN must be different from the old one.")
    _fails.pop(key, None)
    user.pin_hash = hash_pin(body.new_pin)
    user.credentials_changed_at = datetime.now(UTC)
    db.commit()
    return {"token": issue_token(user), "user": _user_out(user), "classrooms": _classrooms_for(db, user)}


@router.get("/me")
def me(p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    u = p.user
    return {"user": _user_out(u), "classrooms": _classrooms_for(db, u), "content_version": pack().version}


# ---------------------------------------------------------------------------------- first-run setup
class SetupIn(BaseModel):
    phone: str = Field(min_length=10, max_length=20)
    pin: str = Field(min_length=1, max_length=12)
    display_name: str = Field(min_length=1, max_length=120)


@router.get("/auth/setup")
def setup_status(db: Session = Depends(get_db)) -> dict:
    """True only on a brand-new installation (no accounts yet): the app then shows the first-admin form."""
    return {"needed": db.scalar(select(User.id).limit(1)) is None}


@router.post("/auth/setup")
def setup_first_admin(body: SetupIn, db: Session = Depends(get_db)) -> dict:
    """Create the top-level (global) admin. Works exactly once: refused as soon as any account exists."""
    if db.scalar(select(User.id).limit(1)) is not None:
        raise HTTPException(409, "setup is already done; log in instead")
    problem = pin_problem(body.pin, body.phone)
    if problem:
        raise HTTPException(422, problem)
    u = User(role="admin", phone_hash=hash_phone(body.phone), pin_hash=hash_pin(body.pin),
             display_name=body.display_name.strip())
    db.add(u)
    db.commit()
    return {"token": issue_token(u), "user": _user_out(u), "classrooms": [], "pin_change_required": False}


# ---------------------------------------------------------------------------------- self sign-up
# "Create account" on the login screen.
#  - Teachers: stored as pending (inactive) until an admin above the class approves; every admin who may
#    approve gets a notification on their dashboard.
#  - Admins (ADMIN_SELF_SIGNUP, default on): active at once as admin of the chosen unit and signed in
#    straight away; the admins above that unit are notified. Never a top-level admin.
MAX_SIGNUPS = 5  # per client address per LOCK_SECONDS


@router.get("/auth/signup-options")
def signup_options(db: Session = Depends(get_db)) -> dict:
    """Units and classes a new account can ask to join (names only; no people, no child data)."""
    units = [{"id": o.id, "kind": o.kind, "name": o.name, "parent_id": o.parent_id}
             for o in db.scalars(select(OrgUnit).order_by(OrgUnit.name))]
    rooms = [{"id": c.id, "name": c.name, "school": s.name, "org_unit_id": s.org_unit_id}
             for c, s in db.execute(select(Classroom, School).join(School, Classroom.school_id == School.id)
                                    .order_by(School.name, Classroom.name)).all()]
    return {"units": units, "classrooms": rooms}


def _signup_units(db: Session, role: str, org_unit_id: str | None, classroom_ids: list[str]) -> set[str | None]:
    """Where a requested account would sit: a teacher's class schools, otherwise the chosen unit."""
    if role == "teacher":
        units: set[str | None] = set()
        for cid in classroom_ids:
            room = db.get(Classroom, cid)
            if room is None:
                raise HTTPException(404, "classroom not found")
            units.add(room.school.org_unit_id)
        return units
    return {org_unit_id} if org_unit_id else set()


def _unit_name(db: Session, org_unit_id: str | None) -> str | None:
    ou = db.get(OrgUnit, org_unit_id) if org_unit_id else None
    return ou.name if ou else None


@router.get("/auth/approvers")
def signup_approvers(role: Literal["teacher", "admin"], org_unit_id: str | None = None,
                     classroom_id: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    """Admins a sign-up request can be sent to: only those above the requested place, nearest first."""
    units = _signup_units(db, role, org_unit_id, [classroom_id] if classroom_id else [])
    if not units:
        return []
    return [{"id": a.id, "display_name": a.display_name, "unit": _unit_name(db, a.org_unit_id)}
            for a in approvers_for(db, role, units)]


class SignupIn(BaseModel):
    role: Literal["teacher", "admin"]
    display_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=10, max_length=20)
    pin: str = Field(min_length=1, max_length=12)
    org_unit_id: str | None = None
    classroom_ids: list[str] = []
    approver_id: str | None = Field(None, description="the admin to send the request to (see /auth/approvers)")


@router.post("/auth/signup")
def signup(body: SignupIn, request: Request, db: Session = Depends(get_db)) -> dict:
    key = f"signup:{request.client.host if request.client else '?'}"
    now = time.monotonic()
    recent = [t for t in _fails.get(key, []) if now - t < LOCK_SECONDS]
    if len(recent) >= MAX_SIGNUPS:
        raise HTTPException(429, "too many sign-ups from this device; try again in 15 minutes")
    if db.scalar(select(User.id).limit(1)) is None:
        raise HTTPException(409, "no accounts exist yet: set up the top-level admin first")
    rooms = list(dict.fromkeys(body.classroom_ids)) if body.role == "teacher" else []
    for cid in rooms:
        if db.get(Classroom, cid) is None:
            raise HTTPException(404, "classroom not found")
    org_unit_id = body.org_unit_id
    if org_unit_id is not None and db.get(OrgUnit, org_unit_id) is None:
        raise HTTPException(404, "org unit not found")
    if body.role == "teacher":
        if not rooms:
            raise HTTPException(422, "choose your class")
        org_unit_id = db.get(Classroom, rooms[0]).school.org_unit_id
    elif org_unit_id is None:
        raise HTTPException(422, "choose your unit (state, district, block or cluster)")
    ph = hash_phone(body.phone)
    if db.scalar(select(User.id).where(User.phone_hash == ph)):
        raise HTTPException(409, "phone already registered")
    problem = pin_problem(body.pin, body.phone)
    if problem:
        raise HTTPException(422, problem)
    name = body.display_name.strip()
    allowed = approvers_for(db, body.role, _signup_units(db, body.role, org_unit_id, rooms))
    if body.role == "admin" and get_settings().admin_self_signup:
        u = User(role="admin", phone_hash=ph, pin_hash=hash_pin(body.pin), display_name=name,
                 org_unit_id=org_unit_id, active=True, pending=False, last_login_at=datetime.now(UTC))
        db.add(u)
        db.flush()
        notify(db, allowed, ADMIN_JOINED, f"New admin: {name}",
               f"{name} created an admin account for {_unit_name(db, org_unit_id)}.", subject_user_id=u.id)
        db.commit()
        _fails[key] = recent + [now]
        return {"id": u.id, "pending": False, "token": issue_token(u), "user": _user_out(u),
                "classrooms": [], "pin_change_required": False}
    if not allowed:
        raise HTTPException(422, "there is no admin above this unit yet who could approve you")
    if body.approver_id is not None and body.approver_id not in {a.id for a in allowed}:
        raise HTTPException(422, "this admin cannot approve an account at this place; choose another")
    u = User(role=body.role, phone_hash=ph, pin_hash=hash_pin(body.pin), display_name=name,
             org_unit_id=org_unit_id, active=False, pending=True, approver_id=body.approver_id)
    db.add(u)
    db.flush()
    for cid in rooms:
        db.add(ClassroomTeacher(classroom_id=cid, user_id=u.id))
    where = ", ".join(f"{r.school.name} — {r.name}" for r in (db.get(Classroom, c) for c in rooms) if r)         or _unit_name(db, org_unit_id) or ""
    chosen = next((a.display_name for a in allowed if a.id == body.approver_id), None)
    notify(db, allowed, SIGNUP_REQUEST, f"{hi_role(body.role)} sign-up: {name}",
           f"{name} asks to join {where}." + (f" Sent to {chosen}." if chosen else ""), subject_user_id=u.id)
    db.commit()
    _fails[key] = recent + [now]
    return {"id": u.id, "pending": True}


def hi_role(role: str) -> str:
    return {"teacher": "Teacher", "admin": "Admin"}.get(role, role.title())


def _approved(db: Session, u: User, by: User) -> None:
    resolve(db, u.id)
    notify(db, [u], ACCOUNT_APPROVED, "Your account is approved",
           f"{by.display_name} approved your account. Welcome!", subject_user_id=u.id)


# ---------------------------------------------------------------------------------- admin
# Every admin endpoint is scoped by the caller's place in the hierarchy (security.admin_scope):
# the global admin sees and manages everything; an org-scoped admin only its own subtree.
admin = Depends(require_role("admin"))
AdminP = Depends(require_role("admin"))


def _org_or_404(db: Session, org_unit_id: str | None) -> OrgUnit | None:
    if org_unit_id is None:
        return None
    ou = db.get(OrgUnit, org_unit_id)
    if ou is None:
        raise HTTPException(404, "org unit not found")
    return ou


def _require_scope(scope: set[str] | None, org_unit_id: str | None) -> None:
    if not in_scope(scope, org_unit_id):
        raise HTTPException(403, "outside your part of the hierarchy")


class OrgUnitIn(BaseModel):
    kind: Literal["state", "district", "block", "cluster"]
    name: str = Field(min_length=1, max_length=200)
    code: str | None = Field(None, max_length=64)
    parent_id: str | None = None


@router.get("/admin/org-units")
def list_org_units(p: Principal = AdminP, db: Session = Depends(get_db)) -> list[dict]:
    scope = admin_scope(db, p)
    q = select(OrgUnit).order_by(OrgUnit.name)
    if scope is not None:
        q = q.where(OrgUnit.id.in_(scope))
    return [{"id": o.id, "kind": o.kind, "name": o.name, "code": o.code, "parent_id": o.parent_id}
            for o in db.scalars(q)]


@router.post("/admin/org-units")
def create_org_unit(body: OrgUnitIn, p: Principal = AdminP, db: Session = Depends(get_db)) -> dict:
    scope = admin_scope(db, p)
    parent = _org_or_404(db, body.parent_id)
    if parent is None:
        if scope is not None:
            raise HTTPException(403, "only the top-level admin can create a top-level unit")
    else:
        _require_scope(scope, parent.id)
        if ORG_KINDS.index(body.kind) <= ORG_KINDS.index(parent.kind):
            raise HTTPException(422, f"a {body.kind} cannot be inside a {parent.kind}")
    ou = OrgUnit(kind=body.kind, name=body.name.strip(), code=body.code, parent_id=body.parent_id)
    db.add(ou)
    db.commit()
    return {"id": ou.id}


class SchoolIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    udise_code: str | None = Field(None, max_length=32)
    org_unit_id: str | None = None
    region_profile: str = "standard"


@router.get("/admin/schools")
def list_schools(p: Principal = AdminP, db: Session = Depends(get_db)) -> list[dict]:
    scope = admin_scope(db, p)
    q = select(School).order_by(School.name)
    if scope is not None:
        q = q.where(School.org_unit_id.in_(scope))
    return [{"id": s.id, "name": s.name, "udise_code": s.udise_code, "org_unit_id": s.org_unit_id,
             "region_profile": s.region_profile} for s in db.scalars(q)]


@router.post("/admin/schools")
def create_school(body: SchoolIn, p: Principal = AdminP, db: Session = Depends(get_db)) -> dict:
    scope = admin_scope(db, p)
    _org_or_404(db, body.org_unit_id)
    _require_scope(scope, body.org_unit_id)
    udise = (body.udise_code or "").strip() or None
    if udise and db.scalar(select(School.id).where(School.udise_code == udise)):
        raise HTTPException(409, "a school with this UDISE code already exists")
    s = School(name=body.name.strip(), udise_code=udise, org_unit_id=body.org_unit_id,
               region_profile=body.region_profile)
    db.add(s)
    db.commit()
    return {"id": s.id}


class ClassroomIn(BaseModel):
    school_id: str
    name: str = Field(min_length=1, max_length=120)
    grades: list[int] = Field(min_length=1)
    region_profile: str | None = None
    daily_kiosk_budget_min: float = 12.0


def _school_in_scope(db: Session, scope: set[str] | None, school_id: str) -> School:
    s = db.get(School, school_id)
    if s is None:
        raise HTTPException(404, "school not found")
    _require_scope(scope, s.org_unit_id)
    return s


@router.get("/admin/classrooms")
def list_classrooms(p: Principal = AdminP, db: Session = Depends(get_db)) -> list[dict]:
    scope = admin_scope(db, p)
    q = select(Classroom, School).join(School, Classroom.school_id == School.id).order_by(School.name, Classroom.name)
    if scope is not None:
        q = q.where(School.org_unit_id.in_(scope))
    rows = db.execute(q).all()
    teachers: dict[str, list[dict]] = {}
    if rows:
        links = db.execute(
            select(ClassroomTeacher.classroom_id, User.id, User.display_name)
            .join(User, User.id == ClassroomTeacher.user_id)
            .where(ClassroomTeacher.classroom_id.in_([c.id for c, _ in rows]))
        ).all()
        for cid, uid, name in links:
            teachers.setdefault(cid, []).append({"id": uid, "display_name": name})
    return [{"id": c.id, "name": c.name, "grades": c.grades, "school_id": s.id, "school": s.name,
             "teachers": teachers.get(c.id, [])} for c, s in rows]


@router.post("/admin/classrooms")
def create_classroom(body: ClassroomIn, p: Principal = AdminP, db: Session = Depends(get_db)) -> dict:
    _school_in_scope(db, admin_scope(db, p), body.school_id)
    c = Classroom(**{**body.model_dump(), "name": body.name.strip()})
    db.add(c)
    db.commit()
    return {"id": c.id}


class UserIn(BaseModel):
    role: Literal["teacher", "admin"]
    phone: str = Field(min_length=10, max_length=20)
    pin: str | None = Field(None, max_length=12, description="omit to have the server generate a strong PIN")
    display_name: str = Field(min_length=1, max_length=120)
    org_unit_id: str | None = None
    classroom_ids: list[str] = []


def _check_classrooms(db: Session, scope: set[str] | None, ids: list[str]) -> list[str]:
    ids = list(dict.fromkeys(ids))
    for cid in ids:
        room = db.get(Classroom, cid)
        if room is None:
            raise HTTPException(404, "classroom not found")
        _school_in_scope(db, scope, room.school_id)
    return ids


def _user_admin_out(db: Session, p: Principal, u: User) -> dict:
    rooms = db.execute(
        select(Classroom.id, Classroom.name, School.name)
        .join(School, Classroom.school_id == School.id)
        .join(ClassroomTeacher, ClassroomTeacher.classroom_id == Classroom.id)
        .where(ClassroomTeacher.user_id == u.id)
    ).all()
    approver = db.get(User, u.approver_id) if u.pending and u.approver_id else None
    return {**_user_out(u), "active": u.active, "pending": u.pending,
            "approver": {"id": approver.id, "display_name": approver.display_name} if approver else None, "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "classrooms": [{"id": cid, "name": name, "school": school} for cid, name, school in rooms],
            "can_manage": can_manage_user(db, p, u), "is_self": u.id == p.user.id}


@router.get("/admin/users")
def list_users(p: Principal = AdminP, db: Session = Depends(get_db)) -> list[dict]:
    """Accounts in the caller's part of the hierarchy (phones are stored hashed, so they are never listed)."""
    scope = admin_scope(db, p)
    out = []
    for u in db.scalars(select(User).order_by(User.role, User.display_name)):
        if scope is not None and u.id != p.user.id:
            units = user_org_units(db, u)
            if not units or not all(x in scope for x in units):
                continue
        out.append(_user_admin_out(db, p, u))
    return out


@router.post("/admin/users")
def create_user(body: UserIn, p: Principal = AdminP, db: Session = Depends(get_db)) -> dict:
    scope = admin_scope(db, p)
    _org_or_404(db, body.org_unit_id)
    rooms = _check_classrooms(db, scope, body.classroom_ids) if body.role == "teacher" else []
    org_unit_id = body.org_unit_id
    if body.role == "teacher" and org_unit_id is None and rooms:
        org_unit_id = db.get(Classroom, rooms[0]).school.org_unit_id  # so org admins can find the teacher
    if org_unit_id is not None or scope is not None:
        _require_scope(scope, org_unit_id)
    if body.role == "admin" and scope is not None and org_unit_id == p.user.org_unit_id:
        raise HTTPException(403, "you can create admins only for units below your own")
    ph = hash_phone(body.phone)
    if db.scalar(select(User).where(User.phone_hash == ph)):
        raise HTTPException(409, "phone already registered")
    pin = body.pin or generate_pin(8 if body.role == "admin" else 6)
    problem = pin_problem(pin, body.phone)
    if problem:
        raise HTTPException(422, problem)
    u = User(role=body.role, phone_hash=ph, pin_hash=hash_pin(pin), display_name=body.display_name.strip(),
             org_unit_id=org_unit_id)
    db.add(u)
    db.flush()
    for cid in rooms:
        db.add(ClassroomTeacher(classroom_id=cid, user_id=u.id))
    db.commit()
    # A generated PIN is returned exactly once (only its hash is stored); hand it over in person.
    return {"id": u.id, **({"pin": pin} if body.pin is None else {})}


def _managed_user(db: Session, p: Principal, uid: str) -> User:
    u = db.get(User, uid)
    if u is None:
        raise HTTPException(404, "user not found")
    if not can_manage_user(db, p, u):
        raise HTTPException(403, "you can only manage accounts below you in the hierarchy")
    return u


class UserPatch(BaseModel):
    active: bool | None = None
    display_name: str | None = Field(None, min_length=1, max_length=120)
    classroom_ids: list[str] | None = None


@router.patch("/admin/users/{uid}")
def update_user(uid: str, body: UserPatch, p: Principal = AdminP, db: Session = Depends(get_db)) -> dict:
    u = _managed_user(db, p, uid)
    if body.display_name is not None:
        u.display_name = body.display_name.strip()
    if body.active is not None and body.active != u.active:
        if body.active and u.pending:
            _approved(db, u, p.user)  # activating a sign-up request approves it
        u.active = body.active
        u.pending = False
        if not body.active:  # ends every session of that account right away
            u.credentials_changed_at = datetime.now(UTC)
    if body.classroom_ids is not None:
        if u.role != "teacher":
            raise HTTPException(422, "only teachers have classes")
        rooms = _check_classrooms(db, admin_scope(db, p), body.classroom_ids)
        for link in db.scalars(select(ClassroomTeacher).where(ClassroomTeacher.user_id == u.id)).all():
            db.delete(link)
        db.flush()
        for cid in rooms:
            db.add(ClassroomTeacher(classroom_id=cid, user_id=u.id))
    db.commit()
    return _user_admin_out(db, p, u)


@router.post("/admin/users/{uid}/approve")
def approve_user(uid: str, p: Principal = AdminP, db: Session = Depends(get_db)) -> dict:
    u = _managed_user(db, p, uid)
    if not u.pending:
        raise HTTPException(409, "this account is not waiting for approval")
    u.pending, u.active = False, True
    _approved(db, u, p.user)
    db.commit()
    return _user_admin_out(db, p, u)


@router.delete("/admin/users/{uid}")
def reject_user(uid: str, p: Principal = AdminP, db: Session = Depends(get_db)) -> dict:
    """Reject a sign-up request (removes it). Approved accounts are deactivated instead, never deleted."""
    u = _managed_user(db, p, uid)
    if not u.pending:
        raise HTTPException(409, "only sign-up requests can be removed; deactivate this account instead")
    for link in db.scalars(select(ClassroomTeacher).where(ClassroomTeacher.user_id == u.id)).all():
        db.delete(link)
    resolve(db, u.id)
    db.execute(delete(Notification).where(Notification.recipient_id == u.id))
    db.delete(u)
    db.commit()
    return {"deleted": uid}


@router.post("/admin/users/{uid}/reset-pin")
def reset_pin(uid: str, p: Principal = AdminP, db: Session = Depends(get_db)) -> dict:
    """Issue a new random PIN (returned once) and end all sessions of that account."""
    u = _managed_user(db, p, uid)
    pin = generate_pin(8 if u.role == "admin" else 6)
    u.pin_hash = hash_pin(pin)
    u.credentials_changed_at = datetime.now(UTC)
    db.commit()
    return {"id": u.id, "pin": pin}


@router.get("/admin/bug-proposals", dependencies=[admin])
def list_proposals(db: Session = Depends(get_db)) -> list[dict]:
    return [{"id": b.id, "spec": b.spec, "description": b.description, "explains": b.explains, "status": b.status}
            for b in db.scalars(select(BugProposal).order_by(BugProposal.created_at.desc()))]


class ReviewIn(BaseModel):
    decision: Literal["approved", "rejected"]


@router.post("/admin/bug-proposals/{pid}/review")
def review_proposal(pid: str, body: ReviewIn, p: Principal = Depends(require_role("admin")),
                    db: Session = Depends(get_db)) -> dict:
    if p.user.org_unit_id is not None:  # the bug library is global: only the top-level admin may change it
        raise HTTPException(403, "only the top-level admin can review bug proposals")
    bp = db.get(BugProposal, pid)
    if bp is None:
        raise HTTPException(404, "not found")
    bp.status, bp.reviewed_by = body.decision, p.user.id
    db.commit()
    if bp.status == "approved":  # other API/worker processes pick it up on their next start
        load_approved_bugs(db)
    return {"id": bp.id, "status": bp.status, "library_size": len(DEFAULT_LIBRARY.bugs)}
