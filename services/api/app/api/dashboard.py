"""Student activity read models for the class teacher (names stay on the phone)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..security import Principal, current_principal, ensure_child, ensure_classroom
from ..services import students as svc

router = APIRouter(prefix="/v1", tags=["activity"])


@router.get("/classrooms/{cid}/activity")
def classroom_activity(cid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    ensure_classroom(db, p, cid)
    return svc.classroom_activity(db, cid)


@router.get("/children/{child_id}/activity")
def child_activity(child_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    child = ensure_child(db, p, child_id)
    return svc.child_activity(db, child)
