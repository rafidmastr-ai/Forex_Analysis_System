from core.confidence.confidence_engine import ConfidenceEngine
from core.signals.enums import ConfidenceLabel, Direction, StrategyCategory
from core.signals.selected_setup import SelectedSetup
from core.signals.strategy_signal import PriceZone, StrategySignal

ENGINE = ConfidenceEngine(thresholds={"weak_max": 49, "medium_max": 74}, multi_strategy_agreement_bonus=10)


def _signal(strategy_id, category, base_confidence, rationale, **extra_components):
    return StrategySignal(
        strategy_id=strategy_id, category=category, direction=Direction.BUY,
        suggested_entry_zone=PriceZone(1.10, 1.10), suggested_stop_loss=1.09,
        suggested_take_profit_1=1.115, suggested_take_profit_2=1.13, rationale=rationale,
        raw_score_components={"base_confidence": base_confidence, **extra_components},
    )


def test_thresholds_map_to_labels():
    weak = _signal("a", StrategyCategory.CLASSIC, 40, ["x"])
    medium = _signal("b", StrategyCategory.CLASSIC, 60, ["y"])
    strong = _signal("c", StrategyCategory.CLASSIC, 90, ["z"])

    assert ENGINE.score_group(weak, [])[1] == ConfidenceLabel.WEAK
    assert ENGINE.score_group(medium, [])[1] == ConfidenceLabel.MEDIUM
    assert ENGINE.score_group(strong, [])[1] == ConfidenceLabel.STRONG


def test_score_is_clamped_to_100():
    strong = _signal("a", StrategyCategory.CLASSIC, 95, ["x"])
    agreeing = [_signal("b", StrategyCategory.SMC, 90, ["y"]), _signal("c", StrategyCategory.ICT, 90, ["z"])]

    score, *_ = ENGINE.score_group(strong, agreeing)

    assert score == 100


def test_duplicate_rationale_across_strategies_is_not_double_counted_in_reasons():
    shared_line = "Trend alignment confirmed"
    primary = _signal("a", StrategyCategory.CLASSIC, 55, [shared_line, "Classic-only reason"])
    agreeing = [_signal("b", StrategyCategory.SMC, 55, [shared_line, "SMC-only reason"])]

    _, _, _, reasons = ENGINE.score_group(primary, agreeing)

    assert reasons.count(shared_line) == 1
    assert "Classic-only reason" in reasons
    assert "SMC-only reason" in reasons


def test_breakdown_flags_each_category_only_when_present():
    primary = _signal("a", StrategyCategory.CLASSIC, 55, ["x"])
    agreeing = [_signal("b", StrategyCategory.SMC, 55, ["y"])]

    _, _, breakdown, _ = ENGINE.score_group(primary, agreeing)

    assert breakdown["classic_confirmation"] is True
    assert breakdown["smc_confirmation"] is True
    assert breakdown["ict_confirmation"] is False


def test_contributing_signals_includes_winner_and_agreeing_only():
    winner = _signal("a", StrategyCategory.CLASSIC, 70, ["x"])
    agreeing = [_signal("b", StrategyCategory.SMC, 60, ["y"])]
    conflicting = [_signal("c", StrategyCategory.ICT, 50, ["z"])]
    setup = SelectedSetup(
        winning_signal=winner, agreeing_signals=agreeing, conflicting_signals=conflicting,
        direction=Direction.BUY, entry=1.10, stop_loss=1.09, take_profit_1=1.115, take_profit_2=1.13,
        confidence_score=80, confidence_label=ConfidenceLabel.STRONG,
    )

    contributing = setup.contributing_signals

    assert contributing == [winner, agreeing[0]]
    assert conflicting[0] not in contributing
