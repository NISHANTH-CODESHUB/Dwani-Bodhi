import pytest

from app.diagnosis.bugs import DEFAULT_LIBRARY
from app.diagnosis.itemgen import SPACES, analyse, generate, needs_regroup
from app.diagnosis.procedures import ProcedureSpec, execute
from app.diagnosis.verify import BUG, CORRECT, SLIP, UNEXPLAINED, is_slip, normalize_answer, verify


def ans(bug_id: str, a: int, b: int) -> str | None:
    return DEFAULT_LIBRARY.get(bug_id).apply(a, b)


@pytest.mark.parametrize("bug,a,b,expected", [
    ("SUB_SMALLER_FROM_LARGER", 52, 19, "47"),
    ("SUB_BORROW_NO_DECREMENT", 52, 19, "43"),
    ("OP_SWAP_SUB", 52, 19, "71"),
    ("SUB_ZERO_MINUS_N_IS_ZERO", 40, 17, "30"),
    ("SUB_ZERO_MINUS_N_IS_N", 40, 17, "37"),
    ("SUB_BORROW_NO_DECREMENT", 40, 17, "33"),
    ("SUB_BORROW_ACROSS_ZERO", 302, 147, "255"),
    ("SUB_ALWAYS_BORROW", 57, 23, "214"),
    ("ADD_NO_CARRY", 47, 38, "75"),
    ("ADD_CARRY_WRITE_BOTH", 47, 38, "715"),
    ("ADD_LEFT_ALIGN", 52, 7, "122"),
    ("ADD_ALL_DIGITS", 23, 14, "10"),
    ("ANSWER_REVERSED_ADD", 47, 25, "27"),
])
def test_bug_library_matches_guide_examples(bug, a, b, expected):
    assert ans(bug, a, b) == expected


def test_correct_procedures():
    assert execute(ProcedureSpec(op="-"), 52, 19) == "33"
    assert execute(ProcedureSpec(op="-"), 302, 147) == "155"
    assert execute(ProcedureSpec(op="-"), 1000, 1) == "999"
    assert execute(ProcedureSpec(op="+"), 999, 1) == "1000"
    assert execute(ProcedureSpec(op="-"), 19, 52) is None


def test_not_applicable_returns_none():
    assert ans("ADD_LEFT_ALIGN", 52, 17) is None  # same length: cannot misalign
    assert ans("ANSWER_REVERSED_ADD", 3, 4) is None  # single digit


def test_verify_statuses():
    v = verify(52, 19, "-", "47")
    assert v.status == BUG and v.matching_bugs == ["SUB_SMALLER_FROM_LARGER"]
    assert "SUB_BORROW_NO_DECREMENT" in v.discriminable_bugs
    assert verify(52, 19, "-", "33").status == CORRECT
    assert verify(47, 38, "+", "86").status == SLIP
    assert verify(52, 19, "-", "12").status == UNEXPLAINED
    assert verify(52, 19, "-", "४७").status == BUG  # Devanagari digits
    assert verify(52, 19, "-", "").status == "BLANK"
    assert verify(52, 19, "-", "4?").status == "ILLEGIBLE"


def test_slip_and_normalize():
    assert is_slip("84", "85") and not is_slip("85", "85") and not is_slip("65", "85")
    # a dropped carry looks like a slip, but verify() checks bugs first
    assert is_slip("75", "85") and verify(47, 38, "+", "75").status == BUG
    assert normalize_answer(" 047 ") == "47"
    assert normalize_answer("0") == "0"


def test_63_minus_8_collides_sfl_bnd():
    item = analyse(63, 8, "-", ("SUB_SMALLER_FROM_LARGER", "SUB_BORROW_NO_DECREMENT"))
    assert item.collisions  # both predict 65 → not discriminating (guide §6.3.1)


def test_regroup_detection():
    assert needs_regroup(52, 19, "-") and not needs_regroup(57, 23, "-")
    assert needs_regroup(47, 38, "+") and not needs_regroup(23, 14, "+")


@pytest.mark.parametrize("skill", list(SPACES))
def test_generated_items_are_discriminating(skill):
    items = generate(skill, n=8)
    assert len(items) >= 4
    for it in items:
        assert not it.collisions
        preds = list(it.signature.values())
        assert len(preds) == len(set(preds))
        assert it.correct not in preds
        assert needs_regroup(it.a, it.b, it.op) == SPACES[skill].regroup
