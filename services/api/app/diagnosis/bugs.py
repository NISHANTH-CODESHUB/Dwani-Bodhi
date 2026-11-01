"""The MVP bug library (guide §6.2.3). Each bug = a ProcedureSpec + metadata.

Sources: Brown & Burton (1978); VanLehn (1990). Teachers see the English description (`description_en`).
New bugs (from the discovery loop) are appended at runtime from the database via `BugLibrary.add`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .procedures import ProcedureSpec, execute


@dataclass(frozen=True)
class Bug:
    id: str
    spec: ProcedureSpec
    skill_ids: tuple[str, ...]
    description_en: str
    description_hi: str
    remediation_tag: str  # links to activities that target this bug

    def apply(self, a: int, b: int) -> str | None:
        return execute(self.spec, a, b)


S = ProcedureSpec

DEFAULT_BUGS: tuple[Bug, ...] = (
    Bug("SUB_SMALLER_FROM_LARGER", S(op="-", column="abs_diff"), ("M9", "M5"),
        "In every column subtracts the smaller digit from the larger.",
        "हर खाने में बड़े अंक में से छोटा अंक घटाता है (उधार नहीं लेता)।", "borrow_concept"),
    Bug("SUB_BORROW_NO_DECREMENT", S(op="-", borrow="no_decrement"), ("M9",),
        "Borrows 10 but does not reduce the next column.",
        "उधार लेता है पर अगले खाने का अंक एक कम नहीं करता।", "borrow_procedure"),
    Bug("SUB_ZERO_MINUS_N_IS_ZERO", S(op="-", zero_top="write_zero"), ("M9",),
        "Writes 0 when the top digit is 0.",
        "ऊपर 0 होने पर उत्तर में 0 लिख देता है।", "zero_in_subtraction"),
    Bug("SUB_ZERO_MINUS_N_IS_N", S(op="-", zero_top="write_bottom"), ("M9",),
        "Writes the bottom digit when the top digit is 0.",
        "ऊपर 0 होने पर नीचे वाला अंक लिख देता है।", "zero_in_subtraction"),
    Bug("SUB_BORROW_ACROSS_ZERO", S(op="-", borrow_across_zero="nine_no_propagate"), ("M10", "M9"),
        "When borrowing across a zero, turns 0 into 9 but does not reduce the next column.",
        "शून्य के पार उधार लेते समय 0 को 9 तो करता है पर आगे का अंक कम नहीं करता।", "borrow_procedure"),
    Bug("SUB_ALWAYS_BORROW", S(op="-", borrow="always"), ("M9", "M8"),
        "Borrows in every column even when it is not needed.",
        "ज़रूरत न होने पर भी हर खाने में उधार लेता है।", "borrow_concept"),
    Bug("ADD_NO_CARRY", S(op="+", carry="drop"), ("M7", "M5"),
        "Drops the carry.",
        "हासिल (carry) को आगे नहीं ले जाता।", "carry_concept"),
    Bug("ADD_CARRY_WRITE_BOTH", S(op="+", carry="write_both"), ("M7", "M5"),
        "Writes the whole column sum instead of carrying.",
        "खाने का पूरा जोड़ (जैसे 15) वहीं लिख देता है, हासिल नहीं ले जाता।", "carry_concept"),
    Bug("ADD_LEFT_ALIGN", S(op="+", align="left"), ("M5", "M6"),
        "Lines numbers up from the left instead of the right.",
        "संख्याओं को बाईं ओर से मिलाकर लिखता है (इकाई-दहाई गलत)।", "place_value"),
    Bug("OP_SWAP_SUB", S(op="-", special="op_swap"), ("M8",),
        "Adds instead of subtracting.",
        "घटाने की जगह जोड़ देता है।", "operation_meaning"),
    Bug("OP_SWAP_ADD", S(op="+", special="op_swap"), ("M6",),
        "Subtracts instead of adding.",
        "जोड़ने की जगह घटा देता है।", "operation_meaning"),
    Bug("ADD_ALL_DIGITS", S(op="+", special="all_digits_sum"), ("M5", "M6"),
        "Adds all digits together, ignoring place value.",
        "सभी अंकों को एक साथ जोड़ देता है (स्थानीय मान नहीं समझता)।", "place_value"),
    Bug("ANSWER_REVERSED_ADD", S(op="+", special="reverse_answer"), ("M2", "M5"),
        "Writes the answer's digits in reverse order.",
        "उत्तर के अंक उल्टे क्रम में लिखता है।", "number_writing"),
    Bug("ANSWER_REVERSED_SUB", S(op="-", special="reverse_answer"), ("M2", "M5"),
        "Writes the answer's digits in reverse order.",
        "उत्तर के अंक उल्टे क्रम में लिखता है।", "number_writing"),
)


@dataclass
class BugLibrary:
    bugs: dict[str, Bug] = field(default_factory=lambda: {b.id: b for b in DEFAULT_BUGS})

    def for_op(self, op: str) -> list[Bug]:
        return [b for b in self.bugs.values() if b.spec.op == op]

    def add(self, bug: Bug) -> None:
        self.bugs[bug.id] = bug

    def get(self, bug_id: str) -> Bug | None:
        return self.bugs.get(bug_id)


DEFAULT_LIBRARY = BugLibrary()
