from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from backend.dependencies import get_market_data_provider, get_selection_engine, get_strategy_registry
from backtesting.combinations_runner import run_all_combinations
from backtesting.engine import BacktestEngine
from backtesting.run_config import STRATEGY_COMBINATIONS, BacktestRunConfig
from core.market_data.models import Timeframe

router = APIRouter(prefix="/backtest", tags=["backtest"])


class BacktestRequest(BaseModel):
    symbol: str
    entry_timeframe: str
    strategy_set: str  # one of STRATEGY_COMBINATIONS keys, or "AllCombinations"
    start: datetime
    end: datetime


@router.get("/strategy-sets")
def list_strategy_sets():
    return list(STRATEGY_COMBINATIONS.keys())


@router.post("/run")
def run_backtest(payload: BacktestRequest, provider=Depends(get_market_data_provider),
                  registry=Depends(get_strategy_registry), selection_engine=Depends(get_selection_engine)):
    engine = BacktestEngine(provider=provider, registry=registry, selection_engine=selection_engine)

    if payload.strategy_set == "AllCombinations":
        reports = run_all_combinations(engine, payload.symbol, Timeframe(payload.entry_timeframe), payload.start, payload.end)
        return {name: _summarize(r) for name, r in reports.items()}

    config = BacktestRunConfig(
        symbol_name=payload.symbol, entry_timeframe=Timeframe(payload.entry_timeframe),
        strategy_set=payload.strategy_set, start=payload.start, end=payload.end,
    )
    report = engine.run(config)
    return _summarize(report)


def _summarize(report) -> dict:
    return jsonable_encoder({
        "strategy_set": report.run_config.strategy_set,
        "total_setups": report.total_setups,
        "win_rate_tp1_or_tp2": report.win_rate_tp1,
    })
