"""Human-readable catalog of every misconception id the system can produce."""

from __future__ import annotations

from ..diagnosis.bugs import DEFAULT_LIBRARY

READING = {
    "READ_MLEN": ("Confuses short/long matras (ि/ी, ु/ू)", "Short/long matra confusion", "literacy"),
    "READ_ASP": ("Confuses aspirated sounds (क/ख, ब/भ)", "Aspiration confusion", "literacy"),
    "READ_VIS": ("Confuses look-alike letters (ब/व, घ/ध)", "Look-alike letter confusion", "literacy"),
    "READ_MDROP": ("Reads while ignoring matras", "Ignores matras", "literacy"),
    "READ_MSWAP": ("Confuses the ए/ऐ, ओ/औ matras", "e/ai, o/au matra confusion", "literacy"),
    "READ_NAS": ("Drops bindi/chandrabindu", "Drops nasal marks", "literacy"),
    "READ_CONJ": ("Difficulty reading conjunct letters", "Conjunct decoding difficulty", "literacy"),
}
NUMBER = {
    "NUM_REVERSAL": ("Reverses the digits of a number (47 as 74)", "Reverses digits", "numeracy"),
    "NUM_CONCAT": ("Writes numbers in pieces (205 for twenty-five)", "Concatenates number words", "numeracy"),
    "NUM_ZERO_PLACE": ("Confuses where zero goes (340/304)", "Zero placement confusion", "numeracy"),
    "NUM_UNITS_COMPARE": ("Compares numbers by the units digit", "Compares by units digit", "numeracy"),
}


def describe(mis_id: str) -> dict:
    if mis_id in READING:
        hi, en, dom = READING[mis_id]
        return {"id": mis_id, "description_hi": hi, "description_en": en, "domain": dom, "tags": []}
    if mis_id in NUMBER:
        hi, en, dom = NUMBER[mis_id]
        return {"id": mis_id, "description_hi": hi, "description_en": en, "domain": dom, "tags": []}
    bug = DEFAULT_LIBRARY.get(mis_id)
    if bug:
        return {"id": mis_id, "description_hi": bug.description_en, "description_en": bug.description_en,
                "domain": "numeracy", "tags": [bug.remediation_tag]}
    return {"id": mis_id, "description_hi": mis_id, "description_en": mis_id, "domain": "unknown", "tags": []}


def certainty_hi(mean: float, confirmed: bool) -> str:
    if confirmed:
        return "confirmed" if mean >= 0.75 else "mostly confirmed"
    return "still being checked"
