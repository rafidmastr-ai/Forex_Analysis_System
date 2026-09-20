from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.config import Settings
from backend.dependencies import get_market_data_provider, get_settings_dep

router = APIRouter(prefix="/market-data", tags=["market-data"])


@router.get("/symbols")
def list_symbols(settings: Settings = Depends(get_settings_dep)):
    return {"symbols": [s["name"] for s in settings.symbols]}


@router.get("/{symbol}/snapshot")
def get_snapshot(symbol: str, provider=Depends(get_market_data_provider)):
    try:
        symbol_info = provider.get_symbol_info(symbol)
        tick = provider.get_latest_tick(symbol_info)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"symbol": symbol, "bid": tick.bid, "ask": tick.ask, "spread": tick.spread,
            "timestamp": tick.timestamp.isoformat()}
