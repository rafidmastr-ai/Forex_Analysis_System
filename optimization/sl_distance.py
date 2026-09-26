"""SL Distance Integrity Audit -- pure, descriptive analysis functions over
already-computed, already-decided trades (each a plain dict with at least
`direction`, `entry`, `stop_loss`, `hit`, `r_multiple`).

Nothing here feeds back into any Strategy/Entry/SL/TP/Filter/Threshold
decision -- this module only describes trades BacktestEngine has already
resolved (see scripts/sl_distance_audit.py, the only caller that touches
real backtest data). No trade is re-simulated, no minimum-SL-distance rule
is introduced, and no decision logic from core/ or backtesting/ is imported
or exercised here.

Reuses optimization.rr_distribution's global_distribution_summary/percentile
rather than duplicating win-rate/net-R/PF/percentile arithmetic.
"""
from __future__ import annotations

from optimization.rr_distribution import global_distribution_summary, percentile

SL_DIRECTION_CORRECT = "correct"
SL_DIRECTION_EQUAL = "equal"
SL_DIRECTION_INVERTED = "inverted"

DEFAULT_PERCENTILES = [0.1, 1, 5, 10, 25, 50, 75, 90, 95, 99, 100]

TINY_SL_EXTREMELY_SMALL = "extremely_small"
TINY_SL_VERY_SMALL = "very_small"
TINY_SL_NORMAL = "normal"
TINY_SL_LARGE = "large"


def sl_distance(entry: float, stop_loss: float) -> float:
    """abs(entry - stop_loss) -- item 3's absolute_sl_distance, verbatim."""
    return abs(entry - stop_loss)


def pip_distance(distance: float, pip_size: float) -> float | None:
    """Normalizes an absolute price distance into pips using the symbol's
    OWN existing pip_size (core.market_data.models.Symbol.pip_size, as
    already defined in scripts/optimize_strategy.py's SYMBOLS table) --
    never a newly invented conversion."""
    if not pip_size:
        return None
    return distance / pip_size


def precision_units_distance(distance: float, digits: int) -> float:
    """Normalizes distance into units of the symbol's own smallest
    representable price increment (10**-digits, from the existing
    Symbol.digits field) -- how many distinguishable price steps the SL
    distance spans."""
    precision = 10.0 ** (-digits)
    return distance / precision


def is_sub_precision(distance: float, digits: int) -> bool:
    """True if the SL distance is smaller than the symbol's own smallest
    representable price increment (10**-digits) -- i.e. the distance is not
    even one distinguishable price step for this symbol's quoting
    precision."""
    return distance < 10.0 ** (-digits)


def classify_sl_direction(direction: str, entry: float, stop_loss: float) -> str:
    """Item 13: BUY requires SL < Entry, SELL requires SL > Entry. Returns
    'correct', 'equal' (SL == Entry exactly), or 'inverted'."""
    if stop_loss == entry:
        return SL_DIRECTION_EQUAL
    if direction == "BUY":
        return SL_DIRECTION_CORRECT if stop_loss < entry else SL_DIRECTION_INVERTED
    return SL_DIRECTION_CORRECT if stop_loss > entry else SL_DIRECTION_INVERTED


def signed_sl_offset(direction: str, entry: float, stop_loss: float) -> float:
    """Positive = correctly sided (and its magnitude is the real risk
    distance); negative = inverted by that magnitude; zero = SL == Entry.
    Useful for describing HOW FAR past entry an inverted SL landed, not
    just that it is inverted."""
    if direction == "BUY":
        return entry - stop_loss
    return stop_loss - entry


def percentile_table(values: list[float], percentiles: list[float] = DEFAULT_PERCENTILES) -> dict[str, float | None]:
    return {f"p{p:g}": percentile(values, p) for p in percentiles}


def classify_tiny_sl_bucket(distance: float, p5: float | None, p25: float | None, p90: float | None) -> str:
    """Item 5: symbol-aware bucket, boundaries supplied by the CALLER from
    that symbol's OWN observed distribution (P5/P25/P90) -- never a fixed
    cross-symbol threshold. If a boundary is unavailable (e.g. too few
    trades), the trade falls through to the next coarser bucket rather than
    being silently dropped."""
    if p5 is not None and distance < p5:
        return TINY_SL_EXTREMELY_SMALL
    if p25 is not None and distance < p25:
        return TINY_SL_VERY_SMALL
    if p90 is not None and distance < p90:
        return TINY_SL_NORMAL
    return TINY_SL_LARGE


def bucket_r_summary(trades: list[dict]) -> dict:
    """Item 5/15's per-bucket performance statistics, reusing
    global_distribution_summary rather than recomputing win rate/Net R/PF/
    percentiles a second way."""
    summary = global_distribution_summary(trades)
    return {
        "trade_count": summary["total_trades"], "winning_trades": summary["winning_trades"],
        "losing_trades": summary["losing_trades"], "unresolved_trades": summary["unresolved_trades"],
        "win_rate": summary["win_rate"], "net_r": summary["net_r"], "profit_factor": summary["profit_factor"],
        "mean_winning_r": summary["mean_winning_r"], "median_winning_r": summary["median_winning_r"],
        "p95_winning_r": summary["p95_winning_r"], "p99_winning_r": summary["p99_winning_r"],
        "max_winning_r": summary["max_winning_r"], "gross_winning_r": summary["gross_winning_r"],
        "gross_losing_r": summary["gross_losing_r"],
    }


def counterfactual_exclude_below(trades: list[dict], distance_field: str, threshold: float) -> dict:
    """Item 15's POST-TRADE DIAGNOSTIC ONLY counterfactual: excludes every
    trade whose distance_field is below threshold and recomputes summary
    statistics over the remainder. Never re-runs the strategy, never alters
    trade generation -- a pure arithmetic exclusion over already-decided
    trades, exactly like optimization.rr_distribution.trim_analysis."""
    removed = [t for t in trades if t[distance_field] < threshold]
    remaining = [t for t in trades if t[distance_field] >= threshold]
    summary = global_distribution_summary(remaining)
    return {
        "threshold": threshold,
        "trades_removed": len(removed),
        "winners_removed": sum(1 for t in removed if t["hit"] in ("TP1", "TP2")),
        "losses_removed": sum(1 for t in removed if t["hit"] == "SL"),
        "trade_count": summary["total_trades"], "win_rate": summary["win_rate"],
        "net_r": summary["net_r"], "profit_factor": summary["profit_factor"],
        "expectancy": (summary["net_r"] / summary["resolved_trades"]) if summary["resolved_trades"] else 0.0,
        "gross_winning_r": summary["gross_winning_r"], "gross_losing_r": summary["gross_losing_r"],
    }
