"""Assessment-design rules: EGMA tap tasks, pack validation of tap items, practice examples, stop rules."""

from datetime import date

from app.config import get_settings
from app.content.pack import get_pack
from app.content.schema import TAP_TYPES, Item, Option
from app.learner.planner import plan_session
from app.learner.state import LearnerState
from app.models import Response
from app.services.scoring import score_tap

CP = get_pack(get_settings().content_pack_dir)


def fresh(grade: int) -> LearnerState:
    st = LearnerState(child_id=f"t{grade}", grade=grade)
    st.ensure(CP.graph)
    return st


def test_pack_has_counting_and_missing_number_tasks_that_validate():
    assert not CP.validate()
    for t in ("tap_count", "tap_missing"):
        items = CP.items_of(t)
        assert len(items) >= 8, t
        for it in items:
            assert it.text and it.prompt_hi and it.answer in [o.value for o in it.options]


def test_validation_rejects_broken_tap_items():
    bad = Item(id="x.bad", type="tap_count", skills=["M1"], prompt_hi="How many?", answer="9",
               options=[Option(value="3"), Option(value="3")])
    CP.items[bad.id] = bad
    try:
        errs = " ".join(CP.validate())
    finally:
        del CP.items[bad.id]
    assert "answer must be one of the options" in errs
    assert "duplicate option values" in errs
    assert "needs text" in errs


def test_maths_block_draws_from_all_tap_tasks_and_sends_stop_rule():
    seen: set[str] = set()
    for seed in range(12):
        plan = plan_session(fresh(1), CP, today=date(2026, 10, 24), seed=seed)
        maths = [i for i in plan.items if i.block == "numeracy"]
        assert maths and all(i.type in TAP_TYPES for i in maths)
        seen |= {i.type for i in maths}
        assert plan.rules["stop_block_after_silent"] == 3
    assert {"tap_count", "tap_missing"} & seen  # the new EGMA tasks are actually chosen


def test_new_tap_tasks_score_and_reveal_misconception_probes():
    it = CP.items["m.count.12"]
    right = Response(id="r1", item_id=it.id, payload={"chosen": "12"})
    score_tap(right)
    assert right.verdict["correct"] is True and right.status == "scored"
    wrong = Response(id="r2", item_id=it.id, payload={"chosen": "21"})
    score_tap(wrong)
    assert wrong.verdict == {"correct": False, "chosen": "21", "probe": "NUM_REVERSAL"}


def test_practice_examples_are_never_test_items():
    texts = {i.text for i in CP.items.values() if i.text}
    for t in ("akshara", "word", "nonword"):
        ex = CP.prompts.get(f"example_{t}")
        assert ex and ex not in texts, t
