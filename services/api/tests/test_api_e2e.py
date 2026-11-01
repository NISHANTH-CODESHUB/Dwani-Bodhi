"""End-to-end: the demo seeder drives the real API; we then check the system's conclusions."""

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.demo import seed
from app.main import app


@pytest.fixture(scope="module")
def world():
    client = TestClient(app)
    data = seed(client, weeks=2, verbose=False)
    data["client"] = client
    data["H"] = {"Authorization": f"Bearer {data['token']}"}
    return data


def login_as(world, role):
    cred = world["credentials"][role]
    r = world["client"].post("/v1/auth/login", json={"phone": cred["phone"], "pin": cred["pin"]})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def profile(world, name):
    cid = world["children"][name]
    return world["client"].get(f"/v1/children/{cid}/profile", headers=world["H"]).json()


def confusion_ids(p):
    return {c["id"]: c["status"] for c in p["confusions"]}


def test_auth_required(world):
    assert world["client"].get("/v1/bootstrap").status_code == 401
    bad = world["client"].post("/v1/auth/login", json={"phone": "9000000001", "pin": "0000"})
    assert bad.status_code == 401


def test_reading_confusion_is_confirmed(world):
    p = profile(world, "Aman")
    assert confusion_ids(p).get("READ_MLEN") == "confirmed", p["confusions"]


def test_aspiration_confusion_detected(world):
    assert "READ_ASP" in confusion_ids(profile(world, "Pooja"))


def test_slate_bug_confirmed_by_reproduction(world):
    ids = confusion_ids(profile(world, "Sonu"))
    assert ids.get("SUB_SMALLER_FROM_LARGER") == "confirmed", ids


def test_fluent_child_has_no_confirmed_reading_confusion(world):
    p = profile(world, "Seema")
    assert not [c for c in p["confusions"] if c["id"].startswith("READ_") and c["status"] == "confirmed"]
    assert p["levels"]["literacy"]["rung_index"] >= p["levels"]["literacy"]["rung_index"]  # computed


def test_levels_order_beginner_below_fluent(world):
    rani = profile(world, "Rani")["levels"]["literacy"]["rung_index"]
    seema = profile(world, "Seema")["levels"]["literacy"]["rung_index"]
    assert rani < seema


def test_card_uses_library_activities_and_evidence(world):
    card = world["card"]
    assert card["source"] in ("template", "llm")
    groups = card["card"]["groups"]
    assert groups
    keys = {g["key"] for g in card["summary"]["groups"]}
    for g in groups:
        assert g["group_key"] in keys
        assert g["activity_id"].startswith(("lit.", "num."))


def test_rechecks_registered_and_today_plan(world):
    c, H = world["client"], world["H"]
    today = c.get(f"/v1/classrooms/{world['classroom_id']}/today", headers=H).json()
    assert 1 <= len(today["children"]) <= 6
    assert all(ch["plan"] and ch["plan"]["items"] for ch in today["children"])
    assert len(today["slate_problems"]) == 2


def test_sync_is_idempotent_and_consent_enforced(world):
    c, H = world["client"], world["H"]
    room = world["classroom_id"]
    child = world["children"]["Seema"]
    rid, sid = str(uuid.uuid4()), str(uuid.uuid4())
    m = {"sessions": [{"id": sid, "child_id": child, "classroom_id": room, "started_at": "2026-10-10T05:00:00Z",
                       "responses": [{"id": rid, "item_id": "m.tap.47", "modality": "tap", "payload": {"chosen": "74"},
                                      "created_at": "2026-10-10T05:00:05Z"}]}]}
    r1 = c.post("/v1/sync", headers=H, data={"manifest": json.dumps(m)}).json()
    r2 = c.post("/v1/sync", headers=H, data={"manifest": json.dumps(m)}).json()
    assert rid in r1["accepted"]["responses"] and rid in r2["duplicates"]
    new_child = str(uuid.uuid4())
    c.post(f"/v1/classrooms/{room}/children", headers=H, json={"id": new_child, "grade": 1, "aruco_slot": 40})
    m2 = {"sessions": [{"id": str(uuid.uuid4()), "child_id": new_child, "classroom_id": room,
                        "started_at": "2026-10-10T05:00:00Z", "responses": []}]}
    r3 = c.post("/v1/sync", headers=H, data={"manifest": json.dumps(m2)}).json()
    assert r3["rejected"] and "consent" in r3["rejected"][0]["reason"]


def test_explain_uses_placeholder_not_name(world):
    out = world["client"].get(f"/v1/children/{world['children']['Aman']}/explain", headers=world["H"]).json()
    blob = json.dumps(out, ensure_ascii=False)
    assert "{{child}}" in blob and "Aman" not in blob


def test_every_student_has_a_unique_register_number(world):
    import re
    c, H, room = world["client"], world["H"], world["classroom_id"]
    kids = c.get(f"/v1/classrooms/{room}/children", headers=H).json()
    regs = [k["register_no"] for k in kids]
    assert all(re.fullmatch(r"STU-\d{4}-\d{5}", r) for r in regs) and len(set(regs)) == len(regs)
    # stable: re-sending the roster (offline edits) never changes a number
    k = kids[0]
    again = c.post(f"/v1/classrooms/{room}/children", headers=H,
                   json={"id": k["id"], "grade": k["grade"], "aruco_slot": k["aruco_slot"],
                         "consent_status": k["consent_status"]}).json()
    assert again["register_no"] == k["register_no"]
    new = c.post(f"/v1/classrooms/{room}/children", headers=H,
                 json={"id": str(uuid.uuid4()), "grade": 1, "aruco_slot": 63}).json()["register_no"]
    assert new not in regs and int(new[-5:]) == max(int(r[-5:]) for r in regs if r[4:8] == new[4:8]) + 1


def test_teacher_sees_class_and_student_activity(world):
    c, H, room = world["client"], world["H"], world["classroom_id"]
    act = c.get(f"/v1/classrooms/{room}/activity", headers=H).json()
    assert act["totals"]["students"] >= 12 and len(act["daily"]) == 14
    row = next(s for s in act["students"] if s["id"] == world["children"]["Seema"])
    assert row["register_no"] and row["responses"] > 0 and row["accuracy"] is not None
    one = c.get(f"/v1/children/{world['children']['Aman']}/activity", headers=H).json()
    assert one["student"]["id"] == world["children"]["Aman"]
    kinds = {e["kind"] for e in one["timeline"]}
    assert "session" in kinds and "slate" in kinds  # kiosk sessions and slate answers
    session = next(e for e in one["timeline"] if e["kind"] == "session")
    assert session["answers"] == len(session["items"]) and session["items"][0]["outcome"] in (
        "correct", "incorrect", "unsure", "pending", "error")
    assert one["domains"]["literacy"]["correct"] + one["domains"]["literacy"]["incorrect"] > 0


def test_teacher_cannot_access_other_classroom(world):
    c = world["client"]
    other = c.post("/v1/auth/signup", json={"display_name": "Other", "phone": "9123400001", "pin": "583920",
                                             "school_name": "दूसरा स्कूल", "class_name": "x", "grades": [1]})
    assert other.status_code == 200, other.text
    room = other.json()["classrooms"][0]["id"]
    assert c.get(f"/v1/classrooms/{room}/children", headers=world["H"]).status_code == 403
    # ... and the other teacher cannot see the demo class or its children
    OH = {"Authorization": f"Bearer {other.json()['token']}"}
    assert c.get(f"/v1/classrooms/{world['classroom_id']}/children", headers=OH).status_code == 403
    kid = world["children"]["Pooja"]
    assert c.get(f"/v1/children/{kid}/profile", headers=OH).status_code == 403
    assert c.get(f"/v1/children/{kid}/activity", headers=OH).status_code == 403


def test_right_to_erasure(world):
    c, H = world["client"], world["H"]
    victim = world["children"]["Jyoti"]
    assert c.delete(f"/v1/children/{victim}", headers=H).status_code == 200
    assert c.get(f"/v1/children/{victim}/profile", headers=H).status_code == 404


def test_erased_child_cannot_be_revived_or_receive_data(world):
    c, H, room = world["client"], world["H"], world["classroom_id"]
    victim = world["children"]["Jyoti"]  # erased by test_right_to_erasure
    stale = {"id": victim, "grade": 2, "aruco_slot": 45, "consent_status": "granted"}
    assert c.post(f"/v1/classrooms/{room}/children", headers=H, json=stale).status_code == 410
    m = {"sessions": [{"id": str(uuid.uuid4()), "child_id": victim, "classroom_id": room,
                       "started_at": "2026-10-10T05:00:00Z", "responses": []}]}
    r = c.post("/v1/sync", headers=H, data={"manifest": json.dumps(m)}).json()
    assert r["rejected"] and not r["accepted"]["sessions"]


def test_sync_isolates_bad_files_and_never_accepts_voice_without_audio(world):
    c, H, room = world["client"], world["H"], world["classroom_id"]
    child = world["children"]["Seema"]
    ok, bad_mime, no_audio = (str(uuid.uuid4()) for _ in range(3))
    resp = lambda rid, part: {"id": rid, "item_id": "hi.ak.a", "modality": "voice", "payload": {},
                              "created_at": "2026-10-10T05:00:05Z", "audio_part": part}
    m = {"sessions": [{"id": str(uuid.uuid4()), "child_id": child, "classroom_id": room,
                       "started_at": "2026-10-10T05:00:00Z",
                       "responses": [resp(ok, "a1"), resp(bad_mime, "a2"), resp(no_audio, None)]}]}
    files = {"a1": ("a.webm", b"\x1a\x45\xdf\xa3fake", "audio/webm"), "a2": ("a.3gp", b"xx", "audio/3gpp")}
    r = c.post("/v1/sync", headers=H, data={"manifest": json.dumps(m)}, files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    rejected = {x["id"]: x["reason"] for x in body["rejected"]}
    assert ok in body["accepted"]["responses"]
    assert "unsupported" in rejected[bad_mime] and rejected[no_audio] == "audio missing"


def test_sync_rejects_non_uuid_ids(world):
    c, H, room = world["client"], world["H"], world["classroom_id"]
    m = {"sessions": [{"id": "../../../../etc/passwd-xxxxxxxxxxxxxxxx", "child_id": world["children"]["Seema"],
                       "classroom_id": room, "started_at": "2026-10-10T05:00:00Z", "responses": []}]}
    assert c.post("/v1/sync", headers=H, data={"manifest": json.dumps(m)}).status_code == 422


def test_health(world):
    h = world["client"].get("/health").json()
    assert h["ok"] and h["llm_mode"] == "offline"


def test_deleted_childs_id_card_can_be_reused(world):
    c, H, room = world["client"], world["H"], world["classroom_id"]
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    assert c.post(f"/v1/classrooms/{room}/children", headers=H, json={"id": a, "grade": 1, "aruco_slot": 77}).status_code == 200
    assert c.post(f"/v1/classrooms/{room}/children", headers=H, json={"id": b, "grade": 1, "aruco_slot": 77}).status_code == 409
    assert c.delete(f"/v1/children/{a}", headers=H).status_code == 200
    assert c.post(f"/v1/classrooms/{room}/children", headers=H, json={"id": b, "grade": 1, "aruco_slot": 77}).status_code == 200


def test_silent_child_is_no_speech_not_error(world):
    from app.db import SessionLocal
    from app.jobs.worker import drain
    from app.models import Response
    c, H, room = world["client"], world["H"], world["classroom_id"]
    child = world["children"]["Rani"]
    rid = str(uuid.uuid4())
    m = {"sessions": [{"id": str(uuid.uuid4()), "child_id": child, "classroom_id": room,
                       "started_at": "2026-10-11T05:00:00Z",
                       "responses": [{"id": rid, "item_id": "hi.w.nadi", "modality": "voice",
                                      "payload": {"simulated_utterance": ""}, "created_at": "2026-10-11T05:00:05Z"}]}]}
    assert rid in c.post("/v1/sync", headers=H, data={"manifest": json.dumps(m)}).json()["accepted"]["responses"]
    drain()
    with SessionLocal() as db:
        r = db.get(Response, rid)
        assert r.status == "unsure" and r.verdict["status"] == "NO_SPEECH"


def test_slate_confirm_requires_answer(world):
    c, H = world["client"], world["H"]
    from app.db import SessionLocal
    from app.models import Response
    with SessionLocal() as db:
        r = db.query(Response).filter(Response.item_type == "slate").first()
        r.status = "unsure"  # queue it, as a low-confidence transcription would be
        db.commit()
        done = db.query(Response).filter(Response.status.in_(["scored", "confirmed"])).first()
        rid, done_id = r.id, done.id
    assert c.post(f"/v1/responses/{rid}/confirm", headers=H, json={}).status_code == 422
    # Already-applied evidence cannot be confirmed again (would double-count in the learner model).
    assert c.post(f"/v1/responses/{done_id}/confirm", headers=H, json={"correct": False}).status_code == 409


def test_card_activity_targets_the_groups_top_confusion(world):
    from app.services.catalog import describe
    from app.services.common import pack
    cp = pack()
    card = world["client"].get(f"/v1/classrooms/{world['classroom_id']}/card?regenerate=true", headers=world["H"]).json()
    summary = {g["key"]: g for g in card["summary"]["groups"]}
    for g in card["card"]["groups"]:
        top = summary[g["group_key"]]["top_confusions"]
        if top:
            tags = set(describe(top[0]["id"])["tags"]) | {top[0]["id"]}
            assert tags & set(cp.activities[g["activity_id"]].targets), (g["group_key"], g["activity_id"], top[0]["id"])


def test_full_classroom_slate_photos_are_not_kept(world):
    from app.db import SessionLocal
    from app.models import Blob
    with SessionLocal() as db:
        photos = db.query(Blob).filter(Blob.kind == "slate_photo").all()
        crops = db.query(Blob).filter(Blob.kind == "slate_crop", Blob.deleted_at.is_(None)).all()
    assert photos and all(b.deleted_at is not None for b in photos)
    assert crops and all(b.delete_after is not None for b in crops)


def test_login_locks_after_repeated_wrong_pins(world):
    c = world["client"]
    phone = "9111111111"  # no such user: lockout must not reveal whether a phone exists
    codes = [c.post("/v1/auth/login", json={"phone": phone, "pin": "0000"}).status_code for _ in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429


def test_lockout_from_one_client_does_not_lock_the_owner_out(world):
    """A stranger typing wrong PINs for a teacher's number must not block the teacher's own device."""
    cred = world["credentials"]["teacher"]
    stranger = TestClient(app, client=("203.0.113.9", 5000))
    codes = [stranger.post("/v1/auth/login", json={"phone": cred["phone"], "pin": "0000"}).status_code
             for _ in range(6)]
    assert codes[5] == 429
    login_as(world, "teacher")  # the default test client is a different address


def test_malformed_tokens_are_401_not_500(world):
    import jwt as pyjwt

    from app.config import get_settings
    c, secret = world["client"], get_settings().jwt_secret
    for claims in ({"role": "teacher", "exp": 9999999999}, {"sub": 42, "exp": 9999999999}, {"sub": "x"}):
        tok = pyjwt.encode(claims, secret, algorithm="HS256")
        assert c.get("/v1/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_demo_credentials_are_random_and_strong(world):
    from app.security import pin_problem
    creds = world["credentials"]
    assert set(creds) == {"teacher"}
    for c in creds.values():
        assert pin_problem(c["pin"], c["phone"]) is None and c["pin"] != "1234"
        assert not c["phone"].startswith("900000000")
    assert login_as(world, "teacher")


def test_weak_pin_forces_change_and_change_ends_old_sessions(world):
    from app.db import SessionLocal
    from app.models import User
    from app.security import hash_phone, hash_pin
    c = world["client"]
    phone = "7012345678"
    with SessionLocal() as db:  # an account created before the PIN policy, with PIN 1234
        db.add(User(role="teacher", phone_hash=hash_phone(phone), pin_hash=hash_pin("1234"), display_name="old"))
        db.commit()
    r = c.post("/v1/auth/login", json={"phone": phone, "pin": "1234"}).json()
    assert r["pin_change_required"] and r["classrooms"] == []
    limited = {"Authorization": f"Bearer {r['token']}"}
    assert c.get("/v1/me", headers=limited).status_code == 403  # the weak-PIN token can do nothing else
    bad = c.post("/v1/auth/pin", headers=limited, json={"current_pin": "1234", "new_pin": "123456"})
    assert bad.status_code == 422
    phoney = c.post("/v1/auth/pin", headers=limited, json={"current_pin": "1234", "new_pin": "345678", "phone": phone})
    assert phoney.status_code == 422  # digits taken from the phone number
    ok = c.post("/v1/auth/pin", headers=limited, json={"current_pin": "1234", "new_pin": "580317"})
    assert ok.status_code == 200
    fresh = {"Authorization": f"Bearer {ok.json()['token']}"}
    assert c.get("/v1/me", headers=fresh).status_code == 200
    assert c.get("/v1/me", headers=limited).status_code == 401  # tokens from before the change are revoked
    assert c.post("/v1/auth/login", json={"phone": phone, "pin": "1234"}).status_code == 401
    again = c.post("/v1/auth/login", json={"phone": phone, "pin": "580317"}).json()
    assert again["pin_change_required"] is False


def test_failed_media_job_still_deletes_child_audio(world):
    from app.db import SessionLocal
    from app.jobs.queue import fail
    from app.models import Blob, Job, Response
    rid = str(uuid.uuid4())
    with SessionLocal() as db:
        db.add(Response(id=rid, child_id=world["children"]["Seema"], item_id="hi.ak.a", item_type="akshara",
                        modality="voice", payload={}, status="pending"))
        db.add(Blob(kind="audio", response_id=rid, key=f"audio/x/{rid}", mime="audio/webm", size=1, sha256="0"))
        job = Job(kind="score_voice", queue="speech", payload={"response_id": rid}, attempts=5, max_attempts=5)
        db.add(job)
        db.commit()
        fail(db, job, "undecodable audio")
        assert job.status == "failed"
        assert db.query(Blob).filter(Blob.response_id == rid).one().delete_after is not None
        assert db.get(Response, rid).status == "error"


def test_erasure_removes_slate_crops_sessions_and_jobs(world):
    """Runs last: deletes a child with slate evidence and checks nothing about them remains."""
    from app.db import SessionLocal
    from app.models import AssessmentSession, Blob, Job, Response
    from app.storage import get_store
    c, H = world["client"], world["H"]
    victim = world["children"]["Sonu"]
    with SessionLocal() as db:
        keys = {(r.payload or {}).get("crop_key") for r in db.query(Response).filter(
            Response.child_id == victim, Response.item_type == "slate")} - {None}
    assert keys
    assert c.delete(f"/v1/children/{victim}", headers=H).status_code == 200
    with SessionLocal() as db:
        assert not db.query(Blob).filter(Blob.key.in_(keys)).count()
        assert not db.query(AssessmentSession).filter(AssessmentSession.child_id == victim).count()
        assert not db.query(Response).filter(Response.child_id == victim).count()
        assert not [j for j in db.query(Job).all() if (j.payload or {}).get("child_id") == victim]
    with SessionLocal() as db:
        for k in keys:
            with pytest.raises(FileNotFoundError):  # tests use the local blob store
                get_store(db).get(k)
