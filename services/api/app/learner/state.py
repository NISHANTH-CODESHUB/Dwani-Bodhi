"""Pure (DB-independent) learner state and evidence application.

The worker loads a child's rows into a `LearnerState`, applies evidence from scored responses,
and writes the state back. Keeping this pure makes it unit-testable and lets it run anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from .bkt import BKTParams, learn, propagate_success, update
from .graph import SkillGraph
from .misconceptions import CONFIRMED, BetaState

SPOKEN = BKTParams(guess=0.10, slip=0.10)
TAP4 = BKTParams(guess=0.25, slip=0.08)
WRITTEN = BKTParams(guess=0.05, slip=0.10)


def reading_misconception_id(rule: str) -> str:
    return f"READ_{rule}"


@dataclass
class LearnerState:
    child_id: str
    grade: int
    skills: dict[str, float] = field(default_factory=dict)
    n_obs: dict[str, int] = field(default_factory=dict)
    misconceptions: dict[str, BetaState] = field(default_factory=dict)
    speech_variants: set[str] = field(default_factory=set)  # e.g. "व→ब" heard in listen-and-repeat
    recheck: set[str] = field(default_factory=set)  # skill or misconception ids needing a re-check
    last_updated: datetime | None = None
    sounding_out_count: int = 0
    wcpm_history: list[tuple[str, float]] = field(default_factory=list)

    # ---- helpers -------------------------------------------------------------------------
    def ensure(self, graph: SkillGraph) -> None:
        for sid, sk in graph.skills.items():
            self.skills.setdefault(sid, sk.prior(self.grade))
            self.n_obs.setdefault(sid, 0)

    def advance_time(self, now: datetime, params: BKTParams = SPOKEN) -> None:
        if self.last_updated is None:
            self.last_updated = now
            return
        weeks = (now - self.last_updated).total_seconds() / (7 * 24 * 3600)
        if weeks > 0.05:
            for sid in self.skills:
                self.skills[sid] = learn(self.skills[sid], weeks, params)
        self.last_updated = now

    def mis(self, mid: str) -> BetaState:
        return self.misconceptions.setdefault(mid, BetaState())

    # ---- evidence ------------------------------------------------------------------------
    def observe_skill(self, graph: SkillGraph, skill_ids: list[str], correct: bool, confidence: float,
                      params: BKTParams = SPOKEN, propagate: bool = True) -> None:
        for sid in skill_ids:
            if sid not in self.skills:
                continue
            self.skills[sid] = update(self.skills[sid], correct, confidence, params)
            self.n_obs[sid] = self.n_obs.get(sid, 0) + 1
            if correct and propagate:
                direct = set(graph.skills[sid].prereqs)
                for anc in graph.ancestors(sid):
                    lam = 0.5 if anc in direct else 0.25
                    self.skills[anc] = propagate_success(self.skills[anc], confidence, lam)

    def observe_reading_word(self, graph: SkillGraph, verdict: dict, skills: list[str], probes: list[str],
                             control: bool = False) -> None:
        """verdict: ECCL WordVerdict dict. probes: confusion rules this item can reveal."""
        status = verdict.get("status")
        conf = float(verdict.get("confidence") or 0.0)
        if control:  # listen-and-repeat: record speech variants, never reading evidence
            if status == "ERROR" and verdict.get("detail"):
                self.speech_variants.add(verdict["detail"])
            return
        if status in ("UNSURE", "OTHER", "NO_SPEECH", None):
            self.recheck.update(skills)
            return
        if verdict.get("sounding_out"):
            self.sounding_out_count += 1
        if status == "ERROR" and verdict.get("detail") in self.speech_variants:
            status = "CORRECT_DIALECT"  # the child says it this way when merely repeating, too
        correct = status in ("CORRECT", "CORRECT_DIALECT")
        self.observe_skill(graph, skills, correct, conf, SPOKEN)
        rule = verdict.get("rule")
        for probe in probes:
            m = self.mis(reading_misconception_id(probe))
            if correct:
                m.observe("correct", conf)
            elif rule == probe:
                m.observe("reproduced", conf)
            else:
                m.observe("other_error", conf)
        if not correct and rule and rule not in probes:  # an un-probed confusion still counts, lightly
            teacher = bool(verdict.get("teacher_confirmed"))  # a teacher heard it: verified, full weight
            self.mis(reading_misconception_id(rule)).observe("reproduced", conf if teacher else 0.5 * conf,
                                                             verified=teacher)

    def observe_passage(self, graph: SkillGraph, verdict: dict, benchmark_wcpm: float, skills: list[str]) -> None:
        n = max(1, verdict.get("attempted", 0))
        unsure_frac = verdict.get("unsure", 0) / n
        conf = max(0.0, 1.0 - 2 * unsure_frac)
        wcpm = float(verdict.get("wcpm", 0.0))
        self.wcpm_history.append(((self.last_updated or datetime.now(UTC)).date().isoformat(), wcpm))
        fluent = wcpm >= benchmark_wcpm
        self.observe_skill(graph, [s for s in skills if s == "L10"], fluent, conf, SPOKEN)
        accurate = float(verdict.get("accuracy", 0.0)) >= 0.8
        self.observe_skill(graph, [s for s in skills if s == "L9"], accurate, conf, SPOKEN)
        for w in verdict.get("words", []):  # word-level confusions feed misconceptions at half weight
            if w.get("status") == "ERROR" and w.get("rule") and w.get("detail") not in self.speech_variants:
                self.mis(reading_misconception_id(w["rule"])).observe(
                    "reproduced", 0.5 * float(w.get("confidence", 0)), verified=False)

    def observe_tap(self, graph: SkillGraph, skills: list[str], correct: bool, chosen_probe: str | None = None) -> None:
        # Multiple-choice taps can be guessed (G=0.25), so they update only their own skill and never
        # propagate to prerequisites — a lucky comprehension guess must not "prove" decoding.
        self.observe_skill(graph, skills, correct, 1.0, TAP4, propagate=False)
        if chosen_probe:  # a distractor pick may be a guess (1 in 4): weak, unverified evidence
            self.mis(chosen_probe).observe("reproduced", 0.5, verified=False)

    def observe_slate(self, graph: SkillGraph, verdict: dict, skills: list[str], confidence: float = 1.0) -> None:
        """verdict: diagnosis.verify.AnswerVerdict dict."""
        status = verdict.get("status")
        if status in ("BLANK",):
            self.observe_skill(graph, skills, False, 0.5 * confidence, WRITTEN, propagate=False)
            return
        if status == "ILLEGIBLE":
            self.recheck.update(skills)
            return
        disc = verdict.get("discriminable_bugs", [])
        matches = verdict.get("matching_bugs", [])
        if status == "CORRECT":
            self.observe_skill(graph, skills, True, confidence, WRITTEN)
            for b in disc:
                self.mis(b).observe("correct", confidence)
        elif status == "SLIP":
            self.observe_skill(graph, skills, True, 0.5 * confidence, WRITTEN)
            for b in disc:
                self.mis(b).observe("correct", 0.5 * confidence)
        elif status == "BUG":
            self.observe_skill(graph, skills, False, confidence, WRITTEN, propagate=False)
            w = confidence / max(1, len(matches))
            for b in disc:
                self.mis(b).observe("reproduced" if b in matches else "other_error", w if b in matches else confidence)
        else:  # UNEXPLAINED
            self.observe_skill(graph, skills, False, confidence, WRITTEN, propagate=False)
            for b in disc:
                self.mis(b).observe("other_error", confidence)

    # ---- summaries -----------------------------------------------------------------------
    def confirmed_misconceptions(self) -> list[str]:
        return [k for k, v in self.misconceptions.items() if v.status == CONFIRMED]

    def to_dict(self) -> dict:
        return {
            "child_id": self.child_id, "grade": self.grade, "skills": self.skills, "n_obs": self.n_obs,
            "misconceptions": {k: {"alpha": v.alpha, "beta": v.beta, "was_confirmed": v.was_confirmed,
                                   "verified": v.verified, "status": v.status, "mean": round(v.mean, 3)} for k, v in self.misconceptions.items()},
            "speech_variants": sorted(self.speech_variants), "recheck": sorted(self.recheck),
            "sounding_out_count": self.sounding_out_count, "wcpm_history": self.wcpm_history,
        }
