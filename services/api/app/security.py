"""Authentication (PIN + JWT), role scoping, and privacy helpers."""

from __future__ import annotations

import hashlib
import hmac
import itertools
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import Child, Classroom, ClassroomTeacher, OrgUnit, School, User

_bearer = HTTPBearer(auto_error=False)
PBKDF2_ROUNDS = 200_000


def hash_phone(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())[-10:]
    return hmac.new(get_settings().phone_pepper.encode(), digits.encode(), hashlib.sha256).hexdigest()


def hash_pin(pin: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2${PBKDF2_ROUNDS}${salt.hex()}${dk.hex()}"


def verify_pin(pin: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        _, rounds, salt, digest = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(dk.hex(), digest)
    except ValueError:
        return False


# Hash checked when the phone is unknown, so a wrong phone costs the same time as a wrong PIN
# (otherwise response timing reveals which phone numbers are registered).
_DUMMY_PIN_HASH = hash_pin(secrets.token_hex(8))


def burn_pin_check(pin: str) -> None:
    verify_pin(pin, _DUMMY_PIN_HASH)


# ------------------------------------------------------------------------------ PIN policy
PIN_MIN, PIN_MAX = 6, 12
# Most-used 6-digit PINs beyond plain repeats/sequences (which are caught structurally below).
_COMMON_PINS = frozenset({
    "123123", "121212", "112233", "123321", "654321", "111222", "112211", "131313", "159753", "147258",
    "258456", "102030", "101010", "100200", "200000", "786786", "007007", "123654", "147852", "696969",
    "520520", "520131", "123456789", "1234567890", "0123456789", "123412", "232323", "202020", "212121",
})


def pin_problem(pin: str, phone: str | None = None) -> str | None:
    """Return an English reason why `pin` is too weak, or None if it is acceptable."""
    if not pin.isdigit():
        return "The PIN must contain digits only."
    if not PIN_MIN <= len(pin) <= PIN_MAX:
        return f"The PIN must be {PIN_MIN} to {PIN_MAX} digits long."
    if len(set(pin)) <= 2:
        return "The PIN must have at least 3 different digits (not like 111111 or 121212)."
    steps = {(int(b) - int(a)) % 10 for a, b in itertools.pairwise(pin)}
    if steps in ({1}, {9}):
        return "A sequential PIN (like 123456 or 987654) is easy to guess."
    if pin in _COMMON_PINS or pin[: len(pin) // 2] * 2 == pin:
        return "This PIN is too common. Choose another one."
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if digits and (pin in digits or digits[-PIN_MIN:] in pin):
        return "Do not use your mobile number in the PIN."
    return None


def generate_pin(length: int = PIN_MIN) -> str:
    """A random PIN that passes `pin_problem` (for demo seeding and admin-issued first PINs)."""
    while True:
        pin = "".join(secrets.choice("0123456789") for _ in range(length))
        if pin_problem(pin) is None:
            return pin


# ---------------------------------------------------------------------------------- tokens
PIN_CHANGE_SCOPE = "pin_change"


def issue_token(user: User, scope: str | None = None) -> str:
    """`scope="pin_change"` tokens can only call POST /v1/auth/pin (forced change of a weak PIN)."""
    s = get_settings()
    now = datetime.now(UTC)
    changed = user.credentials_changed_at
    if changed is not None:
        # Clocks can be coarse (≈1–16 ms on Windows): a token issued right after a PIN change could carry the
        # same timestamp and be revoked instantly. Tokens issued now must always be newer than the change.
        changed = changed.replace(tzinfo=changed.tzinfo or UTC)
        now = max(now, changed + timedelta(microseconds=1))
    ttl = timedelta(minutes=15) if scope else timedelta(hours=s.jwt_ttl_hours)
    # `ts` is the precise issue time (iat is whole seconds) so a PIN change revokes even same-second tokens.
    claims = {"sub": user.id, "role": user.role, "iat": int(now.timestamp()), "ts": now.timestamp(), "exp": now + ttl}
    if scope:
        claims["scope"] = scope
    return jwt.encode(claims, s.jwt_secret, algorithm="HS256")


@dataclass
class Principal:
    user: User

    @property
    def role(self) -> str:
        return self.user.role


def _principal(creds: HTTPAuthorizationCredentials | None, db: Session, allow_scope: str | None) -> Principal:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing token")
    try:
        claims = jwt.decode(creds.credentials, get_settings().jwt_secret, algorithms=["HS256"],
                            options={"require": ["exp", "sub"]})
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from e
    sub = claims.get("sub")
    user = db.get(User, sub) if isinstance(sub, str) else None
    if user is None or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown user")
    changed = user.credentials_changed_at
    if changed is not None:
        issued = float(claims.get("ts", claims.get("iat", 0)))
        if issued <= changed.replace(tzinfo=changed.tzinfo or UTC).timestamp():
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session ended: PIN was changed")
    scope = claims.get("scope")
    if scope is not None and scope != allow_scope:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "PIN change required before using the app")
    return Principal(user)


def current_principal(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)
) -> Principal:
    return _principal(creds, db, allow_scope=None)


def pin_change_principal(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)
) -> Principal:
    """Accepts full tokens and the short-lived pin_change token."""
    return _principal(creds, db, allow_scope=PIN_CHANGE_SCOPE)


def require_role(*roles: str):
    def dep(p: Principal = Depends(current_principal)) -> Principal:
        if p.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "forbidden for role")
        return p
    return dep


def org_descendants(db: Session, root_id: str) -> set[str]:
    out, frontier = {root_id}, [root_id]
    while frontier:
        rows = db.scalars(select(OrgUnit.id).where(OrgUnit.parent_id.in_(frontier))).all()
        frontier = [r for r in rows if r not in out]
        out.update(frontier)
    return out


# ------------------------------------------------------------------------------ hierarchy
# Who manages whom: a global admin (org_unit_id=None) is the top-level account and manages everything.
# An org-scoped admin manages only its own org subtree, and only accounts strictly below its own unit.
ORG_KINDS = ("state", "district", "block", "cluster")


def admin_scope(db: Session, p: Principal) -> set[str] | None:
    """Org unit ids an admin may manage; None = everything (global admin)."""
    if p.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "forbidden for role")
    return None if p.user.org_unit_id is None else org_descendants(db, p.user.org_unit_id)


def in_scope(scope: set[str] | None, org_unit_id: str | None) -> bool:
    return scope is None or (org_unit_id is not None and org_unit_id in scope)


def user_org_units(db: Session, user: User) -> set[str | None]:
    """Org units a user sits in: their own unit, plus (teachers) the units of the schools they teach in."""
    units: set[str | None] = {user.org_unit_id} if user.org_unit_id else set()
    if user.role == "teacher":
        rows = db.execute(
            select(School.org_unit_id)
            .join(Classroom, Classroom.school_id == School.id)
            .join(ClassroomTeacher, ClassroomTeacher.classroom_id == Classroom.id)
            .where(ClassroomTeacher.user_id == user.id)
        ).scalars().all()
        units.update(rows)
    return units


def manages(db: Session, manager: User, role: str, units: set[str | None]) -> bool:
    """Is `manager` above an account of `role` sitting in `units`? (empty units = a top-level account)"""
    if manager.role != "admin" or not manager.active or manager.pending:
        return False
    if manager.org_unit_id is None:
        return True
    if not units or None in units:
        return False
    if role == "admin" and manager.org_unit_id in units:
        return False  # a peer admin of the same unit
    scope = org_descendants(db, manager.org_unit_id)
    return all(u in scope for u in units)


def can_manage_user(db: Session, p: Principal, target: User) -> bool:
    """Reset PIN / deactivate / reassign / approve: only accounts below you in the hierarchy (never yourself)."""
    if target.id == p.user.id:
        return False
    return manages(db, p.user, target.role, user_org_units(db, target))


def approvers_for(db: Session, role: str, units: set[str | None]) -> list[User]:
    """Admins allowed to approve a sign-up of `role` in `units`, nearest (deepest unit) first, top level last."""
    depth: dict[str | None, int] = {None: -1}

    def unit_depth(uid: str | None) -> int:
        if uid not in depth:
            parent = db.get(OrgUnit, uid)
            depth[uid] = 0 if parent is None or parent.parent_id is None else unit_depth(parent.parent_id) + 1
        return depth[uid]

    admins = db.scalars(select(User).where(User.role == "admin", User.active.is_(True))).all()
    ok = [a for a in admins if manages(db, a, role, units)]
    return sorted(ok, key=lambda a: (-unit_depth(a.org_unit_id), a.display_name))


def can_access_classroom(db: Session, p: Principal, classroom_id: str) -> bool:
    """Classroom endpoints expose child-level data (never names: those stay on the teacher's phone).
    Allowed: the class teacher, the top-level admin, and an org admin whose subtree contains the school."""
    if p.role == "teacher":
        return db.get(ClassroomTeacher, (classroom_id, p.user.id)) is not None
    if p.role != "admin":
        return False
    if p.user.org_unit_id is None:
        return True
    room = db.get(Classroom, classroom_id)
    unit = room.school.org_unit_id if room is not None else None
    return unit is not None and unit in org_descendants(db, p.user.org_unit_id)


def ensure_classroom(db: Session, p: Principal, classroom_id: str) -> Classroom:
    room = db.get(Classroom, classroom_id)
    if room is None:
        raise HTTPException(404, "classroom not found")
    if not can_access_classroom(db, p, classroom_id):
        raise HTTPException(403, "no access to classroom")
    return room


def ensure_child(db: Session, p: Principal, child_id: str, teacher_only: bool = False) -> Child:
    child = db.get(Child, child_id)
    if child is None or child.deleted_at is not None:
        raise HTTPException(404, "child not found")
    if teacher_only and p.role not in ("teacher", "admin"):
        raise HTTPException(403, "child-level data is visible to the class teacher and admins only")
    ensure_classroom(db, p, child.classroom_id)  # admins: only inside their part of the hierarchy
    return child
