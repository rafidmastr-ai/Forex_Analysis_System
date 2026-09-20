from datetime import datetime, timedelta, timezone

from core.market_data.models import Symbol, Timeframe
from core.results.analysis_result import AnalysisResult, AnalysisStatus
from core.risk.risk_manager import RiskManager
from core.risk.trade_plan import LotSource
from core.signals.enums import ConfidenceLabel, Direction, StrategyCategory
from core.signals.selected_setup import SelectedSetup
from core.signals.strategy_signal import PriceZone, StrategySignal

SYMBOL = Symbol(name="EURUSD", pip_size=0.0001, digits=5, contract_size=100000)


def _setup(entry, sl, tp1, tp2) -> SelectedSetup:
    signal = StrategySignal(
        strategy_id="dummy", category=StrategyCategory.CLASSIC, direction=Direction.BUY,
        suggested_entry_zone=PriceZone(entry, entry), suggested_stop_loss=sl,
        suggested_take_profit_1=tp1, suggested_take_profit_2=tp2, rationale=["test"],
    )
    return SelectedSetup(
        winning_signal=signal, agreeing_signals=[], conflicting_signals=[], direction=Direction.BUY,
        entry=entry, stop_loss=sl, take_profit_1=tp1, take_profit_2=tp2,
        confidence_score=80, confidence_label=ConfidenceLabel.STRONG,
    )


def test_risk_reward_is_dynamic_not_fixed():
    setup_a = _setup(entry=1.1000, sl=1.0950, tp1=1.1075, tp2=1.1150)  # 1:1.5 and 1:3
    setup_b = _setup(entry=1.1000, sl=1.0950, tp1=1.1060, tp2=1.1100)  # 1:1.2 and 1:2

    assert round(setup_a.risk_reward_tp1, 2) == 1.5
    assert setup_a.meets_min_risk_reward(1.5) is True
    assert round(setup_b.risk_reward_tp1, 2) == 1.2
    assert setup_b.meets_min_risk_reward(1.5) is False


def test_analysis_result_status_reflects_validity_window():
    now = datetime.now(timezone.utc)
    plan = RiskManager().build_trade_plan(
        _setup(1.1000, 1.0950, 1.1075, 1.1150), SYMBOL, lot_mode=LotSource.MANUAL, manual_lot=0.1
    )

    fresh = AnalysisResult.from_trade_plan(
        symbol="EURUSD", trade_plan=plan, current_bid=1.1000, current_ask=1.1001,
        analysis_timestamp=now, valid_until=now + timedelta(minutes=15),
    )
    expired = AnalysisResult.from_trade_plan(
        symbol="EURUSD", trade_plan=plan, current_bid=1.1000, current_ask=1.1001,
        analysis_timestamp=now, valid_until=now - timedelta(minutes=1),
    )

    assert fresh.status == AnalysisStatus.ACTIVE
    assert expired.status == AnalysisStatus.EXPIRED


def test_compute_valid_until_uses_entry_timeframe_when_no_fixed_minutes():
    created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    valid_until = AnalysisResult.compute_valid_until(
        created_at, entry_timeframe_minutes=Timeframe.M15.minutes, bars_multiplier=2, fixed_minutes=None
    )
    assert valid_until == created_at + timedelta(minutes=30)
