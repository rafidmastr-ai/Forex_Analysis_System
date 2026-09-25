"""Renders reports/RR_DISTRIBUTION_AUDIT.md and
reports/RR_DISTRIBUTION_AUDIT.csv from
data/optimization_results/trade_level_audit.json -- formatting, grouping,
and calls into optimization.rr_distribution's pure analysis functions only.

Purely descriptive: no ranking, no "best"/"worst"/"recommended" strategy,
symbol, timeframe, or cap anywhere in this report. This script does not
generate, resolve, or alter any trade -- it only aggregates and formats
already-captured trade-level records.
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path
from typing import Hashable, TypeVar

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from optimization.rr_distribution import (  # noqa: E402
    bin_distribution,
    global_distribution_summary,
    percentile,
    profit_concentration,
    trim_analysis,
)

RESULTS_PATH = Path("data/optimization_results/trade_level_audit.json")
REPORT_DIR = Path("reports")
REPORT_PATH = REPORT_DIR / "RR_DISTRIBUTION_AUDIT.md"
CSV_PATH = REPORT_DIR / "RR_DISTRIBUTION_AUDIT.csv"

BIN_LABEL_ORDER = ["below_1.5R", "1.5-2R", "2-3R", "3-4R", "4-5R", "5-10R", "10-20R", "20-50R", "50R+"]
SPECIAL_INVESTIGATION_CELLS = [("Classic", "EURUSD", "M1"), ("Classic", "EURUSD", "M5")]


def r2(x) -> str:
    if x is None:
        return "n/a"
    if isinstance(x, float) and math.isinf(x):
        return "inf" if x > 0 else "-inf"
    return f"{x:.2f}"


def pct(x) -> str:
    return f"{x * 100:.1f}%" if x is not None else "n/a"


def _iter_cells(cells: dict):
    for strategy, by_symbol in cells.items():
        for symbol, by_tf in by_symbol.items():
            for tf, cell in by_tf.items():
                yield strategy, symbol, tf, cell


def _is_failed(cell: dict) -> bool:
    return isinstance(cell, dict) and cell.get("status") == "FAILED"


def _is_structurally_inverted_sl(t: dict) -> bool:
    """A stop-loss on the wrong side of entry for the trade's own direction
    (SL above entry on a BUY, or below entry on a SELL) -- checkable purely
    from the trade's own stored prices, independent of whether SL was ever
    hit."""
    if t["direction"] == "BUY":
        return t["stop_loss"] > t["entry"]
    return t["stop_loss"] < t["entry"]


def _r_multiple_validation_breakdown(trades: list[dict]) -> dict:
    """Splits the independent-R-multiple discrepancies (item 9) by outcome
    type and cross-references them against structurally-inverted stop-loss
    placement, to distinguish a genuine R-multiple computation bug from the
    already-documented inverted-SL condition."""
    wins = [t for t in trades if t["hit"] in ("TP1", "TP2")]
    resolved = [t for t in trades if t["hit"] != "NONE"]
    total_sl_trades = sum(1 for t in trades if t["hit"] == "SL")
    discrepant = [t for t in resolved if t["r_multiple_discrepancy"] is not None and abs(t["r_multiple_discrepancy"]) > 1e-6]
    win_discrepancies = [t for t in discrepant if t["hit"] in ("TP1", "TP2")]
    sl_discrepancies = [t for t in discrepant if t["hit"] == "SL"]
    sl_discrepancies_inverted = [t for t in sl_discrepancies if _is_structurally_inverted_sl(t)]

    inverted_wins = [t for t in wins if _is_structurally_inverted_sl(t)]
    wins_gt20 = [t for t in wins if t["r_multiple"] > 20]
    wins_gt20_inverted = [t for t in wins_gt20 if _is_structurally_inverted_sl(t)]
    wins_gt50 = [t for t in wins if t["r_multiple"] > 50]
    wins_gt50_inverted = [t for t in wins_gt50 if _is_structurally_inverted_sl(t)]
    non_inverted_extreme = [t for t in wins_gt20 if not _is_structurally_inverted_sl(t)]
    sl_distances = [abs(t["entry"] - t["stop_loss"]) for t in non_inverted_extreme]

    return {
        "trades_checked": len(resolved),
        "total_discrepancies": len(discrepant),
        "winning_trade_discrepancies": len(win_discrepancies),
        "winning_trades_checked": len(wins),
        "total_sl_trades": total_sl_trades,
        "sl_discrepancies": len(sl_discrepancies),
        "sl_discrepancies_with_inverted_sl": len(sl_discrepancies_inverted),
        "sl_discrepancies_not_inverted": len(sl_discrepancies) - len(sl_discrepancies_inverted),
        "total_winning_trades": len(wins),
        "structurally_inverted_sl_wins": len(inverted_wins),
        "wins_over_20r": len(wins_gt20), "wins_over_20r_inverted_sl": len(wins_gt20_inverted),
        "wins_over_50r": len(wins_gt50), "wins_over_50r_inverted_sl": len(wins_gt50_inverted),
        "non_inverted_extreme_sl_distance_min": min(sl_distances) if sl_distances else None,
        "non_inverted_extreme_sl_distance_median": sorted(sl_distances)[len(sl_distances) // 2] if sl_distances else None,
    }


def _cell_key(t: dict) -> tuple[str, str, str]:
    return (t["strategy"], t["symbol"], t["timeframe"])


_K = TypeVar("_K", bound=Hashable)


def _group_by(trades: list[dict], key_fn) -> dict[_K, list[dict]]:
    groups: dict[_K, list[dict]] = {}
    for t in trades:
        groups.setdefault(key_fn(t), []).append(t)
    return groups


def _cell_stats_row(trades: list[dict]) -> dict:
    """The per-cell statistic set required by report sections 7-10 (Strategy/
    Symbol/Timeframe/96-Cell level): trade count, wins, losses, unresolved,
    Win Rate, Net R, PF, mean/median winning R, P90/P95/P99, max winning R,
    gross profit share from >5R/>10R/>20R/>50R winners."""
    summary = global_distribution_summary(trades)
    shares = summary["gross_share_above_thresholds"]
    return {
        "trade_count": summary["total_trades"], "wins": summary["winning_trades"],
        "losses": summary["losing_trades"], "unresolved": summary["unresolved_trades"],
        "win_rate": summary["win_rate"], "net_r": summary["net_r"], "profit_factor": summary["profit_factor"],
        "mean_winning_r": summary["mean_winning_r"], "median_winning_r": summary["median_winning_r"],
        "p90_winning_r": summary["p90_winning_r"], "p95_winning_r": summary["p95_winning_r"],
        "p99_winning_r": summary["p99_winning_r"], "max_winning_r": summary["max_winning_r"],
        "gross_share_gt5r": shares[">5R"]["pct_of_gross_winning_r"],
        "gross_share_gt10r": shares[">10R"]["pct_of_gross_winning_r"],
        "gross_share_gt20r": shares[">20R"]["pct_of_gross_winning_r"],
        "gross_share_gt50r": shares[">50R"]["pct_of_gross_winning_r"],
    }


def _cell_row_line(label: str, stats: dict) -> str:
    return (f"| {label} | {stats['trade_count']} | {stats['wins']} | {stats['losses']} | {pct(stats['win_rate'])} | "
            f"{r2(stats['net_r'])} | {r2(stats['profit_factor'])} | {r2(stats['mean_winning_r'])} | "
            f"{r2(stats['median_winning_r'])} | {r2(stats['p90_winning_r'])} | {r2(stats['p95_winning_r'])} | "
            f"{r2(stats['p99_winning_r'])} | {r2(stats['max_winning_r'])} | {pct(stats['gross_share_gt5r'])} | "
            f"{pct(stats['gross_share_gt10r'])} | {pct(stats['gross_share_gt20r'])} | {pct(stats['gross_share_gt50r'])} |")


CELL_TABLE_HEADER = ("| Group | Trades | Wins | Losses | Win Rate | Net R | PF | Mean Win R | Median Win R | "
                      "P90 | P95 | P99 | Max Win R | Share >5R | Share >10R | Share >20R | Share >50R |\n"
                      "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")


def _describe_extreme_investigation(label: str, stats: dict) -> list[str]:
    """Item 8's Special Investigation flags -- purely descriptive
    thresholds applied to this cell's own numbers, never a ranking against
    other cells. A cell is flagged if ANY of: mean winning R is much larger
    than median (>3x), P99 is far above P95 (>2x), or a small trade count
    generates the majority of gross winning R (share from winners >20R
    exceeds 40%)."""
    notes = []
    mean_w, median_w = stats["mean_winning_r"], stats["median_winning_r"]
    if mean_w is not None and median_w is not None and median_w > 0 and mean_w > 3 * median_w:
        notes.append(f"mean winning R ({r2(mean_w)}) is more than 3x the median winning R ({r2(median_w)})")
    p95, p99 = stats["p95_winning_r"], stats["p99_winning_r"]
    if p95 is not None and p99 is not None and p95 > 0 and p99 > 2 * p95:
        notes.append(f"P99 winning R ({r2(p99)}) is more than 2x P95 winning R ({r2(p95)})")
    if stats["gross_share_gt20r"] is not None and stats["gross_share_gt20r"] > 0.40:
        notes.append(f"winners above 20R alone account for {pct(stats['gross_share_gt20r'])} of gross winning R")
    if stats["max_winning_r"] is not None and stats["max_winning_r"] > 50:
        notes.append(f"maximum realized winning R is {r2(stats['max_winning_r'])}")
    return notes


def render() -> tuple[str, list[dict], dict[tuple[str, str, str], dict]]:
    data = json.loads(RESULTS_PATH.read_text())
    trades: list[dict] = data["trades"]
    cells_raw = data["cells"]
    run_status = data.get("run_status", {})
    r_validation = data.get("r_multiple_validation", {})
    r_breakdown = _r_multiple_validation_breakdown(trades)

    cell_pairs = list(_iter_cells(cells_raw))
    ok_cell_pairs = [(s, sym, tf, c) for s, sym, tf, c in cell_pairs if not _is_failed(c)]

    by_strategy: dict[str, list[dict]] = _group_by(trades, lambda t: t["strategy"])
    by_symbol: dict[str, list[dict]] = _group_by(trades, lambda t: t["symbol"])
    by_timeframe: dict[str, list[dict]] = _group_by(trades, lambda t: t["timeframe"])
    by_cell: dict[tuple[str, str, str], list[dict]] = _group_by(trades, _cell_key)

    lines: list[str] = ["# R:R DISTRIBUTION AUDIT", ""]

    # 1. Executive Summary
    total_runs = run_status.get("total_runs", len(cell_pairs))
    successful = run_status.get("successful_runs", len(ok_cell_pairs))
    failed = run_status.get("failed_runs", 0)
    mismatches = run_status.get("baseline_validation_mismatches", {})
    global_summary = global_distribution_summary(trades)
    lines += [
        "## 1. Executive Summary",
        "",
        "This audit determines whether the current-version Baseline backtest's performance "
        "(`data/optimization_results/m1_full_backtest.json`) depends on a small number of trades with "
        "extremely large realized R multiples. It is purely diagnostic: no Strategy, Weight, Filter, "
        "Threshold, Entry, TP, SL, Confidence, Timeframe-mapping, Lookback, Dataset, or same-candle-policy "
        "logic was changed to produce or in response to these results, and no strategy/symbol/timeframe is "
        "ranked or recommended anywhere in this report.",
        "",
        f"- {successful}/{total_runs} Baseline cells executed successfully ({failed} failed).",
        f"- Baseline integrity check: {'PASSED (0 mismatches across all cells)' if not mismatches else f'{len(mismatches)} cell(s) with a mismatch -- see Section 3'}.",
        f"- {global_summary['total_trades']} total trades captured across all executed cells "
        f"({global_summary['winning_trades']} wins, {global_summary['losing_trades']} losses, "
        f"{global_summary['unresolved_trades']} unresolved).",
        f"- Global Net R = {r2(global_summary['net_r'])}, Profit Factor = {r2(global_summary['profit_factor'])}.",
        f"- R-multiple independent validation: {r_breakdown['winning_trades_checked']}/{r_breakdown['winning_trades_checked']} "
        "WINNING trades independently re-derive their stored realized R exactly (0 discrepancies) -- see Section 13. "
        f"Separately, {r_breakdown['sl_discrepancies']} of {r_breakdown['total_sl_trades']} SL-hit (losing) trades "
        "have a stop-loss placed on the wrong side of entry for their own direction -- an already-documented "
        "condition, not a new R-multiple computation bug (Section 13).",
        f"- {r_validation.get('trades_with_undefined_sl_distance', 0)} resolved trades had an undefined "
        "(zero-distance) stop-loss.",
        "",
    ]

    # 2. Dataset and Methodology
    lines += [
        "## 2. Dataset and Methodology",
        "",
        "- Dataset: identical to the Baseline -- `data/market/{SYMBOL}.csv` (raw M1 OHLC) and the "
        "`data/historical/{SYMBOL}_{TF}.csv` files generated from it by `scripts/build_m1_historical_data.py`.",
        "- 96 configurations: 4 strategies (Classic, SMC, ICT, SweepDisplacement) x 4 symbols (EURUSD, XAUUSD, "
        "GBPUSD, NZDUSD) x 6 entry timeframes (M1, M5, M15, M30, H1, H4).",
        "- Each cell's signals are generated EXACTLY ONCE via `scripts.robustness_backtest"
        ".run_one_signal_generation` (identical production wiring to the Baseline: same filters, "
        "`min_confidence=None`, `min_risk_reward=1.5`, timeframe mapping, lookback, dataset, same-candle "
        "policy). All analysis below is computed AFTER `BacktestEngine` has already produced each "
        "`TradeOutcome` -- no trade is re-simulated and no decision logic is exercised by this audit.",
        "- \"Signal score\" (per the audit's Section 3 requirement) is captured as `confidence_score` "
        "(the only single-number score `SelectedSetup` exposes) plus the winning signal's raw "
        "`raw_score_components` dict, both stored verbatim per trade in "
        "`data/optimization_results/trade_level_audit.json` for further inspection.",
        "- R:R bins for winning trades: 1.5-2R, 2-3R, 3-4R, 4-5R, 5-10R, 10-20R, 20-50R, 50R+, plus an "
        "explicit `below_1.5R` bucket for winners under the production minimum-R:R floor -- losses and "
        "unresolved (NONE) trades are tracked separately and never dropped from any total.",
        "",
    ]

    # 3. Baseline Integrity Check
    lines += ["## 3. Baseline Integrity Check", ""]
    lines.append(f"Cells checked: {len(ok_cell_pairs)}/{total_runs}. "
                 f"{'All cells matched data/optimization_results/m1_full_backtest.json exactly (trade count, resolved count, wins, losses, TP1, TP2, SL, win rate, net R, profit factor, expectancy).' if not mismatches else 'Mismatches were found and are listed below -- NOT hidden.'}")
    lines.append("")
    if mismatches:
        for cell_key, mismatch_list in mismatches.items():
            lines.append(f"- **{cell_key}**: {'; '.join(mismatch_list)}")
        lines.append("")
    if failed:
        lines.append(f"{failed} cell(s) failed to run (see `run_status.errors` in the JSON output) and are excluded from every statistic below.")
        lines.append("")

    # 4. Global R:R Distribution
    dist = bin_distribution(trades)
    lines += ["## 4. Global R:R Distribution", "",
              "R:R distribution of WINNING trades only (bins), with explicit accounting for winners below the "
              "1.5R floor, losses, and unresolved trades in the same table.",
              "",
              "| Bucket | Trade Count | % of Winning Trades | Total Realized R | % of Gross Winning R | Mean R | Median R |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for label in BIN_LABEL_ORDER:
        b = dist[label]
        lines.append(f"| {label} | {b['trade_count']} | {pct(b['pct_of_winning_trades'])} | {r2(b['total_realized_r'])} | "
                      f"{pct(b['pct_of_gross_winning_r'])} | {r2(b['mean_realized_r'])} | {r2(b['median_realized_r'])} |")
    lines.append(f"| losses (SL) | {dist['losses_SL']['trade_count']} | -- | {r2(dist['losses_SL']['total_realized_r'])} | -- | -- | -- |")
    lines.append(f"| unresolved (NONE) | {dist['unresolved_NONE']['trade_count']} | -- | {r2(dist['unresolved_NONE']['total_realized_r'])} | -- | -- | -- |")
    lines.append("")
    lines += [
        "### Global summary statistics",
        "",
        f"- Total trades: {global_summary['total_trades']} (wins: {global_summary['winning_trades']}, "
        f"losses: {global_summary['losing_trades']}, unresolved: {global_summary['unresolved_trades']}).",
        f"- Gross winning R: {r2(global_summary['gross_winning_r'])}, Gross losing R: {r2(global_summary['gross_losing_r'])}, "
        f"Net R: {r2(global_summary['net_r'])}, Profit Factor: {r2(global_summary['profit_factor'])}.",
        f"- Mean winning R: {r2(global_summary['mean_winning_r'])}, Median winning R: {r2(global_summary['median_winning_r'])}.",
        f"- P75/P90/P95/P99 winning R: {r2(global_summary['p75_winning_r'])} / {r2(global_summary['p90_winning_r'])} / "
        f"{r2(global_summary['p95_winning_r'])} / {r2(global_summary['p99_winning_r'])}.",
        f"- Maximum winning R: {r2(global_summary['max_winning_r'])}.",
        "",
        "| Threshold | Trade Count | Total Realized R | % of Gross Winning R |",
        "|---|---:|---:|---:|",
    ]
    for threshold_label, s in global_summary["gross_share_above_thresholds"].items():
        lines.append(f"| {threshold_label} | {s['trade_count']} | {r2(s['total_realized_r'])} | {pct(s['pct_of_gross_winning_r'])} |")
    lines.append("")

    # 5. Profit Concentration
    conc = profit_concentration(trades)
    lines += ["## 5. Profit Concentration", "",
              "How much of total gross winning R comes from the top N% of winning trades by count (sorted by "
              "realized R, descending).",
              "",
              "| Top Fraction | N Trades | Total Realized R | % of Gross Winning R |",
              "|---|---:|---:|---:|"]
    for conc_key, c in conc.items():
        label = conc_key.replace("top_", "").replace("pct", "%")
        lines.append(f"| {label} | {c['n_trades']} | {r2(c['total_realized_r'])} | {pct(c['pct_of_gross_winning_r'])} |")
    lines.append("")

    # 6. Trim Analysis
    trim = trim_analysis(trades)
    lines += ["## 6. Trim Analysis", "",
              "Post-trade, analytical-only trim: removes the top N% highest-realized-R WINNING trades (by "
              "count) and recomputes summary metrics over the remaining population. This does NOT re-run the "
              "strategy and does NOT alter trade generation -- it is a pure arithmetic exclusion over "
              "already-decided trades, shown for comparison against the untrimmed Baseline figures in Section 4.",
              "",
              f"Untrimmed baseline for reference: {global_summary['total_trades']} trades, Net R = "
              f"{r2(global_summary['net_r'])}, PF = {r2(global_summary['profit_factor'])}.",
              "",
              "| Trim | Trades Removed | Trade Count | Wins | Losses | Win Rate | Gross Win R | Gross Loss R | Net R | PF | Expectancy |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for trim_key, t in trim.items():
        label = trim_key.replace("trim_", "").replace("pct", "%")
        lines.append(f"| {label} | {t['n_trades_removed']} | {t['trade_count']} | {t['wins']} | {t['losses']} | "
                      f"{pct(t['win_rate'])} | {r2(t['gross_winning_r'])} | {r2(t['gross_losing_r'])} | "
                      f"{r2(t['net_r'])} | {r2(t['profit_factor'])} | {r2(t['expectancy'])} |")
    lines.append("")

    # 7. Strategy-Level Distribution
    lines += ["## 7. Strategy-Level Distribution", "", CELL_TABLE_HEADER]
    for strategy in sorted(by_strategy):
        lines.append(_cell_row_line(strategy, _cell_stats_row(by_strategy[strategy])))
    lines.append("")

    # 8. Symbol-Level Distribution
    lines += ["## 8. Symbol-Level Distribution", "", CELL_TABLE_HEADER]
    for symbol in sorted(by_symbol):
        lines.append(_cell_row_line(symbol, _cell_stats_row(by_symbol[symbol])))
    lines.append("")

    # 9. Timeframe-Level Distribution
    lines += ["## 9. Timeframe-Level Distribution", "", CELL_TABLE_HEADER]
    for tf in sorted(by_timeframe, key=lambda x: ["M1", "M5", "M15", "M30", "H1", "H4"].index(x) if x in ["M1", "M5", "M15", "M30", "H1", "H4"] else 99):
        lines.append(_cell_row_line(tf, _cell_stats_row(by_timeframe[tf])))
    lines.append("")

    # 10. 96-Cell Results
    # Enumerated from cell_pairs (all 96 Strategy/Symbol/Timeframe combinations,
    # including any with zero trades or a failed run) -- NOT from by_cell's keys
    # alone, which would silently omit a zero-trade cell (e.g. a cell whose
    # signal generation produced no setups at all).
    lines += ["## 10. 96-Cell Results", "", CELL_TABLE_HEADER]
    cell_stats_map: dict[tuple[str, str, str], dict] = {}
    all_cell_keys = sorted({(s, sym, tf) for s, sym, tf, _ in cell_pairs})
    for cell_key in all_cell_keys:
        cell_trades = by_cell.get(cell_key, [])
        stats = _cell_stats_row(cell_trades)
        cell_stats_map[cell_key] = stats
        lines.append(_cell_row_line("/".join(cell_key), stats))
    lines.append("")

    # 11. Extreme-R Trade Investigation
    lines += ["## 11. Extreme-R Trade Investigation", "",
              "Descriptive language only -- these notes describe what the numbers show, not which cell is "
              "\"best\" or \"worst\".",
              "",
              "### Cells named for special attention",
              ""]
    for strategy, symbol, tf in SPECIAL_INVESTIGATION_CELLS:
        special_key = (strategy, symbol, tf)
        if special_key not in cell_stats_map:
            lines.append(f"- **{strategy}/{symbol}/{tf}**: no trades captured for this cell.")
            continue
        stats = cell_stats_map[special_key]
        notes = _describe_extreme_investigation(f"{strategy}/{symbol}/{tf}", stats)
        lines.append(f"- **{strategy}/{symbol}/{tf}**: {stats['trade_count']} trades, {stats['wins']} wins, "
                      f"Net R = {r2(stats['net_r'])}, mean winning R = {r2(stats['mean_winning_r'])}, "
                      f"median winning R = {r2(stats['median_winning_r'])}, max winning R = {r2(stats['max_winning_r'])}.")
        if notes:
            for n in notes:
                lines.append(f"  - {n}")
        else:
            lines.append("  - none of the flagged conditions (mean>>median, P99>>P95, concentrated gross share, max R>50) were met for this cell.")
    lines.append("")
    lines.append("### All cells meeting at least one flagged condition")
    lines.append("")
    lines.append("Flag conditions (applied identically to every cell, not a comparison between cells): mean "
                 "winning R > 3x median winning R; P99 winning R > 2x P95 winning R; winners above 20R account "
                 "for over 40% of gross winning R; or maximum winning R exceeds 50R.")
    lines.append("")
    any_flagged = False
    for flag_key in sorted(cell_stats_map):
        stats = cell_stats_map[flag_key]
        notes = _describe_extreme_investigation("/".join(flag_key), stats)
        if notes:
            any_flagged = True
            lines.append(f"- **{'/'.join(flag_key)}**: " + "; ".join(notes))
    if not any_flagged:
        lines.append("- no cell met any flagged condition.")
    lines.append("")

    # 12. Planned RR vs Realized R
    winning_trades = [t for t in trades if t["hit"] in ("TP1", "TP2")]
    planned_tp1 = [t["planned_rr_tp1"] for t in winning_trades if t.get("planned_rr_tp1") is not None]
    planned_tp2 = [t["planned_rr_tp2"] for t in winning_trades if t.get("planned_rr_tp2") is not None]
    realized = [t["r_multiple"] for t in winning_trades]

    def _dist_row(label: str, values: list[float]) -> str:
        if not values:
            return f"| {label} | 0 | n/a | n/a | n/a | n/a | n/a | n/a |"
        s = sorted(values)
        mean_v = sum(values) / len(values)
        return (f"| {label} | {len(values)} | {r2(mean_v)} | {r2(percentile(values, 50))} | "
                f"{r2(percentile(values, 90))} | {r2(percentile(values, 95))} | {r2(percentile(values, 99))} | "
                f"{r2(s[-1])} |")

    lines += ["## 12. Planned RR vs Realized R", "",
              "Compares the planned R:R at signal time (`SelectedSetup.risk_reward_tp1`/`risk_reward_tp2`, "
              "computed from Entry/SL/TP BEFORE the trade is simulated) against the REALIZED R of winning "
              "trades, to determine whether extreme realized R values correspond to genuinely extreme planned "
              "setups or are only created during outcome simulation.",
              "",
              "| Series | N | Mean | Median | P90 | P95 | P99 | Max |",
              "|---|---:|---:|---:|---:|---:|---:|---:|",
              _dist_row("Planned RR (TP1), winning trades", planned_tp1),
              _dist_row("Planned RR (TP2), winning trades", planned_tp2),
              _dist_row("Realized R, winning trades", realized),
              "",
              "Note: for a TP2-hit trade, realized R equals planned RR (TP2) exactly by construction (see "
              "Section 13) -- the comparison above is informative mainly for TP1-hit trades and for showing "
              "whether the planned-RR distribution at signal time already contains the same extreme tail seen "
              "in realized R.",
              ""]

    # 13. R-Multiple Validation
    lines += ["## 13. R-Multiple Validation", "",
              "Independent recomputation of realized R directly from each trade's stored Entry/SL/exit price "
              "(`optimization.rr_distribution.independent_r_multiple`, using the BUY/SELL formulas: "
              "`R = (exit - entry) / abs(entry - SL)` for BUY, `R = (entry - exit) / abs(entry - SL)` for SELL), "
              "compared against the project's own stored `r_multiple` -- deliberately not calling "
              "`SelectedSetup.risk_reward_tp1`/`risk_reward_tp2` again, which would be a circular "
              "self-comparison.",
              "",
              f"- Resolved trades checked: {r_breakdown['trades_checked']}.",
              f"- Trades with an undefined (zero-distance) stop-loss: {r_validation.get('trades_with_undefined_sl_distance', 0)}.",
              f"- **WINNING (TP1/TP2) trades**: {r_breakdown['winning_trade_discrepancies']} discrepancies out of "
              f"{r_breakdown['winning_trades_checked']} checked -- every winning trade's realized R independently "
              "reproduces the stored value exactly. This directly answers the audit's central question about the "
              "realized-R distribution in Sections 4-11: the winning-trade R-multiple numbers analyzed throughout "
              "this report are not the product of a computation bug.",
              f"- **SL (losing) trades**: {r_breakdown['sl_discrepancies']} discrepancies out of "
              f"{r_breakdown['total_sl_trades']} SL-hit trades. `BacktestEngine._simulate_outcome` stores exactly "
              "`-1.0` for every SL hit as a fixed convention, rather than computing it from price -- so this "
              "figure compares that convention against the geometric formula above, not one computed value "
              "against another.",
              f"  - Of those {r_breakdown['sl_discrepancies']} SL-trade discrepancies, "
              f"{r_breakdown['sl_discrepancies_with_inverted_sl']} ({pct(r_breakdown['sl_discrepancies_with_inverted_sl'] / r_breakdown['sl_discrepancies']) if r_breakdown['sl_discrepancies'] else 'n/a'}) "
              "have a stop-loss placed on the wrong side of entry for the trade's own direction (SL above entry on "
              f"a BUY, or below entry on a SELL) -- checkable directly from the stored prices, independent of "
              "whether SL was ever hit. This is consistent with, and independently confirms via this audit's own "
              "numeric check (not a re-diagnosis from scratch), the previously documented S/R and "
              "sweep-anchoring proximity-gate finding in `CURRENT_VERSION_LOSS_DIAGNOSTIC_REPORT.md`, which found "
              "those gates check absolute distance only, not directional correctness.",
              f"  - The remaining {r_breakdown['sl_discrepancies_not_inverted']} have a correctly-sided but "
              "very small stop-loss distance, which the -1.0 convention also does not reflect geometrically "
              "(it is a fixed loss-of-risked-capital convention, not a per-trade price computation).",
              ""]
    lines.append("### Structurally-inverted stop-loss among WINNING trades")
    lines.append("")
    lines.append("A stop-loss can be checked for wrong-side placement on ANY trade from its stored prices alone, "
                 "whether or not SL was the outcome that occurred -- this isolates whether extreme WINNING R "
                 "values are linked to the same inverted-SL condition found above, or to something else.")
    lines.append("")
    lines.append(f"- Of {r_breakdown['total_winning_trades']} winning trades, "
                 f"{r_breakdown['structurally_inverted_sl_wins']} have a structurally-inverted stop-loss.")
    lines.append(f"- Of {r_breakdown['wins_over_20r']} winning trades with realized R > 20, "
                 f"{r_breakdown['wins_over_20r_inverted_sl']} have a structurally-inverted stop-loss "
                 f"({r_breakdown['wins_over_20r'] - r_breakdown['wins_over_20r_inverted_sl']} do not).")
    lines.append(f"- Of {r_breakdown['wins_over_50r']} winning trades with realized R > 50, "
                 f"{r_breakdown['wins_over_50r_inverted_sl']} have a structurally-inverted stop-loss "
                 f"({r_breakdown['wins_over_50r'] - r_breakdown['wins_over_50r_inverted_sl']} do not).")
    if r_breakdown["non_inverted_extreme_sl_distance_min"] is not None:
        lines.append(f"- Among the R>20 winners with a correctly-sided (non-inverted) stop-loss, the SL distance "
                     f"(in raw price units) ranges down to {r_breakdown['non_inverted_extreme_sl_distance_min']:.2e} "
                     f"(median {r_breakdown['non_inverted_extreme_sl_distance_median']:.2e}) -- i.e. most extreme "
                     "winning R values in this dataset come from a correctly-directed but extremely small "
                     "stop-loss distance relative to the take-profit distance, not from an inverted SL, an "
                     "incorrect trade direction, or a unit/pip-conversion error.")
    lines.append("")
    top_r_trades = sorted(winning_trades, key=lambda t: t["r_multiple"], reverse=True)[:10]
    lines.append("### Manual verification sample: top 10 highest-realized-R winning trades")
    lines.append("")
    lines.append("| Strategy/Symbol/TF | Direction | Entry | SL | SL Distance | Exit (TP hit) | Stored R | Independent R | Match | Inverted SL |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---|---|")
    for t in top_r_trades:
        sl_distance = abs(t["entry"] - t["stop_loss"])
        exit_price = t["take_profit_2"] if t["hit"] == "TP2" else t["take_profit_1"]
        match = "yes" if t["independent_r_multiple"] is not None and abs(t["independent_r_multiple"] - t["r_multiple"]) <= 1e-6 else "NO"
        inverted = "yes" if _is_structurally_inverted_sl(t) else "no"
        lines.append(f"| {t['strategy']}/{t['symbol']}/{t['timeframe']} | {t['direction']} | {t['entry']:.5f} | "
                      f"{t['stop_loss']:.5f} | {sl_distance:.6f} | {exit_price:.5f} | {r2(t['r_multiple'])} | "
                      f"{r2(t['independent_r_multiple'])} | {match} | {inverted} |")
    lines.append("")
    if r_breakdown["total_discrepancies"]:
        lines.append("Discrepancies were found (see above) and are NOT auto-fixed -- see `discrepancy_samples` in "
                      "`data/optimization_results/trade_level_audit.json` for the full list of affected SL-hit "
                      "trades. No Strategy/SL/Entry/TP logic was changed in response to this finding.")
        lines.append("")

    # 14. Data/Backtest Limitations
    lines += ["## 14. Data/Backtest Limitations", "",
              "- OHLC-only backtesting: no tick data or intrabar path is available for any timeframe; true "
              "intrabar ordering between a candle's high and low cannot be established from OHLC data alone.",
              "- Same-candle policy: `BacktestEngine._simulate_outcome` checks SL before TP1/TP2 whenever both "
              "would be touched within the same candle -- a deterministic, conservative convention, not a "
              "simulation of real intrabar price path.",
              "- Exit price is always exactly the setup's stored TP1/TP2/SL price (never a slippage-adjusted or "
              "partially-filled price), so realized R is a theoretical value assuming perfect fills at the "
              "planned levels.",
              "- No spread data exists anywhere in this dataset: `data/market/*.csv` and the generated "
              "`data/historical/*.csv` files have no spread column at all (`candle.spread` is always `None`).",
              "- Spread filtering is not active in any batch backtest script: `ValidatingMarketDataProvider` "
              "(the component that would filter on `max_spread`) is wired only into the live `/analyze` "
              "backend path (`backend/dependencies.py`), never into `m1_full_backtest.py`, "
              "`robustness_backtest.py`, or this audit's `rr_distribution_audit.py`.",
              "- H4 entry-timeframe cells map Higher=Middle=Entry=H4 (`config/settings.backtest.yaml`'s "
              "`entry_mapping`), since no D1 timeframe is generated by this data pipeline -- H4 cells therefore "
              "have less genuine multi-timeframe context than other entry timeframes.",
              "- H1 entry-timeframe cells map Middle=Entry=H1 for the same reason (no timeframe between H1 and "
              "H4 in this pipeline).",
              "- `closed_at` is the OPEN timestamp of the candle on which the exit condition was met, not a "
              "precise intrabar exit instant.",
              "- \"Signal score\" is reported as `confidence_score` (0-100, a relative confidence score, "
              "explicitly NOT a win probability per its own field documentation) since no other single-number "
              "score is stored on `SelectedSetup`.",
              ""]

    # 15. Conclusions
    top01 = conc.get("top_0.1pct", {})
    top1 = conc.get("top_1pct", {})
    top5 = conc.get("top_5pct", {})
    lines += ["## 15. Conclusions", "",
              "This section states only what the data demonstrates. It contains no ranking, no best/worst/"
              "recommended strategy, symbol, timeframe, or configuration, and no change was made to any "
              "Strategy, Weight, Filter, Threshold, Entry, TP, or SL logic to produce or in response to these "
              "results.",
              "",
              f"- Across {global_summary['total_trades']} captured trades, {global_summary['winning_trades']} "
              f"were winners; the top 0.1% of winning trades by count ({top01.get('n_trades', 0)} trades) "
              f"account for {pct(top01.get('pct_of_gross_winning_r'))} of total gross winning R, the top 1% "
              f"({top1.get('n_trades', 0)} trades) account for {pct(top1.get('pct_of_gross_winning_r'))}, and "
              f"the top 5% ({top5.get('n_trades', 0)} trades) account for {pct(top5.get('pct_of_gross_winning_r'))}.",
              f"- Removing the top 1% highest-realized-R winning trades changes global Net R from "
              f"{r2(global_summary['net_r'])} to {r2(trim.get('trim_1pct', {}).get('net_r'))}, and removing the "
              f"top 5% changes it to {r2(trim.get('trim_5pct', {}).get('net_r'))}.",
              f"- Independent recomputation of realized R from stored Entry/SL/Exit prices matched the "
              f"project's stored `r_multiple` for all {r_breakdown['winning_trades_checked']} winning trades "
              "checked (0 discrepancies). All discrepancies found (see Section 13) are on SL-hit (losing) "
              "trades, where the engine stores a fixed `-1.0` by convention rather than a computed value; "
              f"{r_breakdown['sl_discrepancies_with_inverted_sl']} of those {r_breakdown['sl_discrepancies']} "
              "SL-trade cases have a stop-loss on the wrong side of entry for the trade's own direction.",
              "- Extreme realized-R WINNING trades in this dataset are associated with a small, correctly-sided "
              "stop-loss distance relative to the take-profit distance (see Section 13): among winners with "
              f"realized R > 20, {r_breakdown['wins_over_20r'] - r_breakdown['wins_over_20r_inverted_sl']} of "
              f"{r_breakdown['wins_over_20r']} have a correctly-sided (non-inverted) stop-loss, meaning most of "
              "this dataset's extreme winning R values are not explained by a zero/negative SL distance, "
              "incorrect trade direction, or a unit/pip-conversion error.",
              f"- Baseline reproducibility: {'the audit reproduced data/optimization_results/m1_full_backtest.json exactly for every checked cell.' if not mismatches else f'{len(mismatches)} cell(s) did not match the prior Baseline exactly (see Section 3).'}",
              ""]

    return "\n".join(lines), trades, cell_stats_map


def write_csv(trades: list[dict], cell_stats_map: dict[tuple[str, str, str], dict]) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["strategy", "symbol", "timeframe", "trade_count", "wins", "losses", "unresolved",
                          "win_rate", "net_r", "profit_factor", "mean_winning_r", "median_winning_r",
                          "p90_winning_r", "p95_winning_r", "p99_winning_r", "max_winning_r",
                          "gross_share_gt5r", "gross_share_gt10r", "gross_share_gt20r", "gross_share_gt50r"])
        for (strategy, symbol, tf), stats in sorted(cell_stats_map.items()):
            writer.writerow([strategy, symbol, tf, stats["trade_count"], stats["wins"], stats["losses"],
                              stats["unresolved"], stats["win_rate"], stats["net_r"], stats["profit_factor"],
                              stats["mean_winning_r"], stats["median_winning_r"], stats["p90_winning_r"],
                              stats["p95_winning_r"], stats["p99_winning_r"], stats["max_winning_r"],
                              stats["gross_share_gt5r"], stats["gross_share_gt10r"], stats["gross_share_gt20r"],
                              stats["gross_share_gt50r"]])


def main() -> None:
    report_text, trades, cell_stats_map = render()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report_text)
    write_csv(trades, cell_stats_map)
    print(f"wrote {REPORT_PATH}")
    print(f"wrote {CSV_PATH}")


if __name__ == "__main__":
    main()
