from datetime import datetime, timedelta, timezone

import pytest

from backtesting.engine import TradeOutcome
from core.signals.enums import ConfidenceLabel, Direction, StrategyCategory
from core.signals.selected_setup import SelectedSetup
from core.signals.strategy_signal import PriceZone, StrategySignal
from optimization.extended_metrics import compute_extended_metrics

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _setup(rr1: float = 1.5, rr2: float = 3.0) -> SelectedSetup:
    entry, stop = 1.10, 1.09
    risk = entry - stop
    signal = StrategySignal(
        strategy_id="x", category=StrategyCategory.CLASSIC, direction=Direction.BUY,
        suggested_entry_zone=PriceZone(entry, entry), suggested_stop_loss=stop,
        suggested_take_profit_1=entry + risk * rr1, suggested_take_profit_2=entry + risk * rr2, rationale=["x"],
    )
    return SelectedSetup(
        winning_signal=signal, agreeing_signals=[], conflicting_signals=[], direction=Direction.BUY,
        entry=entry, stop_loss=stop, take_profit_1=entry + risk * rr1, take_profit_2=entry + risk * rr2,
        confidence_score=70, confidence_label=ConfidenceLabel.STRONG,
    )


def _outcome(hit: str, r: float, opened_at=BASE, duration_minutes: float | None = 30, rr1: float = 1.5, rr2: float = 3.0) -> TradeOutcome:
    closed_at = opened_at + timedelta(minutes=duration_minutes) if (hit != "NONE" and duration_minutes is not None) else None
    return TradeOutcome(setup=_setup(rr1, rr2), opened_at=opened_at, hit=hit, r_multiple=r, closed_at=closed_at)


def test_wins_losses_and_rates():
    outcomes = [_outcome("TP1", 1.5), _outcome("TP2", 3.0), _outcome("SL", -1.0), _outcome("SL", -1.0), _outcome("NONE", 0.0)]
    m = compute_extended_metrics(outcomes)

    assert m.trade_count == 5
    assert m.resolved_count == 4
    assert m.none_count == 1
    assert m.wins == 2
    assert m.losses == 2
    assert m.win_rate == pytest.approx(0.5)
    assert m.tp1_rate == pytest.approx(0.25)
    assert m.tp2_rate == pytest.approx(0.25)
    assert m.sl_rate == pytest.approx(0.5)


def test_average_winning_and_losing_r():
    outcomes = [_outcome("TP1", 1.5), _outcome("TP2", 3.0), _outcome("SL", -1.0), _outcome("SL", -1.0)]
    m = compute_extended_metrics(outcomes)

    assert m.average_winning_r == pytest.approx((1.5 + 3.0) / 2)
    assert m.average_losing_r == pytest.approx(-1.0)


def test_max_consecutive_wins_and_losses():
    outcomes = [
        _outcome("TP1", 1.5, opened_at=BASE), _outcome("TP1", 1.5, opened_at=BASE + timedelta(hours=1)),
        _outcome("TP1", 1.5, opened_at=BASE + timedelta(hours=2)),
        _outcome("SL", -1.0, opened_at=BASE + timedelta(hours=3)), _outcome("SL", -1.0, opened_at=BASE + timedelta(hours=4)),
        _outcome("TP1", 1.5, opened_at=BASE + timedelta(hours=5)),
    ]
    m = compute_extended_metrics(outcomes)

    assert m.max_consecutive_wins == 3
    assert m.max_consecutive_losses == 2


def test_streaks_use_chronological_order_regardless_of_input_order():
    """Feeding outcomes out of order must not corrupt the streak count —
    compute_extended_metrics sorts by opened_at itself."""
    outcomes = [
        _outcome("SL", -1.0, opened_at=BASE + timedelta(hours=3)),
        _outcome("TP1", 1.5, opened_at=BASE),
        _outcome("TP1", 1.5, opened_at=BASE + timedelta(hours=1)),
        _outcome("TP1", 1.5, opened_at=BASE + timedelta(hours=2)),
    ]
    m = compute_extended_metrics(outcomes)

    assert m.max_consecutive_wins == 3
    assert m.max_consecutive_losses == 1


def test_average_duration_minutes():
    outcomes = [_outcome("TP1", 1.5, duration_minutes=30), _outcome("SL", -1.0, duration_minutes=90)]
    m = compute_extended_metrics(outcomes)

    assert m.average_duration_minutes == pytest.approx(60.0)


def test_none_outcomes_excluded_from_duration_and_excluded_from_r_stats():
    outcomes = [_outcome("TP1", 1.5, duration_minutes=30), _outcome("NONE", 0.0, duration_minutes=None)]
    m = compute_extended_metrics(outcomes)

    assert m.average_duration_minutes == pytest.approx(30.0)
    assert m.net_r == pytest.approx(1.5)


def test_no_resolved_trades_returns_zeros_not_errors():
    m = compute_extended_metrics([_outcome("NONE", 0.0)])

    assert m.resolved_count == 0
    assert m.win_rate == 0.0
    assert m.average_winning_r == 0.0
    assert m.average_duration_minutes is None


def test_planned_rr_distribution_reflects_every_trade_including_unresolved():
    outcomes = [_outcome("TP1", 1.5, rr1=1.5), _outcome("NONE", 0.0, rr1=2.0), _outcome("SL", -1.0, rr1=1.8)]
    m = compute_extended_metrics(outcomes)

    assert m.planned_rr_tp1["min"] == pytest.approx(1.5)
    assert m.planned_rr_tp1["max"] == pytest.approx(2.0)
    assert m.planned_rr_tp1["mean"] == pytest.approx((1.5 + 2.0 + 1.8) / 3)


def test_profit_factor_matches_objective_module_convention():
    all_wins = [_outcome("TP1", 1.0)] * 5
    m = compute_extended_metrics(all_wins)
    assert m.profit_factor == float("inf")

    no_trades = compute_extended_metrics([])
    assert no_trades.profit_factor == 0.0
