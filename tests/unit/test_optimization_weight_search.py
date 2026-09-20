import random

import pytest

from core.confidence.component_scoring import ComponentWeights
from optimization.weight_search import random_search, sample_simplex_weights


def test_sample_simplex_weights_sums_to_one_and_nonnegative():
    rng = random.Random(42)
    weights = sample_simplex_weights(["a", "b", "c", "d"], rng)

    assert sum(weights.weights.values()) == pytest.approx(1.0)
    assert all(w >= 0 for w in weights.weights.values())
    assert set(weights.weights.keys()) == {"a", "b", "c", "d"}


def test_different_seeds_give_different_samples():
    w1 = sample_simplex_weights(["a", "b"], random.Random(1))
    w2 = sample_simplex_weights(["a", "b"], random.Random(2))
    assert w1.weights != w2.weights


def test_random_search_is_bounded_not_brute_force():
    """The whole point: n_samples caps total evaluations, however many
    components there are — never an exhaustive grid."""
    call_count = 0

    def evaluate(weights: ComponentWeights):
        nonlocal call_count
        call_count += 1
        return weights  # stand-in "metrics" for this test

    results = random_search(["a", "b", "c"], evaluate, objective_fn=lambda m: sum(m.weights.values()), n_samples=20, seed=1)

    assert call_count == 20  # exactly the requested budget, not 3^k or more
    assert len(results) == 20


def test_random_search_includes_every_pure_vertex():
    def evaluate(weights: ComponentWeights):
        return weights

    results = random_search(["a", "b", "c"], evaluate, objective_fn=lambda m: 0.0, n_samples=10, seed=1)
    sampled_weight_dicts = [r.weights.weights for r in results]

    for name in ["a", "b", "c"]:
        vertex = {n: (1.0 if n == name else 0.0) for n in ["a", "b", "c"]}
        assert vertex in sampled_weight_dicts


def test_random_search_sorts_best_first():
    def evaluate(weights: ComponentWeights):
        return weights

    def objective(weights: ComponentWeights) -> float:
        return weights.weights.get("a", 0.0)  # favors weight concentrated on "a"

    results = random_search(["a", "b"], evaluate, objective_fn=objective, n_samples=15, seed=7)

    objectives = [r.objective for r in results]
    assert objectives == sorted(objectives, reverse=True)
    # the pure "a" vertex (a=1.0) must be the best possible score and thus first
    assert results[0].weights.weights["a"] == 1.0
