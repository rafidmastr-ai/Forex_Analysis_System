from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.dependencies import get_strategy_registry
from core.strategies.registry import StrategyRegistry

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("")
def list_strategies(registry: StrategyRegistry = Depends(get_strategy_registry)):
    return [
        {"strategy_id": m.strategy_id, "category": m.category.value, "enabled": m.enabled}
        for m in registry.all()
    ]


@router.post("/{strategy_id}/enabled")
def set_enabled(strategy_id: str, enabled: bool, registry: StrategyRegistry = Depends(get_strategy_registry)):
    registry.set_enabled(strategy_id, enabled)
    return {"strategy_id": strategy_id, "enabled": enabled}
