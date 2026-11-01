"""Teacher-only accounts: self sign-up with no approval, own classes, throttling, data reset, and the
serverless pieces (inline jobs, cron, teacher-review speech, database blob store)."""

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

_n = iter(range(10_000))


def phone() -> str:
    return f"98{next(_n):08d}"


def signup(c: TestClient, **over) -> dict:
    body = {"display_name": "Asha Teacher", "phone": phone(), "pin": "583920", "school_name": "GPS Rampur",
            "class_name": "Class 1", "grades": [1, 2], **over}
    r = c.post("/v1/auth/signup", json=body)
    assert r.status_code == 200, r.text
    return {**r.json(), "phone": body["phone"], "pin": body["pin"]}


@pytest.fixture(scope="module")
def c():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_throttle():
    """Every TestClient request comes from the same address: start each test with no recorded attempts."""
    from sqlalchemy import delete

    from app.db import SessionLocal
    from app.main import init_app
    from app.models import AuthAttempt
    init_app()
    with SessionLocal() as db:
        db.execute(delete(AuthAttempt))
        db.commit()


def H(s: dict) -> dict:
    return {"Authorization": f"Bearer {s['token']}"}


def test_signup_is_active_at_once_with_its_own_class(c):
    s = signup(c)
    assert s["user"]["role"] == "teacher" and s["pin_change_required"] is False
    [room] = s["classrooms"]
    assert room["name"] == "Class 1" and room["school"] == "GPS Rampur" and room["grades"] == [1, 2]
    assert c.get("/v1/me", headers=H(s)).json()["classrooms"][0]["id"] == room["id"]
    assert c.get(f"/v1/classrooms/{room['id']}/children", headers=H(s)).json() == []
    again = c.post("/v1/auth/login", json={"phone": s["phone"], "pin": s["pin"]}).json()
    assert again["classrooms"][0]["id"] == room["id"]


def test_signup_validates_input(c):
    base = {"display_name": "T", "school_name": "S", "class_name": "C", "grades": [1]}
    weak = c.post("/v1/auth/signup", json={**base, "phone": phone(), "pin": "123456"})
    assert weak.status_code == 422 and "sequential" in weak.json()["detail"].lower()
    assert c.post("/v1/auth/signup", json={**base, "phone": "12345", "pin": "583920"}).status_code == 422
    assert c.post("/v1/auth/signup", json={**base, "phone": phone(), "pin": "583920", "grades": [7]}).status_code == 422
    assert c.post("/v1/auth/signup", json={**base, "phone": phone(), "pin": "583920", "class_name": "  "}).status_code == 422
    assert c.post("/v1/auth/signup", json={**base, "phone": phone(), "pin": "583920",
                                           "region_profile": "mars"}).status_code == 422
    s = signup(c)
    dup = c.post("/v1/auth/signup", json={**base, "phone": s["phone"], "pin": "583920"})
    assert dup.status_code == 409


def test_teacher_adds_and_edits_classes(c):
    s = signup(c, school_name="GPS Rampur")
    made = c.post("/v1/classrooms", headers=H(s), json={"school_name": "gps  rampur", "class_name": "Class 3",
                                                         "grades": [3], "region_profile": "east-up-bihar"})
    assert made.status_code == 200, made.text
    rooms = made.json()["classrooms"]
    assert [r["name"] for r in rooms] == ["Class 1", "Class 3"]
    assert rooms[1]["school"] == "GPS Rampur"  # same school (case/space-insensitive) is reused
    assert rooms[1]["region_profile"] == "east-up-bihar"
    rid = made.json()["id"]
    upd = c.patch(f"/v1/classrooms/{rid}", headers=H(s), json={"name": "Class 3 B", "grades": [3, 2, 3]})
    assert upd.status_code == 200
    assert next(r for r in upd.json()["classrooms"] if r["id"] == rid)["grades"] == [2, 3]
    other = signup(c)
    assert c.patch(f"/v1/classrooms/{rid}", headers=H(other), json={"name": "mine"}).status_code == 403
    assert c.get("/v1/regions").json()[0]["id"] == "standard"


def test_children_added_later_in_the_day_join_todays_list(c):
    s = signup(c)
    room = s["classrooms"][0]["id"]
    first = c.get(f"/v1/classrooms/{room}/today", headers=H(s)).json()
    assert first["children"] == []  # the first sync of the day, before any child was added
    kids = [str(uuid.uuid4()) for _ in range(2)]
    for i, kid in enumerate(kids):
        c.post(f"/v1/classrooms/{room}/children", headers=H(s),
               json={"id": kid, "grade": 1, "aruco_slot": i + 1, "consent_status": "granted"})
    later = c.get(f"/v1/classrooms/{room}/today", headers=H(s)).json()
    assert {x["child_id"] for x in later["children"]} == set(kids)
    assert all(x["plan"] and x["plan"]["items"] for x in later["children"])  # ready for the offline kiosk
    assert later["slate_problems"] == first["slate_problems"]  # the board does not change mid-day
    # consent withdrawn → off the list
    c.post(f"/v1/classrooms/{room}/children", headers=H(s),
           json={"id": kids[0], "grade": 1, "aruco_slot": 1, "consent_status": "withdrawn"})
    final = c.get(f"/v1/classrooms/{room}/today", headers=H(s)).json()
    assert [x["child_id"] for x in final["children"]] == [kids[1]]


def test_admin_api_is_gone(c):
    s = signup(c)
    for path in ("/v1/admin/dashboard", "/v1/admin/users", "/v1/notifications", "/v1/auth/setup",
                 "/v1/auth/signup-options"):
        assert c.get(path, headers=H(s)).status_code in (404, 405), path


def test_wrong_pins_are_throttled_in_the_database(c):
    s = signup(c)
    for _ in range(5):
        assert c.post("/v1/auth/login", json={"phone": s["phone"], "pin": "999111"}).status_code == 401
    locked = c.post("/v1/auth/login", json={"phone": s["phone"], "pin": s["pin"]})
    assert locked.status_code == 429  # even the right PIN waits until the window passes


def test_review_speech_backend_sends_recordings_to_the_teacher(c, monkeypatch):
    s = signup(c)
    room = s["classrooms"][0]["id"]
    kid = str(uuid.uuid4())
    assert c.post(f"/v1/classrooms/{room}/children", headers=H(s),
                  json={"id": kid, "grade": 1, "aruco_slot": 1, "consent_status": "granted"}).status_code == 200
    monkeypatch.setattr(get_settings(), "speech_backend", "review")
    monkeypatch.setattr(get_settings(), "inline_jobs", True)  # serverless mode: scored inside the request
    monkeypatch.setattr(get_settings(), "blob_backend", "db")  # ... with media in the database
    rid = str(uuid.uuid4())
    m = {"sessions": [{"id": str(uuid.uuid4()), "child_id": kid, "classroom_id": room,
                       "started_at": "2026-10-10T05:00:00Z", "responses": [
                           {"id": rid, "item_id": "hi.ak.a", "modality": "voice", "payload": {},
                            "created_at": "2026-10-10T05:00:05Z", "audio_part": "a"}]}]}
    r = c.post("/v1/sync", headers=H(s), data={"manifest": json.dumps(m)},
               files={"a": ("a.webm", b"\x1aE\xdf\xa3fake", "audio/webm")}).json()
    assert r["accepted"]["responses"] == [rid] and r["jobs"]["ran"] >= 1
    queue = c.get(f"/v1/classrooms/{room}/unsure", headers=H(s)).json()
    entry = next(e for e in queue if e["id"] == rid)
    assert entry["media"]  # the teacher can listen to it
    assert c.get(entry["media"], headers=H(s)).content.startswith(b"\x1aE")
    ok = c.post(f"/v1/responses/{rid}/confirm", headers=H(s), json={"correct": True})
    assert ok.status_code == 200 and ok.json()["status"] == "confirmed"
    assert c.post("/v1/jobs/run", headers=H(s)).json()["pending"] == 0


def test_cron_tick_needs_the_secret(c, monkeypatch):
    assert c.get("/v1/cron/tick").status_code == 401
    monkeypatch.setattr(get_settings(), "cron_secret", "s3cret-value")
    assert c.get("/v1/cron/tick", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert c.get("/v1/cron/tick", headers={"Authorization": "Bearer s3cret-value"}).status_code == 200


def test_database_blob_store_is_transactional(monkeypatch):
    from app import storage
    from app.db import SessionLocal
    monkeypatch.setattr(get_settings(), "blob_backend", "db")
    with SessionLocal() as db:
        st = storage.get_store(db)
        st.put("audio/x/1", b"abc", "audio/webm")
        st.put("audio/x/1", b"abcd", "audio/webm")  # overwrite is allowed
        assert st.get("audio/x/1") == b"abcd"
        db.rollback()  # the bytes roll back with the request's transaction
        with pytest.raises(FileNotFoundError):
            st.get("audio/x/1")
        st.put("audio/x/2", b"keep", "audio/webm")
        db.commit()
    with SessionLocal() as db:
        st = storage.get_store(db)
        assert st.get("audio/x/2") == b"keep"
        st.delete("audio/x/2")
        db.commit()
        with pytest.raises(FileNotFoundError):
            st.get("audio/x/2")


def test_postgres_urls_are_normalised():
    from app.config import Settings
    assert Settings(DATABASE_URL="postgres://u:p@h/db").database_url == "postgresql+psycopg://u:p@h/db"
    assert Settings(DATABASE_URL="postgresql://u:p@h/db").database_url == "postgresql+psycopg://u:p@h/db"


def test_reset_all_data_gives_a_fresh_start(c):
    """Runs last in this module: wipes every account and child."""
    from app.services.reset import reset_all_data
    s = signup(c)
    counts = reset_all_data()
    assert counts["app_user"] >= 1 and counts["classroom"] >= 1
    assert c.get("/v1/me", headers=H(s)).status_code == 401
    assert c.post("/v1/auth/login", json={"phone": s["phone"], "pin": s["pin"]}).status_code == 401
    signup(c, phone=s["phone"])  # the number can register again
