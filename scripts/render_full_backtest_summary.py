"""Renders the human-readable summaries requested for the full 96-run
current-version backtest (4 symbols x 6 timeframes x 4 strategies) from
data/optimization_results/m1_full_backtest.json -- formatting/aggregation
only. Never ranks or selects a "best" anything, never re-runs or tunes
anything.

Per-cell fields (trade/resolved/none/tp1/tp2/sl counts, wins, losses,
net_r, average_winning_r; average_losing_r is always exactly -1.0, the
fixed per-trade SL loss) are exactly additive, so every rollup below
(per-symbol, per-timeframe, per-strategy, overall) is an EXACT
recombination from stored per-cell data, not an approximation:
    win_rate    = sum(wins) / sum(resolved)
    net_r       = sum(net_r)                              [already additive]
    gross_win   = sum(wins_i * average_winning_r_i)
    gross_loss  = sum(losses_i * 1.0)
    profit_factor = gross_win / gross_loss
    expectancy  = net_r / sum(resolved)
Max Drawdown and median duration are NOT meaningfully combinable across
independent runs (drawdown depends on trade sequence; median of medians
isn't the true combined median) -- rollup tables report only their
per-cell min/max range, with a caveat; the true per-cell values are always
in the full 96-row matrix.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

RESULTS_PATH = Path("data/optimization_results/m1_full_backtest.json")
OUT_PATH = Path("data/optimization_results/FULL_BACKTEST_96_RUN_REPORT.md")


def pct(x):
    return f"{x * 100:.1f}%" if x is not None else "n/a"


def r2(x):
    if x is None:
        return "n/a"
    if x == float("inf"):
        return "inf"
    if x == float("-inf"):
        return "-inf"
    return f"{x:.2f}"


def _iter_cells(data: dict):
    for strategy, by_symbol in data["results"].items():
        for symbol, by_tf in by_symbol.items():
            for tf, cell in by_tf.items():
                yield strategy, symbol, tf, cell


def _is_failed(cell: dict) -> bool:
    return isinstance(cell, dict) and cell.get("status") == "FAILED"


def _aggregate(cells: list[dict]) -> dict:
    ok_cells = [c for c in cells if not _is_failed(c)]
    trade_count = sum(c["trade_count"] for c in ok_cells)
    resolved_count = sum(c["resolved_count"] for c in ok_cells)
    none_count = sum(c["none_count"] for c in ok_cells)
    tp1_count = sum(c["tp1_count"] for c in ok_cells)
    tp2_count = sum(c["tp2_count"] for c in ok_cells)
    sl_count = sum(c["sl_count"] for c in ok_cells)
    wins = sum(c["metrics"]["wins"] for c in ok_cells)
    losses = sum(c["metrics"]["losses"] for c in ok_cells)
    net_r = sum(c["metrics"]["net_r"] for c in ok_cells)
    gross_win = sum(c["metrics"]["wins"] * c["metrics"]["average_winning_r"] for c in ok_cells)
    gross_loss = sum(c["metrics"]["losses"] * abs(c["metrics"]["average_losing_r"]) for c in ok_cells)
    win_rate = (wins / resolved_count) if resolved_count else 0.0
    expectancy = (net_r / resolved_count) if resolved_count else 0.0
    if gross_loss == 0:
        profit_factor = math.inf if gross_win > 0 else 0.0
    else:
        profit_factor = gross_win / gross_loss
    dd_values = [c["metrics"]["max_drawdown_r"] for c in ok_cells]
    return {
        "n_cells": len(cells), "n_ok_cells": len(ok_cells), "n_failed_cells": len(cells) - len(ok_cells),
        "trade_count": trade_count, "resolved_count": resolved_count, "none_count": none_count,
        "tp1_count": tp1_count, "tp2_count": tp2_count, "sl_count": sl_count,
        "wins": wins, "losses": losses, "win_rate": win_rate, "net_r": net_r,
        "profit_factor": profit_factor, "expectancy": expectancy,
        "average_r": expectancy,
        "max_drawdown_r_range": (min(dd_values), max(dd_values)) if dd_values else (None, None),
    }


def _agg_row(label: str, agg: dict) -> str:
    dd_lo, dd_hi = agg["max_drawdown_r_range"]
    dd_str = f"{r2(dd_lo)}-{r2(dd_hi)}" if dd_lo is not None else "n/a"
    fail_note = f" ({agg['n_failed_cells']} failed)" if agg["n_failed_cells"] else ""
    return (f"| {label} | {agg['trade_count']} | {agg['resolved_count']} | {agg['none_count']} | "
            f"{agg['tp1_count']} | {agg['tp2_count']} | {agg['sl_count']} | {pct(agg['win_rate'])} | "
            f"{r2(agg['profit_factor'])} | {r2(agg['net_r'])} | {r2(agg['expectancy'])} | {dd_str}{fail_note} |")


AGG_HEADER = ("| Group | Trades | Resolved | None | TP1 | TP2 | SL | Win Rate | PF | Net R | Expectancy | Max DD range |\n"
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")


def render() -> str:
    data = json.loads(RESULTS_PATH.read_text())
    cells = list(_iter_cells(data))
    run_status = data.get("run_status", {})

    all_cells = [c for _, _, _, c in cells]
    overall = _aggregate(all_cells)

    by_symbol: dict[str, list[dict]] = {}
    by_timeframe: dict[str, list[dict]] = {}
    by_strategy: dict[str, list[dict]] = {}
    for strategy, symbol, tf, cell in cells:
        by_symbol.setdefault(symbol, []).append(cell)
        by_timeframe.setdefault(tf, []).append(cell)
        by_strategy.setdefault(strategy, []).append(cell)

    lines = ["# FULL CURRENT-VERSION BACKTEST — 96-Run Report", ""]
    lines.append("Evaluation-only run: no Strategy/Weight/Filter/Threshold/Entry/TP/SL logic was changed to "
                  "produce these results, and no run's outcome was used to tune anything. This report contains "
                  "no ranking and selects no \"best\" strategy, symbol, timeframe, or combination anywhere.")
    lines.append("")

    lines.append("## Run Status")
    lines.append("")
    total_runs = run_status.get("total_runs", len(all_cells))
    successful = run_status.get("successful_runs", overall["n_ok_cells"])
    failed = run_status.get("failed_runs", overall["n_failed_cells"])
    elapsed = run_status.get("total_elapsed_seconds") or run_status.get("elapsed_seconds_so_far")
    lines.append(f"- Total runs: {total_runs}")
    lines.append(f"- Successful: {successful}")
    lines.append(f"- Failed: {failed}")
    lines.append(f"- Total execution time: {elapsed / 60:.1f} minutes" if elapsed else "- Total execution time: n/a")
    lines.append(f"- Data validation status: {data.get('data_validation_status')}")
    lines.append(f"- Same-candle policy: {data.get('same_candle_policy')}")
    if run_status.get("errors"):
        lines.append("")
        lines.append("### Errors (recorded verbatim, not silently skipped)")
        lines.append("")
        for e in run_status["errors"]:
            lines.append(f"- **{e['strategy']}/{e['symbol']}/{e['timeframe']}** — `{e['error_type']}`: {e['error_message']}")
    lines.append("")
    lines.append("**FULL BACKTEST COMPLETE**" if failed == 0 else "**FULL BACKTEST INCOMPLETE**")
    lines.append("")

    lines.append("## Data Sources & Configuration")
    lines.append("")
    lines.append(f"- Dataset source: {data.get('dataset_source')}")
    lines.append("- Per-symbol actual range and source candle counts:")
    lines.append("")
    lines.append("| Symbol | Source M1 candles | Actual start | Actual end | Cross-validation |")
    lines.append("|---|---:|---|---|---|")
    for symbol, info in data.get("per_symbol_data", {}).items():
        lines.append(f"| {symbol} | {info['source_m1_candles']} | {info['actual_start']} | {info['actual_end']} | "
                      f"{'PASSED' if info['cross_validation_passed_all_timeframes'] else 'FAILED'} |")
    lines.append("")
    lines.append("Generated candle counts per timeframe:")
    lines.append("")
    lines.append("| Symbol | M1 | M5 | M15 | M30 | H1 | H4 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for symbol, info in data.get("per_symbol_data", {}).items():
        counts = info["generated_candle_counts"]
        lines.append(f"| {symbol} | {counts.get('M1')} | {counts.get('M5')} | {counts.get('M15')} | "
                      f"{counts.get('M30')} | {counts.get('H1')} | {counts.get('H4')} |")
    lines.append("")
    lines.append(f"- Timeframe mapping (entry_mapping): `{json.dumps(data.get('timeframe_mapping'))}`")
    lines.append(f"- Lookback configuration: `{json.dumps(data.get('lookback_configuration'))}`")
    lines.append("")

    lines.append("## Concise Summary (Overall)")
    lines.append("")
    lines.append(AGG_HEADER)
    lines.append(_agg_row("ALL 96 RUNS", overall))
    lines.append("")

    lines.append("## Per-Symbol Summary")
    lines.append("")
    lines.append("Each row combines all 4 strategies x 6 timeframes for that symbol (24 cells). "
                  "Max DD range is the min-max across those 24 cells' own values, not a combined drawdown "
                  "(drawdown is sequence-dependent and not additive across independent runs).")
    lines.append("")
    lines.append(AGG_HEADER)
    for symbol in data.get("symbols", sorted(by_symbol)):
        if symbol in by_symbol:
            lines.append(_agg_row(symbol, _aggregate(by_symbol[symbol])))
    lines.append("")

    lines.append("## Per-Timeframe Summary")
    lines.append("")
    lines.append("Each row combines all 4 strategies x 4 symbols for that timeframe (16 cells).")
    lines.append("")
    lines.append(AGG_HEADER)
    for tf in data.get("timeframes", sorted(by_timeframe)):
        if tf in by_timeframe:
            lines.append(_agg_row(tf, _aggregate(by_timeframe[tf])))
    lines.append("")

    lines.append("## Per-Strategy Summary")
    lines.append("")
    lines.append("Each row combines all 4 symbols x 6 timeframes for that strategy (24 cells).")
    lines.append("")
    lines.append(AGG_HEADER)
    for strategy in data.get("strategies", sorted(by_strategy)):
        if strategy in by_strategy:
            lines.append(_agg_row(strategy, _aggregate(by_strategy[strategy])))
    lines.append("")

    lines.append("## Full 96-Run Matrix")
    lines.append("")
    lines.append("| Strategy | Symbol | Timeframe | Trades | Resolved | None | TP1 | TP2 | SL | Win Rate | PF | "
                  "Net R | Expectancy | Avg R | Max DD | Median Dur (min) |")
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for strategy in data.get("strategies", sorted(by_strategy)):
        for symbol in data.get("symbols", sorted(by_symbol)):
            for tf in data.get("timeframes", sorted(by_timeframe)):
                cell = data["results"].get(strategy, {}).get(symbol, {}).get(tf)
                if cell is None:
                    lines.append(f"| {strategy} | {symbol} | {tf} | MISSING | | | | | | | | | | | | |")
                    continue
                if _is_failed(cell):
                    lines.append(f"| {strategy} | {symbol} | {tf} | **FAILED**: {cell['error_type']}: "
                                  f"{cell['error_message']} | | | | | | | | | | | | |")
                    continue
                m = cell["metrics"]
                lines.append(
                    f"| {strategy} | {symbol} | {tf} | {cell['trade_count']} | {cell['resolved_count']} | "
                    f"{cell['none_count']} | {cell['tp1_count']} | {cell['tp2_count']} | {cell['sl_count']} | "
                    f"{pct(m['win_rate'])} | {r2(m['profit_factor'])} | {r2(m['net_r'])} | {r2(m['expectancy'])} | "
                    f"{r2(m['average_r'])} | {r2(m['max_drawdown_r'])} | "
                    f"{r2(cell['median_duration_minutes']) if cell['median_duration_minutes'] is not None else 'n/a'} |"
                )
    lines.append("")
    lines.append("This report contains no recommendation, no ranking, and no \"best\" selection anywhere. "
                  "It establishes a clean, current-version baseline across all 96 configurations only.")
    return "\n".join(lines)


def main() -> None:
    OUT_PATH.write_text(render())
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
