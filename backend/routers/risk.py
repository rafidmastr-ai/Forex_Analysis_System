from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.config import Settings
from backend.dependencies import get_settings_dep

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/risk")
def get_risk_config(settings: Settings = Depends(get_settings_dep)):
    return settings.risk


@router.get("/lots")
def get_lot_config(settings: Settings = Depends(get_settings_dep)):
    return settings.lots
