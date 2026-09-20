"""/analyze — the Analyze button's endpoint.

Flow enforced here (per product requirements):
  1. Fetch FRESH market data from the active provider (never a cache) —
     latest tick + HTF/MTF/LTF candles.
  2. The provider is always the ValidatingMarketDataProvider, so Data
     Validation runs before anything below sees the data.
  3. Build AnalysisContext with as_of = now.
  4. Run Strategy Selection Engine -> SelectedSetup (or None / rejected).
  5. Risk Manager sizes the trade (or explains why it can't).
  6. Assemble AnalysisResult with analysis_timestamp/current_bid/current_ask/
     spread and a created_at/valid_until validity window.
No field here ever uses "guaranteed" language — confidence_score is a
relative score, not a win probability.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from backend.config import Settings
from backend.dependencies import (
    get_market_data_provider,
    get_risk_manager,
    get_selection_engine,
    get_settings_dep,
    get_strategy_registry,
)
from core.context.analysis_context import AnalysisContext
from core.market_data.models import Timeframe
from core.market_data.validation import DataQualityError
from core.results.analysis_result import AnalysisResult
from core.risk.trade_plan import LotSource
from core.risk.user_capital import UserCapitalConfig
from core.signals.enums import SetupStatus

router = APIRouter(tags=["analyze"])


class AnalyzeRequest(BaseModel):
    symbol: str
    risk_percent: float
    capital: float | None = None
    lot_mode: str = Field(default="AUTO", pattern="^(AUTO|MANUAL)$")
    lot_size: float | None = None


def _validate_risk_and_lot(payload: AnalyzeRequest, settings: Settings) -> None:
    if payload.lot_mode == "MANUAL" and payload.lot_size is None:
        raise HTTPException(status_code=422, detail="lot_size is required when lot_mode is MANUAL")

    risk_cfg = settings.risk
    if payload.risk_percent <= 0:
        raise HTTPException(status_code=422, detail="risk_percent must be positive")
    if payload.risk_percent not in risk_cfg["presets_percent"] and not risk_cfg["allow_custom_risk_percent"]:
        raise HTTPException(
            status_code=422,
            detail=f"risk_percent must be one of {risk_cfg['presets_percent']} (custom values are disabled)",
        )

    if payload.lot_mode == "MANUAL":
        lots_cfg = settings.lots
        if payload.lot_size <= 0:
            raise HTTPException(status_code=422, detail="lot_size must be positive")
        if payload.lot_size not in lots_cfg["presets"] and not lots_cfg["allow_custom_lot"]:
            raise HTTPException(
                status_code=422,
                detail=f"lot_size must be one of {lots_cfg['presets']} (custom values are disabled)",
            )

    if payload.capital is not None and payload.capital <= 0:
        raise HTTPException(status_code=422, detail="capital must be positive when provided")


@router.post("/analyze")
def analyze(
    payload: AnalyzeRequest,
    provider=Depends(get_market_data_provider),
    registry=Depends(get_strategy_registry),
    selection_engine=Depends(get_selection_engine),
    risk_manager=Depends(get_risk_manager),
    settings: Settings = Depends(get_settings_dep),
):
    _validate_risk_and_lot(payload, settings)

    try:
        symbol = provider.get_symbol_info(payload.symbol)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    now = datetime.now(timezone.utc)
    tf_map = settings.timeframes["default_mapping"]
    lookback = settings.data["lookback_bars"]

    try:
        latest_tick = provider.get_latest_tick(symbol)
        higher = provider.get_ohlcv(symbol, Timeframe(tf_map["higher"]), lookback["higher"])
        middle = provider.get_ohlcv(symbol, Timeframe(tf_map["middle"]), lookback["middle"])
        entry = provider.get_ohlcv(symbol, Timeframe(tf_map["entry"]), lookback["entry"])
    except DataQualityError as exc:
        raise HTTPException(status_code=502, detail=f"Market data failed validation: {exc}")

    context = AnalysisContext(
        symbol=symbol,
        current_bid=latest_tick.bid,
        current_ask=latest_tick.ask,
        session="unspecified",  # session detection is a follow-up increment
        higher_timeframe=higher,
        middle_timeframe=middle,
        entry_timeframe=entry,
        as_of=now,
    )

    strategies = [strategy_cls() for strategy_cls in registry.enabled_by_category(None)]
    setup = selection_engine.run(strategies, context)

    if setup is None:
        return {"status": "NO_SETUP_FOUND", "symbol": payload.symbol, "analysis_timestamp": now.isoformat()}
    if setup.status == SetupStatus.REJECTED_MIN_RR:
        return {
            "status": "REJECTED_MIN_RISK_REWARD",
            "symbol": payload.symbol,
            "analysis_timestamp": now.isoformat(),
            "risk_reward_tp1": setup.risk_reward_tp1,
            "min_risk_reward": settings.risk["min_risk_reward"],
        }

    lot_mode = LotSource.AUTO if payload.lot_mode == "AUTO" else LotSource.MANUAL
    capital = (
        UserCapitalConfig(capital_amount=payload.capital, currency="USD", risk_percent=payload.risk_percent)
        if payload.capital is not None
        else None
    )
    trade_plan = risk_manager.build_trade_plan(
        setup, symbol, lot_mode=lot_mode, manual_lot=payload.lot_size, capital=capital
    )

    validity_cfg = settings.analysis["validity"]
    valid_until = AnalysisResult.compute_valid_until(
        created_at=now,
        entry_timeframe_minutes=Timeframe(tf_map["entry"]).minutes,
        bars_multiplier=validity_cfg["bars_multiplier"],
        fixed_minutes=validity_cfg["fixed_minutes"],
    )

    result = AnalysisResult.from_trade_plan(
        symbol=symbol.name,
        trade_plan=trade_plan,
        current_bid=latest_tick.bid,
        current_ask=latest_tick.ask,
        analysis_timestamp=now,
        valid_until=valid_until,
    )
    payload_dict = dataclasses.asdict(result)
    payload_dict["status"] = result.status.value
    return jsonable_encoder(payload_dict)
