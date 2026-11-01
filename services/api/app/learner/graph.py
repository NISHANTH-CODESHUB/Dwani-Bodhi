"""Skill graph and TaRL ladders, loaded from the content pack (`skills.yaml`)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Skill:
    id: str
    domain: str  # literacy | numeracy
    name_en: str
    name_hi: str
    prereqs: tuple[str, ...] = ()
    nipun: str = ""
    grade_prior: dict[int, float] = field(default_factory=dict)  # grade -> P(L0)
    weight: float = 1.0

    def prior(self, grade: int) -> float:
        if not self.grade_prior:
            return 0.3
        if grade in self.grade_prior:
            return self.grade_prior[grade]
        nearest = min(self.grade_prior, key=lambda g: abs(g - grade))
        return self.grade_prior[nearest]


@dataclass(frozen=True)
class Rung:
    id: str
    name_en: str
    name_hi: str
    skills: tuple[str, ...]  # all must be mastered to sit at this rung


@dataclass
class SkillGraph:
    skills: dict[str, Skill]
    ladders: dict[str, list[Rung]]  # domain -> ordered rungs (lowest first)

    def ancestors(self, skill_id: str) -> set[str]:
        out: set[str] = set()
        stack = list(self.skills[skill_id].prereqs) if skill_id in self.skills else []
        while stack:
            s = stack.pop()
            if s not in out and s in self.skills:
                out.add(s)
                stack.extend(self.skills[s].prereqs)
        return out

    def validate(self) -> list[str]:
        errors = []
        for s in self.skills.values():
            for p in s.prereqs:
                if p not in self.skills:
                    errors.append(f"{s.id}: unknown prereq {p}")
            if s.id in self.ancestors(s.id):
                errors.append(f"{s.id}: cycle")
        for dom, rungs in self.ladders.items():
            for r in rungs:
                for sk in r.skills:
                    if sk not in self.skills:
                        errors.append(f"ladder {dom}/{r.id}: unknown skill {sk}")
        return errors
