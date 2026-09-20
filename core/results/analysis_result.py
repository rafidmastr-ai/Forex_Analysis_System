"""AnalysisResult — the final payload shown to the user for one Analyze run.

Every result is tied to the moment it was produced and to an explicit
validity window: nothing in the UI should ever treat a stale result as a
current one. `status` is computed on read, not pushed by a background
monitor — there is no continuous trade monitoring in v1.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from core.risk.trade_plan import LotSource, TradePlan
from core.signals.enums import ConfidenceLabel, Direction


class AnalysisStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"


@dataclass
class AnalysisResult:
    symbol: str

    direction: Direction
    selected_strategy: str  # "Classic" | "SMC" | "ICT" | "Combination"
    agreeing_strategies: list[str]
    conflicting_strategies: list[str]

    confidence_score: int
    confidence_label: ConfidenceLabel
    confidence_reasons: list[str]

    timeframe_used: dict[str, str]

    entry: float
    take_profit_1: float
    take_profit_2: float
    stop_loss: float
    risk_reward_tp1: float
    risk_reward_tp2: float

    lot_size: float | None
    lot_source: LotSource
    risk_amount: float | None
    expected_profit_tp1: float | None
    expected_profit_tp2: float | None
    expected_loss: float | None
    financial_disclaimer: str | None

    # Market snapshot at the moment of analysis — freshly fetched, never cached.
    analysis_timestamp: datetime
    current_bid: float
    current_ask: float
    spread: float

    # Validity window.
    created_at: datetime
    valid_until: datetime

    @property
    def status(self) -> AnalysisStatus:
        return AnalysisStatus.ACTIVE if datetime.utcnow() <= self.valid_until.replace(tzinfo=None) else AnalysisStatus.EXPIRED

    @staticmethod
    def compute_valid_until(created_at: datetime, entry_timeframe_minutes: int, bars_multiplier: int = 1,
                             fixed_minutes: int | None = None) -> datetime:
        if fixed_minutes is not None:
            return created_at + timedelta(minutes=fixed_minutes)
        return created_at + timedelta(minutes=entry_timeframe_minutes * bars_multiplier)

    @classmethod
    def from_trade_plan(
        cls,
        symbol: str,
        trade_plan: TradePlan,
        current_bid: float,
        current_ask: float,
        analysis_timestamp: datetime,
        valid_until: datetime,
    ) -> "AnalysisResult":
        setup = trade_plan.setup_ref
        reasons = [key.replace("_", " ") for key, confirmed in setup.confidence_breakdown.items() if confirmed]
        return cls(
            symbol=symbol,
            direction=setup.direction,
            selected_strategy=setup.selected_strategy_display,
            agreeing_strategies=sorted({s.category.value for s in setup.agreeing_signals}),
            conflicting_strategies=sorted({s.category.value for s in setup.conflicting_signals}),
            confidence_score=setup.confidence_score,
            confidence_label=setup.confidence_label,
            confidence_reasons=reasons,
            timeframe_used={
                "higher": setup.timeframe_used.higher,
                "middle": setup.timeframe_used.middle,
                "entry": setup.timeframe_used.entry,
            } if setup.timeframe_used else {},
            entry=setup.entry,
            take_profit_1=setup.take_profit_1,
            take_profit_2=setup.take_profit_2,
            stop_loss=setup.stop_loss,
            risk_reward_tp1=setup.risk_reward_tp1,
            risk_reward_tp2=setup.risk_reward_tp2,
            lot_size=trade_plan.lot_size,
            lot_source=trade_plan.lot_source,
            risk_amount=trade_plan.risk_amount,
            expected_profit_tp1=trade_plan.expected_profit_tp1,
            expected_profit_tp2=trade_plan.expected_profit_tp2,
            expected_loss=trade_plan.expected_loss,
            financial_disclaimer=trade_plan.financial_disclaimer,
            analysis_timestamp=analysis_timestamp,
            current_bid=current_bid,
            current_ask=current_ask,
            spread=current_ask - current_bid,
            created_at=analysis_timestamp,
            valid_until=valid_until,
        )
