"""Bounded weight search over the component-weight simplex.

Explicitly NOT brute force: `n_samples` is a small, fixed budget (tens, not
thousands), and weight vectors are drawn from a uniform distribution over
the simplex (weights >= 0, sum to 1) via the standard Dirichlet(1,...,1)
construction (i.i.d. Exponential(1) draws, normalized) — every region of
the weight space has equal a-priori chance of being sampled, including
"turn this component off" (a weight near 0), without ever enumerating a
grid. This is Random Search, one of the two methods explicitly allowed
instead of brute force.
"""
from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass

from core.confidence.component_scoring import ComponentWeights
from optimization.objective import PerformanceMetrics


@dataclass(frozen=True)
class WeightSearchResult:
    weights: ComponentWeights
    metrics: PerformanceMetrics
    objective: float


def sample_simplex_weights(component_names: list[str], rng: random.Random) -> ComponentWeights:
    """Uniform sample over the simplex: draw an Exponential(1) value per
    component (-ln(U), U ~ Uniform(0,1)) and normalize by their sum — the
    standard construction for a Dirichlet(1,...,1), i.e. a flat prior over
    every possible weight combination that sums to 1."""
    draws = [-math.log(rng.random()) for _ in component_names]
    total = sum(draws)
    return ComponentWeights({name: d / total for name, d in zip(component_names, draws)})


def random_search(
    component_names: list[str],
    evaluate: Callable[[ComponentWeights], PerformanceMetrics],
    objective_fn: Callable[[PerformanceMetrics], float],
    n_samples: int,
    seed: int,
) -> list[WeightSearchResult]:
    """Draws `n_samples` weight vectors (bounded, small budget — never
    millions), evaluates each via `evaluate` (expected to run a backtest on
    the TRAIN period only), and returns results sorted best-first by the
    composite objective. Always includes each pure single-component vertex
    of the simplex once (weight 1.0 on one component, 0 on the rest) before
    spending the random budget, so the search also directly answers "how
    good is this component alone" without relying on random luck to visit
    the corners.
    """
    rng = random.Random(seed)
    results: list[WeightSearchResult] = []

    vertices = [ComponentWeights({n: (1.0 if n == name else 0.0) for n in component_names}) for name in component_names]
    candidates = vertices + [sample_simplex_weights(component_names, rng) for _ in range(max(0, n_samples - len(vertices)))]

    for weights in candidates:
        metrics = evaluate(weights)
        results.append(WeightSearchResult(weights=weights, metrics=metrics, objective=objective_fn(metrics)))

    results.sort(key=lambda r: r.objective, reverse=True)
    return results
