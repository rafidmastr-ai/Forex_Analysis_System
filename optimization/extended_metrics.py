"""Extended, purely descriptive trade statistics for the current-version
evaluation report (scripts/final_evaluation.py) — everything
optimization/objective.py's PerformanceMetrics doesn't already provide
(wins/losses counts, average winning/losing R, consecutive win/loss
streaks, trade duration, planned R:R distribution).

This module NEVER feeds composite_objective or any decision/selection
logic — it exists purely to describe what already happened in a
BacktestReport, and adding it changes no strategy, weight, filter or
threshold anywhere in the system.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean

from backtesting.engine import TradeOutcome


@dataclass(frozen=True)
class ExtendedMetrics:
    trade_count: int
    resolved_count: int
    none_count: int
    wins: int
    losses: int
    win_rate: float
    tp1_rate: float
    tp2_rate: float
    sl_rate: float
    net_r: float
    profit_factor: float
    expectancy: float
    average_r: float
    average_winning_r: float
    average_losing_r: float
    max_drawdown_r: float
    max_consecutive_wins: int
    max_consecutive_losses: int
    average_duration_minutes: float | None
    planned_rr_tp1: dict[str, float]  # distribution of SelectedSetup.risk_reward_tp1 at signal time (every trade, resolved or not)
    planned_rr_tp2: dict[str, float]


def _percentiles(values: list[float]) -> dict[str, float]:
    if not values:
        return {}
    s = sorted(values)

    def pct(p: float) -> float:
        idx = min(len(s) - 1, max(0, round(p / 100 * (len(s) - 1))))
        return s[idx]

    return {"min": s[0], "p25": pct(25), "median": pct(50), "p75": pct(75), "max": s[-1], "mean": mean(s)}


def _max_drawdown(r_values: list[float]) -> float:
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in r_values:
        cumulative += r
        peak = max(peak, cumulative)
        max_dd = max(max_dd, peak - cumulative)
    return max_dd


def compute_extended_metrics(outcomes: list[TradeOutcome]) -> ExtendedMetrics:
    ordered = sorted(outcomes, key=lambda o: o.opened_at)
    resolved = [o for o in ordered if o.hit != "NONE"]
    n = len(resolved)
    wins = [o for o in resolved if o.hit in ("TP1", "TP2")]
    losses = [o for o in resolved if o.hit == "SL"]

    r_values = [o.r_multiple for o in resolved]
    win_r = [o.r_multiple for o in wins]
    loss_r = [o.r_multiple for o in losses]

    net_r = sum(r_values)
    gross_win = sum(r for r in r_values if r > 0)
    gross_loss = abs(sum(r for r in r_values if r < 0))
    if gross_loss == 0:
        profit_factor = math.inf if gross_win > 0 else 0.0
    else:
        profit_factor = gross_win / gross_loss

    max_w = cur_w = 0
    max_l = cur_l = 0
    for o in resolved:
        if o.hit in ("TP1", "TP2"):
            cur_w += 1
            cur_l = 0
        else:
            cur_l += 1
            cur_w = 0
        max_w = max(max_w, cur_w)
        max_l = max(max_l, cur_l)

    durations = [(o.closed_at - o.opened_at).total_seconds() / 60 for o in resolved if o.closed_at is not None]

    return ExtendedMetrics(
        trade_count=len(ordered), resolved_count=n, none_count=len(ordered) - n,
        wins=len(wins), losses=len(losses),
        win_rate=(len(wins) / n) if n else 0.0,
        tp1_rate=(sum(1 for o in resolved if o.hit == "TP1") / n) if n else 0.0,
        tp2_rate=(sum(1 for o in resolved if o.hit == "TP2") / n) if n else 0.0,
        sl_rate=(len(losses) / n) if n else 0.0,
        net_r=net_r, profit_factor=profit_factor,
        expectancy=(net_r / n) if n else 0.0, average_r=(net_r / n) if n else 0.0,
        average_winning_r=mean(win_r) if win_r else 0.0,
        average_losing_r=mean(loss_r) if loss_r else 0.0,
        max_drawdown_r=_max_drawdown(r_values),
        max_consecutive_wins=max_w, max_consecutive_losses=max_l,
        average_duration_minutes=mean(durations) if durations else None,
        planned_rr_tp1=_percentiles([o.setup.risk_reward_tp1 for o in ordered]),
        planned_rr_tp2=_percentiles([o.setup.risk_reward_tp2 for o in ordered]),
    )
