"""A small, safe grammar of column-arithmetic procedures (correct and buggy) — guide §6.2.

Every bug in the library is a `ProcedureSpec`; Claude's hypotheses for unexplained answers must
also be expressed in this grammar (never free code), so they can be executed and verified.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

Op = Literal["+", "-"]


class ProcedureSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    op: Op
    # subtraction column behaviour
    column: Literal["standard", "abs_diff"] = "standard"
    borrow: Literal["standard", "no_decrement", "always"] = "standard"
    zero_top: Literal["standard", "write_zero", "write_bottom"] = "standard"
    borrow_across_zero: Literal["standard", "nine_no_propagate"] = "standard"
    # addition column behaviour
    carry: Literal["standard", "drop", "write_both"] = "standard"
    # layout / whole-answer behaviours
    align: Literal["right", "left"] = "right"
    special: Literal["none", "op_swap", "all_digits_sum", "reverse_answer"] = "none"


def _digits(n: int) -> list[int]:
    return [int(c) for c in reversed(str(n))]


def _join(cols: list[str]) -> str:
    s = "".join(reversed(cols)).lstrip("0")
    return s or "0"


def correct_answer(a: int, b: int, op: Op) -> int | None:
    if op == "+":
        return a + b
    return a - b if a >= b else None


def execute(spec: ProcedureSpec, a: int, b: int) -> str | None:
    """Run the procedure on a (top) and b (bottom). Returns the written answer or None if the
    procedure cannot be applied (e.g. would need a negative final column)."""
    if a < 0 or b < 0:
        return None
    if spec.special == "op_swap":
        if spec.op == "+":
            return str(abs(a - b))
        return str(a + b)
    if spec.special == "all_digits_sum":
        return str(sum(_digits(a)) + sum(_digits(b))) if spec.op == "+" else None
    if spec.special == "reverse_answer":
        c = correct_answer(a, b, spec.op)
        if c is None or c < 10:
            return None
        r = str(c)[::-1].lstrip("0") or "0"
        return r if r != str(c) else None

    if spec.align == "left":
        la, lb = len(str(a)), len(str(b))
        if la == lb:
            return None  # not applicable — no misalignment possible
        if la > lb:
            b = b * 10 ** (la - lb)
        else:
            a = a * 10 ** (lb - la)
    return _add(spec, a, b) if spec.op == "+" else _sub(spec, a, b)


def _add(spec: ProcedureSpec, a: int, b: int) -> str:
    ta, tb = _digits(a), _digits(b)
    n = max(len(ta), len(tb))
    ta += [0] * (n - len(ta))
    tb += [0] * (n - len(tb))
    cols: list[str] = []
    carry = 0
    for i in range(n):
        s = ta[i] + tb[i] + carry
        last = i == n - 1
        if spec.carry == "standard":
            cols.append(str(s % 10))
            carry = s // 10
        elif spec.carry == "drop":
            cols.append(str(s) if last else str(s % 10))
            carry = 0
        else:  # write_both: the whole column sum is written in place
            cols.append(str(s))
            carry = 0
    if carry:
        cols.append(str(carry))
    # multi-digit column strings are written left-to-right as the child writes them
    return "".join(reversed(cols)).lstrip("0") or "0"


def _sub(spec: ProcedureSpec, a: int, b: int) -> str | None:
    ta, tb = _digits(a), _digits(b)
    if len(tb) > len(ta):
        return None
    tb += [0] * (len(ta) - len(tb))
    n = len(ta)
    cols: list[str] = []
    dec = 0  # decrement owed to the current column by a borrow from the right
    for i in range(n):
        top, bot = ta[i], tb[i]
        last = i == n - 1
        if spec.borrow == "no_decrement":
            dec = 0
        # borrow-across-zero bug: a zero that must lend becomes 9 but does not pass the borrow on
        if dec and top == 0 and spec.borrow_across_zero == "nine_no_propagate":
            top_eff, next_dec_override = 9, 0
        else:
            top_eff, next_dec_override = top - dec, None
        if top == 0 and dec == 0 and bot > 0 and spec.zero_top != "standard":
            cols.append("0" if spec.zero_top == "write_zero" else str(bot))
            dec = 0
            continue
        if spec.column == "abs_diff":
            cols.append(str(abs(top_eff - bot)))
            dec = 0 if next_dec_override is None else next_dec_override
            continue
        if spec.borrow == "always" and not last:
            cols.append(str(top_eff + 10 - bot))
            dec = 1 if next_dec_override is None else next_dec_override
            continue
        if top_eff < bot:
            if last:
                return None
            cols.append(str(top_eff + 10 - bot))
            dec = 1 if next_dec_override is None else next_dec_override
        else:
            cols.append(str(top_eff - bot))
            dec = 0 if next_dec_override is None else next_dec_override
    return _join(cols)
