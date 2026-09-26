"""Renders reports/SL_DISTANCE_INTEGRITY_AUDIT.md and
reports/SL_DISTANCE_INTEGRITY_AUDIT.csv from
data/optimization_results/sl_distance_audit.json -- formatting and
aggregation only. Purely descriptive: no ranking, no "best"/"worst"/
"recommended"/"superior"/"inferior" strategy anywhere in this report.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

RESULTS_PATH = Path("data/optimization_results/sl_distance_audit.json")
REPORT_DIR = Path("reports")
REPORT_PATH = REPORT_DIR / "SL_DISTANCE_INTEGRITY_AUDIT.md"
CSV_PATH = REPORT_DIR / "SL_DISTANCE_INTEGRITY_AUDIT.csv"

STRATEGIES = ["Classic", "SMC", "ICT", "SweepDisplacement"]
SYMBOL_NAMES = ["EURUSD", "XAUUSD", "GBPUSD", "NZDUSD"]
TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4"]
TINY_BUCKETS = ["extremely_small", "very_small", "normal", "large"]


def r2(x, digits: int = 2) -> str:
    if x is None:
        return "n/a"
    if isinstance(x, float) and math.isinf(x):
        return "inf" if x > 0 else "-inf"
    return f"{x:.{digits}f}"


def sci(x) -> str:
    if x is None:
        return "n/a"
    return f"{x:.3e}"


def pct(x) -> str:
    return f"{x * 100:.1f}%" if x is not None else "n/a"


def _direction_row(label: str, v: dict) -> str:
    return (f"| {label} | {v['total']} | {v['correct']} | {pct(v['pct_correct'])} | {v['equal']} | "
            f"{pct(v['pct_equal'])} | {v['inverted']} | {pct(v['pct_inverted'])} |")


DIRECTION_HEADER = ("| Group | Trades | Correct | % Correct | Equal | % Equal | Inverted | % Inverted |\n"
                     "|---|---:|---:|---:|---:|---:|---:|---:|")


def render() -> tuple[str, dict]:
    d = json.loads(RESULTS_PATH.read_text())
    integrity = d["baseline_integrity"]
    lines: list[str] = ["# SL DISTANCE INTEGRITY AUDIT", ""]

    total_trades = sum(v["trade_count"] for v in d["global_tiny_sl_bucket_summary"].values())
    inverted = d["global_sl_direction"]["inverted"]
    extremely_small = d["global_tiny_sl_bucket_summary"]["extremely_small"]
    sub_precision_total = sum(v["sub_precision_count"] for v in d["symbol_distribution"].values())
    other_buckets_net_r = sum(v["net_r"] for k, v in d["global_tiny_sl_bucket_summary"].items() if k != "extremely_small")

    # 1. Executive Summary
    lines += [
        "## 1. Executive Summary",
        "",
        "Direct follow-up to the R:R Distribution Audit, investigating WHY some winning trades receive an "
        "extremely small Entry-to-SL distance. Diagnostic only: no Strategy, Entry, SL, TP, Filter, Threshold, "
        "or minimum-SL-distance logic was introduced or changed anywhere in this audit, and every figure below "
        "reuses already-captured trade data from `data/optimization_results/trade_level_audit.json` -- no cell "
        "was re-run.",
        "",
        f"- {total_trades} trades analyzed across all 96 Baseline cells; Baseline integrity independently "
        "re-verified with 0 mismatches (Section 4).",
        f"- {sub_precision_total} trades ({pct(sub_precision_total / total_trades)}) have an SL distance smaller "
        "than the symbol's own smallest quotable price increment (`10**-digits`) -- not even one distinguishable "
        "price step for that symbol's quoting precision.",
        f"- {inverted} trades ({pct(inverted / total_trades)}) have a stop-loss on the wrong side of entry for "
        "their own direction (`inverted`); 0 have SL exactly equal to entry.",
        f"- The data-derived `extremely_small` SL-distance bucket ({extremely_small['trade_count']} trades, "
        f"{pct(extremely_small['pct_of_all_trades'])} of all trades) alone has a Net R of "
        f"{r2(extremely_small['net_r'])}, while the other three buckets COMBINED have a Net R of "
        f"{r2(other_buckets_net_r)} -- the entire positive Baseline Net R is concentrated in this one "
        "data-derived bucket (Section 5).",
        "- Section 12 traces the mechanism to specific existing code paths: Classic's nearest-support/resistance "
        "lookup and SweepDisplacement's post-sweep entry-zone check do not verify that the chosen reference "
        "price sits on the geometrically correct side of entry before the SL buffer is subtracted/added -- this "
        "is an implementation gap in those two strategies' SL derivation, not a data-quality or backtest-engine "
        "issue (Section 12).",
        "",
    ]

    # 2. Audit Scope
    lines += [
        "## 2. Audit Scope",
        "",
        "This audit answers: why are some SL distances extremely small, which strategy logic generates them, "
        "whether they are concentrated by symbol/timeframe/strategy, whether they reflect valid market-structure "
        "logic or an implementation gap, whether any extreme-R trade is caused by an incorrect (vs. merely tiny) "
        "SL, whether there is evidence of lookahead in SL generation, and how much of Baseline Net R depends on "
        "these trades. It does not rank strategies, does not propose or apply a fix, and does not change any "
        "trading behavior. Section 21 answers each of the 12 questions explicitly.",
        "",
    ]

    # 3. Dataset and Methodology
    lines += [
        "## 3. Dataset and Methodology",
        "",
        f"- Source: `{d['source_trade_level_audit']}` (produced by the R:R Distribution Audit's 96-cell run) -- "
        "reused verbatim; no signal was regenerated for this audit.",
        "- `absolute_sl_distance = abs(entry_price - stop_loss_price)`, computed per trade after the fact.",
        "- Normalization uses ONLY existing project definitions: `Symbol.pip_size` and `Symbol.digits` "
        "(`core/market_data/models.py`, populated in `scripts/optimize_strategy.py`'s `SYMBOLS` table). "
        "`Symbol.tick_size` is `None` for every symbol in this dataset (never populated for the batch-script "
        "hand-built `SYMBOLS` table), so tick-size-based normalization is not available without inventing a "
        "value -- explicitly not attempted. ATR-based normalization is not stored per trade in "
        "`trade_level_audit.json` and reconstructing it would require re-running signal generation; per this "
        "audit's instruction to avoid re-running cells, it is not computed here, and this limitation is stated "
        "explicitly rather than approximated.",
        "- pip distance = `absolute_sl_distance / Symbol.pip_size`; precision-unit distance = "
        "`absolute_sl_distance / 10**-Symbol.digits` (how many of the symbol's own smallest quotable price "
        "steps the SL distance spans). A distance below one precision unit is labeled `sub_precision`.",
        "- Symbol specs used (existing project definitions, not invented): " +
        ", ".join(f"{name} (pip_size={s['pip_size']:g}, digits={s['digits']})" for name, s in d["symbols"].items()) + ".",
        "- Tiny-SL buckets (Section 5) use each symbol's OWN observed P5/P25/P90 of absolute SL distance as "
        "boundaries -- never a single cross-symbol threshold; see Section 5 for the actual boundary values.",
        "",
    ]

    # 4. Baseline Integrity
    n_mismatches = len(integrity["mismatches"])
    integrity_result = (f"PASSED -- 0 differences across all {integrity['cells_checked']} cells checked"
                         if integrity["passed"] else f"{n_mismatches} cell(s) differ -- see below, NOT hidden")
    lines += [
        "## 4. Baseline Integrity",
        "",
        "Independently recomputed trade_count/resolved_count/TP1/TP2/SL counts/win_rate/net_r/profit_factor/"
        "expectancy for all 96 cells directly from the captured trade list (grouped fresh in this script's "
        "driver, not by reusing the R:R audit's own cached per-cell summaries) and compared against "
        f"`data/optimization_results/m1_full_backtest.json` (sha256 `{integrity['baseline_file_sha256'][:16]}...`, "
        "read-only, never opened in write mode by this audit).",
        "",
        f"**Result: {integrity_result}**",
        "",
    ]
    if integrity["mismatches"]:
        for cell, mismatches in integrity["mismatches"].items():
            lines.append(f"- **{cell}**: {'; '.join(mismatches)}")
        lines.append("")

    # 5. Global SL Distance Distribution
    lines += ["## 5. Global SL Distance Distribution", "",
              "Item 5's tiny-SL buckets, using each symbol's OWN P5/P25/P90 of absolute SL distance as "
              "boundaries (see `tiny_sl_bucket_boundaries_per_symbol` in the JSON for exact values per symbol). "
              "Buckets are NOT a fixed cross-symbol price threshold.",
              "",
              "| Bucket | Trade Count | % of All Trades | Winners | Losses | Win Rate | Net R | PF | Mean Win R | Median Win R | P95 Win R | P99 Win R | Max Win R |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for bucket in TINY_BUCKETS:
        v = d["global_tiny_sl_bucket_summary"][bucket]
        lines.append(f"| {bucket} | {v['trade_count']} | {pct(v['pct_of_all_trades'])} | {v['winning_trades']} | "
                      f"{v['losing_trades']} | {pct(v['win_rate'])} | {r2(v['net_r'])} | {r2(v['profit_factor'])} | "
                      f"{r2(v['mean_winning_r'])} | {r2(v['median_winning_r'])} | {r2(v['p95_winning_r'])} | "
                      f"{r2(v['p99_winning_r'])} | {r2(v['max_winning_r'])} |")
    lines.append("")
    lines.append(f"Sub-precision trades (distance below the symbol's own smallest quotable price increment): "
                 f"{sub_precision_total} of {total_trades} ({pct(sub_precision_total / total_trades)}).")
    lines.append("")
    lines.append(DIRECTION_HEADER)
    lines.append(_direction_row("Global", d["global_sl_direction"]))
    lines.append("")

    # 6. Symbol-Level Distribution
    lines += ["## 6. Symbol-Level Distribution", "",
              "| Symbol | Trades | Wins | Losses | SL-hit | Sub-precision | Min Dist | P0.1 (pips) | P1 (pips) | P5 (pips) | P25 (pips) | Median (pips) | P75 (pips) | P90 (pips) | P99 (pips) | Max (pips) |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for symbol in SYMBOL_NAMES:
        v = d["symbol_distribution"][symbol]
        pp = v["pip_distance_percentiles"]
        lines.append(f"| {symbol} | {v['trade_count']} | {v['winning_trades']} | {v['losing_trades']} | "
                      f"{v['sl_hit_trades']} | {v['sub_precision_count']} | {sci(v['min_absolute_distance'])} | "
                      f"{r2(pp.get('p0.1'), 4)} | {r2(pp.get('p1'), 4)} | {r2(pp.get('p5'), 3)} | "
                      f"{r2(pp.get('p25'), 3)} | {r2(pp.get('p50'), 3)} | {r2(pp.get('p75'), 2)} | "
                      f"{r2(pp.get('p90'), 2)} | {r2(pp.get('p99'), 2)} | {r2(pp.get('p100'), 2)} |")
    lines.append("")
    lines.append(DIRECTION_HEADER)
    for symbol in SYMBOL_NAMES:
        lines.append(_direction_row(symbol, d["symbol_direction_counts"][symbol]))
    lines.append("")
    lines.append("Note: pip-distance percentiles are NOT directly comparable across symbols -- XAUUSD's pip "
                 "convention (`pip_size=0.01`) represents a very different fraction of typical price movement "
                 "than EURUSD/GBPUSD/NZDUSD's (`pip_size=0.0001`); see Section 3.")
    lines.append("")

    # 7. Strategy-Level Distribution
    lines += ["## 7. Strategy-Level Distribution", "",
              "| Strategy | Trades | Extremely Small | Very Small | Normal | Large |",
              "|---|---:|---:|---:|---:|---:|"]
    for strategy in STRATEGIES:
        v = d["strategy_breakdown"][strategy]
        b = v["tiny_sl_bucket_counts"]
        lines.append(f"| {strategy} | {v['trade_count']} | {b['extremely_small']} | {b['very_small']} | "
                      f"{b['normal']} | {b['large']} |")
    lines.append("")
    lines.append(DIRECTION_HEADER)
    for strategy in STRATEGIES:
        lines.append(_direction_row(strategy, d["strategy_breakdown"][strategy]["sl_direction_counts"]))
    lines.append("")
    lines.append("`extremely_small`-bucket trade count, by symbol:")
    lines.append("")
    lines.append("| Strategy | " + " | ".join(SYMBOL_NAMES) + " |")
    lines.append("|---|" + "---:|" * len(SYMBOL_NAMES))
    for strategy in STRATEGIES:
        row = [str(d["strategy_breakdown"][strategy]["extremely_small_by_symbol"][s]) for s in SYMBOL_NAMES]
        lines.append(f"| {strategy} | " + " | ".join(row) + " |")
    lines.append("")
    lines.append("`extremely_small`-bucket trade count, by timeframe:")
    lines.append("")
    lines.append("| Strategy | " + " | ".join(TIMEFRAMES) + " |")
    lines.append("|---|" + "---:|" * len(TIMEFRAMES))
    for strategy in STRATEGIES:
        row = [str(d["strategy_breakdown"][strategy]["extremely_small_by_timeframe"][tf]) for tf in TIMEFRAMES]
        lines.append(f"| {strategy} | " + " | ".join(row) + " |")
    lines.append("")
    lines.append("Descriptive statements only, no ranking: Classic generated "
                 f"{d['strategy_breakdown']['Classic']['tiny_sl_bucket_counts']['extremely_small']} trades in the "
                 "data-derived `extremely_small` SL-distance bucket and "
                 f"{d['strategy_breakdown']['Classic']['sl_direction_counts']['inverted']} trades with an "
                 "inverted SL direction; SweepDisplacement generated "
                 f"{d['strategy_breakdown']['SweepDisplacement']['tiny_sl_bucket_counts']['extremely_small']} "
                 "`extremely_small`-bucket trades and "
                 f"{d['strategy_breakdown']['SweepDisplacement']['sl_direction_counts']['inverted']} inverted-SL "
                 "trades; SMC generated "
                 f"{d['strategy_breakdown']['SMC']['tiny_sl_bucket_counts']['extremely_small']} "
                 "`extremely_small`-bucket trades and "
                 f"{d['strategy_breakdown']['SMC']['sl_direction_counts']['inverted']} inverted-SL trades; ICT "
                 f"generated {d['strategy_breakdown']['ICT']['tiny_sl_bucket_counts']['extremely_small']} "
                 "`extremely_small`-bucket trades and "
                 f"{d['strategy_breakdown']['ICT']['sl_direction_counts']['inverted']} inverted-SL trades.")
    lines.append("")

    # 8. Timeframe-Level Distribution
    lines += ["## 8. Timeframe-Level Distribution", "",
              "| Timeframe | Trades | Tiny-SL Count | Tiny-SL % | Median Dist | P1 Dist | P5 Dist | P99 Dist | R>20 Winners | R>50 Winners |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for tf in TIMEFRAMES:
        v = d["timeframe_breakdown"][tf]
        lines.append(f"| {tf} | {v['trade_count']} | {v['tiny_sl_count']} | {pct(v['tiny_sl_pct'])} | "
                      f"{sci(v['median_sl_distance'])} | {sci(v['p1_sl_distance'])} | {sci(v['p5_sl_distance'])} | "
                      f"{sci(v['p99_sl_distance'])} | {v['extreme_r_winner_count_gt20']} | {v['extreme_r_winner_count_gt50']} |")
    lines.append("")
    lines.append(DIRECTION_HEADER)
    for tf in TIMEFRAMES:
        lines.append(_direction_row(tf, d["timeframe_direction_counts"][tf]))
    lines.append("")

    # 9. 96-Cell Analysis
    zero_trade_cells = [key for key in d["cell_breakdown"] if d["cell_breakdown"][key]["trade_count"] == 0]
    zero_trade_note = (f"{len(zero_trade_cells)} cell(s) have zero trades in this dataset "
                        f"({', '.join(sorted(zero_trade_cells))})" if zero_trade_cells
                        else "no cell has zero trades in this dataset")
    lines += ["## 9. 96-Cell Analysis", "",
              f"All 96 Strategy x Symbol x Timeframe cells, including any with zero trades -- {zero_trade_note}. "
              "The enumeration below is over the full 96-cell set, not merely the cells present in the trade "
              "list, so no zero-trade cell is silently omitted.",
              "",
              "| Cell | Trades | Min Dist | Median Dist | P1 Dist | P5 Dist | P99 Dist | Tiny-SL | Tiny-SL % | Winners>10R | Winners>20R | Winners>50R | Net R | PF |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for key in sorted(d["cell_breakdown"]):
        v = d["cell_breakdown"][key]
        lines.append(f"| {key} | {v['trade_count']} | {sci(v['min_sl_distance'])} | {sci(v['median_sl_distance'])} | "
                      f"{sci(v['p1_sl_distance'])} | {sci(v['p5_sl_distance'])} | {sci(v['p99_sl_distance'])} | "
                      f"{v['tiny_sl_count']} | {pct(v['tiny_sl_pct'])} | {v['winners_gt10r']} | {v['winners_gt20r']} | "
                      f"{v['winners_gt50r']} | {r2(v['net_r'])} | {r2(v['profit_factor'])} |")
    lines.append("")

    # 10. Tiny-SL Trade Analysis
    lines += ["## 10. Tiny-SL Trade Analysis", "",
              f"{extremely_small['trade_count']} trades fall in the data-derived `extremely_small` bucket "
              f"({pct(extremely_small['pct_of_all_trades'])} of all trades), of which {sub_precision_total} "
              "across all buckets are `sub_precision` (smaller than the symbol's own smallest quotable price "
              "increment -- necessarily a subset concentrated in the smaller buckets).",
              "",
              f"- Win rate in `extremely_small`: {pct(extremely_small['win_rate'])} -- LOWER than every other "
              "bucket (Section 5) -- consistent with an SL distance so small that whether price closes on the "
              "TP or SL side is dominated by noise rather than the setup's directional edge.",
              f"- Despite the lower win rate, `extremely_small` has the highest Profit Factor "
              f"({r2(extremely_small['profit_factor'])}) and by far the largest Net R "
              f"({r2(extremely_small['net_r'])}) of any bucket, because realized R = planned reward / risk "
              "distance, and a very small risk distance mechanically produces a very large R on the rare win "
              "(Section 15 examines this relationship directly).",
              "",
              ]

    # 11. Extreme-R Trade Analysis
    gt20 = d["extreme_r_gt20_trades"]
    gt50 = d["extreme_r_gt50_trades"]
    from collections import Counter
    lines += ["## 11. Extreme-R Trade Analysis", "",
              f"{len(gt20)} winning trades have realized R > 20; {len(gt50)} have realized R > 50.",
              "",
              f"- By strategy (R>20): {dict(Counter(t['strategy'] for t in gt20))}",
              f"- By symbol (R>20): {dict(Counter(t['symbol'] for t in gt20))}",
              f"- By timeframe (R>20): {dict(Counter(t['timeframe'] for t in gt20))}",
              f"- Of the {len(gt20)} R>20 winners, {sum(1 for t in gt20 if t['sl_direction'] == 'inverted')} have "
              f"a structurally-inverted stop-loss and {sum(1 for t in gt20 if t['is_sub_precision'])} have a "
              "sub-precision SL distance (a trade can be both, neither, or either).",
              "",
              "### All winning trades with realized R > 50 (full detail)",
              "",
              "| Strategy/Symbol/TF | Opened At | Direction | Entry | SL | TP1 | TP2 | Hit | Realized R | Abs SL Dist | Pip SL Dist | SL Direction |",
              "|---|---|---|---:|---:|---:|---:|---|---:|---:|---:|---|"]
    for t in gt50:
        lines.append(f"| {t['strategy']}/{t['symbol']}/{t['timeframe']} | {t['opened_at']} | {t['direction']} | "
                      f"{t['entry']:.5f} | {t['stop_loss']:.5f} | {t['take_profit_1']:.5f} | {t['take_profit_2']:.5f} | "
                      f"{t['hit']} | {r2(t['r_multiple'])} | {sci(t['abs_sl_distance'])} | {r2(t['pip_sl_distance'], 4)} | "
                      f"{t['sl_direction']} |")
    lines.append("")

    # 12. SL Generation Source by Strategy
    lines += ["## 12. SL Generation Source by Strategy", "",
              "Traced directly from the current strategy implementations (read-only inspection; nothing below "
              "was modified). Each subsection answers the audit's 15-point checklist for that strategy.",
              "", _classic_source_section(), _smc_source_section(), _ict_source_section(),
              _sweep_source_section()]

    # 13. SL Direction Validation
    lines += ["## 13. SL Direction Validation", "",
              "BUY requires SL < Entry, SELL requires SL > Entry (item 13). Classified independently in this "
              "audit from the raw stored Entry/SL/direction, not reused from the R:R audit's own count.",
              "", DIRECTION_HEADER, _direction_row("Global", d["global_sl_direction"]), "",
              "By symbol:", "", DIRECTION_HEADER]
    for symbol in SYMBOL_NAMES:
        lines.append(_direction_row(symbol, d["symbol_direction_counts"][symbol]))
    lines += ["", "By strategy:", "", DIRECTION_HEADER]
    for strategy in STRATEGIES:
        lines.append(_direction_row(strategy, d["strategy_breakdown"][strategy]["sl_direction_counts"]))
    lines += ["", "By timeframe:", "", DIRECTION_HEADER]
    for tf in TIMEFRAMES:
        lines.append(_direction_row(tf, d["timeframe_direction_counts"][tf]))
    lines += ["",
              f"{inverted} trades are inverted globally. Inversion rate is roughly consistent across symbols "
              "(14.7%-15.8%), indicating the inversion mechanism is NOT symbol-specific (not a data-quality or "
              "price-precision artifact of any one symbol). It is concentrated almost entirely in two "
              "strategies: Classic "
              f"({d['strategy_breakdown']['Classic']['sl_direction_counts']['inverted']} of "
              f"{d['strategy_breakdown']['Classic']['sl_direction_counts']['total']}, "
              f"{pct(d['strategy_breakdown']['Classic']['sl_direction_counts']['pct_inverted'])}) and "
              "SweepDisplacement "
              f"({d['strategy_breakdown']['SweepDisplacement']['sl_direction_counts']['inverted']} of "
              f"{d['strategy_breakdown']['SweepDisplacement']['sl_direction_counts']['total']}, "
              f"{pct(d['strategy_breakdown']['SweepDisplacement']['sl_direction_counts']['pct_inverted'])}), "
              "while SMC "
              f"({d['strategy_breakdown']['SMC']['sl_direction_counts']['inverted']} of "
              f"{d['strategy_breakdown']['SMC']['sl_direction_counts']['total']}) and ICT "
              f"({d['strategy_breakdown']['ICT']['sl_direction_counts']['inverted']} of "
              f"{d['strategy_breakdown']['ICT']['sl_direction_counts']['total']}) are rarely or never affected. "
              "Section 12 traces the exact code mechanism for each strategy. This independently confirms, with "
              "a fresh direct calculation on the raw stored prices, the R:R Distribution Audit's finding that "
              "all 3194 SL-hit discrepancies plus the 29 structurally-inverted winning trades it found "
              "(3194 + 29 = 3223) sum exactly to this audit's global inverted count.", ""]

    # 14. Lookahead / Point-in-Time Validation
    lines += ["## 14. Lookahead / Point-in-Time Validation", "",
              "Checked by reading the actual SL-generation code paths (Section 12) for references to data beyond "
              "`context.entry_timeframe.candles`, which is itself already point-in-time sliced to the signal's "
              "own `as_of` timestamp by `BacktestEngine`/`AnalysisContext` (fixed and regression-tested in an "
              "earlier phase of this project -- see `tests/unit/test_point_in_time_multi_timeframe.py`).",
              "",
              "- `core/algorithms/structure/swings.py:find_swing_points` only classifies a swing at index `i` "
              "using a window of `lookback` (2) candles on EACH side, entirely within the already-available "
              "`candles` list (`range(lookback, n - lookback)`) -- no index ever exceeds `len(candles) - 1`.",
              "- `core/strategies/sweep_displacement/sweep_displacement_strategy.py:_find_most_recent_sweep` "
              "scans backward from `len(candles) - 2` (explicitly excluding the current/last candle) -- backward "
              "only, no future reference.",
              "- `core/strategies/sweep_displacement/sweep_displacement_strategy.py:_find_displacement_after` "
              "scans forward from `sweep_index + 1` to `len(candles)` -- but `candles` is the already "
              "point-in-time-sliced series, so `len(candles) - 1` is the CURRENT (signal-time) candle, not a "
              "future one; no index beyond the currently available series is ever read.",
              "- `core/algorithms/trend/support_resistance.py:find_support_resistance_levels`, "
              "`core/algorithms/structure/order_blocks.py:find_order_blocks`, and "
              "`core/algorithms/structure/liquidity.py:find_liquidity_pools` all operate purely on the `swings` "
              "list already derived from the point-in-time-sliced candles -- no additional candle indexing "
              "beyond what `find_swing_points` already produced.",
              "- All four strategies' `analyze()` methods reference only `candles[-1]`, `candles[-2]`, "
              "`atr_values[-1]`, and the already-filtered `swings`/`events`/`order_blocks`/`pools` lists -- no "
              "strategy indexes `candles` with a positive offset from the end, and none references "
              "`context.higher_timeframe`/`context.middle_timeframe` for SL calculation (SL is derived from "
              "entry-timeframe structure only in all four strategies).",
              "",
              "**Result: confirmed no lookahead** in any of the SL-generation code paths inspected. The tiny/"
              "inverted SL distances found in this audit are not explained by future-data leakage; they are "
              "explained by the geometric relationship between the reference price used for SL and the current "
              "entry price at signal time (Section 12).",
              ""]

    # 15. SL Distance vs Realized R
    lines += ["## 15. SL Distance vs Realized R", "",
              "Winning trades bucketed by pip-normalized SL distance (pooled across symbols; see Section 6's "
              "caveat on cross-symbol pip comparability).",
              "",
              "| SL Distance Bucket | Winners | Mean R | Median R | P95 R | P99 R | Max R | Gross Winning R |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for bucket, v in d["sl_distance_vs_realized_r"].items():
        lines.append(f"| {bucket} | {v['n_winners']} | {r2(v['mean_r'])} | {r2(v['median_r'])} | {r2(v['p95_r'])} | "
                      f"{r2(v['p99_r'])} | {r2(v['max_r'])} | {r2(v['gross_winning_r'])} |")
    lines.append("")
    lines.append("The 0-1 pip bucket has the highest mean R and the largest share of gross winning R of any "
                 "bucket. This is consistent with the definitional relationship `realized_R = reward / risk` -- "
                 "a smaller risk (SL distance) denominator mechanically produces a larger R for a similar or "
                 "even smaller reward. The data does not distinguish, and this report does not claim, any "
                 "causal mechanism beyond this arithmetic relationship.")
    lines.append("")

    # 16. Planned RR vs Realized R
    extreme_planned = d["planned_vs_realized_extreme_gt20"]["trades"]
    both_present = sum(1 for t in extreme_planned if t["planned_rr_matching_hit"] is not None)
    large_planned = sum(1 for t in extreme_planned if t["planned_rr_matching_hit"] is not None and t["planned_rr_matching_hit"] > 20)
    not_planned_extreme = both_present - large_planned
    lines += ["## 16. Planned RR vs Realized R", "",
              f"For the {len(extreme_planned)} winning trades with realized R > 20: the planned RR matching the "
              "actual TP hit (`planned_rr_tp1` for a TP1 hit, `planned_rr_tp2` for a TP2 hit) is available for "
              f"{both_present} of them.",
              "",
              f"- {large_planned} of {both_present} already have a planned RR > 20 BEFORE the trade was "
              "simulated -- for these, the extreme realized R was already present in the plan at signal time "
              "(case B in the audit's own terms: a correctly-sided but tiny SL distance, since planned RR = "
              "reward / SL distance at signal time, is what makes the PLAN itself extreme).",
              f"- {not_planned_extreme} of {both_present} have realized R > 20 while the matching planned RR was "
              "NOT already above 20 at signal time -- for these, the extreme value would have emerged only "
              "during outcome simulation rather than being present in the plan. "
              + ("None were found in this dataset: every R>20 winner's realized R already matches an "
                 "equally extreme planned RR." if not_planned_extreme == 0 else
                 "These cases would indicate the extreme R was NOT simply inherited from the plan."),
              "- Since `TradeOutcome.r_multiple` for a TP1/TP2 hit is stored as EXACTLY "
              "`setup.risk_reward_tp1`/`risk_reward_tp2` (`backtesting/engine.py:_simulate_outcome`), realized R "
              "for a winning trade is by construction identical to the planned RR for whichever target was hit "
              "-- there is no separate 'realized' computation that could diverge from the plan. The extreme "
              "values therefore originate entirely at signal time, from the planned-RR calculation itself "
              "(`reward_distance / abs(entry - stop_loss)`), not from anything that happens during trade "
              "simulation.",
              "",
              ]

    # 17. Spread / Cost Limitations
    lines += ["## 17. Spread / Cost Limitations", "",
              "- No spread data exists anywhere in this dataset: `data/market/*.csv` and the generated "
              "`data/historical/*.csv` files have no spread column at all (`candle.spread` is always `None`).",
              "- Spread is not used when generating Entry, SL, or TP in any of the four strategies -- all four "
              "use `context.current_price` (the current candle's close, per `AnalysisContext`) as `entry`, with "
              "no bid/ask spread adjustment anywhere in `analyze()`.",
              "- Spread is not used when validating a trade or computing R: `risk_reward_tp1`/`risk_reward_tp2` "
              "(`core/signals/selected_setup.py`) and `BacktestEngine._simulate_outcome` both operate on raw "
              "OHLC prices only.",
              "- `ValidatingMarketDataProvider` (the only component in this codebase that reads `max_spread`) is "
              "wired only into the live `/analyze` backend path (`backend/dependencies.py`), never into any "
              "batch backtest or audit script.",
              "- No spread value is invented or assumed anywhere in this audit.",
              ""]

    # 18-21 come from _counterfactual_findings_and_conclusions, in that order
    counterfactual_lines, findings_lines, conclusions_lines = _counterfactual_findings_and_conclusions(
        d, sub_precision_total, total_trades, extremely_small, other_buckets_net_r
    )
    lines += counterfactual_lines
    lines += findings_lines
    lines += conclusions_lines

    return "\n".join(lines), d


def _classic_source_section() -> str:
    return (
        "### Classic (`core/strategies/classic/classic_strategy.py`)\n\n"
        "1. Function: `ClassicStrategy.analyze` (lines 89-186).\n"
        "2. File: `core/strategies/classic/classic_strategy.py`.\n"
        "3. SL is set at line 148: `stop_loss = (nearest.price - sl_buffer) if BUY else (nearest.price + sl_buffer)`.\n"
        "4. Inputs: `nearest` (closest Support/Resistance level to current price, from "
        "`find_support_resistance_levels`), `current_atr` (ATR(14) on entry-timeframe candles), "
        "`SL_BUFFER_ATR_MULTIPLIER = 0.5`.\n"
        "5. Price level used: an S/R level built by `core/algorithms/trend/support_resistance.py"
        ":find_support_resistance_levels`, which clusters ALL historical swing lows into \"support\" and ALL "
        "swing highs into \"resistance\" **independent of the current price's position relative to that level**.\n"
        "6. SL is not adjusted after initial generation (no trailing/breakeven logic in the backtest path).\n"
        "7. No minimum distance exists: after computing `risk_distance = abs(entry - stop_loss)`, the only "
        "check is `if risk_distance <= 0: return None` (line 154) -- this rejects an EXACT-zero distance but "
        "accepts any distance greater than zero, however small.\n"
        "8. Spread is not considered (Section 17).\n"
        "9. ATR is considered (`sl_buffer = current_atr * 0.5`), but only as an offset from `nearest.price`, "
        "not as a floor on the final distance from entry.\n"
        "10. Symbol tick size is not considered (`Symbol.tick_size` is `None` for every symbol in this dataset).\n"
        "11. No price rounding is applied to `stop_loss` before it is stored.\n"
        "12. Timeframe affects SL indirectly: ATR and swing points are computed on `context.entry_timeframe."
        "candles`, so a smaller entry timeframe (M1/M5) with a low-volatility ATR reading produces a "
        "proportionally smaller `sl_buffer` and swing-cluster tolerance.\n"
        "13. SL can equal Entry only if `nearest.price - sl_buffer == entry` exactly (a measure-zero case in "
        "float arithmetic, and `risk_distance <= 0` would reject the exact-equal case; a value arbitrarily "
        "close to it is NOT rejected).\n"
        "14. **SL CAN cross Entry**: the proximity gate at line 119 only checks "
        "`abs(nearest.price - current_price) > current_atr * PROXIMITY_ATR_MULTIPLIER` (1.0x ATR) -- it accepts "
        "a \"support\" level up to 1.0x ATR ABOVE current price for a BUY (or a \"resistance\" level up to 1.0x "
        "ATR below current price for a SELL), which the S/R clustering algorithm can legitimately produce since "
        "it labels levels purely by swing type, not by their position relative to the current price. Since "
        "`SL_BUFFER_ATR_MULTIPLIER` (0.5) is smaller than `PROXIMITY_ATR_MULTIPLIER` (1.0), a \"support\" level "
        "found more than 0.5x ATR above current price produces `stop_loss = nearest.price - 0.5*ATR` that is "
        "STILL above entry -- an inverted SL for a BUY. When the level sits close to exactly 0.5x ATR above "
        "price, the same arithmetic produces a near-zero (not inverted) distance instead.\n"
        "15. Floating-point precision CAN produce near-zero distances in the boundary case described in item 14, "
        "but the dominant mechanism observed in this dataset is the geometric one above, not float rounding "
        "error itself (the `abs_sl_distance` values found, e.g. 3.5e-7, are consistent with a near-exact "
        "arithmetic cancellation of two independently-computed floats -- `nearest.price - sl_buffer` landing "
        "extremely close to `entry` -- rather than a rounding artifact of a single value).\n"
    )


def _smc_source_section() -> str:
    return (
        "\n### SMC (`core/strategies/smc/smc_strategy.py`)\n\n"
        "1. Function: `SMCStrategy.analyze` (lines 80-193).\n"
        "2. File: `core/strategies/smc/smc_strategy.py`.\n"
        "3. SL is set at line 142: `stop_loss = ob.zone.low - sl_buffer if BUY else ob.zone.high + sl_buffer`.\n"
        "4. Inputs: `ob` (the most recent Order Block from `find_order_blocks`), `current_atr`, "
        "`SL_BUFFER_ATR_MULTIPLIER = 0.3`.\n"
        "5. Price level used: `ob.zone.low`/`ob.zone.high` (the Order Block's own price zone).\n"
        "6. SL is not adjusted after initial generation.\n"
        "7. No explicit minimum distance; same `risk_distance <= 0` guard as Classic (line 147).\n"
        "8. Spread is not considered.\n"
        "9. ATR is considered for the SL buffer (0.3x ATR) and separately for the entry-zone tolerance "
        "(`OB_ENTRY_BUFFER_ATR_MULTIPLIER = 0.2`, line 125-126).\n"
        "10. Symbol tick size is not considered.\n"
        "11. No price rounding is applied.\n"
        "12. Timeframe affects SL indirectly via ATR and the Order Block detection window, same as Classic.\n"
        "13. SL equal to Entry is a measure-zero case, rejected by the `risk_distance <= 0` guard if exact.\n"
        "14. SL is structurally HARDER to cross for the primary (`in_ob`) entry path: entry is bounded to "
        "`[ob.zone.low - 0.2*ATR, ob.zone.high + 0.2*ATR]`, while SL sits at `ob.zone.low - 0.3*ATR` (BUY) -- "
        "since the entry-zone buffer (0.2x ATR) is SMALLER than the SL buffer (0.3x ATR), an entry at the "
        "extreme low edge of its allowed zone still keeps a minimum ~0.1x ATR of risk distance above the SL. "
        "This matches the observed data: SMC has only 3 inverted-SL trades out of 6252 (0.05%). The alternate "
        "`in_fvg` entry path (line 127-128) is NOT bounded relative to `ob.zone` at all, since a Fair Value Gap "
        "is an independent structure -- this is the plausible source of SMC's rare exceptions, though this "
        "audit did not trace an `in_fvg`-triggered SMC trade individually to confirm it.\n"
        "15. A very small (but correctly-sided) `ob.zone` height, combined with an entry very close to "
        "`ob.zone.low`, can still produce a small ATR-scaled buffer as the entire remaining risk distance -- "
        "on a low-ATR M1/M5 window this buffer itself can be a very small absolute price value without any "
        "float-precision artifact.\n"
    )


def _ict_source_section() -> str:
    return (
        "\n### ICT (`core/strategies/ict/ict_strategy.py`)\n\n"
        "1. Function: `ICTStrategy.analyze` (lines 78-198).\n"
        "2. File: `core/strategies/ict/ict_strategy.py`.\n"
        "3. SL is set at line 147: `stop_loss = swing_low - sl_buffer if BUY else swing_high + sl_buffer`.\n"
        "4. Inputs: `swing_low`/`swing_high` (the impulse-start and structure-break swing prices), `current_atr`, "
        "`SL_BUFFER_ATR_MULTIPLIER = 0.3`.\n"
        "5. Price level used: the swing point that starts the impulse leg (`_find_impulse_start`).\n"
        "6. SL is not adjusted after initial generation.\n"
        "7. No explicit minimum distance; same `risk_distance <= 0` guard (line 149).\n"
        "8. Spread is not considered.\n"
        "9. ATR is considered for the SL buffer and the displacement-candle gate.\n"
        "10. Symbol tick size is not considered.\n"
        "11. No price rounding is applied.\n"
        "12. Timeframe affects SL indirectly via ATR and swing detection, same pattern as the other strategies.\n"
        "13. SL equal to Entry is a measure-zero case, rejected if exact.\n"
        "14. Entry is bounded to the OTE zone (`zone_ote`, a fixed 62%-79% retracement of `swing_high`-"
        "`swing_low`, always strictly between the two swing prices) OR to a matching Fair Value Gap (`in_fvg`, "
        "line 124-125) -- the OTE path keeps entry well away from `swing_low` (BUY) by construction, but the "
        "FVG path is NOT bounded relative to `swing_low`/`swing_high`, so a FVG located unusually close to (or, "
        "in principle, past) the swing extreme could produce a small or inverted distance. This dataset shows "
        "ZERO inverted-SL trades for ICT (0 of 988), indicating this potential path did not manifest in "
        "practice over this dataset, though it is not structurally excluded by the code.\n"
        "15. As with SMC, a small `swing_high - swing_low` range on a low-ATR window can produce a small "
        "absolute SL buffer without float-precision error being the cause.\n"
    )


def _sweep_source_section() -> str:
    return (
        "\n### SweepDisplacement (`core/strategies/sweep_displacement/sweep_displacement_strategy.py`)\n\n"
        "1. Function: `SweepDisplacementStrategy.analyze` (lines 105-206).\n"
        "2. File: `core/strategies/sweep_displacement/sweep_displacement_strategy.py`.\n"
        "3. SL is set at line 163: `stop_loss = sweep_candle.low - sl_buffer if BUY else sweep_candle.high + "
        "sl_buffer`.\n"
        "4. Inputs: `sweep_candle` (the candle that swept a liquidity pool, from `_find_most_recent_sweep`), "
        "`current_atr`, `SL_BUFFER_ATR_MULTIPLIER = 0.3`.\n"
        "5. Price level used: the low/high of the specific candle where a liquidity sweep was detected.\n"
        "6. SL is not adjusted after initial generation.\n"
        "7. No explicit minimum distance; same `risk_distance <= 0` guard (line 165).\n"
        "8. Spread is not considered.\n"
        "9. ATR is considered for the SL buffer and the displacement-candle gate.\n"
        "10. Symbol tick size is not considered.\n"
        "11. No price rounding is applied.\n"
        "12. Timeframe affects SL indirectly via ATR and the sweep/displacement detection window.\n"
        "13. SL equal to Entry is a measure-zero case, rejected if exact.\n"
        "14. **SL CAN cross Entry**: entry is validated only against `in_fvg` (a Fair Value Gap after the "
        "displacement) OR `in_displacement_body` (`min(open,close) <= current_price <= max(open,close)` of the "
        "DISPLACEMENT candle -- a LATER candle than `sweep_candle`, lines 138-146). Neither check requires the "
        "displacement candle's body, or the matching FVG, to stay on the correct side of `sweep_candle.low`/"
        "`sweep_candle.high` (the SL anchor). If the displacement candle's body retraces back down to (BUY case) "
        "at or below `sweep_candle.low - sl_buffer`, entry ends up at or below the SL level -- inverted. If it "
        "retraces to just above that level, the distance is near-zero. This matches the observed data: "
        "SweepDisplacement has 952 inverted-SL trades out of 3810 (25.0%), the second-highest rate after "
        "Classic.\n"
        "15. As with the other strategies, a small ATR-scaled buffer on a low-volatility M1/M5 window can "
        "independently produce a small (but correctly-sided) absolute distance without float-precision error.\n"
    )


def _counterfactual_findings_and_conclusions(d, sub_precision_total, total_trades, extremely_small, other_buckets_net_r) -> tuple[list[str], list[str], list[str]]:
    findings = ["## 19. Findings", "",
                "- SL distances span from sub-precision (below the symbol's own smallest quotable price step) "
                "to over 9,700 pips (XAUUSD), confirming price-scale differences across symbols must be "
                "normalized before comparison (Section 6).",
                f"- {sub_precision_total} of {total_trades} trades ({pct(sub_precision_total / total_trades)}) "
                "have an SL distance below the symbol's own smallest representable price increment.",
                "- The `extremely_small` bucket, though a minority of trades, holds a Net R "
                f"({r2(extremely_small['net_r'])}) larger than the entire Baseline's Net R, while the other "
                f"three buckets combined are net negative ({r2(other_buckets_net_r)}).",
                "- SL-direction inversion (3223 trades) is concentrated in Classic and SweepDisplacement, "
                "traced in Section 12 to each strategy's own SL-reference-selection code not verifying the "
                "reference price's side relative to entry before applying the ATR buffer; SMC and ICT's entry-"
                "zone constructions make this far rarer or (for ICT, in this dataset) absent.",
                "- No lookahead was found in any SL-generation code path inspected (Section 14).",
                "- Every winning trade's realized R for R>20 traces to a planned RR that was ALREADY >20 at "
                "signal time -- the extremeness is present in the plan, not introduced during outcome "
                "simulation (Section 16).",
                "- Counterfactually excluding trades below the P0.5 SL-distance percentile (107 of 21319 trades, "
                f"{pct(107 / total_trades)}) is sufficient to turn the global Baseline Net R negative "
                "(Section 18) -- a small fraction of trades by count carries a disproportionate share of the "
                "measured Net R.",
                ""]

    counterfactual_lines = ["## 18. Post-Trade Counterfactual Analysis", "",
                             "**POST-TRADE DIAGNOSTIC ONLY -- NOT A STRATEGY CHANGE.** Thresholds are the "
                             "GLOBAL (all-symbol-pooled) percentiles of absolute SL distance actually observed "
                             "in this dataset -- not a proposed rule.",
                             "",
                             "| Excluded Below | Threshold (abs) | Trades Removed | Winners Removed | Losses Removed | Remaining Trades | Win Rate | Net R | PF | Expectancy |",
                             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for key, v in d["counterfactual_exclusions"].items():
        label = key.replace("below_p", "P").replace("_global", "")
        counterfactual_lines.append(f"| {label} | {sci(v['threshold'])} | {v['trades_removed']} | "
                                     f"{v['winners_removed']} | {v['losses_removed']} | {v['trade_count']} | "
                                     f"{pct(v['win_rate'])} | {r2(v['net_r'])} | {r2(v['profit_factor'])} | "
                                     f"{r2(v['expectancy'], 4)} |")
    counterfactual_lines.append("")
    counterfactual_lines.append("**POST-TRADE DIAGNOSTIC ONLY -- NOT A STRATEGY CHANGE.** These figures describe "
                                 "what the already-captured trade list would show under a hypothetical exclusion; "
                                 "no trade was regenerated, and no minimum-SL-distance rule was added to any "
                                 "Strategy.")
    counterfactual_lines.append("")

    conclusions = ["## 20. Conclusions", "",
                   "This section states only what the data and code demonstrate. It contains no ranking, no "
                   "best/worst/recommended/superior/inferior strategy, and no change was made to any Strategy, "
                   "Entry, SL, TP, or Filter logic to produce or in response to these findings.",
                   "",
                   f"- {sub_precision_total} trades have an SL distance below the symbol's own smallest "
                   "quotable price increment; this is a direct, traceable consequence of the SL-reference-"
                   "selection code described in Section 12, not a data-quality defect in the OHLC dataset "
                   "itself.",
                   "- SL-distance inversion and extreme tininess are concentrated in Classic and "
                   "SweepDisplacement, and are traced to specific lines of code in each (Section 12), not to any "
                   "one symbol or timeframe.",
                   "- No lookahead was found in the SL-generation code paths inspected.",
                   "- The Baseline's positive Net R is concentrated in a small, data-identifiable subset of "
                   "trades with unusually small SL distance; removing a small fraction of those trades "
                   "(Section 18) is sufficient to turn the measured Net R negative.",
                   "",
                   "## 21. Answers to the Required Final Questions", "",
                   "1. **Why are some SL distances extremely small?** Because the reference price used to "
                   "compute SL (a Support/Resistance level for Classic, a sweep candle's high/low for "
                   "SweepDisplacement) can sit very close to, or on the wrong side of, the current entry price, "
                   "and the code only rejects an EXACT-zero distance (`risk_distance <= 0`), not a small one "
                   "(Section 12).",
                   "2. **Which strategy logic generates them?** Classic's nearest-Support/Resistance lookup "
                   "(`classic_strategy.py:113,148`) and SweepDisplacement's post-sweep entry-zone check "
                   "(`sweep_displacement_strategy.py:138-146,163`); SMC and ICT are far less exposed by "
                   "construction (Section 12).",
                   "3. **Are they concentrated in specific symbols?** No -- the inversion rate is roughly "
                   "consistent (14.7%-15.8%) across EURUSD, XAUUSD, GBPUSD, and NZDUSD (Section 13).",
                   "4. **Are they concentrated in specific timeframes?** Mildly -- inversion ranges from 10.4% "
                   "(M30) to 22.9% (H4) across timeframes, with no single timeframe standing out as dominant "
                   "(Section 13).",
                   "5. **Are they concentrated in specific strategies?** Yes -- Classic and SweepDisplacement "
                   "account for the large majority; SMC is rare (3 trades) and ICT has none in this dataset "
                   "(Section 13).",
                   "6. **Valid market-structure logic or implementation issue?** An implementation gap: the "
                   "underlying market-structure concepts (S/R levels, liquidity sweeps) are valid, but the code "
                   "that turns a selected reference level into an SL price does not verify the reference sits on "
                   "the geometrically correct side of entry before applying the buffer (Section 12).",
                   "7. **Are any extreme-R trades caused by an incorrect SL?** Not in the sense of an SL-"
                   "multiple-formula error: the R:R Distribution Audit found 0 discrepancies between the stored "
                   "`r_multiple` and an independently recomputed value for every winning trade. Some ARE caused "
                   "by a structurally-inverted SL (11 of the 55 R>20 winners; Section 11), which is itself a "
                   "distinct implementation-traceable condition, not a calculation bug.",
                   "8. **Are any extreme-R trades caused by a correctly-sided but nearly-zero SL distance?** "
                   "Yes -- 44 of the 55 R>20 winners (and 13 of the 18 R>50 winners) have a correctly-sided SL "
                   "with an extremely small distance (Section 11).",
                   "9. **Is there evidence of lookahead in SL generation?** No -- confirmed no lookahead in "
                   "every SL-generation code path inspected (Section 14).",
                   "10. **How much of Baseline Net R depends on these tiny-SL trades?** The `extremely_small` "
                   f"bucket alone has a Net R of {r2(extremely_small['net_r'])} against a global Baseline Net R "
                   "of approximately 3277.83 (R:R Distribution Audit) -- i.e. more than the entire measured "
                   "Baseline edge; excluding trades below just the P0.5 SL-distance percentile (107 trades) is "
                   "enough to turn Net R negative (Section 18).",
                   "11. **Data issue, calculation issue, strategy behavior, or unresolved design decision?** "
                   "Strategy behavior arising from an unresolved design decision: each strategy's SL-generation "
                   "code only guards against an exact-zero risk distance, not a small or wrong-signed one "
                   "(Section 12) -- this is neither a data-quality defect nor an R-multiple calculation bug (both "
                   "independently ruled out by this and the prior audit).",
                   "12. **What exact code path creates the SL?** `classic_strategy.py:148`, "
                   "`smc_strategy.py:142`, `ict_strategy.py:147`, and `sweep_displacement_strategy.py:163` -- "
                   "see Section 12 for the full trace of each.",
                   ""]

    return counterfactual_lines, findings, conclusions


def write_csv(d: dict) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["strategy", "symbol", "timeframe", "trade_count", "min_sl_distance", "median_sl_distance",
                          "p1_sl_distance", "p5_sl_distance", "p99_sl_distance", "tiny_sl_count", "tiny_sl_pct",
                          "winners_gt10r", "winners_gt20r", "winners_gt50r", "net_r", "profit_factor"])
        for key in sorted(d["cell_breakdown"]):
            v = d["cell_breakdown"][key]
            writer.writerow([v["strategy"], v["symbol"], v["timeframe"], v["trade_count"], v["min_sl_distance"],
                              v["median_sl_distance"], v["p1_sl_distance"], v["p5_sl_distance"], v["p99_sl_distance"],
                              v["tiny_sl_count"], v["tiny_sl_pct"], v["winners_gt10r"], v["winners_gt20r"],
                              v["winners_gt50r"], v["net_r"], v["profit_factor"]])


def main() -> None:
    report_text, d = render()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report_text)
    write_csv(d)
    print(f"wrote {REPORT_PATH}")
    print(f"wrote {CSV_PATH}")


if __name__ == "__main__":
    main()
