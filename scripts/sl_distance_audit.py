"""SL Distance Integrity Audit: a direct follow-up to the R:R Distribution
Audit, investigating WHY some winning trades have an extremely small
Entry-to-SL distance.

Diagnostic-only, reusing the ALREADY-CAPTURED trade-level data from
data/optimization_results/trade_level_audit.json (itself produced by the
R:R Distribution Audit's 96-cell run) -- no cell is re-run, no signal is
regenerated, and no Strategy/Entry/SL/TP/Filter/Threshold/minimum-SL-
distance logic is introduced or changed anywhere in this script.

Baseline integrity is re-verified by independently recomputing each of the
96 cells' trade_count/wins/losses/win_rate/net_r/profit_factor/expectancy
directly from the captured trade list and comparing against
data/optimization_results/m1_full_backtest.json -- a fresh, independent
check (not merely re-printing the R:R audit's own prior validation),
without regenerating any signal.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from statistics import mean, median
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from optimization.rr_distribution import percentile  # noqa: E402
from optimization.sl_distance import (  # noqa: E402
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
from scripts.optimize_strategy import SYMBOLS  # noqa: E402

TRADE_LEVEL_AUDIT_PATH = Path("data/optimization_results/trade_level_audit.json")
BASELINE_PATH = Path("data/optimization_results/m1_full_backtest.json")
OUT_JSON = Path("data/optimization_results/sl_distance_audit.json")
FLOAT_TOLERANCE = 1e-6

STRATEGIES = ["Classic", "SMC", "ICT", "SweepDisplacement"]
SYMBOL_NAMES = ["EURUSD", "XAUUSD", "GBPUSD", "NZDUSD"]
TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4"]
SL_DIST_VS_R_EDGES = [0.0, 1.0, 5.0, 10.0, 25.0, 50.0, 100.0, float("inf")]  # pips
COUNTERFACTUAL_PERCENTILES = [0.1, 0.5, 1.0, 5.0]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _numeric_close(a, b, tol: float = FLOAT_TOLERANCE) -> bool:
    if a == b:
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if a == float("inf") or b == float("inf"):
            return a == b
        return abs(a - b) <= tol
    return False


def enrich_trade(t: dict) -> dict:
    """Adds SL-distance-derived fields to a captured trade record, AFTER
    BacktestEngine already produced it -- nothing here influences Entry/SL/
    TP/direction/outcome."""
    symbol = SYMBOLS[t["symbol"]]
    distance = sl_distance(t["entry"], t["stop_loss"])
    t = dict(t)
    t["abs_sl_distance"] = distance
    t["pip_sl_distance"] = pip_distance(distance, symbol.pip_size)
    t["precision_units_sl_distance"] = precision_units_distance(distance, symbol.digits)
    t["is_sub_precision"] = is_sub_precision(distance, symbol.digits)
    t["sl_direction"] = classify_sl_direction(t["direction"], t["entry"], t["stop_loss"])
    t["signed_sl_offset"] = signed_sl_offset(t["direction"], t["entry"], t["stop_loss"])
    return t


def baseline_integrity_check(trades: list[dict], baseline: dict) -> dict:
    """Independently recomputes each of the 96 cells' summary metrics
    directly from the captured trade list (grouped fresh here, not reusing
    the R:R audit's own cached per-cell summaries) and compares against
    data/optimization_results/m1_full_backtest.json. Expected: zero
    differences; any difference is reported, never hidden."""
    by_cell: dict[tuple[str, str, str], list[dict]] = {}
    for t in trades:
        by_cell.setdefault((t["strategy"], t["symbol"], t["timeframe"]), []).append(t)

    mismatches: dict[str, list[str]] = {}
    cells_checked = 0
    for strategy in STRATEGIES:
        for symbol in SYMBOL_NAMES:
            for tf in TIMEFRAMES:
                key = (strategy, symbol, tf)
                cell_trades = by_cell.get(key, [])
                prev_cell = baseline.get("results", {}).get(strategy, {}).get(symbol, {}).get(tf)
                if prev_cell is None or prev_cell.get("status") == "FAILED":
                    if cell_trades:
                        mismatches[f"{strategy}/{symbol}/{tf}"] = ["no comparable prior Baseline cell, but trades were captured"]
                    continue
                cells_checked += 1
                resolved = [t for t in cell_trades if t["hit"] != "NONE"]
                wins = [t for t in resolved if t["hit"] in ("TP1", "TP2")]
                losses = [t for t in resolved if t["hit"] == "SL"]
                net_r = sum(t["r_multiple"] for t in resolved)
                gross_win = sum(t["r_multiple"] for t in wins)
                gross_loss = abs(sum(t["r_multiple"] for t in losses))
                win_rate = (len(wins) / len(resolved)) if resolved else 0.0
                pf = (gross_win / gross_loss) if gross_loss else (float("inf") if gross_win > 0 else 0.0)
                expectancy = (net_r / len(resolved)) if resolved else 0.0
                checks = [
                    ("trade_count", prev_cell["trade_count"], len(cell_trades)),
                    ("resolved_count", prev_cell["resolved_count"], len(resolved)),
                    ("tp1_count", prev_cell["tp1_count"], sum(1 for t in resolved if t["hit"] == "TP1")),
                    ("tp2_count", prev_cell["tp2_count"], sum(1 for t in resolved if t["hit"] == "TP2")),
                    ("sl_count", prev_cell["sl_count"], len(losses)),
                    ("win_rate", prev_cell["metrics"]["win_rate"], win_rate),
                    ("net_r", prev_cell["metrics"]["net_r"], net_r),
                    ("profit_factor", prev_cell["metrics"]["profit_factor"], pf),
                    ("expectancy", prev_cell["metrics"]["expectancy"], expectancy),
                ]
                cell_mismatches = [f"{name}: baseline={expected}, recomputed={actual}"
                                   for name, expected, actual in checks if not _numeric_close(expected, actual)]
                if cell_mismatches:
                    mismatches[f"{strategy}/{symbol}/{tf}"] = cell_mismatches

    return {
        "cells_checked": cells_checked, "baseline_file_sha256": _sha256(BASELINE_PATH),
        "mismatches": mismatches, "passed": not mismatches,
    }


def symbol_distribution(trades: list[dict]) -> dict:
    """Item 4: per-symbol SL distance distribution (absolute and pip-
    normalized), plus item 5's bucket boundaries (that symbol's own P5/P25/
    P90 of absolute distance)."""
    result: dict[str, dict] = {}
    for symbol in SYMBOL_NAMES:
        symbol_trades = [t for t in trades if t["symbol"] == symbol]
        distances = [t["abs_sl_distance"] for t in symbol_trades]
        pip_distances = [t["pip_sl_distance"] for t in symbol_trades if t["pip_sl_distance"] is not None]
        wins = [t for t in symbol_trades if t["hit"] in ("TP1", "TP2")]
        losses = [t for t in symbol_trades if t["hit"] == "SL"]
        spec = SYMBOLS[symbol]
        result[symbol] = {
            "trade_count": len(symbol_trades), "winning_trades": len(wins), "losing_trades": len(losses),
            "sl_hit_trades": len(losses),
            "pip_size": spec.pip_size, "digits": spec.digits,
            "sub_precision_count": sum(1 for t in symbol_trades if t["is_sub_precision"]),
            "absolute_distance_percentiles": percentile_table(distances) if distances else {},
            "pip_distance_percentiles": percentile_table(pip_distances) if pip_distances else {},
            "min_absolute_distance": min(distances) if distances else None,
            "max_absolute_distance": max(distances) if distances else None,
        }
    return result


def compute_bucket_boundaries(trades: list[dict]) -> dict[str, dict]:
    """Item 5: per-symbol P5/P25/P90 of absolute SL distance, used as the
    data-derived boundaries for the extremely_small/very_small/normal/large
    classification -- never a fixed cross-symbol threshold."""
    boundaries: dict[str, dict] = {}
    for symbol in SYMBOL_NAMES:
        distances = [t["abs_sl_distance"] for t in trades if t["symbol"] == symbol]
        boundaries[symbol] = {
            "p5": percentile(distances, 5), "p25": percentile(distances, 25), "p90": percentile(distances, 90),
        }
    return boundaries


def classify_all_tiny_sl(trades: list[dict], boundaries: dict[str, dict]) -> list[dict]:
    out = []
    for t in trades:
        b = boundaries[t["symbol"]]
        t = dict(t)
        t["tiny_sl_bucket"] = classify_tiny_sl_bucket(t["abs_sl_distance"], b["p5"], b["p25"], b["p90"])
        out.append(t)
    return out


def strategy_breakdown(trades: list[dict]) -> dict:
    result = {}
    for strategy in STRATEGIES:
        s_trades = [t for t in trades if t["strategy"] == strategy]
        by_bucket = {}
        for bucket in ("extremely_small", "very_small", "normal", "large"):
            by_bucket[bucket] = sum(1 for t in s_trades if t["tiny_sl_bucket"] == bucket)
        by_symbol = {sym: sum(1 for t in s_trades if t["symbol"] == sym and t["tiny_sl_bucket"] == "extremely_small")
                     for sym in SYMBOL_NAMES}
        by_tf = {tf: sum(1 for t in s_trades if t["timeframe"] == tf and t["tiny_sl_bucket"] == "extremely_small")
                 for tf in TIMEFRAMES}
        result[strategy] = {
            "trade_count": len(s_trades),
            "tiny_sl_bucket_counts": by_bucket,
            "extremely_small_by_symbol": by_symbol,
            "extremely_small_by_timeframe": by_tf,
            "sl_direction_counts": _direction_counts(s_trades),
        }
    return result


def _direction_counts(trades: list[dict]) -> dict:
    correct = sum(1 for t in trades if t["sl_direction"] == "correct")
    equal = sum(1 for t in trades if t["sl_direction"] == "equal")
    inverted = sum(1 for t in trades if t["sl_direction"] == "inverted")
    total = len(trades)
    return {
        "correct": correct, "equal": equal, "inverted": inverted, "total": total,
        "pct_correct": (correct / total) if total else 0.0,
        "pct_equal": (equal / total) if total else 0.0,
        "pct_inverted": (inverted / total) if total else 0.0,
    }


def timeframe_breakdown(trades: list[dict]) -> dict:
    result = {}
    for tf in TIMEFRAMES:
        tf_trades = [t for t in trades if t["timeframe"] == tf]
        distances = [t["abs_sl_distance"] for t in tf_trades]
        pip_dists = [t["pip_sl_distance"] for t in tf_trades if t["pip_sl_distance"] is not None]
        wins = [t for t in tf_trades if t["hit"] in ("TP1", "TP2")]
        result[tf] = {
            "trade_count": len(tf_trades),
            "tiny_sl_count": sum(1 for t in tf_trades if t["tiny_sl_bucket"] == "extremely_small"),
            "tiny_sl_pct": (sum(1 for t in tf_trades if t["tiny_sl_bucket"] == "extremely_small") / len(tf_trades)) if tf_trades else 0.0,
            "median_sl_distance": median(distances) if distances else None,
            "p1_sl_distance": percentile(distances, 1),
            "p5_sl_distance": percentile(distances, 5),
            "p99_sl_distance": percentile(distances, 99),
            "median_pip_distance": median(pip_dists) if pip_dists else None,
            "extreme_r_winner_count_gt20": sum(1 for t in wins if t["r_multiple"] > 20),
            "extreme_r_winner_count_gt50": sum(1 for t in wins if t["r_multiple"] > 50),
        }
    return result


def cell_breakdown(trades: list[dict]) -> dict:
    by_cell: dict[tuple[str, str, str], list[dict]] = {}
    for t in trades:
        by_cell.setdefault((t["strategy"], t["symbol"], t["timeframe"]), []).append(t)

    result: dict[str, dict] = {}
    for strategy in STRATEGIES:
        for symbol in SYMBOL_NAMES:
            for tf in TIMEFRAMES:
                key = (strategy, symbol, tf)
                cell_trades = by_cell.get(key, [])
                distances = [t["abs_sl_distance"] for t in cell_trades]
                wins = [t for t in cell_trades if t["hit"] in ("TP1", "TP2")]
                losses = [t for t in cell_trades if t["hit"] == "SL"]
                net_r = sum(t["r_multiple"] for t in cell_trades if t["hit"] != "NONE")
                gross_win = sum(t["r_multiple"] for t in wins)
                gross_loss = abs(sum(t["r_multiple"] for t in losses))
                pf = (gross_win / gross_loss) if gross_loss else (float("inf") if gross_win > 0 else 0.0)
                tiny_count = sum(1 for t in cell_trades if t["tiny_sl_bucket"] == "extremely_small")
                result["/".join(key)] = {
                    "strategy": strategy, "symbol": symbol, "timeframe": tf,
                    "trade_count": len(cell_trades),
                    "min_sl_distance": min(distances) if distances else None,
                    "median_sl_distance": median(distances) if distances else None,
                    "p1_sl_distance": percentile(distances, 1),
                    "p5_sl_distance": percentile(distances, 5),
                    "p99_sl_distance": percentile(distances, 99),
                    "tiny_sl_count": tiny_count,
                    "tiny_sl_pct": (tiny_count / len(cell_trades)) if cell_trades else 0.0,
                    "winners_gt10r": sum(1 for t in wins if t["r_multiple"] > 10),
                    "winners_gt20r": sum(1 for t in wins if t["r_multiple"] > 20),
                    "winners_gt50r": sum(1 for t in wins if t["r_multiple"] > 50),
                    "net_r": net_r, "profit_factor": pf,
                }
    return result


def extreme_r_trades(trades: list[dict], threshold: float) -> list[dict]:
    wins = [t for t in trades if t["hit"] in ("TP1", "TP2") and t["r_multiple"] > threshold]
    return sorted(wins, key=lambda t: t["r_multiple"], reverse=True)


def sl_distance_vs_r(trades: list[dict], edges: list[float] = SL_DIST_VS_R_EDGES) -> dict:
    """Item 14: SL distance (in pips, symbol-normalized) -> realized R,
    bucketed by pip-distance ranges shared across symbols."""
    wins = [t for t in trades if t["hit"] in ("TP1", "TP2") and t["pip_sl_distance"] is not None]
    result = {}
    for lo, hi in zip(edges[:-1], edges[1:]):
        label = f"{lo:g}-{hi:g}pips" if hi != float("inf") else f">{lo:g}pips"
        bucket = [t for t in wins if lo <= t["pip_sl_distance"] < hi]
        r_values = [t["r_multiple"] for t in bucket]
        result[label] = {
            "n_winners": len(bucket),
            "mean_r": mean(r_values) if r_values else None,
            "median_r": median(r_values) if r_values else None,
            "p95_r": percentile(r_values, 95),
            "p99_r": percentile(r_values, 99),
            "max_r": max(r_values) if r_values else None,
            "gross_winning_r": sum(r_values),
        }
    return result


def planned_vs_realized_for_extreme(trades: list[dict]) -> dict:
    """Item 16: for extreme-R winners, whether the extreme realized R comes
    from an intentionally large planned RR, an unusually tiny SL distance,
    or both -- classified per trade from already-stored planned_rr_tp1/tp2
    and abs_sl_distance, no speculation."""
    out = []
    for t in trades:
        planned = t["planned_rr_tp1"] if t["hit"] == "TP1" else t["planned_rr_tp2"]
        out.append({
            "strategy": t["strategy"], "symbol": t["symbol"], "timeframe": t["timeframe"],
            "opened_at": t["opened_at"], "r_multiple": t["r_multiple"], "planned_rr_matching_hit": planned,
            "abs_sl_distance": t["abs_sl_distance"], "pip_sl_distance": t["pip_sl_distance"],
            "is_sub_precision": t["is_sub_precision"],
        })
    return {"trades": out}


def main() -> None:
    data = json.loads(TRADE_LEVEL_AUDIT_PATH.read_text())
    baseline = json.loads(BASELINE_PATH.read_text())
    raw_trades = data["trades"]

    trades = [enrich_trade(t) for t in raw_trades]

    integrity = baseline_integrity_check(trades, baseline)

    boundaries = compute_bucket_boundaries(trades)
    trades = classify_all_tiny_sl(trades, boundaries)

    global_bucket_summary = {
        bucket: bucket_r_summary([t for t in trades if t["tiny_sl_bucket"] == bucket])
        for bucket in ("extremely_small", "very_small", "normal", "large")
    }
    for bucket, summary in global_bucket_summary.items():
        count = summary["trade_count"]
        summary["pct_of_all_trades"] = (count / len(trades)) if trades else 0.0

    extreme_20 = extreme_r_trades(trades, 20)
    extreme_50 = extreme_r_trades(trades, 50)

    counterfactuals = {}
    for p in COUNTERFACTUAL_PERCENTILES:
        global_threshold = percentile([t["abs_sl_distance"] for t in trades if t["hit"] in ("TP1", "TP2", "SL")], p)
        if global_threshold is None:
            continue
        counterfactuals[f"below_p{p:g}_global"] = counterfactual_exclude_below(trades, "abs_sl_distance", global_threshold)

    output: dict[str, Any] = {
        "source_trade_level_audit": str(TRADE_LEVEL_AUDIT_PATH),
        "baseline_reference": str(BASELINE_PATH),
        "symbols": {name: {"pip_size": s.pip_size, "digits": s.digits} for name, s in SYMBOLS.items()},
        "baseline_integrity": integrity,
        "tiny_sl_bucket_boundaries_per_symbol": boundaries,
        "global_sl_direction": _direction_counts(trades),
        "symbol_direction_counts": {sym: _direction_counts([t for t in trades if t["symbol"] == sym]) for sym in SYMBOL_NAMES},
        "timeframe_direction_counts": {tf: _direction_counts([t for t in trades if t["timeframe"] == tf]) for tf in TIMEFRAMES},
        "symbol_distribution": symbol_distribution(trades),
        "global_tiny_sl_bucket_summary": global_bucket_summary,
        "strategy_breakdown": strategy_breakdown(trades),
        "timeframe_breakdown": timeframe_breakdown(trades),
        "cell_breakdown": cell_breakdown(trades),
        "sl_distance_vs_realized_r": sl_distance_vs_r(trades),
        "extreme_r_gt20_trades": extreme_20,
        "extreme_r_gt50_trades": extreme_50,
        "planned_vs_realized_extreme_gt20": planned_vs_realized_for_extreme(extreme_20),
        "counterfactual_exclusions": counterfactuals,
        "global_summary": bucket_r_summary(trades),
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(output, indent=2, default=str))

    print(f"cells checked: {integrity['cells_checked']}, baseline mismatches: {len(integrity['mismatches'])}")
    print(f"trades analyzed: {len(trades)}")
    print(f"sub-precision trades: {sum(1 for t in trades if t['is_sub_precision'])}")
    print(f"extremely_small bucket: {global_bucket_summary['extremely_small']['trade_count']}")
    print(f"extreme R>20 winners: {len(extreme_20)}, R>50 winners: {len(extreme_50)}")
    print(f"inverted SL: {output['global_sl_direction']['inverted']}, equal SL: {output['global_sl_direction']['equal']}")
    print("SL DISTANCE AUDIT COMPLETE" if integrity["passed"] else "SL DISTANCE AUDIT INCOMPLETE -- baseline mismatches found")
    print(f"written to {OUT_JSON}")


if __name__ == "__main__":
    main()
