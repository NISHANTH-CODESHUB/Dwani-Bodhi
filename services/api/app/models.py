"""ORM models (guide §11.1). Child names are NEVER stored server-side — only UUIDs.

Hierarchy for multi-tenant scale: OrgUnit (state → district → block → cluster) → School → Classroom.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, JSONType


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


UUID = String(36)


class OrgUnit(Base):
    __tablename__ = "org_unit"
    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(16))  # state | district | block | cluster
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("org_unit.id"), nullable=True, index=True)


class School(Base):
    __tablename__ = "school"
    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    udise_code: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)
    org_unit_id: Mapped[str | None] = mapped_column(ForeignKey("org_unit.id"), nullable=True, index=True)
    region_profile: Mapped[str] = mapped_column(String(64), default="standard")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Classroom(Base):
    __tablename__ = "classroom"
    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=new_id)
    school_id: Mapped[str] = mapped_column(ForeignKey("school.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    grades: Mapped[list] = mapped_column(JSONType, default=list)
    region_profile: Mapped[str | None] = mapped_column(String(64), nullable=True)  # overrides school
    daily_kiosk_budget_min: Mapped[float] = mapped_column(Float, default=12.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    school: Mapped[School] = relationship()


class User(Base):
    __tablename__ = "app_user"
    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=new_id)
    role: Mapped[str] = mapped_column(String(16))  # teacher | admin
    phone_hash: Mapped[str] = mapped_column(String(64), unique=True)
    pin_hash: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str] = mapped_column(String(120))
    org_unit_id: Mapped[str | None] = mapped_column(ForeignKey("org_unit.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Self-registered (Create account on the login screen) and not yet approved by an admin above; cannot log in.
    pending: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    # The admin the sign-up request was sent to (chosen on the Create account form).
    approver_id: Mapped[str | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    # Tokens issued before this moment are rejected (set when the PIN changes → logs out every device).
    credentials_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Notification(Base):
    """In-app notification for one account (e.g. a teacher's sign-up request for the admins who may approve it)."""
    __tablename__ = "notification"
    __table_args__ = (Index("ix_notification_recipient_read", "recipient_id", "read_at"),)
    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=new_id)
    recipient_id: Mapped[str] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # signup_request | admin_joined | account_approved
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    subject_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)  # who it is about
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ClassroomTeacher(Base):
    __tablename__ = "classroom_teacher"
    classroom_id: Mapped[str] = mapped_column(ForeignKey("classroom.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("app_user.id"), primary_key=True)


class Child(Base):
    __tablename__ = "child"
    __table_args__ = (UniqueConstraint("classroom_id", "aruco_slot"),
                      UniqueConstraint("register_no", name="uq_child_register_no"))
    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=new_id)  # generated on the phone
    classroom_id: Mapped[str] = mapped_column(ForeignKey("classroom.id"), index=True)
    grade: Mapped[int] = mapped_column(Integer)
    aruco_slot: Mapped[int] = mapped_column(Integer)
    # Human-readable, permanent student register number (STU-<year>-<seq>), generated by the server.
    register_no: Mapped[str | None] = mapped_column(String(20), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(1), nullable=True)  # optional, fairness reporting only
    consent_status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|granted|withdrawn
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AssessmentSession(Base):
    __tablename__ = "assessment_session"
    id: Mapped[str] = mapped_column(UUID, primary_key=True)  # client UUID → idempotent sync
    child_id: Mapped[str] = mapped_column(ForeignKey("child.id"), index=True)
    classroom_id: Mapped[str] = mapped_column(ForeignKey("classroom.id"), index=True)
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    plan_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    content_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    discontinued: Mapped[bool] = mapped_column(Boolean, default=False)


class Response(Base):
    __tablename__ = "response"
    __table_args__ = (Index("ix_response_child_status", "child_id", "status"),)
    id: Mapped[str] = mapped_column(UUID, primary_key=True)  # client UUID (or server UUID for slates)
    session_id: Mapped[str | None] = mapped_column(ForeignKey("assessment_session.id"), nullable=True, index=True)
    child_id: Mapped[str] = mapped_column(ForeignKey("child.id"), index=True)
    item_id: Mapped[str] = mapped_column(String(120), index=True)
    item_type: Mapped[str] = mapped_column(String(24))
    modality: Mapped[str] = mapped_column(String(8))  # voice | tap | slate
    payload: Mapped[dict] = mapped_column(JSONType, default=dict)
    verdict: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # pending → scored | unsure | error ; unsure → confirmed (teacher) ; applied flag tracks learner update
    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    content_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SlatePhoto(Base):
    __tablename__ = "slate_photo"
    id: Mapped[str] = mapped_column(UUID, primary_key=True)  # client UUID
    classroom_id: Mapped[str] = mapped_column(ForeignKey("classroom.id"), index=True)
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    problems: Mapped[list] = mapped_column(JSONType, default=list)  # [{item_id,a,b,op}]
    status: Mapped[str] = mapped_column(String(12), default="pending")
    result: Mapped[dict | None] = mapped_column(JSONType, nullable=True)


class Blob(Base):
    __tablename__ = "blob"
    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(16))  # audio | slate_photo | slate_crop
    response_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    slate_photo_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    key: Mapped[str] = mapped_column(String(300))
    mime: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    delete_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SkillState(Base):
    __tablename__ = "skill_state"
    child_id: Mapped[str] = mapped_column(ForeignKey("child.id"), primary_key=True)
    skill_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    p: Mapped[float] = mapped_column(Float)
    n_obs: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MisconceptionState(Base):
    __tablename__ = "misconception_state"
    child_id: Mapped[str] = mapped_column(ForeignKey("child.id"), primary_key=True)
    mis_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    alpha: Mapped[float] = mapped_column(Float)
    beta: Mapped[float] = mapped_column(Float)
    was_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    verified: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    status: Mapped[str] = mapped_column(String(12), default="none", index=True)
    first_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LearnerAux(Base):
    __tablename__ = "learner_aux"
    child_id: Mapped[str] = mapped_column(ForeignKey("child.id"), primary_key=True)
    speech_variants: Mapped[list] = mapped_column(JSONType, default=list)
    recheck: Mapped[list] = mapped_column(JSONType, default=list)
    wcpm_history: Mapped[list] = mapped_column(JSONType, default=list)
    sounding_out_count: Mapped[int] = mapped_column(Integer, default=0)
    levels: Mapped[dict] = mapped_column(JSONType, default=dict)
    last_assessed: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Plan(Base):
    __tablename__ = "plan"
    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=new_id)
    child_id: Mapped[str] = mapped_column(ForeignKey("child.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    plan: Mapped[dict] = mapped_column(JSONType)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)


class ClassDay(Base):
    __tablename__ = "class_day"
    __table_args__ = (UniqueConstraint("classroom_id", "day"),)
    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=new_id)
    classroom_id: Mapped[str] = mapped_column(ForeignKey("classroom.id"), index=True)
    day: Mapped[date] = mapped_column(Date)
    children: Mapped[list] = mapped_column(JSONType, default=list)  # [{child_id, priority, reasons}]
    slate_problems: Mapped[list] = mapped_column(JSONType, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ActionCard(Base):
    __tablename__ = "action_card"
    __table_args__ = (UniqueConstraint("classroom_id", "week"),)
    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=new_id)
    classroom_id: Mapped[str] = mapped_column(ForeignKey("classroom.id"), index=True)
    week: Mapped[str] = mapped_column(String(10))  # ISO week, e.g. 2026-W46
    card: Mapped[dict] = mapped_column(JSONType)
    summary: Mapped[dict] = mapped_column(JSONType, default=dict)
    source: Mapped[str] = mapped_column(String(12))  # llm | template
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Recheck(Base):
    """N5 closed loop: a targeted re-check registered by an Action Card."""
    __tablename__ = "recheck"
    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=new_id)
    child_id: Mapped[str] = mapped_column(ForeignKey("child.id"), index=True)
    target_id: Mapped[str] = mapped_column(String(64))  # misconception or skill id
    activity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    card_id: Mapped[str | None] = mapped_column(ForeignKey("action_card.id"), nullable=True)
    baseline: Mapped[float] = mapped_column(Float)  # misconception mean / skill p at registration
    due: Mapped[date] = mapped_column(Date)
    outcome: Mapped[str | None] = mapped_column(String(12), nullable=True)  # resolved | persists | improved
    latest: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TeacherOverride(Base):
    __tablename__ = "teacher_override"
    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=new_id)
    response_id: Mapped[str] = mapped_column(ForeignKey("response.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("app_user.id"))
    old: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    new: Mapped[dict] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditSample(Base):
    __tablename__ = "audit_sample"
    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=new_id)
    child_id: Mapped[str] = mapped_column(ForeignKey("child.id"), index=True)
    assessor_id: Mapped[str] = mapped_column(ForeignKey("app_user.id"))
    result: Mapped[dict] = mapped_column(JSONType)
    agreement: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BugProposal(Base):
    """Discovery loop (guide §6.2.4): Claude proposes, executor verifies, human approves."""
    __tablename__ = "bug_proposal"
    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=new_id)
    spec: Mapped[dict] = mapped_column(JSONType)
    description: Mapped[str] = mapped_column(Text)
    explains: Mapped[list] = mapped_column(JSONType, default=list)  # response ids reproduced
    status: Mapped[str] = mapped_column(String(12), default="proposed")  # proposed|approved|rejected
    reviewed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Job(Base):
    __tablename__ = "job"
    __table_args__ = (Index("ix_job_claim", "queue", "status", "run_after"),)
    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(48))
    queue: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict] = mapped_column(JSONType, default=dict)
    status: Mapped[str] = mapped_column(String(10), default="queued")  # queued|running|done|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    dedupe_key: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    locked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LLMCall(Base):
    __tablename__ = "llm_call"
    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=new_id)
    purpose: Mapped[str] = mapped_column(String(32), index=True)
    model: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
