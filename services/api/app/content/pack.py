"""Load and validate a content pack directory into memory (cached per process)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from ..learner.graph import Rung, Skill, SkillGraph
from ..speech.regions import ProfileRegistry
from .schema import TAP_TYPES, Activity, Benchmarks, Item


@dataclass
class ContentPack:
    id: str
    version: str
    language: str
    graph: SkillGraph
    items: dict[str, Item]
    activities: dict[str, Activity]
    benchmarks: Benchmarks
    regions: ProfileRegistry
    root: Path
    prompts: dict[str, str] = field(default_factory=dict)  # prompt key -> text Cheenu speaks

    def items_of(self, *types: str) -> list[Item]:
        return [i for i in self.items.values() if i.type in types]

    def validate(self) -> list[str]:
        errs = self.graph.validate()
        for it in self.items.values():
            for s in it.skills:
                if s not in self.graph.skills:
                    errs.append(f"item {it.id}: unknown skill {s}")
            if it.type == "slate" and (it.a is None or it.b is None or it.op is None):
                errs.append(f"item {it.id}: slate item needs a, b, op")
            if it.type in ("word", "nonword", "akshara", "passage", "repeat") and not it.text:
                errs.append(f"item {it.id}: needs text")
            if it.type in TAP_TYPES:
                values = [o.value for o in it.options]
                if not it.prompt_hi:
                    errs.append(f"item {it.id}: tap item needs prompt_hi")
                if it.answer not in values:
                    errs.append(f"item {it.id}: answer must be one of the options")
                if len(set(values)) != len(values):
                    errs.append(f"item {it.id}: duplicate option values")
                if it.type in ("tap_count", "tap_missing") and not it.text:
                    errs.append(f"item {it.id}: needs text (the objects or number sequence shown)")
        for a in self.activities.values():
            for m in a.materials:
                if m not in self.benchmarks.allowed_materials:
                    errs.append(f"activity {a.id}: material '{m}' not in allowed list")
        return errs


def _load_yaml(p: Path):
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def load_pack(root: Path) -> ContentPack:
    meta = _load_yaml(root / "pack.yaml")
    sk = _load_yaml(root / "skills.yaml")
    skills = {
        s["id"]: Skill(
            id=s["id"], domain=s["domain"], name_en=s["name_en"], name_hi=s["name_hi"],
            prereqs=tuple(s.get("prereqs", [])), nipun=s.get("nipun", ""),
            grade_prior={int(k): float(v) for k, v in (s.get("prior") or {}).items()},
            weight=float(s.get("weight", 1.0)),
        )
        for s in sk["skills"]
    }
    ladders = {
        dom: [Rung(r["id"], r["name_en"], r["name_hi"], tuple(r["skills"])) for r in rungs]
        for dom, rungs in sk["ladders"].items()
    }
    items: dict[str, Item] = {}
    for f in sorted((root / "items").glob("*.yaml")):
        for raw in _load_yaml(f) or []:
            it = Item.model_validate(raw)
            if it.id in items:
                raise ValueError(f"duplicate item id {it.id} in {f.name}")
            items[it.id] = it
    activities: dict[str, Activity] = {}
    for f in sorted((root / "activities").glob("*.yaml")):
        for raw in _load_yaml(f) or []:
            act = Activity.model_validate(raw)
            activities[act.id] = act
    bm = Benchmarks.model_validate(_load_yaml(root / "benchmarks.yaml"))
    prompts = _load_yaml(root / "prompts.yaml") if (root / "prompts.yaml").exists() else {}
    h = hashlib.sha256()
    for f in sorted(root.rglob("*.yaml")):
        h.update(f.read_bytes())
    return ContentPack(
        id=meta["id"], version=f"{meta.get('version', '0')}+{h.hexdigest()[:10]}", language=meta["language"],
        graph=SkillGraph(skills, ladders), items=items, activities=activities, benchmarks=bm,
        regions=ProfileRegistry.from_dir(root / "regions"), root=root, prompts=prompts or {},
    )


@lru_cache(maxsize=8)
def get_pack(root: str) -> ContentPack:
    return load_pack(Path(root))
