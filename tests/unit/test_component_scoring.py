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
