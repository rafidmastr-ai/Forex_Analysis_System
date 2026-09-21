"""Diagnostic-only trade-level analysis of the current-version evaluation
(scripts/final_evaluation.py). NOT an optimization step: this script never
touches BacktestEngine, any strategy, any filter, or any threshold, and
its output is never fed back into a decision. It exists purely to explain
WHY the current-version evaluation's numbers came out the way they did,
at the level of individual trades rather than aggregates.

Re-runs the exact "All" configuration (all 4 adopted strategies together,
both adopted filters, min_confidence=None) per symbol -- byte-for-byte the
same construction as scripts/final_evaluation.py (imported from it, not
duplicated), over the same full historical window -- so every trade here
is one of the trades already counted in final_evaluation_summary.json.
Sanity-checked against that file's own "All" aggregate counts before any
further analysis is trusted (see main()).

For each trade this adds (all computed AFTER the trade's own outcome is
already fixed by the engine -- descriptive analysis of what already
happened, never a decision input):
  - SL distance in price units and in ATR units (ATR computed the same
    causal way core.algorithms.indicators.atr.atr() always has, indexed at
    the entry candle -- no look-ahead).
  - MAE/MFE in R, walking the real candles from just after entry to the
    trade's own closed_at (or to the window end for a "NONE" trade that
    never resolved) -- the same future-candles-only window the engine
    itself used to decide the outcome, just also recording the path.
  - First-move classification (does price move >=0.25R favorably or
    adversely first, in the first candles after entry).
  - For SL losses only: whether price returned to entry (or beyond, in the
    original direction) within 20 candles AFTER the stop was hit -- a
    "would this direction have worked with different entry timing" check
    that only uses data AFTER the trade already closed, never used to
    reopen or alter the trade.
  - Session, ATR-percentile volatility regime, confidence score, and which
    other strategies agreed/conflicted -- computed the same way
    scripts/final_evaluation.py already did for its own breakdowns.

Loss-cause classification (documented, transparent thresholds, computed
from this run's own data distribution -- never an arbitrary absolute
number invented ahead of time) assigns each SL-hit trade one PRIMARY
mechanism tag from the user's numbered list, plus independent cross-
cutting flags (late-entry-chase, disproportionate-to-volatility, and
whether the trade sits in a statistically worse session/regime/strategy
bucket) that can coexist with any primary tag. See `classify_loss()`.
"""
from __future__ import annotations

import bisect
import csv
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.algorithms.indicators.atr import atr  # noqa: E402
from core.algorithms.volatility.volatility import classify_volatility  # noqa: E402
from core.market_data.models import Timeframe  # noqa: E402
from core.signals.enums import Direction  # noqa: E402
from optimization.extended_metrics import compute_extended_metrics  # noqa: E402
from optimization.runner import run_backtest  # noqa: E402
from scripts.final_evaluation import (  # noqa: E402
    ALL_NAMES,
    FULL_WINDOW,
    LOOKBACK_BARS,
    TIMEFRAMES_CONFIG,
    _build_strategies,
    _load_session_defs,
    _production_selection_engine,
    _provider,
    _session_for,
)

FIRST_MOVE_THRESHOLD_R = 0.25
POST_SL_LOOKAHEAD_CANDLES = 20  # 5 hours of M15 -- a bounded, documented window, not "forever"
LATE_ENTRY_LOOKBACK_CANDLES = 4  # 1 hour of M15 immediately before entry
LATE_ENTRY_IMPULSE_THRESHOLD_R = 1.0


@dataclass
class TradeRecord:
    symbol: str
    strategy: str  # selected_strategy_display: Classic/SMC/ICT/Liquidity/Combination
    direction: str
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    planned_rr1: float
    planned_rr2: float
    opened_at: str
    closed_at: str | None
    duration_minutes: float | None
    outcome: str  # TP1/TP2/SL/NONE
    r_multiple: float
    confidence_score: int
    agreeing_categories: list[str]
    conflicting_categories: list[str]
    regime: str
    session: str
    sl_distance_price: float
    sl_distance_atr: float | None
    spread_at_entry_price: float | None
    spread_at_entry_r: float | None
    mae_r: float | None
    mfe_r: float | None
    first_move: str | None  # "favorable" | "adverse" | "both_within_same_candle" | "sideways_or_unresolved" | None (no data)
    late_entry_chase: bool | None
    post_sl_continuation: str | None  # only set for SL trades
    sl_on_correct_side: bool  # False = stop_loss sits on the WRONG side of entry (>=entry for BUY, <=entry for SELL) -- see main()'s summary for prevalence; a diagnostic flag only, no strategy code touched


def _index_of(timestamps: list[datetime], ts: datetime) -> int | None:
    i = bisect.bisect_left(timestamps, ts)
    if i < len(timestamps) and timestamps[i] == ts:
        return i
    return None


def _excursions_at(candle, entry: float, direction: Direction, risk_distance: float) -> tuple[float, float]:
    """Returns (adverse_r, favorable_r) for one candle."""
    if direction == Direction.BUY:
        adverse = (entry - candle.low) / risk_distance
        favorable = (candle.high - entry) / risk_distance
    else:
        adverse = (candle.high - entry) / risk_distance
        favorable = (entry - candle.low) / risk_distance
    return adverse, favorable


def _walk_mae_mfe(candles, entry_idx: int, exit_idx: int | None, entry: float, direction: Direction, risk_distance: float) -> tuple[float, float]:
    end = exit_idx if exit_idx is not None else len(candles) - 1
    mae = mfe = 0.0
    for i in range(entry_idx + 1, end + 1):
        adverse, favorable = _excursions_at(candles[i], entry, direction, risk_distance)
        mae = max(mae, adverse)
        mfe = max(mfe, favorable)
    return mae, mfe


def _first_move(candles, entry_idx: int, exit_idx: int | None, entry: float, direction: Direction, risk_distance: float) -> str:
    end = exit_idx if exit_idx is not None else len(candles) - 1
    for i in range(entry_idx + 1, end + 1):
        adverse, favorable = _excursions_at(candles[i], entry, direction, risk_distance)
        favorable_hit = favorable >= FIRST_MOVE_THRESHOLD_R
        adverse_hit = adverse >= FIRST_MOVE_THRESHOLD_R
        if favorable_hit and adverse_hit:
            return "both_within_same_candle"
        if favorable_hit:
            return "favorable"
        if adverse_hit:
            return "adverse"
    return "sideways_or_unresolved"


def _post_sl_continuation(candles, exit_idx: int, entry: float, direction: Direction) -> str:
    if exit_idx >= len(candles) - 1:
        return "no_data_after_window_end"
    end = min(exit_idx + POST_SL_LOOKAHEAD_CANDLES, len(candles) - 1)
    for i in range(exit_idx + 1, end + 1):
        c = candles[i]
        if direction == Direction.BUY and c.high >= entry:
            return "returned_to_entry_or_beyond"
        if direction == Direction.SELL and c.low <= entry:
            return "returned_to_entry_or_beyond"
    return "did_not_return"


def _late_entry_chase(candles, entry_idx: int, direction: Direction, risk_distance: float) -> bool | None:
    start = max(0, entry_idx - LATE_ENTRY_LOOKBACK_CANDLES)
    if start == entry_idx:
        return None
    pre_candles = candles[start:entry_idx]
    pre_move = pre_candles[-1].close - pre_candles[0].open
    pre_move_r = (pre_move if direction == Direction.BUY else -pre_move) / risk_distance
    return pre_move_r >= LATE_ENTRY_IMPULSE_THRESHOLD_R


def build_trade_records(symbol_name: str) -> tuple[list[TradeRecord], dict]:
    provider = _provider()
    symbol = provider.get_symbol_info(symbol_name)
    entry_series = provider.get_ohlcv(symbol, Timeframe.M15, count=100000)
    candles = entry_series.candles
    timestamps = [c.timestamp for c in candles]
    atr_values = atr(candles, period=14)
    session_defs = _load_session_defs()

    strategies = _build_strategies(ALL_NAMES)
    selection_engine = _production_selection_engine()
    report = run_backtest(
        strategies=strategies, provider=provider, selection_engine=selection_engine,
        symbol_name=symbol_name, timeframe=Timeframe.M15, start=FULL_WINDOW[0], end=FULL_WINDOW[1],
        timeframes_config=TIMEFRAMES_CONFIG, lookback_bars=LOOKBACK_BARS, min_confidence=None,
    )
    sanity = asdict(compute_extended_metrics(report.outcomes))

    records: list[TradeRecord] = []
    for outcome in report.outcomes:
        setup = outcome.setup
        entry_idx = _index_of(timestamps, outcome.opened_at)
        risk_distance = abs(setup.entry - setup.stop_loss)
        atr_at_entry = atr_values[entry_idx] if entry_idx is not None else None

        regime = "unavailable"
        session = "unavailable"
        mae = mfe = None
        first_move = None
        continuation = None
        chase = None
        if entry_idx is not None:
            regime = classify_volatility(atr_values[: entry_idx + 1])
            session = _session_for(outcome.opened_at, session_defs)
            exit_idx = _index_of(timestamps, outcome.closed_at) if outcome.closed_at is not None else None
            if risk_distance > 0:
                mae, mfe = _walk_mae_mfe(candles, entry_idx, exit_idx, setup.entry, setup.direction, risk_distance)
                first_move = _first_move(candles, entry_idx, exit_idx, setup.entry, setup.direction, risk_distance)
                chase = _late_entry_chase(candles, entry_idx, setup.direction, risk_distance)
                if outcome.hit == "SL" and exit_idx is not None:
                    continuation = _post_sl_continuation(candles, exit_idx, setup.entry, setup.direction)

        entry_candle = candles[entry_idx] if entry_idx is not None else None
        spread_price = entry_candle.spread if (entry_candle is not None and entry_candle.spread) else None

        records.append(TradeRecord(
            symbol=symbol_name, strategy=setup.selected_strategy_display, direction=setup.direction.value,
            entry=setup.entry, stop_loss=setup.stop_loss, take_profit_1=setup.take_profit_1, take_profit_2=setup.take_profit_2,
            planned_rr1=setup.risk_reward_tp1, planned_rr2=setup.risk_reward_tp2,
            opened_at=outcome.opened_at.isoformat(), closed_at=outcome.closed_at.isoformat() if outcome.closed_at else None,
            duration_minutes=((outcome.closed_at - outcome.opened_at).total_seconds() / 60) if outcome.closed_at else None,
            outcome=outcome.hit, r_multiple=outcome.r_multiple, confidence_score=setup.confidence_score,
            agreeing_categories=[s.category.value for s in setup.agreeing_signals],
            conflicting_categories=[s.category.value for s in setup.conflicting_signals],
            regime=regime, session=session,
            sl_distance_price=risk_distance, sl_distance_atr=(risk_distance / atr_at_entry) if atr_at_entry else None,
            spread_at_entry_price=spread_price, spread_at_entry_r=(spread_price / risk_distance) if (spread_price and risk_distance > 0) else None,
            mae_r=mae, mfe_r=mfe, first_move=first_move, late_entry_chase=chase, post_sl_continuation=continuation,
            sl_on_correct_side=(setup.stop_loss < setup.entry) if setup.direction == Direction.BUY else (setup.stop_loss > setup.entry),
        ))

    return records, sanity


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    idx = min(len(s) - 1, max(0, round(p / 100 * (len(s) - 1))))
    return s[idx]


def classify_loss(trade: TradeRecord, sl_atr_p25: float, sl_atr_p75: float, worse_sessions: set[str], worse_regimes: set[str], worse_strategies: set[str]) -> dict:
    """Returns {"primary": <one of 1,3,4,5,6,7,12>, "tags": [...]}. Only
    called for outcome=="SL" trades. Thresholds (percentile cutoffs) are
    computed from THIS run's own SL-distance/ATR distribution, never an
    externally-assumed number -- see main() for how sl_atr_p25/p75 and the
    "worse_*" sets are derived."""
    if not trade.sl_on_correct_side:
        # Mechanically distinct from every other category: the "stop loss" sits on the
        # wrong side of entry, so the SL check can fire on FAVORABLE movement -- MAE/MFE-
        # based reasoning below would misclassify this as ordinary adverse price action.
        return {"primary": "0_inverted_stop_loss_setup", "tags": []}

    tags = []
    if trade.late_entry_chase:
        tags.append("2_late_entry_after_delayed_move")
    if trade.session in worse_sessions:
        tags.append("9_session_related")
    if trade.regime in worse_regimes:
        tags.append("10_regime_related")
    if trade.strategy in worse_strategies:
        tags.append("11_strategy_related")

    if trade.mae_r is None or trade.mfe_r is None:
        return {"primary": "12_cannot_determine_no_path_data", "tags": tags}

    if trade.sl_distance_atr is not None and (trade.sl_distance_atr <= sl_atr_p25 or trade.sl_distance_atr >= sl_atr_p75):
        tags.append("8_tp_sl_disproportionate_to_volatility")

    if trade.first_move == "adverse" and trade.mfe_r < FIRST_MOVE_THRESHOLD_R:
        primary = "1_moved_directly_against_entry"
    elif trade.post_sl_continuation == "returned_to_entry_or_beyond":
        primary = "5_direction_correct_entry_poor"
    elif trade.mfe_r >= 0.7 * trade.planned_rr1:
        primary = "6_approached_tp_then_reversed_to_sl"
    elif trade.mfe_r >= 0.5:
        primary = "7_tp1_reasonable_but_not_reached"
    elif trade.sl_distance_atr is not None and trade.sl_distance_atr <= sl_atr_p25:
        primary = "3_sl_too_close_to_normal_noise"
    elif trade.sl_distance_atr is not None and trade.sl_distance_atr >= sl_atr_p75 and trade.mfe_r < FIRST_MOVE_THRESHOLD_R:
        primary = "4_sl_far_but_direction_wrong"
    else:
        primary = "12_cannot_determine_from_available_data"

    return {"primary": primary, "tags": tags}


def main() -> None:
    out_dir = Path("data/optimization_results/diagnostics")
    out_dir.mkdir(parents=True, exist_ok=True)

    all_records: list[TradeRecord] = []
    sanity_report = {}
    for symbol_name in ("EURUSD", "XAUUSD"):
        print(f"=== building trade records :: {symbol_name} ===", flush=True)
        records, sanity = build_trade_records(symbol_name)
        all_records.extend(records)
        sanity_report[symbol_name] = sanity
        print(f"  {len(records)} trades, extended-metrics sanity: trade_count={sanity['trade_count']} "
              f"net_r={sanity['net_r']:.2f} win_rate={sanity['win_rate']:.3f}", flush=True)

    # Diagnostic: is stop_loss even on the correct side of entry? (False here means the
    # "stop loss" cannot function as one -- it sits between entry and the profit side, so
    # the SL check can trigger on FAVORABLE movement, not adverse movement. This is a
    # descriptive flag on already-produced setups, computed from setup.entry/stop_loss/
    # direction alone -- no strategy code is read or touched to compute it.)
    inverted_sl = [t for t in all_records if not t.sl_on_correct_side]
    inverted_sl_by_strategy = Counter(t.strategy for t in inverted_sl)
    inverted_sl_by_symbol = Counter(t.symbol for t in inverted_sl)
    inverted_sl_outcomes = Counter(t.outcome for t in inverted_sl)
    print(f"Inverted-SL trades (stop_loss on the WRONG side of entry): {len(inverted_sl)} of {len(all_records)}", flush=True)
    print(f"  by strategy: {dict(inverted_sl_by_strategy)}", flush=True)
    print(f"  by symbol: {dict(inverted_sl_by_symbol)}", flush=True)
    print(f"  by outcome: {dict(inverted_sl_outcomes)}", flush=True)

    # Per-strategy SL-distance/ATR percentiles + worse-than-average buckets, computed once from this run's own data
    sl_trades = [t for t in all_records if t.outcome == "SL" and t.sl_distance_atr is not None]
    sl_atr_values = [t.sl_distance_atr for t in sl_trades]
    p25 = _percentile(sl_atr_values, 25) or 0.0
    p75 = _percentile(sl_atr_values, 75) or 0.0

    def _sl_rate(group: list[TradeRecord]) -> float:
        resolved = [t for t in group if t.outcome != "NONE"]
        return sum(1 for t in resolved if t.outcome == "SL") / len(resolved) if resolved else 0.0

    overall_sl_rate = _sl_rate(all_records)
    by_session_groups: dict[str, list[TradeRecord]] = {}
    by_regime_groups: dict[str, list[TradeRecord]] = {}
    by_strategy_groups: dict[str, list[TradeRecord]] = {}
    for t in all_records:
        by_session_groups.setdefault(t.session, []).append(t)
        by_regime_groups.setdefault(t.regime, []).append(t)
        by_strategy_groups.setdefault(t.strategy, []).append(t)

    worse_sessions = {k for k, v in by_session_groups.items() if len(v) >= 10 and _sl_rate(v) > overall_sl_rate + 0.05}
    worse_regimes = {k for k, v in by_regime_groups.items() if len(v) >= 10 and _sl_rate(v) > overall_sl_rate + 0.05}
    worse_strategies = {k for k, v in by_strategy_groups.items() if len(v) >= 10 and _sl_rate(v) > overall_sl_rate + 0.05}

    print(f"SL-distance/ATR: p25={p25:.3f} p75={p75:.3f} (n={len(sl_atr_values)})", flush=True)
    print(f"overall SL rate={overall_sl_rate:.3f}; worse-than-average (+5pt) sessions={worse_sessions} "
          f"regimes={worse_regimes} strategies={worse_strategies}", flush=True)

    classification_counts = Counter()
    tag_counts = Counter()
    for t in sl_trades:
        result = classify_loss(t, p25, p75, worse_sessions, worse_regimes, worse_strategies)
        classification_counts[result["primary"]] += 1
        for tag in result["tags"]:
            tag_counts[tag] += 1

    print("Primary loss-cause classification counts:", dict(classification_counts), flush=True)
    print("Cross-cutting tag counts:", dict(tag_counts), flush=True)

    # Persist full per-trade data
    csv_path = out_dir / "trade_level_records.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(all_records[0]).keys()) + ["loss_primary", "loss_tags"])
        writer.writeheader()
        for t in all_records:
            row = asdict(t)
            if t.outcome == "SL" and t.sl_distance_atr is not None:
                result = classify_loss(t, p25, p75, worse_sessions, worse_regimes, worse_strategies)
                row["loss_primary"] = result["primary"]
                row["loss_tags"] = ";".join(result["tags"])
            else:
                row["loss_primary"] = ""
                row["loss_tags"] = ""
            row["agreeing_categories"] = ";".join(row["agreeing_categories"])
            row["conflicting_categories"] = ";".join(row["conflicting_categories"])
            writer.writerow(row)
    print(f"trade-level CSV written to {csv_path}", flush=True)

    summary = {
        "sanity_report": sanity_report,
        "inverted_sl": {
            "count": len(inverted_sl), "by_strategy": dict(inverted_sl_by_strategy),
            "by_symbol": dict(inverted_sl_by_symbol), "by_outcome": dict(inverted_sl_outcomes),
        },
        "sl_atr_percentiles": {"p25": p25, "p75": p75, "n": len(sl_atr_values)},
        "overall_sl_rate": overall_sl_rate,
        "worse_than_average_buckets": {
            "sessions": sorted(worse_sessions), "regimes": sorted(worse_regimes), "strategies": sorted(worse_strategies),
        },
        "loss_classification_primary_counts": dict(classification_counts),
        "loss_classification_tag_counts": dict(tag_counts),
        "total_trades": len(all_records),
        "total_sl_trades": len(sl_trades),
    }
    summary_path = out_dir / "diagnostic_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str))
    print(f"diagnostic summary written to {summary_path}", flush=True)


if __name__ == "__main__":
    main()
