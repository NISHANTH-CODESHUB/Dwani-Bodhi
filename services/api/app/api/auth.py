"""Teacher accounts: sign up (active at once, no approval), log in, change PIN, who am I."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import AuthAttempt, User
from ..security import (
    PIN_CHANGE_SCOPE,
    Principal,
    burn_pin_check,
    current_principal,
    hash_phone,
    hash_pin,
    issue_token,
    pin_change_principal,
    pin_problem,
    verify_pin,
)
from ..services.accounts import ClassroomFields, classrooms_for, create_classroom
from ..services.common import pack

router = APIRouter(prefix="/v1", tags=["auth"])

# ------------------------------------------------------------------------------ brute-force throttle
# PINs are short, so each phone gets MAX_FAILS tries per WINDOW from one client, and MAX_FAILS_PER_PHONE
# from everywhere (stops distributed guessing without letting a stranger lock a teacher out of her number).
MAX_FAILS, MAX_FAILS_PER_PHONE, MAX_SIGNUPS = 5, 20, 5
WINDOW = timedelta(minutes=15)


def client_ip(request: Request) -> str:
    """Behind Vercel / a reverse proxy the socket address is the proxy's; the platform sets x-real-ip."""
    if get_settings().trust_proxy_headers:
        real = request.headers.get("x-real-ip") or request.headers.get("x-forwarded-for", "").split(",")[0]
        if real.strip():
            return real.strip()
    return request.client.host if request.client else "?"


def _check(db: Session, key: str, limit: int, msg: str = "too many wrong PINs; try again in 15 minutes") -> None:
    since = datetime.now(UTC) - WINDOW
    n = db.scalar(select(func.count()).select_from(AuthAttempt).where(AuthAttempt.key == key, AuthAttempt.at >= since))
    if (n or 0) >= limit:
        raise HTTPException(429, msg)


def _record(db: Session, *keys: str) -> None:
    now = datetime.now(UTC)
    db.execute(delete(AuthAttempt).where(AuthAttempt.at < now - timedelta(days=1)))  # keep the table tiny
    for key in keys:
        db.add(AuthAttempt(key=key, at=now))
    db.commit()


def _clear(db: Session, *keys: str) -> None:
    db.execute(delete(AuthAttempt).where(AuthAttempt.key.in_(keys)))
    db.commit()


def user_out(user: User) -> dict:
    return {"id": user.id, "role": user.role, "display_name": user.display_name}


def session_out(db: Session, user: User) -> dict:
    return {"token": issue_token(user), "user": user_out(user), "classrooms": classrooms_for(db, user),
            "pin_change_required": False}


# ------------------------------------------------------------------------------ login
class LoginIn(BaseModel):
    phone: str = Field(min_length=6, max_length=20)
    pin: str = Field(min_length=4, max_length=12)


@router.post("/auth/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)) -> dict:
    ph = hash_phone(body.phone)
    key, phone_key = f"login:{ph}:{client_ip(request)}", f"login:{ph}"
    _check(db, key, MAX_FAILS)
    _check(db, phone_key, MAX_FAILS_PER_PHONE)
    user = db.scalar(select(User).where(User.phone_hash == ph))
    if user is None:
        burn_pin_check(body.pin)  # same cost as a wrong PIN, so timing does not reveal registered phones
    if user is None or not user.active or not verify_pin(body.pin, user.pin_hash):
        _record(db, key, phone_key)
        raise HTTPException(401, "wrong phone or PIN")
    _clear(db, key, phone_key)
    user.last_login_at = datetime.now(UTC)
    db.commit()
    weak = pin_problem(body.pin, body.phone)
    if weak:  # e.g. an old 4-digit PIN: the only thing this session may do is set a strong one
        return {"token": issue_token(user, scope=PIN_CHANGE_SCOPE), "user": user_out(user), "classrooms": [],
                "pin_change_required": True, "pin_problem": weak}
    return session_out(db, user)


@router.post("/auth/open")
def open_session(db: Session = Depends(get_db)) -> dict:
    """AUTH_DISABLED (dev/demo only): sign in as the first active teacher, no phone or PIN."""
    if not get_settings().auth_disabled:
        raise HTTPException(404, "not found")
    user = db.scalar(select(User).where(User.active.is_(True)).order_by(User.created_at))
    if user is None:
        raise HTTPException(404, "no teacher account yet; create one or run `python -m app.demo` first")
    return session_out(db, user)


# ------------------------------------------------------------------------------ sign up
class SignupIn(ClassroomFields):
    display_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=10, max_length=20)
    pin: str = Field(min_length=1, max_length=12)

    @field_validator("display_name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("enter your name")
        return v


@router.post("/auth/signup")
def signup(body: SignupIn, request: Request, db: Session = Depends(get_db)) -> dict:
    """Create a teacher account together with the teacher's school and first class. The account is active
    at once — there is no approval step — and the response is a signed-in session."""
    key = f"signup:{client_ip(request)}"
    _check(db, key, MAX_SIGNUPS, "too many sign-ups from this device; try again in 15 minutes")
    digits = "".join(ch for ch in body.phone if ch.isdigit())
    if len(digits) < 10:
        raise HTTPException(422, "Enter a 10-digit mobile number.")
    ph = hash_phone(body.phone)
    if db.scalar(select(User.id).where(User.phone_hash == ph)):
        raise HTTPException(409, "This mobile number already has an account. Log in instead.")
    problem = pin_problem(body.pin, body.phone)
    if problem:
        raise HTTPException(422, problem)
    u = User(role="teacher", phone_hash=ph, pin_hash=hash_pin(body.pin), display_name=body.display_name,
             active=True, last_login_at=datetime.now(UTC))
    db.add(u)
    db.flush()
    create_classroom(db, u, body)
    db.commit()
    _record(db, key)  # counts sign-ups per client (successful ones only) for the same window
    return session_out(db, u)


# ------------------------------------------------------------------------------ PIN + me
class PinChangeIn(BaseModel):
    current_pin: str = Field(min_length=4, max_length=12)
    new_pin: str = Field(min_length=1, max_length=12)
    phone: str | None = Field(None, max_length=20, description="optional: lets the server reject phone-derived PINs")


@router.post("/auth/pin")
def change_pin(body: PinChangeIn, p: Principal = Depends(pin_change_principal), db: Session = Depends(get_db)) -> dict:
    """Change the PIN. Ends every other session (all older tokens are rejected) and returns a fresh token."""
    user = p.user
    key = f"pinchange:{user.id}"
    _check(db, key, MAX_FAILS)
    if not verify_pin(body.current_pin, user.pin_hash):
        _record(db, key)  # 400, not 401: a typo must not look like an expired session
        raise HTTPException(400, "The current PIN is wrong.")
    phone = body.phone if body.phone and hash_phone(body.phone) == user.phone_hash else None
    problem = pin_problem(body.new_pin, phone)
    if problem:
        raise HTTPException(422, problem)
    if body.new_pin == body.current_pin:
        raise HTTPException(422, "The new PIN must be different from the old one.")
    _clear(db, key)
    user.pin_hash = hash_pin(body.new_pin)
    user.credentials_changed_at = datetime.now(UTC)
    db.commit()
    return {"token": issue_token(user), "user": user_out(user), "classrooms": classrooms_for(db, user)}


@router.get("/me")
def me(p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    u = p.user
    return {"user": user_out(u), "classrooms": classrooms_for(db, u), "content_version": pack().version}


@router.get("/regions")
def regions() -> list[dict]:
    """Dialect profiles a class can use (the reading scorer tolerates these regional pronunciations)."""
    profiles = pack().regions.profiles
    return [{"id": r.id, "name": r.name} for r in sorted(profiles.values(), key=lambda r: (r.id != "standard", r.name))]
