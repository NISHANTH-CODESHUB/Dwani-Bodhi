from datetime import UTC, date, datetime, timedelta

import pytest

from app.config import get_settings
from app.content.pack import get_pack
from app.demo import slate_photo
from app.diagnosis.verify import verify
from app.learner.bkt import BKTParams, expected_info_gain, learn, posterior, update
from app.learner.levels import assign_level
from app.learner.misconceptions import CONFIRMED, RESOLVED, BetaState
from app.learner.planner import plan_class_slate, plan_session
from app.learner.scheduler import ChildScheduleInput, pick_today
from app.learner.state import LearnerState
from app.llm import card as llm_card
from app.llm.client import LLMUnavailable, cost_usd, parse
from app.vision.slates import detect_and_crop

CP = get_pack(get_settings().content_pack_dir)
G = CP.graph


def fresh(grade=2) -> LearnerState:
    st = LearnerState("c1", grade)
    st.ensure(G)
    return st


def test_bkt_direction_and_soft_evidence():
    p = BKTParams()
    assert posterior(0.5, True, p) > 0.5 > posterior(0.5, False, p)
    assert update(0.5, True, 0.0, p) == pytest.approx(0.5)  # zero-confidence verdict changes nothing
    assert learn(0.2, 4, p) > 0.2
    assert expected_info_gain(0.5, p) > expected_info_gain(0.98, p)


def test_asymmetric_propagation():
    st = fresh()
    before_m8, before_m5 = st.skills["M8"], st.skills["M5"]
    st.observe_skill(G, ["M9"], True, 1.0)
    assert st.skills["M8"] > before_m8 and st.skills["M5"] > before_m5
    st2 = fresh()
    st2.observe_skill(G, ["M9"], False, 1.0, propagate=False)
    assert st2.skills["M8"] == pytest.approx(before_m8)  # failure says nothing about prerequisites


def test_misconception_lifecycle():
    m = BetaState()
    m.observe("reproduced")
    assert m.status != CONFIRMED  # never from a single item
    m.observe("reproduced")
    assert m.status == CONFIRMED
    for _ in range(6):
        m.observe("correct")
    assert m.status == RESOLVED


def test_slate_evidence_updates_bug_and_skill():
    st = fresh()
    for a, b in ((52, 19), (40, 17), (71, 38)):
        st.observe_slate(G, verify(a, b, "-", None if False else str(abs(a % 10 - b % 10) + 10 * (a // 10 - b // 10))).to_dict(), ["M9"])
    assert st.misconceptions["SUB_SMALLER_FROM_LARGER"].status == CONFIRMED
    assert st.skills["M9"] < 0.15


def test_dialect_variant_from_control_item_neutralises_reading_error():
    st = fresh()
    st.observe_reading_word(G, {"status": "ERROR", "rule": "VIS", "detail": "व→ब", "confidence": 0.9}, ["L1"], ["VIS"],
                            control=True)
    st.observe_reading_word(G, {"status": "ERROR", "rule": "VIS", "detail": "व→ब", "confidence": 0.9}, ["L6"], ["VIS"])
    assert "READ_VIS" not in st.misconceptions or st.misconceptions["READ_VIS"].hits == 0


def test_levels_and_uncertainty():
    st = fresh()
    for s in st.skills:
        st.skills[s] = 0.95
    lv = assign_level(G, st.skills, "literacy")
    assert lv.rung_id == "story" and lv.certain
    st.skills["L10"] = 0.5
    lv = assign_level(G, st.skills, "literacy")
    assert lv.rung_id == "paragraph" and not lv.certain and "L10" in lv.blocking_skills


def test_scheduler_respects_budget_and_consent():
    kids = [ChildScheduleInput(f"c{i}", {"L7": 0.5}, ["L7"], None if i < 3 else date(2026, 10, 1), False, i != 0)
            for i in range(10)]
    chosen = pick_today(kids, date(2026, 10, 17), budget_minutes=10, avg_session_minutes=2.5)
    assert len(chosen) == 4 and "c0" not in {c.child_id for c in chosen}
    assert {"c1", "c2"} <= {c.child_id for c in chosen}  # never-assessed first


def test_plan_session_budget_and_blocks():
    st = fresh(1)
    plan = plan_session(st, CP, today=date(2026, 10, 17), seed=1)
    assert plan.items and plan.est_seconds <= 150 + 10
    assert plan.items[-1].block == "closing" or all(i.block != "closing" for i in plan.items)
    assert len({i.item_id for i in plan.items}) == len(plan.items)
    recent = {i.item_id: date(2026, 10, 16) for i in plan.items}
    plan2 = plan_session(st, CP, last_seen=recent, today=date(2026, 10, 17), seed=1)
    assert not ({i.item_id for i in plan2.items if i.block != "closing"} & set(recent))


def test_class_slate_selection_returns_discriminating_items():
    probs = plan_class_slate([fresh(2), fresh(2)], CP, n=2)
    assert len(probs) == 2 and all(p["op"] in "+-" for p in probs)


def test_slate_photo_crops_by_aruco_marker():
    img = slate_photo([(3, ["47", "75"]), (7, ["33", "85"]), (12, ["40", "9"])],
                      [{"a": 52, "b": 19, "op": "-"}, {"a": 47, "b": 38, "op": "+"}])
    crops, meta = detect_and_crop(img)
    assert meta["markers"] == 3
    assert [c.marker_id for c in crops] == [3, 7, 12]
    assert all(c.jpeg[:2] == b"\xff\xd8" and c.width > 400 for c in crops)


def test_llm_offline_raises_and_cost_math():
    from app.db import SessionLocal, create_all
    create_all()
    with SessionLocal() as db, pytest.raises(LLMUnavailable):
        parse(db, purpose="t", model="claude-haiku-5-5", system="x", content="y", output_format=llm_card.CardOut)
    # Sonnet slate call from the guide: 700 in, 400 out, 1500 cache-read ≈ $0.0057
    assert cost_usd("claude-sonnet-5-5", 700, 400, cache_read=1500) == pytest.approx(0.0057, abs=1e-4)
    assert cost_usd("claude-sonnet-5-5", 700, 400, cache_read=1500, batch=True) == pytest.approx(0.00285, abs=1e-4)


def test_card_validator_rejects_invented_activity():
    summary = {"groups": [{"key": "literacy:word", "candidate_activities": ["lit.chhoti_badi_taali"]}]}
    good = llm_card.CardOut(headline_hi="h", teacher_tip_hi="t", groups=[llm_card.CardGroup(
        group_key="literacy:word", activity_id="lit.chhoti_badi_taali", title_hi="x", why_hi="y",
        steps_hi=["a", "b", "c"], example_items=[])])
    assert llm_card.validate(good, summary, CP.activities) == []
    bad = good.model_copy(deep=True)
    bad.groups[0].activity_id = "lit.made_up"
    assert any("invented" in e for e in llm_card.validate(bad, summary, CP.activities))


def test_advance_time_learning_transition():
    st = fresh()
    st.last_updated = datetime.now(UTC) - timedelta(weeks=4)
    p0 = st.skills["L7"]
    st.advance_time(datetime.now(UTC))
    assert st.skills["L7"] > p0


def test_guessable_taps_do_not_propagate_to_prerequisites():
    st = fresh()
    before = {s: st.skills[s] for s in ("L9", "L7", "L3")}
    st.observe_tap(G, ["L11"], True)  # a lucky comprehension guess
    assert all(st.skills[s] == pytest.approx(before[s]) for s in before)
    assert st.skills["L11"] > fresh().skills["L11"]


def test_tap_distractor_picks_never_confirm_a_misconception():
    # A tapped distractor may be a 1-in-4 guess: weak evidence can raise "suspected", never "confirmed".
    st = fresh()
    for _ in range(6):
        st.observe_tap(G, ["M2"], False, "NUM_REVERSAL")
    assert st.misconceptions["NUM_REVERSAL"].status != CONFIRMED


def test_unprobed_reading_errors_stay_unconfirmed_until_teacher_confirms():
    st = fresh()
    err = {"status": "ERROR", "rule": "CONJ", "confidence": 0.9}
    for _ in range(5):
        st.observe_reading_word(G, err, ["L6"], ["MLEN"])  # item designed for MLEN, not CONJ
    assert st.misconceptions["READ_CONJ"].status != CONFIRMED
    for _ in range(2):  # a teacher listened and confirmed the CONJ error twice → verified evidence
        st.observe_reading_word(G, {**err, "confidence": 1.0, "teacher_confirmed": True}, ["L6"], ["MLEN"])
    assert st.misconceptions["READ_CONJ"].status == CONFIRMED


def test_card_wording_hedges_suspected_confusions():
    from app.services.cards import why_hi
    t = {"n_children": 3, "n_confirmed": 0, "n_suspected": 3, "description_hi": "a confusion"}
    assert "Possibly" in why_hi(t) and "Confirmed" not in why_hi(t)
    assert "Confirmed" in why_hi({**t, "n_confirmed": 2, "n_suspected": 1})
    summary = {"groups": [{"key": "literacy:akshara", "candidate_activities": ["x"],
                           "top_confusions": [t]}]}
    out = llm_card.CardOut(headline_hi="h", teacher_tip_hi="t", groups=[llm_card.CardGroup(
        group_key="literacy:akshara", activity_id="x", title_hi="t", why_hi="3 बच्चे ी को ि पढ़ते हैं",
        steps_hi=["a", "b"], example_items=[])])
    errs = llm_card.validate(out, summary, {"x": object()})
    assert any("suspected" in e for e in errs)


def test_llm_schema_failure_falls_back_instead_of_crashing(monkeypatch):
    from pydantic import ValidationError

    from app.db import SessionLocal
    from app.llm import client as llm_client
    from app.models import LLMCall
    try:
        llm_card.CardOut.model_validate({})
    except ValidationError as e:
        err = e

    class Boom:
        class messages:
            @staticmethod
            def parse(**_):
                raise err

    monkeypatch.setattr(get_settings(), "llm_mode", "live")
    monkeypatch.setattr(llm_client, "_sdk", lambda: Boom)
    with SessionLocal() as db:
        with pytest.raises(LLMUnavailable):
            parse(db, purpose="test_fallback", model="claude-opus-5-5", system="s", content="c",
                  output_format=llm_card.CardOut)
        logged = db.query(LLMCall).filter(LLMCall.purpose == "test_fallback").one()
        assert not logged.ok and "ValidationError" in logged.error


def test_approved_discovered_bug_joins_library_and_diagnoses():
    from app.db import SessionLocal
    from app.diagnosis.bugs import BugLibrary
    from app.models import BugProposal
    from app.services.discovery import load_approved_bugs
    lib = BugLibrary()
    spec = {"op": "-", "column": "abs_diff", "align": "left"}  # a combination not in the MVP library
    with SessionLocal() as db:
        bp = BugProposal(spec=spec, description="left-aligned smaller-from-larger | बाएँ से मिलाकर छोटा घटाना",
                         explains=[], status="approved")
        db.add(bp)
        db.commit()
        assert load_approved_bugs(db, lib) >= 1
        bug = lib.get(f"DISC_{bp.id[:8].upper()}")
        assert bug and bug.description_hi.startswith("बाएँ")
        assert load_approved_bugs(db, lib) == 0  # idempotent
        db.delete(bp)
        db.commit()


@pytest.mark.parametrize("pin", ["1234", "123456", "654321", "890123", "111111", "121212", "112233", "123123",
                                 "abcdef", "12345678901234", "786786"])
def test_weak_pins_rejected(pin):
    from app.security import pin_problem
    assert pin_problem(pin) is not None


def test_pin_policy_accepts_random_and_rejects_phone_digits():
    from app.security import generate_pin, pin_problem
    assert all(pin_problem(generate_pin()) is None for _ in range(200))
    assert pin_problem("580317") is None
    assert pin_problem("456789", phone="9123456789") is not None  # last six digits of the phone
