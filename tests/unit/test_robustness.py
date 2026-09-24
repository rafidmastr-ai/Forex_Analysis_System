"""Regression tests for optimization/robustness.py's R:R-cap post-
processing -- see config/robustness_backtest.yaml. These prove the cap
never touches decision logic: it cannot change trade count, win rate,
TP1/TP2/SL counts, Outcome, or Entry/SL/TP, and it can only ever reduce
(never increase) a winning trade's realized R.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from backtesting.engine import TradeOutcome
from core.signals.enums import ConfidenceLabel, Direction, StrategyCategory
from core.signals.selected_setup import SelectedSetup
from core.signals.strategy_signal import PriceZone, StrategySignal
from optimization.extended_metrics import compute_extended_metrics
from optimization.robustness import RobustnessMode, apply_rr_cap, load_robustness_modes

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


def _outcome(hit: str, r: float, opened_at=BASE, duration_minutes: float | None = 30) -> TradeOutcome:
    closed_at = opened_at + timedelta(minutes=duration_minutes) if (hit != "NONE" and duration_minutes is not None) else None
    return TradeOutcome(setup=_setup(), opened_at=opened_at, hit=hit, r_multiple=r, closed_at=closed_at)


def _mixed_outcomes() -> list[TradeOutcome]:
    return [
        _outcome("TP1", 1.8, opened_at=BASE),
        _outcome("TP2", 8.0, opened_at=BASE + timedelta(hours=1)),  # the "outlier"
        _outcome("TP1", 2.9, opened_at=BASE + timedelta(hours=2)),
        _outcome("SL", -1.0, opened_at=BASE + timedelta(hours=3)),
        _outcome("SL", -1.0, opened_at=BASE + timedelta(hours=4)),
        _outcome("NONE", 0.0, opened_at=BASE + timedelta(hours=5), duration_minutes=None),
        _outcome("TP2", 12.5, opened_at=BASE + timedelta(hours=6)),  # a second, bigger outlier
    ]


# 1. Baseline robustness == the original results exactly.
def test_baseline_mode_is_the_identity_transform():
    outcomes = _mixed_outcomes()
    capped = apply_rr_cap(outcomes, None)
    assert len(capped) == len(outcomes)
    for original, result in zip(outcomes, capped):
        assert result.r_multiple == original.r_multiple
        assert result.hit == original.hit
        assert result.opened_at == original.opened_at
        assert result.closed_at == original.closed_at
        assert result.setup is original.setup

    m_baseline = compute_extended_metrics(outcomes)
    m_identity = compute_extended_metrics(capped)
    assert m_baseline == m_identity


# 2. Trade count never changes between caps.
@pytest.mark.parametrize("cap", [None, 5.0, 4.0, 3.0, 2.5, 2.0])
def test_trade_count_unchanged_across_all_caps(cap):
    outcomes = _mixed_outcomes()
    capped = apply_rr_cap(outcomes, cap)
    assert len(capped) == len(outcomes)
    m = compute_extended_metrics(capped)
    assert m.trade_count == len(outcomes)


# 3. Win rate never changes between caps (outcome/hit is never altered).
@pytest.mark.parametrize("cap", [5.0, 4.0, 3.0, 2.5, 2.0])
def test_win_rate_unchanged_across_all_caps(cap):
    outcomes = _mixed_outcomes()
    baseline_win_rate = compute_extended_metrics(outcomes).win_rate
    capped_win_rate = compute_extended_metrics(apply_rr_cap(outcomes, cap)).win_rate
    assert capped_win_rate == pytest.approx(baseline_win_rate)


# 4. TP1/TP2/SL counts never change.
@pytest.mark.parametrize("cap", [5.0, 4.0, 3.0, 2.5, 2.0])
def test_tp1_tp2_sl_counts_unchanged_across_all_caps(cap):
    outcomes = _mixed_outcomes()
    capped = apply_rr_cap(outcomes, cap)
    for label in ("TP1", "TP2", "SL", "NONE"):
        original_count = sum(1 for o in outcomes if o.hit == label)
        capped_count = sum(1 for o in capped if o.hit == label)
        assert capped_count == original_count, f"{label} count changed under cap={cap}"


# 5. A cap never increases Net R.
@pytest.mark.parametrize("cap", [5.0, 4.0, 3.0, 2.5, 2.0])
def test_cap_never_increases_net_r(cap):
    outcomes = _mixed_outcomes()
    baseline_net_r = compute_extended_metrics(outcomes).net_r
    capped_net_r = compute_extended_metrics(apply_rr_cap(outcomes, cap)).net_r
    assert capped_net_r <= baseline_net_r + 1e-9


# 6. A cap never increases average winning R.
@pytest.mark.parametrize("cap", [5.0, 4.0, 3.0, 2.5, 2.0])
def test_cap_never_increases_average_winning_r(cap):
    outcomes = _mixed_outcomes()
    baseline_avg_win = compute_extended_metrics(outcomes).average_winning_r
    capped_avg_win = compute_extended_metrics(apply_rr_cap(outcomes, cap)).average_winning_r
    assert capped_avg_win <= baseline_avg_win + 1e-9


# 7. A cap never changes losing R.
@pytest.mark.parametrize("cap", [5.0, 4.0, 3.0, 2.5, 2.0])
def test_cap_never_changes_losing_r(cap):
    outcomes = _mixed_outcomes()
    baseline_avg_loss = compute_extended_metrics(outcomes).average_losing_r
    capped_avg_loss = compute_extended_metrics(apply_rr_cap(outcomes, cap)).average_losing_r
    assert capped_avg_loss == pytest.approx(baseline_avg_loss)
    assert capped_avg_loss == pytest.approx(-1.0)


# 8 & 9. Cap 2R / Cap 3R must never produce a winning trade above the cap.
@pytest.mark.parametrize("cap", [2.0, 3.0])
def test_cap_produces_no_winning_trade_above_the_cap(cap):
    outcomes = _mixed_outcomes()
    capped = apply_rr_cap(outcomes, cap)
    wins = [o for o in capped if o.hit in ("TP1", "TP2")]
    assert wins, "test fixture must contain winning trades"
    for w in wins:
        assert w.r_multiple <= cap + 1e-9


# 10. A cap never changes Outcome (hit).
@pytest.mark.parametrize("cap", [5.0, 4.0, 3.0, 2.5, 2.0])
def test_cap_never_changes_outcome(cap):
    outcomes = _mixed_outcomes()
    capped = apply_rr_cap(outcomes, cap)
    for original, result in zip(outcomes, capped):
        assert result.hit == original.hit


# 11. A cap never changes Entry/SL/TP (the setup object is untouched).
@pytest.mark.parametrize("cap", [5.0, 4.0, 3.0, 2.5, 2.0])
def test_cap_never_changes_entry_sl_tp(cap):
    outcomes = _mixed_outcomes()
    capped = apply_rr_cap(outcomes, cap)
    for original, result in zip(outcomes, capped):
        assert result.setup is original.setup
        assert result.setup.entry == original.setup.entry
        assert result.setup.stop_loss == original.setup.stop_loss
        assert result.setup.take_profit_1 == original.setup.take_profit_1
        assert result.setup.take_profit_2 == original.setup.take_profit_2


# 12. No NaN/Inf introduced by capping itself (a legitimate all-wins Inf PF
# is a pre-existing, unrelated convention -- see test_extended_metrics.py's
# test_profit_factor_matches_objective_module_convention -- not something
# introduced by capping).
@pytest.mark.parametrize("cap", [5.0, 4.0, 3.0, 2.5, 2.0])
def test_cap_never_introduces_nan(cap):
    outcomes = _mixed_outcomes()
    capped = apply_rr_cap(outcomes, cap)
    for o in capped:
        assert not math.isnan(o.r_multiple)
        assert math.isfinite(o.r_multiple)
    m = compute_extended_metrics(capped)
    for field in (m.net_r, m.expectancy, m.average_r, m.average_winning_r, m.average_losing_r, m.max_drawdown_r):
        assert not math.isnan(field)


def test_load_robustness_modes_reads_the_six_documented_modes(tmp_path):
    modes = load_robustness_modes()
    labels = [m.label for m in modes]
    assert labels == ["Baseline", "Cap_5.0", "Cap_4.0", "Cap_3.0", "Cap_2.5", "Cap_2.0"]
    caps = {m.label: m.rr_cap for m in modes}
    assert caps["Baseline"] is None
    assert caps["Cap_5.0"] == 5.0
    assert caps["Cap_4.0"] == 4.0
    assert caps["Cap_3.0"] == 3.0
    assert caps["Cap_2.5"] == 2.5
    assert caps["Cap_2.0"] == 2.0


def test_cap_below_a_trades_r_reduces_it_exactly_to_the_cap():
    outcomes = [_outcome("TP2", 8.0)]
    capped = apply_rr_cap(outcomes, 3.0)
    assert capped[0].r_multiple == pytest.approx(3.0)


def test_cap_above_a_trades_r_leaves_it_unchanged():
    outcomes = [_outcome("TP1", 1.8)]
    capped = apply_rr_cap(outcomes, 5.0)
    assert capped[0].r_multiple == pytest.approx(1.8)


def test_none_and_sl_outcomes_always_pass_through_every_cap_unchanged():
    outcomes = [_outcome("NONE", 0.0, duration_minutes=None), _outcome("SL", -1.0)]
    for cap in (5.0, 4.0, 3.0, 2.5, 2.0):
        capped = apply_rr_cap(outcomes, cap)
        assert capped[0].r_multiple == 0.0
        assert capped[1].r_multiple == -1.0


def test_apply_rr_cap_does_not_mutate_the_input_list_or_objects():
    outcomes = _mixed_outcomes()
    original_r_values = [o.r_multiple for o in outcomes]
    apply_rr_cap(outcomes, 2.0)
    assert [o.r_multiple for o in outcomes] == original_r_values


def test_robustness_mode_is_a_frozen_value_object():
    mode = RobustnessMode(label="Cap_3.0", rr_cap=3.0)
    with pytest.raises(Exception):
        mode.rr_cap = 4.0  # type: ignore[misc]
