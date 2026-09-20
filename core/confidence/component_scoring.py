"""Independent per-component evidence scoring, shared by Classic/SMC/ICT.

Before this module, each strategy built a single `base_confidence` integer
by sequentially mutating it (`base = 55; if X: base += 10; ...`) — there was
no way to isolate how much any one piece of evidence contributed, weight it
independently, or ablate it. This module is the reusable mechanism instead:
a strategy computes a `components: dict[str, float]` of 0..1 evidence
strengths, and `weighted_score()` combines them via a `ComponentWeights`.

Weights are strategy-tuning parameters (not environment config): each
strategy exposes a `DEFAULT_WEIGHTS` class attribute reproducing today's
baseline behavior, overridable via constructor for the optimization
framework in `optimization/`.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ComponentWeights:
    weights: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if any(w < 0 for w in self.weights.values()):
            raise ValueError("component weights must be non-negative")

    def excluding(self, disabled: frozenset[str]) -> "ComponentWeights":
        return ComponentWeights({name: w for name, w in self.weights.items() if name not in disabled})

    def perturbed(self, name: str, factor: float) -> "ComponentWeights":
        """Returns a copy with one component's weight scaled by `factor`
        (e.g. 1.10 for +10%) — used by the robustness/perturbation test."""
        updated = dict(self.weights)
        if name in updated:
            updated[name] = updated[name] * factor
        return ComponentWeights(updated)


def weighted_score(components: dict[str, float], weights: ComponentWeights, base: int, scale: int) -> int:
    """`base` is the confidence floor every signal that reached scoring
    already earned by clearing its hard gates (matches prior behavior where
    a bare qualifying signal started at e.g. 55); `scale` is how many
    additional points the weighted components can contribute at most (e.g.
    45, so base + scale = 100 when every active component scores 1.0).
    Weights are renormalized over whichever components are active (not
    disabled), so disabling one doesn't silently shrink the achievable max.
    """
    active = {name: w for name, w in weights.weights.items() if name in components}
    total_weight = sum(active.values())
    if total_weight <= 0:
        return base
    contribution = sum(components[name] * w for name, w in active.items()) / total_weight
    return base + round(contribution * scale)
