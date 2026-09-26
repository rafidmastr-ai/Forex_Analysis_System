"""Regression tests for optimization/sl_distance.py -- the SL Distance
Integrity Audit's pure analysis functions. Purely descriptive: none of
these functions feed into any Strategy/Entry/SL/TP/Filter decision, and
none of them introduce a minimum-SL-distance rule.
"""
from __future__ import annotations

import pytest

from optimization.sl_distance import (
    SL_DIRECTION_CORRECT,
    SL_DIRECTION_EQUAL,
    SL_DIRECTION_INVERTED,
    TINY_SL_EXTREMELY_SMALL,
    TINY_SL_LARGE,
    TINY_SL_NORMAL,
    TINY_SL_VERY_SMALL,
    bucket_r_summary,
    classify_sl_direction,
    classify_tiny_sl_bucket,
    counterfactual_exclude_below,
    is_sub_precision,
    percentile_table,
    pip_distance,
    precision_units_distance,
    signed_sl_offset,
    sl_distance,
)


def _t(hit: str, r: float, **kw) -> dict:
    base = {"hit": hit, "r_multiple": r}
    base.update(kw)
    return base


# --- SL distance calculation ---

def test_sl_distance_is_absolute():
    assert sl_distance(1.1050, 1.1000) == pytest.approx(0.0050)
    assert sl_distance(1.1000, 1.1050) == pytest.approx(0.0050)


# --- BUY / SELL SL direction classification ---

def test_classify_sl_direction_buy_correct():
    assert classify_sl_direction("BUY", entry=1.1050, stop_loss=1.1000) == SL_DIRECTION_CORRECT


def test_classify_sl_direction_sell_correct():
    assert classify_sl_direction("SELL", entry=1.1000, stop_loss=1.1050) == SL_DIRECTION_CORRECT


def test_classify_sl_direction_buy_inverted():
    assert classify_sl_direction("BUY", entry=1.1000, stop_loss=1.1050) == SL_DIRECTION_INVERTED


def test_classify_sl_direction_sell_inverted():
    assert classify_sl_direction("SELL", entry=1.1050, stop_loss=1.1000) == SL_DIRECTION_INVERTED


def test_classify_sl_direction_equal_entry_and_sl():
    assert classify_sl_direction("BUY", entry=1.1000, stop_loss=1.1000) == SL_DIRECTION_EQUAL
    assert classify_sl_direction("SELL", entry=1.1000, stop_loss=1.1000) == SL_DIRECTION_EQUAL


def test_signed_sl_offset_positive_for_correct_buy():
    assert signed_sl_offset("BUY", entry=1.1050, stop_loss=1.1000) == pytest.approx(0.0050)


def test_signed_sl_offset_negative_for_inverted_buy():
    assert signed_sl_offset("BUY", entry=1.1000, stop_loss=1.1050) == pytest.approx(-0.0050)


def test_signed_sl_offset_positive_for_correct_sell():
    assert signed_sl_offset("SELL", entry=1.1000, stop_loss=1.1050) == pytest.approx(0.0050)


def test_signed_sl_offset_negative_for_inverted_sell():
    assert signed_sl_offset("SELL", entry=1.1050, stop_loss=1.1000) == pytest.approx(-0.0050)


def test_signed_sl_offset_zero_when_equal():
    assert signed_sl_offset("BUY", entry=1.1000, stop_loss=1.1000) == 0.0


# --- symbol-aware normalization ---

def test_pip_distance_converts_using_symbol_pip_size():
    assert pip_distance(0.0010, pip_size=0.0001) == pytest.approx(10.0)
    assert pip_distance(2.0, pip_size=0.01) == pytest.approx(200.0)  # XAUUSD-style


def test_pip_distance_none_when_pip_size_missing():
    assert pip_distance(0.0010, pip_size=0.0) is None


def test_precision_units_distance_eurusd_style():
    # digits=5 -> smallest increment 1e-5; a 1e-4 distance is 10 units.
    assert precision_units_distance(1e-4, digits=5) == pytest.approx(10.0)


def test_precision_units_distance_xauusd_style():
    # digits=2 -> smallest increment 1e-2; a 0.5 distance is 50 units.
    assert precision_units_distance(0.5, digits=2) == pytest.approx(50.0)


def test_is_sub_precision_true_below_smallest_increment():
    assert is_sub_precision(3.5e-7, digits=5) is True


def test_is_sub_precision_false_above_smallest_increment():
    assert is_sub_precision(1e-4, digits=5) is False


def test_is_sub_precision_boundary_is_not_sub_precision():
    assert is_sub_precision(1e-5, digits=5) is False


# --- percentile calculations (symbol-aware table) ---

def test_percentile_table_matches_manual_percentile():
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    table = percentile_table(values, percentiles=[0, 50, 100])
    assert table["p0"] == pytest.approx(1.0)
    assert table["p50"] == pytest.approx(5.0)
    assert table["p100"] == pytest.approx(10.0)


def test_percentile_table_empty_values_returns_none_entries():
    table = percentile_table([], percentiles=[50])
    assert table["p50"] is None


# --- tiny-SL classification ---

def test_classify_tiny_sl_bucket_extremely_small():
    assert classify_tiny_sl_bucket(0.5, p5=1.0, p25=5.0, p90=20.0) == TINY_SL_EXTREMELY_SMALL


def test_classify_tiny_sl_bucket_very_small():
    assert classify_tiny_sl_bucket(2.0, p5=1.0, p25=5.0, p90=20.0) == TINY_SL_VERY_SMALL


def test_classify_tiny_sl_bucket_normal():
    assert classify_tiny_sl_bucket(10.0, p5=1.0, p25=5.0, p90=20.0) == TINY_SL_NORMAL


def test_classify_tiny_sl_bucket_large():
    assert classify_tiny_sl_bucket(30.0, p5=1.0, p25=5.0, p90=20.0) == TINY_SL_LARGE


def test_classify_tiny_sl_bucket_missing_boundaries_falls_through_gracefully():
    assert classify_tiny_sl_bucket(5.0, p5=None, p25=None, p90=None) == TINY_SL_LARGE


# --- bucket R summary (reuses global_distribution_summary) ---

def test_bucket_r_summary_basic():
    trades = [_t("TP1", 2.0), _t("TP2", 8.0), _t("SL", -1.0)]
    summary = bucket_r_summary(trades)
    assert summary["trade_count"] == 3
    assert summary["winning_trades"] == 2
    assert summary["losing_trades"] == 1
    assert summary["net_r"] == pytest.approx(9.0)


def test_bucket_r_summary_empty_returns_none_percentiles_not_errors():
    summary = bucket_r_summary([])
    assert summary["trade_count"] == 0
    assert summary["mean_winning_r"] is None


# --- counterfactual filtering (post-trade diagnostic only) ---

def test_counterfactual_exclude_below_removes_only_tiny_distance_trades():
    trades = [
        _t("TP1", 2.0, sl_distance=0.5),
        _t("TP2", 50.0, sl_distance=0.001),  # tiny -- should be excluded
        _t("SL", -1.0, sl_distance=0.5),
    ]
    result = counterfactual_exclude_below(trades, "sl_distance", threshold=0.01)
    assert result["trades_removed"] == 1
    assert result["winners_removed"] == 1
    assert result["losses_removed"] == 0
    assert result["trade_count"] == 2
    assert result["net_r"] == pytest.approx(1.0)  # 2.0 win - 1.0 loss, the 50.0 win excluded


def test_counterfactual_exclude_below_never_touches_trades_at_or_above_threshold():
    trades = [_t("TP1", 3.0, sl_distance=1.0), _t("SL", -1.0, sl_distance=1.0)]
    result = counterfactual_exclude_below(trades, "sl_distance", threshold=0.5)
    assert result["trades_removed"] == 0
    assert result["trade_count"] == 2


def test_counterfactual_exclude_below_zero_threshold_removes_nothing():
    trades = [_t("TP1", 3.0, sl_distance=0.0001)]
    result = counterfactual_exclude_below(trades, "sl_distance", threshold=0.0)
    assert result["trades_removed"] == 0
