"""Seed a realistic demo classroom by driving the REAL API (sync → scoring → learner → plan → card).

Children follow "personas" with systematic confusions; their reading is simulated through the
SimulatedBackend (payload.simulated_utterance) so the full pipeline runs without a speech model.
Slates are synthesised as real images with ArUco cards; in offline LLM mode their answers go to the
teacher-confirm queue and are confirmed via the API, exactly as a teacher would.

    python -m app.demo                       # seeds into DATABASE_URL
    python -m app.demo --reset-credentials   # new random phones + PINs for the demo accounts

Demo accounts get random phone numbers and strong random PINs, created once per database. They are
printed once and written to data/demo-credentials.txt (git-ignored); the database keeps only hashes.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import select

from .config import REPO_ROOT
from .content.schema import TAP_TYPES
from .db import SessionLocal, create_all
from .diagnosis.bugs import DEFAULT_LIBRARY
from .jobs.worker import drain
from .models import Classroom, ClassroomTeacher, OrgUnit, School, User
from .security import generate_pin, hash_phone, hash_pin, issue_token
from .speech.mutations import generate_candidates
from .vision.slates import make_marker_card

DEMO_NAMES = {"teacher": "Sunita Didi", "admin": "Admin (demo)"}
DEMO_SCHOOL = "Primary School Rampur (demo)"
CREDENTIALS_FILE = Path(os.environ.get("DEMO_CREDENTIALS_FILE", REPO_ROOT / "data" / "demo-credentials.txt"))


def _random_phone() -> str:
    return secrets.choice("6789") + "".join(secrets.choice("0123456789") for _ in range(9))


def new_credentials() -> dict[str, dict[str, str]]:
    phones: set[str] = set()
    while len(phones) < len(DEMO_NAMES):
        phones.add(_random_phone())
    return {role: {"phone": ph, "pin": generate_pin()} for role, ph in zip(DEMO_NAMES, sorted(phones))}


def _demo_users(db, room_id: str) -> dict[str, User]:
    teacher_id = db.scalar(select(ClassroomTeacher.user_id).where(ClassroomTeacher.classroom_id == room_id))
    out = {"teacher": db.get(User, teacher_id)} if teacher_id else {}
    for role in ("admin",):
        u = db.scalar(select(User).where(User.role == role, User.display_name.in_([DEMO_NAMES[role], "Admin"])))
        if u:
            out[role] = u
    return out


def _apply_credentials(users: dict[str, User], creds: dict[str, dict[str, str]]) -> None:
    now = datetime.now(UTC)
    for role, u in users.items():
        u.phone_hash, u.pin_hash = hash_phone(creds[role]["phone"]), hash_pin(creds[role]["pin"])
        u.credentials_changed_at = now  # sessions issued under the old credentials end


def save_credentials(creds: dict[str, dict[str, str]]) -> None:
    CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Dhwani-Bodhi demo logins (generated; do not commit or share publicly)"]
    lines += [f"{role:8s} phone {c['phone']}  PIN {c['pin']}" for role, c in creds.items()]
    CREDENTIALS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(CREDENTIALS_FILE, 0o600)
    except OSError:
        pass


@dataclass
class Persona:
    name: str
    grade: int
    reading_rules: set[str] = field(default_factory=set)  # systematic reading confusions
    letters_known: bool = True
    math_bug: str | None = None  # bug id applied to slate answers
    tap_probe: str | None = None  # e.g. NUM_REVERSAL
    fluent: bool = False


PERSONAS = [
    Persona("Rani", 1, letters_known=False),
    Persona("Aman", 2, {"MLEN"}, math_bug="SUB_SMALLER_FROM_LARGER"),
    Persona("Sonu", 2, {"MLEN"}, math_bug="SUB_SMALLER_FROM_LARGER"),
    Persona("Pooja", 2, {"ASP"}, math_bug="ADD_NO_CARRY", tap_probe="NUM_REVERSAL"),
    Persona("Rahul", 1, {"MDROP"}, tap_probe="NUM_REVERSAL"),
    Persona("Seema", 2, fluent=True),
    Persona("Arif", 2, {"MLEN", "NAS"}, math_bug="SUB_BORROW_NO_DECREMENT"),
    Persona("Geeta", 1, {"ASP"}),
    Persona("Mohan", 2, fluent=True, math_bug="ADD_NO_CARRY"),
    Persona("Neha", 2, {"MLEN"}),
    Persona("Karan", 1, {"MDROP", "MLEN"}, math_bug="SUB_SMALLER_FROM_LARGER"),
    Persona("Jyoti", 2, fluent=True),
]


def _speak(text: str, p: Persona, rng: random.Random) -> str:
    if not p.letters_known:
        return ""  # a true beginner: silent on every reading item (exercises the discontinue rule)
    words = text.split()
    out = []
    for w in words:
        said = w
        for c in generate_candidates(w):
            if c.rule in p.reading_rules and rng.random() < 0.85:
                said = c.text
                break
        out.append(said)
    return " ".join(out)


def ensure_org(db, reset_credentials: bool = False) -> dict:
    """Create the demo org once. Returns the classroom, the teacher, and credentials only when they were
    (re)generated: existing ones cannot be shown again because the database stores only hashes."""
    school = db.scalar(select(School).where(School.name == DEMO_SCHOOL))
    if school is not None:
        room = db.scalar(select(Classroom).where(Classroom.school_id == school.id))
        users = _demo_users(db, room.id)
        creds = None
        if reset_credentials:
            creds = new_credentials()
            _apply_credentials(users, creds)
            db.commit()
        return {"classroom_id": room.id, "teacher_id": users["teacher"].id, "credentials": creds}
    state = OrgUnit(kind="state", name="Uttar Pradesh")
    db.add(state)
    db.flush()
    district = OrgUnit(kind="district", name="Hardoi", parent_id=state.id)
    db.add(district)
    db.flush()
    block = OrgUnit(kind="block", name="Sandila", parent_id=district.id)
    db.add(block)
    db.flush()
    cluster = OrgUnit(kind="cluster", name="Cluster 4", parent_id=block.id)
    db.add(cluster)
    db.flush()
    school = School(name=DEMO_SCHOOL, org_unit_id=cluster.id, region_profile="west-central-up")
    db.add(school)
    db.flush()
    room = Classroom(school_id=school.id, name="Class 1-2", grades=[1, 2], daily_kiosk_budget_min=12)
    db.add(room)
    db.flush()
    creds = new_credentials()
    users = {
        "teacher": User(role="teacher", display_name=DEMO_NAMES["teacher"]),
        "admin": User(role="admin", display_name=DEMO_NAMES["admin"]),
    }
    _apply_credentials(users, creds)
    for u in users.values():
        u.credentials_changed_at = None
    db.add_all(users.values())
    db.flush()
    db.add(ClassroomTeacher(classroom_id=room.id, user_id=users["teacher"].id))
    db.commit()
    return {"classroom_id": room.id, "teacher_id": users["teacher"].id, "credentials": creds}


def slate_photo(entries: list[tuple[int, list[str]]], problems: list[dict]) -> bytes:
    """Synthesise a photo of several chalk slates, each with an ArUco card at its top-left corner."""
    W, H = 1600, 1000
    img = np.full((H, W, 3), (70, 95, 120), np.uint8)  # floor
    cols = 3
    for idx, (slot, answers) in enumerate(entries):
        x0, y0 = 40 + (idx % cols) * 520, 40 + (idx // cols) * 470
        cv2.rectangle(img, (x0, y0), (x0 + 480, y0 + 430), (40, 40, 40), -1)  # slate
        card = cv2.resize(make_marker_card(slot, 300), (64, 80))
        img[y0 + 6:y0 + 86, x0 + 6:x0 + 70] = cv2.cvtColor(card, cv2.COLOR_GRAY2BGR)
        for j, (prob, ans) in enumerate(zip(problems, answers)):
            yy = y0 + 150 + j * 140
            txt = f"{prob['a']} {prob['op']} {prob['b']} = {ans}"
            cv2.putText(img, txt, (x0 + 30, yy), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (235, 235, 235), 3, cv2.LINE_AA)
    _ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return buf.tobytes()


def seed(client: TestClient | None = None, weeks: int = 2, seed_value: int = 7, verbose: bool = True,
         reset_credentials: bool = False) -> dict:
    from .main import app

    create_all()
    rng = random.Random(seed_value)
    with SessionLocal() as db:
        org = ensure_org(db, reset_credentials=reset_credentials)
        tok = issue_token(db.get(User, org["teacher_id"]))  # the seeder acts as the teacher without a PIN
    cid = org["classroom_id"]
    client = client or TestClient(app)
    H = {"Authorization": f"Bearer {tok}"}
    boot = client.get("/v1/bootstrap", headers=H).json()
    items = {i["id"]: i for i in boot["items"]}

    ids: dict[str, str] = {}
    existing = client.get(f"/v1/classrooms/{cid}/children", headers=H).json()
    if existing:
        ids = {p.name: e["id"] for p, e in zip(PERSONAS, existing)}
    else:
        for slot, p in enumerate(PERSONAS, start=1):
            child_id = str(uuid.uuid4())
            client.post(f"/v1/classrooms/{cid}/children", headers=H,
                        json={"id": child_id, "grade": p.grade, "aruco_slot": slot, "consent_status": "granted"})
            ids[p.name] = child_id

    base = datetime.now(UTC) - timedelta(days=7 * weeks)
    for week in range(weeks):
        for p in PERSONAS:
            child_id = ids[p.name]
            for rep in range(2):  # two sessions per week per child
                plan = client.get(f"/v1/children/{child_id}/plan", headers=H).json()
                t0 = base + timedelta(days=7 * week + rep * 3, hours=rng.randint(0, 3))
                responses = []
                for k, it in enumerate(plan.get("items", [])):
                    item = items[it["item_id"]]
                    at = (t0 + timedelta(seconds=10 * k)).isoformat()
                    if item["type"] in TAP_TYPES:
                        chosen = item["answer"]
                        if p.tap_probe:
                            wrong = [o["value"] for o in item["options"] if o.get("probe") == p.tap_probe]
                            if wrong and rng.random() < 0.8:
                                chosen = wrong[0]
                        responses.append({"id": str(uuid.uuid4()), "item_id": item["id"], "modality": "tap",
                                          "payload": {"chosen": chosen}, "created_at": at})
                        continue
                    said = _speak(item.get("text", ""), p, rng)
                    if item["type"] == "repeat":
                        said = item["text"]
                    responses.append({"id": str(uuid.uuid4()), "item_id": item["id"], "modality": "voice",
                                      "payload": {"simulated_utterance": said or "", "duration_ms": 3000},
                                      "created_at": at})
                    for q in (item.get("questions", []) if said else []):  # kiosk skips questions after a silent passage
                        ok = p.fluent or rng.random() < 0.5
                        chosen = q["answer"] if ok else q["options"][-1]["value"]
                        responses.append({"id": str(uuid.uuid4()), "item_id": item["id"], "modality": "tap",
                                          "payload": {"question_id": q["id"], "chosen": chosen}, "created_at": at})
                manifest = {"device_id": "demo-phone", "sessions": [{
                    "id": str(uuid.uuid4()), "child_id": child_id, "classroom_id": cid, "started_at": t0.isoformat(),
                    "ended_at": (t0 + timedelta(minutes=3)).isoformat(), "plan_id": plan.get("plan_id"),
                    "responses": responses}]}
                client.post("/v1/sync", headers=H, data={"manifest": json.dumps(manifest)})
                drain()
        # whole-class slate rounds: 2 per week
        for rnd in range(2):
            today = client.get(f"/v1/classrooms/{cid}/today?force=true", headers=H).json()
            probs = today["slate_problems"]
            entries = []
            for slot, p in enumerate(PERSONAS, start=1):
                answers = []
                for pr in probs:
                    bug = DEFAULT_LIBRARY.get(p.math_bug) if p.math_bug else None
                    ans = bug.apply(pr["a"], pr["b"]) if bug and bug.spec.op == pr["op"] else None
                    if ans is None:
                        ans = str(pr["a"] + pr["b"] if pr["op"] == "+" else pr["a"] - pr["b"])
                    answers.append(ans)
                entries.append((slot, answers))
            for chunk in (entries[:6], entries[6:]):
                photo_id = str(uuid.uuid4())
                img = slate_photo(chunk, probs)
                manifest = {"device_id": "demo-phone", "slate_photos": [{
                    "id": photo_id, "classroom_id": cid, "image_part": "img",
                    "taken_at": (base + timedelta(days=7 * week + 2 + rnd * 2)).isoformat(),
                    "problems": [{"item_id": x["item_id"], "a": x["a"], "b": x["b"], "op": x["op"]} for x in probs]}]}
                client.post("/v1/sync", headers=H, data={"manifest": json.dumps(manifest)},
                            files={"img": ("slates.jpg", img, "image/jpeg")})
                drain()
                answer_of = {slot: answers for slot, answers in chunk}
                for u in client.get(f"/v1/classrooms/{cid}/unsure", headers=H).json():
                    if u["type"] != "slate":
                        continue
                    slot = next(s for s, pp in enumerate(PERSONAS, 1) if ids[pp.name] == u["child_id"])
                    if slot not in answer_of:
                        continue
                    k = [x["item_id"] for x in probs].index(u["item_id"]) if u["item_id"] in [x["item_id"] for x in probs] else 0
                    client.post(f"/v1/responses/{u['id']}/confirm", headers=H, json={"answer": answer_of[slot][k]})
                drain()
    card = client.get(f"/v1/classrooms/{cid}/card?regenerate=true", headers=H).json()
    drain()
    names = {v: k for k, v in ids.items()}
    creds = org["credentials"]
    if verbose:
        print("Seeded classroom", cid)
        print("Card source:", card["source"], "· groups:", [g["group_key"] for g in card["card"]["groups"]])
        if creds:
            save_credentials(creds)
            print(f"\nDemo logins (shown once; also saved to {CREDENTIALS_FILE}; keep it private):")
            for role, c in creds.items():
                print(f"  {role:8s} phone {c['phone']}   PIN {c['pin']}")
        else:
            print(f"\nDemo logins unchanged: see {CREDENTIALS_FILE}, "
                  "or run `python -m app.demo --reset-credentials` for new ones.")
    return {"classroom_id": cid, "children": ids, "names": names, "token": tok, "card": card, "credentials": creds}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="app.demo")
    ap.add_argument("--reset-credentials", action="store_true", help="issue new random phones and PINs")
    seed(reset_credentials=ap.parse_args().reset_credentials)
