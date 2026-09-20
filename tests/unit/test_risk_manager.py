from datetime import datetime, timezone

from core.market_data.models import Symbol
from core.risk.risk_manager import RiskManager
from core.risk.trade_plan import CapitalSource, LotSource
from core.risk.user_capital import UserCapitalConfig
from core.signals.enums import ConfidenceLabel, Direction, StrategyCategory
from core.signals.selected_setup import SelectedSetup
from core.signals.strategy_signal import PriceZone, StrategySignal

SYMBOL = Symbol(name="EURUSD", pip_size=0.0001, digits=5, contract_size=100000)


def _setup(entry=1.1000, sl=1.0950, tp1=1.1075, tp2=1.1150) -> SelectedSetup:
    signal = StrategySignal(
        strategy_id="dummy", category=StrategyCategory.CLASSIC, direction=Direction.BUY,
        suggested_entry_zone=PriceZone(entry, entry), suggested_stop_loss=sl,
        suggested_take_profit_1=tp1, suggested_take_profit_2=tp2, rationale=["test"],
        generated_at=datetime.now(timezone.utc),
    )
    return SelectedSetup(
        winning_signal=signal, agreeing_signals=[], conflicting_signals=[], direction=Direction.BUY,
        entry=entry, stop_loss=sl, take_profit_1=tp1, take_profit_2=tp2,
        confidence_score=80, confidence_label=ConfidenceLabel.STRONG,
    )


def test_auto_lot_without_capital_has_no_financial_values():
    plan = RiskManager().build_trade_plan(_setup(), SYMBOL, lot_mode=LotSource.AUTO, capital=None)

    assert plan.lot_size is None
    assert plan.financial_values_available is False
    assert plan.financial_disclaimer is not None


def test_auto_lot_with_capital_computes_expected_values():
    capital = UserCapitalConfig(capital_amount=10_000, currency="USD", risk_percent=1.0)
    plan = RiskManager().build_trade_plan(_setup(), SYMBOL, lot_mode=LotSource.AUTO, capital=capital)

    assert plan.financial_values_available is True
    assert plan.risk_amount == 100.0  # 1% of 10,000
    assert plan.expected_loss == plan.risk_amount
    assert plan.lot_size is not None and plan.lot_size > 0
    assert plan.expected_profit_tp1 > 0
    assert plan.expected_profit_tp2 > plan.expected_profit_tp1  # TP2 farther than TP1


def test_manual_lot_computes_values_without_capital():
    plan = RiskManager().build_trade_plan(_setup(), SYMBOL, lot_mode=LotSource.MANUAL, manual_lot=0.10, capital=None)

    assert plan.lot_size == 0.10
    assert plan.financial_values_available is True
    assert plan.capital_basis == CapitalSource.NONE
    assert plan.risk_percent_of_capital is None
    assert plan.financial_disclaimer is not None  # explains risk % can't be computed
    assert plan.risk_amount > 0


def test_manual_lot_with_capital_also_reports_risk_percent():
    capital = UserCapitalConfig(capital_amount=10_000, currency="USD", risk_percent=1.0)
    plan = RiskManager().build_trade_plan(_setup(), SYMBOL, lot_mode=LotSource.MANUAL, manual_lot=0.10, capital=capital)

    assert plan.risk_percent_of_capital is not None
    assert plan.financial_disclaimer is None
