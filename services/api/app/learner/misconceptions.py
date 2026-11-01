"""Beta-Binomial misconception tracking (guide §8.4; prior Beta(1,2)).

Evidence only counts on items where the misconception was *discriminable* (it predicts an answer
different from the correct one). Confirmation needs mean ≥ 0.6 and ≥ 2 *verified* reproductions:
an ECCL reproduction on an item designed to probe the confusion, a symbolic reproduction of the exact
slate answer, or a teacher confirmation. Weak signals (a tapped distractor, which may be a guess, or an
error the item was not designed to probe) move the posterior and can raise "suspected", never "confirmed".
"""

from __future__ import annotations

from dataclasses import dataclass

PRIOR_ALPHA = 1.0
PRIOR_BETA = 2.0  # exact reproduction of a buggy answer is strong evidence; 2 hits, 0 correct → 0.6
CONFIRM_MEAN = 0.6
CONFIRM_MIN_HITS = 2.0
RESOLVE_MEAN = 0.3

SUSPECTED = "suspected"
CONFIRMED = "confirmed"
RESOLVED = "resolved"
NONE = "none"


@dataclass
class BetaState:
    alpha: float = PRIOR_ALPHA
    beta: float = PRIOR_BETA
    was_confirmed: bool = False
    verified: float = 0.0  # weight of verified reproductions (see module docstring)

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def hits(self) -> float:
        return self.alpha - PRIOR_ALPHA

    def observe(self, outcome: str, weight: float = 1.0, verified: bool = True) -> None:
        """outcome: 'reproduced' | 'correct' | 'other_error'. `verified=False` marks weak evidence."""
        if outcome == "reproduced":
            self.alpha += weight
            if verified:
                self.verified += weight
        elif outcome == "correct":
            self.beta += weight
        elif outcome == "other_error":
            self.beta += 0.5 * weight
        if self.status == CONFIRMED:
            self.was_confirmed = True

    @property
    def status(self) -> str:
        if self.mean >= CONFIRM_MEAN and self.verified >= CONFIRM_MIN_HITS:
            return CONFIRMED
        if self.was_confirmed and self.mean < RESOLVE_MEAN:
            return RESOLVED
        if self.hits >= 1 and self.mean >= 0.3:
            return SUSPECTED
        return NONE
