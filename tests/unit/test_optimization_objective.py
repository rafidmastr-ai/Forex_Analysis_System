from datetime import datetime, timezone

import pytest

from backtesting.engine import TradeOutcome
from core.signals.enums import ConfidenceLabel, Direction, StrategyCategory
from core.signals.selected_setup import SelectedSetup
from core.signals.strategy_signal import PriceZone, StrategySignal
from optimization.objective import composite_objective, compute_metrics

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _dummy_setup() -> SelectedSetup:
    signal = StrategySignal(
        strategy_id="x", category=StrategyCategory.CLASSIC, direction=Direction.BUY,
        suggested_entry_zone=PriceZone(1.10, 1.10), suggested_stop_loss=1.09,
        suggested_take_profit_1=1.115, suggested_take_profit_2=1.13, rationale=["x"],
    )
    return SelectedSetup(
        winning_signal=signal, agreeing_signals=[], conflicting_signals=[], direction=Direction.BUY,
        entry=1.10, stop_loss=1.09, take_profit_1=1.115, take_profit_2=1.13,
        confidence_score=70, confidence_label=ConfidenceLabel.STRONG,
    )


def _outcome(hit: str, r: float) -> TradeOutcome:
    return TradeOutcome(setup=_dummy_setup(), opened_at=BASE, hit=hit, r_multiple=r)


def test_win_rate_alone_does_not_determine_the_better_objective():
    """A strategy with a LOWER win rate but bigger wins must be able to
    score higher — proves Win Rate isn't secretly the objective. Wins and
    losses are interleaved (not grouped) so the comparison isn't confounded
    by drawdown ordering artifacts."""
    high_winrate_tiny_wins = [_outcome("TP1", 0.3), _outcome("TP1", 0.3), _outcome("TP1", 0.3), _outcome("TP1", 0.3),
                              _outcome("SL", -1.0), _outcome("TP1", 0.3), _outcome("TP1", 0.3), _outcome("TP1", 0.3),
                              _outcome("TP1", 0.3), _outcome("SL", -1.0)]
    low_winrate_big_wins = [_outcome("SL", -1.0), _outcome("SL", -1.0), _outcome("TP2", 3.0), _outcome("SL", -1.0),
                            _outcome("SL", -1.0), _outcome("TP2", 3.0), _outcome("SL", -1.0), _outcome("SL", -1.0),
                            _outcome("TP2", 3.0), _outcome("SL", -1.0)]

    m1 = compute_metrics(high_winrate_tiny_wins)
    m2 = compute_metrics(low_winrate_big_wins)

    assert m1.win_rate > m2.win_rate
    # net_r: m1 = 8*0.3 - 2 = 0.4 ; m2 = 3*3.0 - 7 = 2.0 -> m2 clearly better despite lower win rate
    assert m2.net_r > m1.net_r
    assert composite_objective(m2, min_trades=5) > composite_objective(m1, min_trades=5)


def test_none_outcomes_excluded_from_every_r_statistic():
    outcomes = [_outcome("TP1", 2.0), _outcome("NONE", 0.0), _outcome("NONE", 0.0)]
    metrics = compute_metrics(outcomes)

    assert metrics.trade_count == 3
    assert metrics.resolved_count == 1
    assert metrics.win_rate == 1.0  # only the resolved trade counts
    assert metrics.none_rate == pytest.approx(2 / 3)


def test_low_trade_count_is_penalized_via_trade_count_factor():
    few = [_outcome("TP2", 3.0)] * 3  # great looking, but tiny sample
    many_same_ratio = [_outcome("TP2", 3.0)] * 40

    m_few = compute_metrics(few)
    m_many = compute_metrics(many_same_ratio)

    assert composite_objective(m_few, min_trades=30) < composite_objective(m_many, min_trades=30)


def test_high_drawdown_reduces_composite_objective():
    steady = [_outcome("TP1", 0.2)] * 10  # net R = 2.0, monotonic, zero drawdown
    # net R = 3*3 - 7*1 = 2.0 (same as steady), but with a real peak-to-trough swing
    volatile = [_outcome("TP2", 3.0), _outcome("SL", -1.0), _outcome("SL", -1.0), _outcome("SL", -1.0),
                _outcome("TP2", 3.0), _outcome("SL", -1.0), _outcome("SL", -1.0), _outcome("SL", -1.0),
                _outcome("TP2", 3.0), _outcome("SL", -1.0)]

    m_steady = compute_metrics(steady)
    m_volatile = compute_metrics(volatile)

    assert m_volatile.max_drawdown_r > m_steady.max_drawdown_r
    assert abs(m_steady.net_r - m_volatile.net_r) < 1e-9
    assert composite_objective(m_steady, min_trades=5) > composite_objective(m_volatile, min_trades=5)


def test_profit_factor_infinite_with_zero_losses_is_capped_not_broken():
    all_wins = [_outcome("TP1", 1.0)] * 10
    metrics = compute_metrics(all_wins)

    assert metrics.profit_factor == float("inf")
    score = composite_objective(metrics, min_trades=5)
    assert score == score  # not NaN
    assert score > 0
