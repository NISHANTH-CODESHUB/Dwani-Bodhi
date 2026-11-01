"""Dialect tolerance profiles (guide §6.1.5).

A profile lists substitutions that are features of a child's spoken variety, not reading errors.
Variants generated from a profile enter the lattice with rule "DIALECT" and are scored as correct.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .devanagari import VIRAMA, normalize
from .mutations import Candidate


@dataclass(frozen=True)
class RegionProfile:
    id: str = "standard"
    name: str = "Standard (no dialect tolerance)"
    substitutions: tuple[tuple[str, str], ...] = ()
    prothesis: bool = False  # स्कूल → इस्कूल
    notes: str = ""

    def variants(self, word: str) -> list[Candidate]:
        word = normalize(word)
        out: list[Candidate] = []
        for src, dst in self.substitutions:
            start = 0
            while (idx := word.find(src, start)) >= 0:
                out.append(Candidate(word[:idx] + dst + word[idx + len(src):], "DIALECT", -1, f"{src}→{dst}"))
                start = idx + 1
            if src in word and word.count(src) > 1:
                out.append(Candidate(word.replace(src, dst), "DIALECT", -1, f"{src}→{dst} (all)"))
        if self.prothesis and len(word) > 2 and word[0] in "सश" and word[1] == VIRAMA:
            out.append(Candidate("इ" + word, "DIALECT", 0, "prothesis इ"))
        return out


STANDARD = RegionProfile()


def load_profile(path: Path) -> RegionProfile:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    subs = tuple((normalize(s["from"]), normalize(s["to"])) for s in data.get("tolerate", []))
    return RegionProfile(
        id=data["id"], name=data.get("name", data["id"]), substitutions=subs,
        prothesis=bool(data.get("prothesis", False)), notes=data.get("notes", ""),
    )


@dataclass
class ProfileRegistry:
    profiles: dict[str, RegionProfile] = field(default_factory=lambda: {"standard": STANDARD})

    def get(self, profile_id: str | None) -> RegionProfile:
        return self.profiles.get(profile_id or "standard", STANDARD)

    @classmethod
    def from_dir(cls, directory: Path) -> ProfileRegistry:
        reg = cls()
        if directory.exists():
            for p in sorted(directory.glob("*.yaml")):
                prof = load_profile(p)
                reg.profiles[prof.id] = prof
        return reg
