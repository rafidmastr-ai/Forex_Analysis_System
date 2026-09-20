"""Account info — only meaningful when the active provider is MT5.

Never returns MT5 login/password/server; only balance-type figures. If the
active data source is not MT5, there is no account to report. This is
informational only (e.g. for the Web Interface to optionally show real MT5
balance) — it is NEVER used automatically as the capital basis for sizing;
that stays governed by UserCapitalConfig (see core/risk/risk_manager.py).
"""
from __future__ import annotations

import dataclasses

from fastapi import APIRouter, Depends, HTTPException

from backend.config import get_settings
from backend.dependencies import get_market_data_provider

router = APIRouter(prefix="/account", tags=["account"])


@router.get("")
def get_account(provider=Depends(get_market_data_provider)):
    settings = get_settings()
    if settings.data_source_provider != "mt5":
        raise HTTPException(status_code=404, detail="No broker account connected in this environment.")
    try:
        state = provider.get_account_state()
    except AttributeError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    return dataclasses.asdict(state)
