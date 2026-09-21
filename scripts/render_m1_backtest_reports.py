"""Renders FINAL_BACKTEST_<STRATEGY>.md (one per adopted strategy) and
FINAL_BACKTEST_INDEX.md from data/optimization_results/m1_full_backtest.json
-- purely a report-formatting step over already-computed, already-saved
results. Writes no new backtest, changes no Strategy/Weight/Filter/
Threshold, and contains no ranking or "best" selection anywhere.
"""
from __future__ import annotations

import json
from pathlib import Path

RESULTS_PATH = Path("data/optimization_results/m1_full_backtest.json")
OUT_DIR = Path("data/optimization_results")

SYMBOLS = ["EURUSD", "XAUUSD"]
TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4"]
DURATION_ORDER = ["<15min", "15-30min", "30-60min", "1-2h", "2-4h", ">4h"]
REGIME_ORDER = ["low", "medium", "high"]
SESSION_ORDER = ["Asian", "London", "LondonNewYorkOverlap", "NewYork", "unspecified"]

STRATEGY_META = {
    "Classic": {
        "file": "FINAL_BACKTEST_CLASSIC.md",
        "title": "Classic",
        "description": (
            "Trend-following pullback entries at Support/Resistance with candlestick "
            "confirmation and optional Fibonacci confluence. Trend (EMA20/EMA50 slope + "
            "ADX) sets direction and is required (no trade without a clear trend). By "
            "default requires price near a trend-agreeing S/R level plus a candlestick "
            "reversal/continuation confirmation on the last closed candle; Fibonacci "
            "retracement of the latest swing leg is an optional confluence bonus, never "
            "a hard requirement."
        ),
        "entry": "Trend (EMA20/EMA50 + ADX) sets direction; price near a trend-agreeing Support/Resistance level; candlestick reversal/continuation confirmation on the last closed candle.",
        "sl": "Just beyond the S/R level (ATR-buffered), or an ATR-based fallback when the S/R gate is disabled and no level is nearby.",
        "tp": "Next opposing S/R levels when available, else an ATR-based projection.",
        "rr": "Never a fixed R:R multiple; derived from TP/SL structure, subject to the min_risk_reward=1.5 floor (rejection only, never a target).",
    },
    "SMC": {
        "file": "FINAL_BACKTEST_SMC.md",
        "title": "SMC (Smart Money Concepts)",
        "description": (
            "Structure break (BOS/CHoCH) sets direction and is required. The breaking "
            "candle must be a displacement candle. Entry requires retracement into the "
            "Order Block that produced the break (or a Fair Value Gap from the same "
            "impulse) -- a bare structure break is not traded. Premium/Discount filter "
            "restricts BUY to discount/equilibrium and SELL to premium/equilibrium. A "
            "liquidity sweep just before the break is an optional confluence bonus."
        ),
        "entry": "Break of Structure / Change of Character sets direction; displacement-candle confirmation; retracement into the Order Block or a same-impulse Fair Value Gap; Premium/Discount filter.",
        "sl": "Just beyond the Order Block, or an ATR fallback when that gate is disabled.",
        "tp": "Nearest opposing liquidity pools when present, else an ATR-based projection.",
        "rr": "Never a fixed R:R multiple; subject to the min_risk_reward=1.5 floor (rejection only, never a target).",
    },
    "ICT": {
        "file": "FINAL_BACKTEST_ICT.md",
        "title": "ICT",
        "description": (
            "Kill-Zone-gated (New York time, DST-aware) structure break with an Optimal "
            "Trade Entry (62%-79% retracement) or Fair Value Gap trigger. Structure break "
            "(confirmed by a displacement candle) sets direction and is required. "
            "Premium/Discount filter restricts BUY to discount/equilibrium and SELL to "
            "premium/equilibrium. Breaker Block alignment is an optional confidence bonus."
        ),
        "entry": "Active ICT Kill Zone required; structure break with displacement confirmation sets direction; price inside the OTE zone or a same-impulse Fair Value Gap; Premium/Discount filter.",
        "sl": "Beyond the impulse's origin swing point.",
        "tp": "Nearest opposing liquidity pools, else an ATR-based projection.",
        "rr": "Never a fixed R:R multiple; subject to the min_risk_reward=1.5 floor (rejection only, never a target).",
    },
    "SweepDisplacement": {
        "file": "FINAL_BACKTEST_SWEEPDISPLACEMENT.md",
        "title": "Sweep-Displacement-Retracement (Liquidity)",
        "description": (
            "A liquidity-pool sweep (equal highs/lows, wick through + close back inside) "
            "sets direction and is required -- the sweep itself is the setup, not a bonus "
            "on top of a structure break (unlike SMC). A displacement candle within a "
            "short window after the sweep confirms real momentum. Entry requires "
            "retracement into the Fair Value Gap formed by that displacement, or into the "
            "displacement candle's own body. Premium/Discount filter as in SMC/ICT."
        ),
        "entry": "Liquidity-pool sweep sets direction; displacement-candle confirmation within a short window after the sweep; retracement into the resulting Fair Value Gap or the displacement candle's body; Premium/Discount filter.",
        "sl": "Just beyond the sweep's extreme wick (ATR-buffered).",
        "tp": "Nearest opposing liquidity pools when present, else an ATR-based projection.",
        "rr": "Never a fixed R:R multiple; subject to the min_risk_reward=1.5 floor (rejection only, never a target).",
    },
}

MTF_NOTE = (
    "Higher/Middle timeframe roles (`config.timeframes.default_mapping`) are held fixed "
    "at Higher=H4, Middle=H1 -- the existing, unmodified production default -- for every "
    "entry timeframe tested below. This is the current architecture used as-is: "
    "`default_mapping` is a static config value in every existing script and in "
    "`backend/dependencies.py`, never derived from the entry timeframe by any existing "
    "code, so no new mapping scheme was invented for this test. A direct consequence, "
    "reported rather than hidden: for entry=H1 the Middle role is the SAME timeframe as "
    "entry, and for entry=H4 both Middle (H1) and Higher (H4 itself) are at or below the "
    "entry timeframe's own resolution -- there is no timeframe above H4 in the current "
    "architecture's default mapping, and none was invented for this test. "
    "`HTFTrendAlignmentFilter` and any Higher/Middle-timeframe read inside a strategy use "
    "whatever series that fixed mapping actually resolves to at each entry timeframe."
)

FILTERS_NOTE = (
    "`VolatilityRegimeFilter()` (rejects signals when the entry timeframe's own "
    "ATR-percentile regime is \"high\") and `HTFTrendAlignmentFilter()` (rejects on active "
    "conflict with a clear Higher-timeframe trend) -- the exact filter list "
    "`backend/dependencies.py` wires into production, unchanged."
)


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


def main_results_table(results: dict, strategy: str) -> str:
    lines = ["| Symbol | Timeframe | Trades | Wins | Losses | Win Rate | TP1 | TP2 | SL | Net R | PF | Expectancy | Avg R | Max DD |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            m = results[strategy][symbol][tf]["metrics"]
            lines.append(
                f"| {symbol} | {tf} | {m['trade_count']} | {m['wins']} | {m['losses']} | {pct(m['win_rate'])} | "
                f"{pct(m['tp1_rate'])} | {pct(m['tp2_rate'])} | {pct(m['sl_rate'])} | {r2(m['net_r'])} | "
                f"{r2(m['profit_factor'])} | {r2(m['expectancy'])} | {r2(m['average_r'])} | {r2(m['max_drawdown_r'])} |"
            )
    return "\n".join(lines)


def duration_section(results: dict, strategy: str) -> str:
    lines = ["| Symbol | Timeframe | Avg Duration (min) | Median Duration (min) |", "|---|---|---:|---:|"]
    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            cell = results[strategy][symbol][tf]
            m = cell["metrics"]
            avg_d = m["average_duration_minutes"]
            med_d = cell["median_duration_minutes"]
            lines.append(f"| {symbol} | {tf} | {r2(avg_d) if avg_d is not None else 'n/a'} | {r2(med_d) if med_d is not None else 'n/a'} |")

    lines.append("")
    lines.append("| Symbol | Timeframe | Bucket | Trades | Win Rate | SL Rate | TP1 Rate | Net R | Expectancy |")
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|")
    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            db = results[strategy][symbol][tf]["duration_breakdown"]
            for bucket in DURATION_ORDER:
                if bucket not in db:
                    continue
                m = db[bucket]
                lines.append(f"| {symbol} | {tf} | {bucket} | {m['resolved_count']} | {pct(m['win_rate'])} | "
                              f"{pct(m['sl_rate'])} | {pct(m['tp1_rate'])} | {r2(m['net_r'])} | {r2(m['expectancy'])} |")
    return "\n".join(lines)


def rr_distribution_section(results: dict, strategy: str) -> str:
    lines = ["| Symbol | Timeframe | RR(TP1) min | p25 | median | p75 | max | mean | RR(TP2) median | RR(TP2) mean |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            m = results[strategy][symbol][tf]["metrics"]
            rr1 = m["planned_rr_tp1"]
            rr2 = m["planned_rr_tp2"]
            if not rr1:
                lines.append(f"| {symbol} | {tf} | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |")
                continue
            lines.append(
                f"| {symbol} | {tf} | {r2(rr1['min'])} | {r2(rr1['p25'])} | {r2(rr1['median'])} | {r2(rr1['p75'])} | "
                f"{r2(rr1['max'])} | {r2(rr1['mean'])} | {r2(rr2.get('median'))} | {r2(rr2.get('mean'))} |"
            )
    return "\n".join(lines)


def direction_section(results: dict, strategy: str) -> str:
    lines = ["| Symbol | Timeframe | Direction | Trades | Win Rate | Net R | PF | Expectancy | Max DD |",
             "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            db = results[strategy][symbol][tf]["direction_breakdown"]
            for direction in ("BUY", "SELL"):
                if direction not in db:
                    continue
                m = db[direction]
                lines.append(f"| {symbol} | {tf} | {direction} | {m['resolved_count']} | {pct(m['win_rate'])} | "
                              f"{r2(m['net_r'])} | {r2(m['profit_factor'])} | {r2(m['expectancy'])} | {r2(m['max_drawdown_r'])} |")
    return "\n".join(lines)


def regime_section(results: dict, strategy: str) -> str:
    lines = ["| Symbol | Timeframe | Regime | Trades | Win Rate | Net R | PF | Expectancy |",
             "|---|---|---|---:|---:|---:|---:|---:|"]
    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            rb = results[strategy][symbol][tf]["regime_breakdown"]
            for regime in REGIME_ORDER:
                if regime not in rb:
                    continue
                m = rb[regime]
                lines.append(f"| {symbol} | {tf} | {regime} | {m['resolved_count']} | {pct(m['win_rate'])} | "
                              f"{r2(m['net_r'])} | {r2(m['profit_factor'])} | {r2(m['expectancy'])} |")
            extra = [k for k in rb if k not in REGIME_ORDER]
            for regime in extra:
                m = rb[regime]
                lines.append(f"| {symbol} | {tf} | {regime} | {m['resolved_count']} | {pct(m['win_rate'])} | "
                              f"{r2(m['net_r'])} | {r2(m['profit_factor'])} | {r2(m['expectancy'])} |")
    return "\n".join(lines)


def session_section(results: dict, strategy: str) -> str:
    lines = ["| Symbol | Timeframe | Session | Trades | Win Rate | Net R | PF | Expectancy |",
             "|---|---|---|---:|---:|---:|---:|---:|"]
    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            sb = results[strategy][symbol][tf]["session_breakdown"]
            for session in SESSION_ORDER:
                if session not in sb:
                    continue
                m = sb[session]
                lines.append(f"| {symbol} | {tf} | {session} | {m['resolved_count']} | {pct(m['win_rate'])} | "
                              f"{r2(m['net_r'])} | {r2(m['profit_factor'])} | {r2(m['expectancy'])} |")
    return "\n".join(lines)


def low_sample_warnings(results: dict, strategy: str) -> str:
    lines = []
    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            m = results[strategy][symbol][tf]["metrics"]
            if m["resolved_count"] < 20:
                lines.append(f"- {symbol} {tf}: only {m['resolved_count']} resolved trade(s) -- any rate or ratio here "
                              f"(win rate, PF, expectancy) is based on a small sample and can swing sharply on one or "
                              f"two trades.")
    if not lines:
        return "No Symbol x Timeframe cell for this strategy has fewer than 20 resolved trades."
    return "\n".join(lines)


def rr_skew_note(results: dict, strategy: str) -> str:
    flagged = []
    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            m = results[strategy][symbol][tf]["metrics"]
            rr1 = m["planned_rr_tp1"]
            if rr1 and rr1["median"] > 0 and rr1["mean"] > 3 * rr1["median"]:
                flagged.append(f"{symbol}/{tf} (planned R:R(TP1) mean={rr1['mean']:.2f} vs median={rr1['median']:.2f})")
    if not flagged:
        return "No Symbol x Timeframe cell for this strategy shows a mean-vs-median planned-R:R divergence over 3x."
    return ("The following cells show a planned R:R(TP1) mean more than 3x its own median -- a small number of trades "
            "with an unusually small risk (SL) distance relative to the target distance pull the MEAN far above the "
            "MEDIAN; the median is the representative figure for a typical trade in that cell. This pattern was "
            "already identified and quantified for the prior M15 evaluation (see "
            "CURRENT_VERSION_LOSS_DIAGNOSTIC_REPORT.md) and reappears here, more pronounced at finer entry "
            "timeframes where price movement per candle is naturally smaller: " + "; ".join(flagged) + ".")


def objective_findings(results: dict, strategy: str) -> str:
    lines = []
    for symbol in SYMBOLS:
        best_tf, best_net = None, None
        worst_tf, worst_net = None, None
        for tf in TIMEFRAMES:
            net = results[strategy][symbol][tf]["metrics"]["net_r"]
            if best_net is None or net > best_net:
                best_tf, best_net = tf, net
            if worst_net is None or net < worst_net:
                worst_tf, worst_net = tf, net
        lines.append(f"- {symbol}: Net R across the six tested entry timeframes ranged from {r2(worst_net)} "
                     f"({worst_tf}) to {r2(best_net)} ({best_tf}). This describes what the data shows for this "
                     f"strategy at each timeframe; it is not a recommendation to use any particular timeframe.")
    return "\n".join(lines)


def render_strategy(results: dict, strategy: str, window: list[str]) -> str:
    meta = STRATEGY_META[strategy]
    return f"""# FINAL BACKTEST — {meta['title']}

## 1. Strategy Tested

{meta['description']}

## 2. Test Configuration

- **Data Source:** M1 OHLC (newly uploaded EURUSD/XAUUSD files), aggregated to M5/M15/M30/H1/H4 as needed for each entry timeframe below. No previously existing EURUSD/XAUUSD data was used.
- **Symbols:** EURUSD, XAUUSD
- **Entry Timeframes tested:** M1, M5, M15, M30, H1, H4 (each run independently)
- **Test Period:** {window[0]} to {window[1]} (full available M1 history for both symbols; identical range on both symbols)
- **Entry Logic (current, unmodified):** {meta['entry']}
- **SL Logic (current, unmodified):** {meta['sl']}
- **TP Logic (current, unmodified):** {meta['tp']}
- **R:R Logic (current, unmodified):** {meta['rr']}
- **Filters (current, unmodified):** {FILTERS_NOTE}
- **Confidence gating:** `min_confidence=None` -- confidence is never used to gate a trade in production `/analyze`; every setup that clears the min-R:R floor is taken, matching production exactly.
- **MTF Logic:** {MTF_NOTE}
- **Weights:** Each strategy's shipped `DEFAULT_WEIGHTS` (the currently adopted, unmodified weights) — no weight was changed for this test.

## 3. Data Quality

See `M1_DATA_QUALITY_REPORT.md` for the full data quality and multi-timeframe build validation (shared across all four strategy files, since it describes the source data, not strategy-specific behavior). Summary: 0 NaN, 0 invalid OHLC, 0 duplicate timestamps, 0 out-of-order rows in either source file; all gaps identified and explained (weekly market close + a handful of holiday closures); volume absent in source (written as 0.0, consumed by no tested strategy).

## 4. M1 → Higher Timeframe Validation

M5/M15/M30/H1/H4 were built from the M1 source and validated candle-by-candle (100% of candles, not a sample) by two independently-coded aggregation methods, which agreed exactly on every bucket in both files (see `M1_DATA_QUALITY_REPORT.md`, §4, for the full per-timeframe bucket counts and validation results).

## 5. Main Results

{main_results_table(results, strategy)}

## 6. Duration Analysis

{duration_section(results, strategy)}

## 7. R:R Distribution

Percentiles of `SelectedSetup.risk_reward_tp1` / `risk_reward_tp2` at signal time (every trade, resolved or not), per Symbol x Timeframe.

{rr_distribution_section(results, strategy)}

**Mean-vs-median caveat:** {rr_skew_note(results, strategy)}

## 8. BUY / SELL Analysis

{direction_section(results, strategy)}

## 9. Market Regime Analysis

Regime (low/medium/high) computed from ATR(14)-percentile classification on the run's own entry-timeframe candles, point-in-time (only candles up to and including each signal's own bar) -- the same computation `VolatilityRegimeFilter` itself uses in production. No "high" bucket appears because `VolatilityRegimeFilter` already rejects "high"-regime signals before they reach the backtest's trade list.

{regime_section(results, strategy)}

## 10. Session Analysis

Session windows: Asian 00:00-07:00 UTC, London 07:00-12:00 UTC, NewYork 12:00-17:00 UTC, LondonNewYorkOverlap 12:00-16:00 UTC (current `config/settings.backtest.yaml` definitions, unchanged). **"unspecified" is not a real trading session** -- it is every trade whose entry falls outside all four defined windows (17:00-23:59 UTC), shown here only as an unclassified/out-of-window bucket, not as an independently-preferred session.

{session_section(results, strategy)}

## 11. Sample Size

{low_sample_warnings(results, strategy)}

## 12. M1 OHLC Limitations

This backtest uses M1 OHLC, not tick data. Within any single M1 candle, if price would have touched both TP and SL, the existing, unmodified conservative rule in `backtesting/engine.py` is applied (SL is checked before TP on that candle) -- no tick-level path was fabricated or interpolated to resolve same-candle ambiguity. This bound is coarser at H1/H4 (a single candle spans 60-240 minutes of real price action) than at M1 itself, where the same-candle ambiguity window is only one minute wide. Volume is not present in the source data and is written as 0.0 throughout; no tested strategy consumes it (see `M1_DATA_QUALITY_REPORT.md`, §5). No Tick Data exists for this dataset in this environment; none was fabricated.

## 13. Objective Findings

{objective_findings(results, strategy)}

This section states only what the data shows for **{meta['title']}**. It does not select a best timeframe, a best symbol, or a recommended configuration -- see the repository-wide note in `FINAL_BACKTEST_INDEX.md`.
"""


def render_index(results: dict, window: list[str]) -> str:
    lines = [
        "# FINAL BACKTEST — Index",
        "",
        "Full current-version backtest of every adopted strategy, independently, on both symbols, across all six "
        "requested entry timeframes, using ONLY the newly-uploaded M1 OHLC data (EURUSD/XAUUSD) and the M5/M15/M30/"
        "H1/H4 timeframes built from it. No Strategy, Weight, Threshold, Entry, TP, SL, or Filter logic was changed "
        "to produce these results; no Optimization, Tuning, or new Filter was performed in this phase.",
        "",
        f"**Test period (both symbols):** {window[0]} to {window[1]}",
        "",
        "## Strategy Files",
        "",
    ]
    for strategy, meta in STRATEGY_META.items():
        lines.append(f"- [{meta['title']}]({meta['file']})")
    lines += [
        "",
        "## Compact Summary Table",
        "",
        "This table is provided for at-a-glance reference only. **It is not a ranking and does not identify a "
        "\"best\" strategy, timeframe, symbol, or combination** -- see each strategy's own file (§13, Objective "
        "Findings) for what the data shows about that strategy specifically.",
        "",
        "| Strategy | Symbol | Timeframe | Trades | Win Rate | Net R | PF | Expectancy | Max DD |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for strategy in STRATEGY_META:
        for symbol in SYMBOLS:
            for tf in TIMEFRAMES:
                m = results[strategy][symbol][tf]["metrics"]
                lines.append(f"| {strategy} | {symbol} | {tf} | {m['trade_count']} | {pct(m['win_rate'])} | "
                              f"{r2(m['net_r'])} | {r2(m['profit_factor'])} | {r2(m['expectancy'])} | {r2(m['max_drawdown_r'])} |")
    lines += [
        "",
        "## Data Sources",
        "",
        "- `M1_DATA_QUALITY_REPORT.md` -- source file inspection, row-level validity, gaps, and the M1→HTF build validation.",
        "- `data/optimization_results/m1_full_backtest.json` -- the complete machine-readable results this index and every strategy file are generated from.",
    ]
    return "\n".join(lines)


def main() -> None:
    data = json.loads(RESULTS_PATH.read_text())
    results = data["results"]
    window = data["window"]

    for strategy, meta in STRATEGY_META.items():
        content = render_strategy(results, strategy, window)
        out_path = OUT_DIR / meta["file"]
        out_path.write_text(content)
        print(f"wrote {out_path}")

    index_content = render_index(results, window)
    index_path = OUT_DIR / "FINAL_BACKTEST_INDEX.md"
    index_path.write_text(index_content)
    print(f"wrote {index_path}")


if __name__ == "__main__":
    main()
