"""Confusion-lattice candidate generation for ECCL (guide §6.1.2).

Given a target word, produce the correct reading plus pedagogically meaningful mis-readings.
Each candidate carries the rule that produced it, so the error type is known by construction.
Rule tables are data (see `RuleTables`) so other Indic scripts can plug in their own.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .devanagari import ANUSVARA, CHANDRABINDU, VIRAMA, aksharas, normalize


@dataclass(frozen=True)
class Candidate:
    text: str
    rule: str | None = None  # None = the correct reading
    site: int | None = None  # akshara index where the mutation applies
    detail: str = ""  # e.g. "ी→ि"

    @property
    def is_target(self) -> bool:
        return self.rule is None


def _pairs(*pairs: tuple[str, str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for a, b in pairs:
        out.setdefault(a, []).append(b)
        out.setdefault(b, []).append(a)
    return out


@dataclass(frozen=True)
class RuleTables:
    aspiration: dict[str, list[str]] = field(default_factory=lambda: _pairs(
        ("क", "ख"), ("ग", "घ"), ("च", "छ"), ("ज", "झ"), ("ट", "ठ"),
        ("ड", "ढ"), ("त", "थ"), ("द", "ध"), ("प", "फ"), ("ब", "भ"),
    ))
    matra_length: dict[str, list[str]] = field(default_factory=lambda: _pairs(
        ("ि", "ी"), ("ु", "ू"), ("इ", "ई"), ("उ", "ऊ"),
    ))
    matra_swap: dict[str, list[str]] = field(default_factory=lambda: _pairs(
        ("े", "ै"), ("ो", "ौ"), ("ए", "ऐ"), ("ओ", "औ"),
    ))
    visual: dict[str, list[str]] = field(default_factory=lambda: {
        "ब": ["व"], "व": ["ब"], "घ": ["ध"], "ध": ["घ"], "म": ["भ"], "भ": ["म"],
        "थ": ["य"], "य": ["थ"], "प": ["ष"], "ष": ["प"], "ख": ["रव"],
    })


DEFAULT_TABLES = RuleTables()

RULES = ("ASP", "MLEN", "MDROP", "MSWAP", "VIS", "NAS", "CONJ")


def _replace_in_akshara(word: str, ak_start: int, ak_end: int, old: str, new: str) -> str | None:
    seg = word[ak_start:ak_end]
    idx = seg.find(old)
    if idx < 0:
        return None
    return word[:ak_start] + seg[:idx] + new + seg[idx + len(old):] + word[ak_end:]


def generate_candidates(
    target: str,
    tables: RuleTables = DEFAULT_TABLES,
    rules: tuple[str, ...] = RULES,
    extra: list[Candidate] | None = None,
    max_candidates: int = 40,
) -> list[Candidate]:
    """Correct reading first, then unique single-site mutations (and any `extra`, e.g. dialect variants)."""
    word = normalize(target)
    out: list[Candidate] = [Candidate(word)]
    seen = {word}

    def add(text: str | None, rule: str, site: int, detail: str) -> None:
        if text and text not in seen and len(out) < max_candidates:
            seen.add(text)
            out.append(Candidate(text, rule, site, detail))

    # Tolerated (dialect) variants go first so an identical-looking error mutation never shadows them.
    for c in extra or []:
        add(normalize(c.text), c.rule or "DIALECT", c.site if c.site is not None else -1, c.detail)

    for i, ak in enumerate(aksharas(word)):
        s, e, t = ak.start, ak.end, ak.text
        if "ASP" in rules:
            for ch in ak.base_consonants:
                for alt in tables.aspiration.get(ch, []):
                    add(_replace_in_akshara(word, s, e, ch, alt), "ASP", i, f"{ch}→{alt}")
        if "VIS" in rules:
            for ch in ak.base_consonants:
                for alt in tables.visual.get(ch, []):
                    add(_replace_in_akshara(word, s, e, ch, alt), "VIS", i, f"{ch}→{alt}")
        m = ak.matra
        first = t[0]
        if "MLEN" in rules:
            for src in ([m] if m else []) + ([first] if first in tables.matra_length and not m else []):
                for alt in tables.matra_length.get(src, []):
                    add(_replace_in_akshara(word, s, e, src, alt), "MLEN", i, f"{src}→{alt}")
        if "MSWAP" in rules:
            for src in ([m] if m else []) + ([first] if first in tables.matra_swap and not m else []):
                for alt in tables.matra_swap.get(src, []):
                    add(_replace_in_akshara(word, s, e, src, alt), "MSWAP", i, f"{src}→{alt}")
        if "MDROP" in rules and m:
            add(_replace_in_akshara(word, s, e, m, ""), "MDROP", i, f"{m}→∅")
        if "NAS" in rules:
            for nas in (ANUSVARA, CHANDRABINDU):
                if nas in t:
                    add(_replace_in_akshara(word, s, e, nas, ""), "NAS", i, f"{nas}→∅")
        if "CONJ" in rules and ak.is_conjunct:
            cons = ak.base_consonants
            # split with inherent vowel (प्या→पया), epenthetic i (प्या→पिया), drop first / second consonant
            add(_replace_in_akshara(word, s, e, VIRAMA, ""), "CONJ", i, "split")
            add(_replace_in_akshara(word, s, e, VIRAMA, "ि"), "CONJ", i, "split+ि")
            if len(cons) >= 2:
                add(_replace_in_akshara(word, s, e, cons[0] + VIRAMA, ""), "CONJ", i, f"drop {cons[0]}")
                add(_replace_in_akshara(word, s, e, VIRAMA + cons[1], ""), "CONJ", i, f"drop {cons[1]}")

    return out
