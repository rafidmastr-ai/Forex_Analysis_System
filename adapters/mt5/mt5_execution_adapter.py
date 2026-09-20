"""MT5ExecutionAdapter — interface for future order execution.

v1 does NOT place any real trade. Every method raises NotImplementedError
by design so no code path can accidentally send a live order. This class
exists only so the rest of the architecture (Backend API routes, TradePlan
consumers) can be wired against a stable shape ahead of time.
"""
from __future__ import annotations

from core.risk.trade_plan import TradePlan

_NOT_ENABLED = "Trade execution is not enabled in v1. This is an interface placeholder only."


class MT5ExecutionAdapter:
    def place_order(self, trade_plan: TradePlan):
        raise NotImplementedError(_NOT_ENABLED)

    def close_position(self, position_id: int):
        raise NotImplementedError(_NOT_ENABLED)

    def modify_position(self, position_id: int, stop_loss: float, take_profit: float):
        raise NotImplementedError(_NOT_ENABLED)
