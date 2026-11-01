"""Accounts and the org hierarchy: who may create, see and manage what."""

import secrets

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal, create_all
from app.main import app
from app.models import User
from app.security import generate_pin, hash_phone, hash_pin


def phone() -> str:
    return "7" + "".join(secrets.choice("0123456789") for _ in range(9))


def login(c, ph, pin):
    r = c.post("/v1/auth/login", json={"phone": ph, "pin": pin})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def tree():
    """Top-level admin → state → two districts; a district admin for D1 and a teacher in D1."""
    create_all()
    c = TestClient(app)
    ph, pin = phone(), generate_pin(8)
    with SessionLocal() as db:
        db.add(User(role="admin", phone_hash=hash_phone(ph), pin_hash=hash_pin(pin), display_name="Top"))
        db.commit()
    top = login(c, ph, pin)
    state = c.post("/v1/admin/org-units", headers=top, json={"kind": "state", "name": "S"}).json()["id"]
    d1 = c.post("/v1/admin/org-units", headers=top, json={"kind": "district", "name": "D1", "parent_id": state}).json()["id"]
    d2 = c.post("/v1/admin/org-units", headers=top, json={"kind": "district", "name": "D2", "parent_id": state}).json()["id"]
    dph = phone()
    made = c.post("/v1/admin/users", headers=top,
                  json={"role": "admin", "phone": dph, "display_name": "D1 admin", "org_unit_id": d1})
    assert made.status_code == 200, made.text
    dadmin = login(c, dph, made.json()["pin"])
    return {"c": c, "top": top, "state": state, "d1": d1, "d2": d2, "dadmin": dadmin, "dphone": dph}


def test_first_run_setup_is_refused_once_accounts_exist(tree):
    c = tree["c"]
    assert c.get("/v1/auth/setup").json() == {"needed": False}
    r = c.post("/v1/auth/setup", json={"phone": phone(), "pin": "48151623", "display_name": "x"})
    assert r.status_code == 409


def test_org_kind_order_is_enforced(tree):
    c = tree["c"]
    r = c.post("/v1/admin/org-units", headers=tree["top"], json={"kind": "state", "name": "x", "parent_id": tree["d1"]})
    assert r.status_code == 422


def test_district_admin_builds_inside_own_subtree_only(tree):
    c, A = tree["c"], tree["dadmin"]
    block = c.post("/v1/admin/org-units", headers=A, json={"kind": "block", "name": "B1", "parent_id": tree["d1"]})
    assert block.status_code == 200
    assert c.post("/v1/admin/org-units", headers=A,
                  json={"kind": "block", "name": "x", "parent_id": tree["d2"]}).status_code == 403
    assert c.post("/v1/admin/org-units", headers=A, json={"kind": "state", "name": "x"}).status_code == 403
    assert c.post("/v1/admin/schools", headers=A, json={"name": "x", "org_unit_id": tree["d2"]}).status_code == 403
    assert c.post("/v1/admin/schools", headers=A, json={"name": "no unit"}).status_code == 403
    school = c.post("/v1/admin/schools", headers=A, json={"name": "School 1", "org_unit_id": block.json()["id"]})
    assert school.status_code == 200
    room = c.post("/v1/admin/classrooms", headers=A, json={"school_id": school.json()["id"], "name": "C1", "grades": [1]})
    assert room.status_code == 200
    units = {o["id"] for o in c.get("/v1/admin/org-units", headers=A).json()}
    assert tree["d1"] in units and tree["d2"] not in units and tree["state"] not in units
    assert [r["name"] for r in c.get("/v1/admin/classrooms", headers=A).json()] == ["C1"]
    tree["room"] = room.json()["id"]


def test_district_admin_cannot_create_peer_or_global_admin(tree):
    c, A = tree["c"], tree["dadmin"]
    peer = c.post("/v1/admin/users", headers=A,
                  json={"role": "admin", "phone": phone(), "display_name": "p", "org_unit_id": tree["d1"]})
    assert peer.status_code == 403
    glob = c.post("/v1/admin/users", headers=A, json={"role": "admin", "phone": phone(), "display_name": "g"})
    assert glob.status_code == 403
    crcc = c.post("/v1/admin/users", headers=A, json={"role": "crcc", "phone": phone(), "display_name": "c"})
    assert crcc.status_code == 422  # the CRCC role no longer exists


def test_teacher_account_lifecycle(tree):
    c, A = tree["c"], tree["dadmin"]
    ph = phone()
    made = c.post("/v1/admin/users", headers=A,
                  json={"role": "teacher", "phone": ph, "display_name": "T1", "classroom_ids": [tree["room"]]})
    assert made.status_code == 200, made.text
    uid, pin = made.json()["id"], made.json()["pin"]
    T = login(c, ph, pin)
    assert [r["id"] for r in c.get("/v1/me", headers=T).json()["classrooms"]] == [tree["room"]]
    # teachers cannot use admin endpoints
    assert c.get("/v1/admin/users", headers=T).status_code == 403
    listed = {u["id"]: u for u in c.get("/v1/admin/users", headers=A).json()}
    assert listed[uid]["can_manage"]
    assert listed[uid]["org_unit_id"] is not None  # defaults to the class's school unit (block B1)
    # reset PIN: old sessions end, new PIN works
    new_pin = c.post(f"/v1/admin/users/{uid}/reset-pin", headers=A).json()["pin"]
    assert c.get("/v1/me", headers=T).status_code == 401
    T = login(c, ph, new_pin)
    # deactivate: sessions end and login is refused; reactivate restores it
    assert c.patch(f"/v1/admin/users/{uid}", headers=A, json={"active": False}).json()["active"] is False
    assert c.get("/v1/me", headers=T).status_code == 401
    assert c.post("/v1/auth/login", json={"phone": ph, "pin": new_pin}).status_code == 401
    c.patch(f"/v1/admin/users/{uid}", headers=A, json={"active": True})
    login(c, ph, new_pin)


def test_district_admin_cannot_touch_accounts_above_or_outside(tree):
    c, A, top = tree["c"], tree["dadmin"], tree["top"]
    users = c.get("/v1/admin/users", headers=top).json()
    top_id = next(u["id"] for u in users if u["display_name"] == "Top")
    me = next(u for u in c.get("/v1/admin/users", headers=A).json() if u["is_self"])
    assert top_id not in {u["id"] for u in c.get("/v1/admin/users", headers=A).json()}
    assert c.post(f"/v1/admin/users/{top_id}/reset-pin", headers=A).status_code == 403
    assert c.patch(f"/v1/admin/users/{me['id']}", headers=A, json={"active": False}).status_code == 403
    other = c.post("/v1/admin/users", headers=top,
                   json={"role": "admin", "phone": phone(), "display_name": "D2 admin", "org_unit_id": tree["d2"]}).json()
    assert c.post(f"/v1/admin/users/{other['id']}/reset-pin", headers=A).status_code == 403
    # the top-level admin manages everyone below, including the district admin
    reset = c.post(f"/v1/admin/users/{me['id']}/reset-pin", headers=top)
    assert reset.status_code == 200
    tree["dadmin"] = login(c, tree["dphone"], reset.json()["pin"])  # the reset ended the old session


def test_signup_waits_for_approval_by_an_admin_above(tree):
    c, A = tree["c"], tree["dadmin"]
    opts = c.get("/v1/auth/signup-options").json()
    assert tree["room"] in {r["id"] for r in opts["classrooms"]}
    ph, pin = phone(), "48261537"
    r = c.post("/v1/auth/signup", json={"role": "teacher", "display_name": "New T", "phone": ph, "pin": pin,
                                        "classroom_ids": [tree["room"]]})
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    # cannot log in yet; a wrong PIN still says only "wrong phone or PIN"
    assert c.post("/v1/auth/login", json={"phone": ph, "pin": pin}).status_code == 403
    assert c.post("/v1/auth/login", json={"phone": ph, "pin": "93726154"}).status_code == 401
    # duplicate phone, weak PIN, missing class are refused
    assert c.post("/v1/auth/signup", json={"role": "teacher", "display_name": "x", "phone": ph, "pin": pin,
                                           "classroom_ids": [tree["room"]]}).status_code == 409
    assert c.post("/v1/auth/signup", json={"role": "crcc", "display_name": "x", "phone": phone(),
                                           "pin": "123456", "org_unit_id": tree["d1"]}).status_code == 422
    assert c.post("/v1/auth/signup", json={"role": "teacher", "display_name": "x", "phone": phone(),
                                           "pin": pin}).status_code == 422
    # the district admin above the class sees the request and approves it
    req = next(u for u in c.get("/v1/admin/users", headers=A).json() if u["id"] == uid)
    assert req["pending"] and req["can_manage"]
    assert c.post(f"/v1/admin/users/{uid}/approve", headers=A).json()["active"] is True
    login(c, ph, pin)


def test_admin_signup_is_active_at_once_and_notifies_admins_above(tree):
    c, A, top = tree["c"], tree["dadmin"], tree["top"]
    ph = phone()
    assert c.post("/v1/auth/signup", json={"role": "admin", "display_name": "x", "phone": ph,
                                           "pin": "48261537"}).status_code == 422  # no top-level admin sign-ups
    r = c.post("/v1/auth/signup", json={"role": "admin", "display_name": "Peer", "phone": ph, "pin": "48261537",
                                        "org_unit_id": tree["d1"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pending"] is False and body["token"] and body["user"]["role"] == "admin"
    assert c.get("/v1/me", headers={"Authorization": f"Bearer {body['token']}"}).status_code == 200
    login(c, ph, "48261537")  # no approval needed
    # the top-level admin (above D1) is told; the D1 admin is a peer and is not
    top_notes = c.get("/v1/notifications", headers=top).json()["items"]
    assert any(n["kind"] == "admin_joined" and n["subject_user_id"] == body["id"] for n in top_notes)
    assert not any(n["subject_user_id"] == body["id"] for n in c.get("/v1/notifications", headers=A).json()["items"])


def test_admin_signup_can_require_approval_again(tree):
    from app.config import get_settings
    c = tree["c"]
    s = get_settings()
    s.admin_self_signup = False
    try:
        r = c.post("/v1/auth/signup", json={"role": "admin", "display_name": "Strict", "phone": phone(),
                                            "pin": "48261537", "org_unit_id": tree["d2"]})
        assert r.status_code == 200 and r.json()["pending"] is True and "token" not in r.json()
    finally:
        s.admin_self_signup = True


def test_teacher_signup_notifies_every_admin_who_may_approve(tree):
    c, A, top = tree["c"], tree["dadmin"], tree["top"]
    ph, pin = phone(), "48261537"
    d1_admin_id = next(u["id"] for u in c.get("/v1/admin/users", headers=A).json() if u["is_self"])
    uid = c.post("/v1/auth/signup", json={"role": "teacher", "display_name": "Notified T", "phone": ph, "pin": pin,
                                          "classroom_ids": [tree["room"]], "approver_id": d1_admin_id}).json()["id"]
    for H in (A, top):
        notes = c.get("/v1/notifications", headers=H).json()
        note = next(n for n in notes["items"] if n["subject_user_id"] == uid)
        assert note["kind"] == "signup_request" and not note["read"] and notes["unread"] >= 1
    req = next(u for u in c.get("/v1/admin/users", headers=A).json() if u["id"] == uid)
    assert req["approver"]["id"] == d1_admin_id
    assert c.post(f"/v1/admin/users/{uid}/approve", headers=A).status_code == 200
    # handled once → cleared for every admin; the teacher is told
    for H in (A, top):
        assert next(n for n in c.get("/v1/notifications", headers=H).json()["items"] if n["subject_user_id"] == uid)["read"]
    T = login(c, ph, pin)
    mine = c.get("/v1/notifications", headers=T).json()
    assert mine["items"][0]["kind"] == "account_approved"
    nid = mine["items"][0]["id"]
    assert c.post(f"/v1/notifications/{nid}/read", headers=T).json()["read"] is True
    assert c.post(f"/v1/notifications/{nid}/read", headers=A).status_code == 404  # not yours


def test_org_admin_sees_student_data_only_inside_own_subtree(tree):
    import uuid
    c, A, top = tree["c"], tree["dadmin"], tree["top"]
    # a D2 class with a student, made by the top-level admin
    school = c.post("/v1/admin/schools", headers=top, json={"name": "D2 school", "org_unit_id": tree["d2"]}).json()["id"]
    room2 = c.post("/v1/admin/classrooms", headers=top, json={"school_id": school, "name": "C2", "grades": [1]}).json()["id"]
    kid2 = str(uuid.uuid4())
    made = c.post(f"/v1/classrooms/{room2}/children", headers=top, json={"id": kid2, "grade": 1, "aruco_slot": 1})
    assert made.status_code == 200 and made.json()["register_no"].startswith("STU-")
    kid1 = str(uuid.uuid4())
    assert c.post(f"/v1/classrooms/{tree['room']}/children", headers=A,
                  json={"id": kid1, "grade": 1, "aruco_slot": 1}).status_code == 200
    # D1 admin: own class yes, D2 class no
    assert c.get(f"/v1/children/{kid1}/activity", headers=A).status_code == 200
    assert c.get(f"/v1/children/{kid2}/activity", headers=A).status_code == 403
    assert c.get(f"/v1/classrooms/{room2}/children", headers=A).status_code == 403
    ids = {s["id"] for s in c.get("/v1/admin/students", headers=A).json()["students"]}
    assert kid1 in ids and kid2 not in ids
    assert c.patch(f"/v1/admin/students/{kid2}", headers=A, json={"consent_status": "granted"}).status_code == 403
    assert c.patch(f"/v1/admin/students/{kid1}", headers=A, json={"consent_status": "granted"}).json()["consent"] == "granted"
    # the top-level admin sees both, and the dashboards only count what is in scope
    all_ids = {s["id"] for s in c.get("/v1/admin/students", headers=top, params={"limit": 200}).json()["students"]}
    assert {kid1, kid2} <= all_ids
    d1 = c.get("/v1/admin/dashboard", headers=A).json()
    assert d1["totals"]["classrooms"] == 1 and d1["totals"]["students"] == 1
    teachers = {t["display_name"] for t in c.get("/v1/admin/teachers", headers=A).json()}
    assert "T1" in teachers


def test_approvers_are_only_admins_above_nearest_first(tree):
    c, A = tree["c"], tree["dadmin"]
    block = next(o["id"] for o in c.get("/v1/admin/org-units", headers=A).json() if o["name"] == "B1")
    names = [a["display_name"] for a in c.get("/v1/auth/approvers", params={"role": "admin", "org_unit_id": block}).json()]
    assert names[:1] == ["D1 admin"] and "Top" in names
    # an admin for D1 itself: the D1 admin is a peer, so only admins above D1
    names = [a["display_name"] for a in c.get("/v1/auth/approvers", params={"role": "admin", "org_unit_id": tree["d1"]}).json()]
    assert "D1 admin" not in names and "Top" in names
    names = [a["display_name"] for a in c.get("/v1/auth/approvers", params={"role": "teacher", "classroom_id": tree["room"]}).json()]
    assert names[:1] == ["D1 admin"] and "Top" in names
