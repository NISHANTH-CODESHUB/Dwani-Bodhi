"""Teacher-owned schools and classes (no admin, no hierarchy: a teacher creates and manages their own)."""

from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Classroom, ClassroomTeacher, School, User
from .common import pack

MAX_CLASSES_PER_TEACHER = 20


class ClassroomFields(BaseModel):
    school_name: str = Field(min_length=1, max_length=200)
    class_name: str = Field(min_length=1, max_length=120)
    grades: list[int] = Field(min_length=1, max_length=5)
    region_profile: str = Field("standard", max_length=64)

    @field_validator("school_name", "class_name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("must not be empty")
        return v

    @field_validator("grades")
    @classmethod
    def _grades(cls, v: list[int]) -> list[int]:
        if any(g < 1 or g > 5 for g in v):
            raise ValueError("grades must be between 1 and 5")
        return sorted(set(v))


def check_region(region: str) -> str:
    if region not in pack().regions.profiles:
        raise HTTPException(422, f"unknown region profile '{region}'")
    return region


def classroom_out(room: Classroom, school: School | None) -> dict:
    return {"id": room.id, "name": room.name, "grades": room.grades, "school": school.name if school else None,
            "region_profile": room.region_profile or (school.region_profile if school else "standard"),
            "daily_kiosk_budget_min": room.daily_kiosk_budget_min}


def classrooms_for(db: Session, user: User) -> list[dict]:
    rows = db.execute(
        select(Classroom, School)
        .join(School, Classroom.school_id == School.id)
        .join(ClassroomTeacher, ClassroomTeacher.classroom_id == Classroom.id)
        .where(ClassroomTeacher.user_id == user.id)
        .order_by(Classroom.created_at)
    ).all()
    return [classroom_out(r, s) for r, s in rows]


def create_classroom(db: Session, user: User, body: ClassroomFields) -> Classroom:
    """New class for `user`. A school with the same name the teacher already uses is reused."""
    region = check_region(body.region_profile)
    # One row per class the teacher has (so len() is the class count).
    mine = db.execute(
        select(School).join(Classroom, Classroom.school_id == School.id)
        .join(ClassroomTeacher, ClassroomTeacher.classroom_id == Classroom.id)
        .where(ClassroomTeacher.user_id == user.id)
    ).scalars().all()
    if len(mine) >= MAX_CLASSES_PER_TEACHER:
        raise HTTPException(422, f"a teacher can have at most {MAX_CLASSES_PER_TEACHER} classes")
    school = next((s for s in mine if s.name.casefold() == body.school_name.casefold()), None)
    if school is None:
        school = School(name=body.school_name, region_profile=region)
        db.add(school)
        db.flush()
    room = Classroom(school_id=school.id, name=body.class_name, grades=body.grades, region_profile=region)
    db.add(room)
    db.flush()
    db.add(ClassroomTeacher(classroom_id=room.id, user_id=user.id))
    db.flush()
    return room
