"""Regression guard: importing the backend must populate the strategy
registry with Classic/SMC/ICT. A strategy package is inert until imported
(see core/strategies/bootstrap.py) — this test exists because that wiring
was silently missing until Phase 11 and /analyze would have always
returned NO_SETUP_FOUND in the real running app despite passing unit tests
that import the strategy packages directly.

Assertions check Classic/SMC/ICT are a SUBSET of what's registered, not
the exact set: `core.strategies.registry.registry` is a shared,
process-wide singleton, and research-phase strategies (sweep/displacement,
session breakout, ...) self-register via the same @register_strategy
decorator the moment ANY test module in the same pytest process imports
them — regardless of whether backend/bootstrap.py itself ever imports
them. What actually matters for production correctness (bootstrap.py
wires these three into /analyze) is that they're always present, not that
nothing else in the whole test session happens to also be registered.
"""
from __future__ import annotations

REQUIRED_STRATEGY_IDS = {"classic_sr_trend_fib", "smc_structure_ob_fvg", "ict_ote_killzone"}


def test_importing_backend_dependencies_registers_all_three_strategies():
    import backend.dependencies as deps

    registry = deps.get_strategy_registry()
    ids = {m.strategy_id for m in registry.all()}

    assert REQUIRED_STRATEGY_IDS <= ids


def test_strategies_endpoint_lists_all_three(monkeypatch):
    monkeypatch.setenv("APP_ENV", "dev")
    from fastapi.testclient import TestClient

    from backend.main import app

    client = TestClient(app)
    response = client.get("/strategies")

    assert response.status_code == 200
    ids = {row["strategy_id"] for row in response.json()}
    assert REQUIRED_STRATEGY_IDS <= ids
