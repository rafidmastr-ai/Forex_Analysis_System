from datetime import datetime, timezone

from core.confidence.confidence_engine import ConfidenceEngine
from core.context.analysis_context import AnalysisContext
from core.market_data.models import Candle, CandleSeries, Symbol, Timeframe
from core.selection.strategy_selection_engine import StrategySelectionEngine
from core.signals.enums import Direction, SetupStatus, StrategyCategory
from core.signals.strategy_signal import PriceZone, StrategySignal
from core.strategies.base import BaseStrategy

SYMBOL = Symbol(name="EURUSD", pip_size=0.0001, digits=5, contract_size=100000)


def _empty_context() -> AnalysisContext:
    now = datetime.now(timezone.utc)
    empty_series = CandleSeries(symbol=SYMBOL, timeframe=Timeframe.M15, candles=[
        Candle(timestamp=now, open=1.1, high=1.1, low=1.1, close=1.1, volume=1)
    ])
    return AnalysisContext(
        symbol=SYMBOL, current_bid=1.1000, current_ask=1.1001, session="London",
        higher_timeframe=empty_series, middle_timeframe=empty_series, entry_timeframe=empty_series, as_of=now,
    )


class _FixedStrategy(BaseStrategy):
    def __init__(self, strategy_id, category, direction, entry, sl, tp1, tp2, base_confidence=60):
        self.strategy_id = strategy_id
        self.category = category
        self._direction = direction
        self._entry, self._sl, self._tp1, self._tp2 = entry, sl, tp1, tp2
        self._base_confidence = base_confidence

    def analyze(self, context):
        return StrategySignal(
            strategy_id=self.strategy_id, category=self.category, direction=self._direction,
            suggested_entry_zone=PriceZone(self._entry, self._entry), suggested_stop_loss=self._sl,
            suggested_take_profit_1=self._tp1, suggested_take_profit_2=self._tp2, rationale=["fixture"],
            raw_score_components={"base_confidence": self._base_confidence},
        )


def _engine(min_rr=1.5) -> StrategySelectionEngine:
    confidence_engine = ConfidenceEngine(thresholds={"weak_max": 49, "medium_max": 74}, multi_strategy_agreement_bonus=10)
    return StrategySelectionEngine(confidence_engine=confidence_engine, filters=[], min_risk_reward=min_rr)


def test_agreeing_strategies_boost_confidence():
    classic = _FixedStrategy("classic_1", StrategyCategory.CLASSIC, Direction.BUY, 1.1000, 1.0950, 1.1075, 1.1150)
    smc = _FixedStrategy("smc_1", StrategyCategory.SMC, Direction.BUY, 1.1000, 1.0950, 1.1075, 1.1150)

    setup = _engine().run([classic, smc], _empty_context())

    assert setup is not None
    assert setup.status == SetupStatus.SELECTED
    assert setup.selected_strategy_display == "Combination"
    assert len(setup.agreeing_signals) == 1
    assert setup.confidence_score == 70  # 60 base + 10 agreement bonus


def test_conflicting_direction_is_reported_not_hidden():
    buy = _FixedStrategy("classic_1", StrategyCategory.CLASSIC, Direction.BUY, 1.1000, 1.0950, 1.1075, 1.1150, base_confidence=80)
    sell = _FixedStrategy("ict_1", StrategyCategory.ICT, Direction.SELL, 1.1000, 1.1050, 1.0925, 1.0850, base_confidence=40)

    setup = _engine().run([buy, sell], _empty_context())

    assert setup is not None
    assert setup.direction == Direction.BUY  # higher confidence group wins
    assert len(setup.conflicting_signals) == 1
    assert setup.conflicting_signals[0].strategy_id == "ict_1"


def test_setup_below_min_risk_reward_is_rejected():
    weak_rr = _FixedStrategy("classic_1", StrategyCategory.CLASSIC, Direction.BUY, 1.1000, 1.0950, 1.1030, 1.1050)

    setup = _engine(min_rr=1.5).run([weak_rr], _empty_context())

    assert setup is not None
    assert setup.status == SetupStatus.REJECTED_MIN_RR


def test_no_strategies_returns_no_setup():
    assert _engine().run([], _empty_context()) is None
