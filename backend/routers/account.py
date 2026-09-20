"""Account info — only meaningful when the active provider is MT5.

Never returns MT5 login/password/server; only balance-type figures. If the
active data source is not MT5, there is no account to report.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import get_settings

router = APIRouter(prefix="/account", tags=["account"])


@router.get("")
def get_account():
    settings = get_settings()
    if settings.data_source_provider != "mt5":
        raise HTTPException(status_code=404, detail="No broker account connected in this environment.")
    raise HTTPException(status_code=501, detail="MT5 account state retrieval not implemented in v1.")
