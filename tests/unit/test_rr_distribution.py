"""Regression tests for optimization/rr_distribution.py -- the R:R
Distribution Audit's pure analysis functions. Purely descriptive: none of
these functions are called by, or feed back into, any Strategy/Weight/
Filter/Threshold/Entry/TP/SL decision.
"""
from __future__ import annotations

import math

import pytest

from optimization.rr_distribution import (
    BELOW_FLOOR_LABEL,
    bin_distribution,
    classify_rr_bin,
    gross_share_above_thresholds,
    independent_r_multiple,
    percentile,
    profit_concentration,
    trim_analysis,
)


def _t(hit: str, r: float) -> dict:
    return {"hit": hit, "r_multiple": r}


# --- R:R bin classification ---

@pytest.mark.parametrize("r, expected", [
    (1.0, BELOW_FLOOR_LABEL),
    (1.49, BELOW_FLOOR_LABEL),
    (1.5, "1.5-2R"),
    (1.99, "1.5-2R"),
    (2.0, "2-3R"),
    (2.99, "2-3R"),
    (3.0, "3-4R"),
    (4.0, "4-5R"),
    (4.99, "4-5R"),
    (5.0, "5-10R"),
    (9.99, "5-10R"),
    (10.0, "10-20R"),
    (19.99, "10-20R"),
    (20.0, "20-50R"),
    (49.99, "20-50R"),
    (50.0, "50R+"),
    (1234.5, "50R+"),
])
def test_classify_rr_bin(r, expected):
    assert classify_rr_bin(r) == expected


def test_bin_distribution_never_silently_discards_any_category():
    trades = [
        _t("TP1", 1.2),   # below floor
        _t("TP1", 1.8),   # 1.5-2R
        _t("TP2", 7.0),   # 5-10R
        _t("SL", -1.0),
        _t("SL", -1.0),
        _t("NONE", 0.0),
    ]
    dist = bin_distribution(trades)
    assert dist[BELOW_FLOOR_LABEL]["trade_count"] == 1
    assert dist["1.5-2R"]["trade_count"] == 1
    assert dist["5-10R"]["trade_count"] == 1
    assert dist["losses_SL"]["trade_count"] == 2
    assert dist["unresolved_NONE"]["trade_count"] == 1
    # every win accounted for across bins
    total_wins_in_bins = sum(v["trade_count"] for k, v in dist.items() if k not in ("losses_SL", "unresolved_NONE"))
    assert total_wins_in_bins == 3


def test_bin_distribution_percentages_sum_to_one_across_winning_bins():
    trades = [_t("TP1", 1.8), _t("TP1", 2.5), _t("TP2", 8.0), _t("TP2", 60.0)]
    dist = bin_distribution(trades)
    pct_sum = sum(v["pct_of_winning_trades"] for k, v in dist.items() if k not in ("losses_SL", "unresolved_NONE"))
    assert pct_sum == pytest.approx(1.0)
    r_pct_sum = sum(v["pct_of_gross_winning_r"] for k, v in dist.items() if k not in ("losses_SL", "unresolved_NONE"))
    assert r_pct_sum == pytest.approx(1.0)


# --- >5R / >10R / >20R / >50R calculations ---

def test_gross_share_above_thresholds():
    trades = [_t("TP1", 1.8), _t("TP2", 6.0), _t("TP2", 12.0), _t("TP2", 25.0), _t("TP2", 60.0), _t("SL", -1.0)]
    shares = gross_share_above_thresholds(trades)
    gross_win = 1.8 + 6.0 + 12.0 + 25.0 + 60.0
    assert shares[">5R"]["trade_count"] == 4  # 6, 12, 25, 60
    assert shares[">10R"]["trade_count"] == 3  # 12, 25, 60
    assert shares[">20R"]["trade_count"] == 2  # 25, 60
    assert shares[">50R"]["trade_count"] == 1  # 60
    assert shares[">50R"]["pct_of_gross_winning_r"] == pytest.approx(60.0 / gross_win)


def test_gross_share_above_thresholds_empty_wins_returns_zero_not_nan():
    trades = [_t("SL", -1.0), _t("NONE", 0.0)]
    shares = gross_share_above_thresholds(trades)
    for v in shares.values():
        assert v["trade_count"] == 0
        assert v["pct_of_gross_winning_r"] == 0.0


# --- percentile calculations ---

def test_percentile_matches_nearest_rank_method():
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    assert percentile(values, 50) == pytest.approx(5.0)  # matches extended_metrics' own convention
    assert percentile(values, 100) == pytest.approx(10.0)
    assert percentile(values, 0) == pytest.approx(1.0)


def test_percentile_empty_list_returns_none():
    assert percentile([], 50) is None


# --- profit concentration ---

def test_profit_concentration_top_100pct_equals_gross_win():
    trades = [_t("TP1", 2.0), _t("TP2", 5.0), _t("TP2", 10.0)]
    conc = profit_concentration(trades, top_fractions=[1.0])
    assert conc["top_100pct"]["total_realized_r"] == pytest.approx(17.0)
    assert conc["top_100pct"]["pct_of_gross_winning_r"] == pytest.approx(1.0)


def test_profit_concentration_top_fraction_uses_highest_r_first():
    trades = [_t("TP1", 1.5), _t("TP2", 3.0), _t("TP2", 100.0)]
    conc = profit_concentration(trades, top_fractions=[0.34])  # ~1 of 3 trades
    assert conc["top_34pct"]["n_trades"] == 1
    assert conc["top_34pct"]["total_realized_r"] == pytest.approx(100.0)


def test_profit_concentration_no_winners_returns_zero_not_nan():
    trades = [_t("SL", -1.0)]
    conc = profit_concentration(trades, top_fractions=[0.1])
    assert conc["top_10pct"]["total_realized_r"] == 0.0
    assert conc["top_10pct"]["pct_of_gross_winning_r"] == 0.0


# --- trim calculations ---

def test_trim_removes_highest_r_winners_only_and_never_touches_losses():
    trades = [_t("TP1", 1.8), _t("TP2", 5.0), _t("TP2", 100.0), _t("SL", -1.0), _t("SL", -1.0)]
    trimmed = trim_analysis(trades, trim_fractions=[0.34])  # trims 1 of 3 winners (the 100.0 one)
    key = "trim_34pct"
    assert trimmed[key]["n_trades_removed"] == 1
    assert trimmed[key]["wins"] == 2
    assert trimmed[key]["losses"] == 2  # untouched
    assert trimmed[key]["gross_winning_r"] == pytest.approx(1.8 + 5.0)
    assert trimmed[key]["gross_losing_r"] == pytest.approx(2.0)
    assert trimmed[key]["net_r"] == pytest.approx(1.8 + 5.0 - 2.0)


def test_trim_never_increases_net_r_relative_to_baseline():
    import random
    random.seed(0)
    trades = [_t("TP1", random.uniform(1.5, 5)) for _ in range(50)] + \
             [_t("TP2", random.uniform(5, 100)) for _ in range(10)] + \
             [_t("SL", -1.0) for _ in range(120)]
    from optimization.rr_distribution import global_distribution_summary
    baseline_net_r = global_distribution_summary(trades)["net_r"]
    trimmed = trim_analysis(trades)
    for entry in trimmed.values():
        assert entry["net_r"] <= baseline_net_r + 1e-9


def test_trim_preserves_unresolved_trade_count():
    trades = [_t("TP2", 10.0), _t("TP1", 2.0), _t("SL", -1.0), _t("NONE", 0.0), _t("NONE", 0.0)]
    trimmed = trim_analysis(trades, trim_fractions=[0.5])
    key = "trim_50pct"
    # trade_count = resolved (after trim) + unresolved(2, untouched)
    assert trimmed[key]["trade_count"] == trimmed[key]["wins"] + trimmed[key]["losses"] + 2


# --- BUY / SELL independent R calculation ---

def test_independent_r_multiple_buy_winning_trade():
    # entry=1.10, sl=1.095 (risk=0.005), tp1=1.11 (reward=0.01) -> R=2.0
    r = independent_r_multiple("BUY", entry=1.10, stop_loss=1.095, exit_price=1.11)
    assert r == pytest.approx(2.0)


def test_independent_r_multiple_sell_winning_trade():
    # entry=1.10, sl=1.105 (risk=0.005), tp1=1.09 (reward=0.01) -> R=2.0
    r = independent_r_multiple("SELL", entry=1.10, stop_loss=1.105, exit_price=1.09)
    assert r == pytest.approx(2.0)


def test_independent_r_multiple_buy_losing_trade_is_minus_one():
    r = independent_r_multiple("BUY", entry=1.10, stop_loss=1.095, exit_price=1.095)
    assert r == pytest.approx(-1.0)


def test_independent_r_multiple_sell_losing_trade_is_minus_one():
    r = independent_r_multiple("SELL", entry=1.10, stop_loss=1.105, exit_price=1.105)
    assert r == pytest.approx(-1.0)


# --- zero / near-zero SL distance handling ---

def test_independent_r_multiple_zero_sl_distance_returns_none_not_inf_or_nan():
    r = independent_r_multiple("BUY", entry=1.10, stop_loss=1.10, exit_price=1.12)
    assert r is None
    assert not (isinstance(r, float) and math.isnan(r))


def test_independent_r_multiple_near_zero_sl_distance_produces_large_but_finite_r():
    r = independent_r_multiple("BUY", entry=1.10000, stop_loss=1.09999, exit_price=1.11)
    assert r is not None
    assert math.isfinite(r)
    assert r > 100  # tiny risk denominator -> a large R, exactly as the audit's thesis describes


# --- unresolved trade handling ---

def test_unresolved_trades_excluded_from_r_percentiles_and_gross_r():
    from optimization.rr_distribution import global_distribution_summary
    trades = [_t("TP1", 2.0), _t("NONE", 0.0), _t("NONE", 0.0)]
    summary = global_distribution_summary(trades)
    assert summary["unresolved_trades"] == 2
    assert summary["total_trades"] == 3
    assert summary["resolved_trades"] == 1
    assert summary["mean_winning_r"] == pytest.approx(2.0)  # the two NONE trades (r=0.0) never pollute this


def test_unresolved_only_trades_returns_none_percentiles_not_errors():
    from optimization.rr_distribution import global_distribution_summary
    summary = global_distribution_summary([_t("NONE", 0.0), _t("NONE", 0.0)])
    assert summary["mean_winning_r"] is None
    assert summary["p95_winning_r"] is None
    assert summary["win_rate"] == 0.0
