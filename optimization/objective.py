"""Composite optimization objective.

Win Rate alone is explicitly rejected as an objective (a strategy can win
often on tiny R and still lose money, or win rarely on huge R and still be
excellent). This module computes a full set of R-multiple-based
performance metrics from a list of `TradeOutcome`, then combines them into
one composite score with explicit, documented penalties — never a bare
win-rate maximization.

R-multiple convention (see backtesting/engine.py): a win pays the setup's
own realized_risk_reward_tp1/tp2 (dynamic, never a fixed ratio), a loss
pays exactly -1.0R, and a trade still open when the backtest window ends
("NONE") is excluded from every R-based statistic — it neither won nor
lost, so counting it either way would misrepresent the strategy.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from backtesting.engine import TradeOutcome

MIN_TRADES_FOR_FULL_CREDIT = 30
PROFIT_FACTOR_CAP = 3.0  # beyond this, more "wins with no losses" isn't a meaningfully bigger edge
STABILITY_CHUNKS = 4     # number of time-ordered sub-periods used to measure result dispersion


@dataclass(frozen=True)
class PerformanceMetrics:
    trade_count: int
    resolved_count: int
    win_rate: float          # TP1-or-TP2 hits / resolved trades
    tp1_rate: float
    tp2_rate: float
    sl_rate: float
    none_rate: float          # fraction of ALL setups (incl. unresolved) still open at window end
    expectancy: float         # mean R across resolved trades (== average_r; both names kept per spec)
    average_r: float
    net_r: float               # sum of R across resolved trades
    profit_factor: float        # sum(positive R) / abs(sum(negative R)); inf if zero losses, 0 if zero wins
    max_drawdown_r: float        # largest peak-to-trough drop in the cumulative R curve (>= 0)
    instability: float            # dispersion of per-chunk average R across STABILITY_CHUNKS time slices (>= 0)


def compute_metrics(outcomes: list[TradeOutcome]) -> PerformanceMetrics:
    total = len(outcomes)
    resolved = [o for o in outcomes if o.hit != "NONE"]
    n = len(resolved)

    if n == 0:
        return PerformanceMetrics(
            trade_count=total, resolved_count=0, win_rate=0.0, tp1_rate=0.0, tp2_rate=0.0, sl_rate=0.0,
            none_rate=(total / total) if total else 0.0, expectancy=0.0, average_r=0.0, net_r=0.0,
            profit_factor=0.0, max_drawdown_r=0.0, instability=0.0,
        )

    wins = [o for o in resolved if o.hit in ("TP1", "TP2")]
    losses = [o for o in resolved if o.hit == "SL"]
    r_values = [o.r_multiple for o in resolved]

    net_r = sum(r_values)
    expectancy = net_r / n
    gross_win = sum(r for r in r_values if r > 0)
    gross_loss = abs(sum(r for r in r_values if r < 0))
    if gross_loss == 0:
        profit_factor = math.inf if gross_win > 0 else 0.0
    else:
        profit_factor = gross_win / gross_loss

    max_dd = _max_drawdown(r_values)
    instability = _instability(resolved)

    return PerformanceMetrics(
        trade_count=total,
        resolved_count=n,
        win_rate=len(wins) / n,
        tp1_rate=sum(1 for o in resolved if o.hit == "TP1") / n,
        tp2_rate=sum(1 for o in resolved if o.hit == "TP2") / n,
        sl_rate=len(losses) / n,
        none_rate=(total - n) / total if total else 0.0,
        expectancy=expectancy,
        average_r=expectancy,
        net_r=net_r,
        profit_factor=profit_factor,
        max_drawdown_r=max_dd,
        instability=instability,
    )


def _max_drawdown(r_values: list[float]) -> float:
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in r_values:
        cumulative += r
        peak = max(peak, cumulative)
        max_dd = max(max_dd, peak - cumulative)
    return max_dd


def _instability(resolved: list[TradeOutcome]) -> float:
    """Standard deviation of average-R across STABILITY_CHUNKS equal,
    time-ordered slices of the resolved trades — a strategy whose edge
    lives entirely in one slice of the period (over-reliant on a single
    stretch of time) scores worse here even if its overall net R is fine.

    Requires at least 10 resolved trades per chunk before computing this at
    all: with fewer, per-chunk average-R is dominated by small-sample noise
    rather than any real regime effect, and penalizing that would punish
    small-but-genuine backtests for a measurement artifact, not instability.
    """
    if len(resolved) < STABILITY_CHUNKS * 10:
        return 0.0
    chunk_size = len(resolved) // STABILITY_CHUNKS
    chunk_means = []
    for i in range(STABILITY_CHUNKS):
        start = i * chunk_size
        end = start + chunk_size if i < STABILITY_CHUNKS - 1 else len(resolved)
        chunk = resolved[start:end]
        if chunk:
            chunk_means.append(sum(o.r_multiple for o in chunk) / len(chunk))
    if len(chunk_means) < 2:
        return 0.0
    mean = sum(chunk_means) / len(chunk_means)
    variance = sum((m - mean) ** 2 for m in chunk_means) / len(chunk_means)
    return math.sqrt(variance)


def composite_objective(metrics: PerformanceMetrics, min_trades: int = MIN_TRADES_FOR_FULL_CREDIT) -> float:
    """Higher is better. Documented formula (all terms are simple and
    intentionally inspectable rather than a black-box combination):

        raw = 10 * expectancy                    # the main profitability signal, in R
            + 5  * min(profit_factor, CAP) / CAP  # rewards a real edge, capped so one clean run can't dominate
            - 0.5 * max_drawdown_r                # 1 R of drawdown costs half a point
            - 5  * instability                    # a strategy whose edge is concentrated in one time slice is penalized

        composite = raw * trade_count_factor

    trade_count_factor ramps linearly from 0 to 1 as resolved_count goes
    from 0 to min_trades, then stays at 1 — a parameter set that "wins" on
    a handful of trades cannot outscore one with a real sample size, no
    matter how good those few trades looked (guards against exactly the
    kind of overfit-to-noise result this framework exists to reject).
    """
    trade_count_factor = min(metrics.resolved_count / min_trades, 1.0) if min_trades > 0 else 1.0
    pf_component = min(metrics.profit_factor, PROFIT_FACTOR_CAP) / PROFIT_FACTOR_CAP if math.isfinite(metrics.profit_factor) else 1.0

    raw = (10 * metrics.expectancy) + (5 * pf_component) - (0.5 * metrics.max_drawdown_r) - (5 * metrics.instability)
    return raw * trade_count_factor
