"""Devanagari text utilities: normalisation and akshara (orthographic syllable) segmentation.

All text entering the scoring pipeline goes through `normalize` so that candidate strings and
model vocabularies agree (NFC; precomposed nukta letters decomposed to base + U+093C).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

VIRAMA = "्"  # ्
NUKTA = "़"  # ़
ANUSVARA = "ं"  # ं
CHANDRABINDU = "ँ"  # ँ
VISARGA = "ः"  # ः

CONSONANTS = set("कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसह")
INDEPENDENT_VOWELS = set("अआइईउऊऋएऐओऔऑ")
MATRAS = set("ािीुूृेैोौॉ")  # ा ि ी ु ू ृ े ै ो ौ ॉ
NASALS = {ANUSVARA, CHANDRABINDU}

# Precomposed nukta letters (U+0958–U+095F) are composition exclusions: NFC leaves them
# decomposed, but some inputs carry them precomposed. Map explicitly to be safe.
_PRECOMPOSED_NUKTA = {
    "क़": "क़", "ख़": "ख़", "ग़": "ग़", "ज़": "ज़",
    "ड़": "ड़", "ढ़": "ढ़", "फ़": "फ़", "य़": "य़",
}

_CONS = "".join(sorted(CONSONANTS))
_VOW = "".join(sorted(INDEPENDENT_VOWELS))
_MAT = "".join(sorted(MATRAS))
_AKSHARA_RE = re.compile(
    rf"(?:[{_CONS}]{NUKTA}?{VIRAMA})*[{_CONS}]{NUKTA}?(?:[{_MAT}]|{VIRAMA})?[{ANUSVARA}{CHANDRABINDU}{VISARGA}]?"
    rf"|[{_VOW}][{ANUSVARA}{CHANDRABINDU}{VISARGA}]?"
    rf"|\S"
)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    for pre, dec in _PRECOMPOSED_NUKTA.items():
        text = text.replace(pre, dec)
    return " ".join(text.split())


@dataclass(frozen=True)
class Akshara:
    text: str
    start: int  # codepoint offset in the normalised word
    end: int

    @property
    def matra(self) -> str | None:
        for ch in self.text:
            if ch in MATRAS:
                return ch
        return None

    @property
    def is_conjunct(self) -> bool:
        return VIRAMA in self.text[:-1]

    @property
    def base_consonants(self) -> list[str]:
        return [ch for ch in self.text if ch in CONSONANTS]


def aksharas(word: str) -> list[Akshara]:
    word = normalize(word)
    return [Akshara(m.group(0), m.start(), m.end()) for m in _AKSHARA_RE.finditer(word) if not m.group(0).isspace()]


_PUNCT = re.compile(r"[।॥,.;:!?\"'()\[\]“”‘’]")


def words(text: str) -> list[str]:
    """Split connected text into readable words: punctuation (incl. danda) dropped, hyphens split."""
    text = _PUNCT.sub(" ", normalize(text).replace("-", " "))
    return [w for w in text.split() if w]


def is_devanagari_word(word: str) -> bool:
    return bool(word) and all("ऀ" <= ch <= "ॿ" for ch in word)
