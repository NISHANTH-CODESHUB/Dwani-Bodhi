"""Content-pack schema: items, activities, benchmarks. Packs are versioned YAML so new languages,
states or grades can be added without code changes (one pack per language/curriculum)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ItemType = Literal[
    "akshara", "word", "nonword", "passage", "repeat", "comprehension", "tap_number", "tap_compare",
    "tap_count", "tap_missing", "slate",
]

# On-phone tap tasks (EGMA-style): number identification, quantity discrimination, counting objects,
# missing number. All are scored by matching the chosen option against `answer`.
TAP_TYPES: tuple[str, ...] = ("tap_number", "tap_compare", "tap_count", "tap_missing")

EST_SECONDS: dict[str, float] = {
    "akshara": 4, "word": 6, "nonword": 6, "passage": 60, "repeat": 6, "comprehension": 10,
    "tap_number": 7, "tap_compare": 7, "tap_count": 9, "tap_missing": 9, "slate": 0,
}


class Option(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str
    label: str | None = None
    probe: str | None = None  # misconception id revealed when this option is chosen


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    prompt_hi: str
    options: list[Option]
    answer: str


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    type: ItemType
    grade: int = 1
    band: int | None = None
    form: str | None = None
    text: str | None = None
    prompt_hi: str | None = None
    skills: list[str]
    probes: list[str] = Field(default_factory=list)
    pair: str | None = None
    options: list[Option] = Field(default_factory=list)
    answer: str | None = None
    questions: list[Question] = Field(default_factory=list)
    # slate arithmetic
    a: int | None = None
    b: int | None = None
    op: Literal["+", "-"] | None = None
    signature: dict[str, str] = Field(default_factory=dict)
    discrimination: float | None = None
    tags: list[str] = Field(default_factory=list)

    @property
    def est_seconds(self) -> float:
        return EST_SECONDS[self.type]


class ActivityStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hi: str
    en: str | None = None


class Activity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title_hi: str
    title_en: str
    domain: Literal["literacy", "numeracy"]
    levels: list[str]  # ladder rung ids this suits
    targets: list[str]  # skill ids and/or misconception ids / remediation tags
    materials: list[str]
    minutes: int = 10
    group_size: str = "4-12"
    steps: list[ActivityStep]
    variations_hi: list[str] = Field(default_factory=list)
    source: str
    reviewed_by: str | None = None


class Benchmarks(BaseModel):
    model_config = ConfigDict(extra="forbid")
    wcpm_by_grade: dict[int, float]
    passage_band_by_grade: dict[int, int]
    allowed_materials: list[str]
