import pytest

from core.confidence.component_scoring import ComponentWeights, weighted_score


def test_weighted_score_all_components_full_strength_hits_max():
    weights = ComponentWeights({"a": 0.5, "b": 0.5})
    components = {"a": 1.0, "b": 1.0}
    assert weighted_score(components, weights, base=55, scale=45) == 100


def test_weighted_score_zero_strength_stays_at_base():
    weights = ComponentWeights({"a": 0.5, "b": 0.5})
    components = {"a": 0.0, "b": 0.0}
    assert weighted_score(components, weights, base=55, scale=45) == 55


def test_weighted_score_renormalizes_when_a_component_is_missing():
    weights = ComponentWeights({"a": 0.5, "b": 0.5})
    components = {"a": 1.0}  # "b" absent (e.g. disabled for ablation)
    assert weighted_score(components, weights, base=55, scale=45) == 100


def test_excluding_removes_disabled_components():
    weights = ComponentWeights({"a": 0.3, "b": 0.7})
    reduced = weights.excluding(frozenset({"b"}))
    assert reduced.weights == {"a": 0.3}


def test_perturbed_scales_one_component_only():
    weights = ComponentWeights({"a": 0.2, "b": 0.8})
    perturbed = weights.perturbed("a", 1.10)
    assert perturbed.weights["a"] == pytest.approx(0.22)
    assert perturbed.weights["b"] == 0.8


def test_negative_weight_rejected():
    with pytest.raises(ValueError):
        ComponentWeights({"a": -0.1})


def test_perturbed_toward_moves_weight_between_components():
    weights = ComponentWeights({"a": 0.2, "b": 0.8})
    moved = weights.perturbed_toward("b", "a", 0.10)
    assert moved.weights["b"] == pytest.approx(0.72)
    assert moved.weights["a"] == pytest.approx(0.28)


def test_perturbed_toward_produces_real_change_on_a_pure_vertex():
    """The bug perturbed_toward exists to fix: perturbed() is a no-op on a
    pure vertex (one nonzero component) because weighted_score renormalizes
    over active components, so rescaling the lone weight and renormalizing
    always returns 1.0 again. perturbed_toward must not have this blind spot."""
    vertex = ComponentWeights({"a": 1.0, "b": 0.0, "c": 0.0})

    rescaled = vertex.perturbed("a", 0.85)  # the old (still-correct-for-multi-weight) primitive
    assert weighted_score({"a": 1.0, "b": 1.0, "c": 1.0}, rescaled, base=0, scale=100) == \
        weighted_score({"a": 1.0, "b": 1.0, "c": 1.0}, vertex, base=0, scale=100)  # unchanged -> the blind spot

    redistributed = vertex.perturbed_toward("a", "b", 0.15)
    assert redistributed.weights == {"a": pytest.approx(0.85), "b": pytest.approx(0.15), "c": 0.0}
    assert weighted_score({"a": 1.0, "b": 0.0, "c": 1.0}, redistributed, base=0, scale=100) != \
        weighted_score({"a": 1.0, "b": 0.0, "c": 1.0}, vertex, base=0, scale=100)  # genuinely changes the score
