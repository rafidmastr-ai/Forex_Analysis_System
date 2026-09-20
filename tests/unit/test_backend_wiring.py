"""Regression guard: importing the backend must populate the strategy
registry with Classic/SMC/ICT. A strategy package is inert until imported
(see core/strategies/bootstrap.py) — this test exists because that wiring
was silently missing until Phase 11 and /analyze would have always
returned NO_SETUP_FOUND in the real running app despite passing unit tests
that import the strategy packages directly.
"""
from __future__ import annotations


def test_importing_backend_dependencies_registers_all_three_strategies():
    import backend.dependencies as deps

    registry = deps.get_strategy_registry()
    ids = {m.strategy_id for m in registry.all()}

    assert ids == {"classic_sr_trend_fib", "smc_structure_ob_fvg", "ict_ote_killzone"}


def test_strategies_endpoint_lists_all_three(monkeypatch):
    monkeypatch.setenv("APP_ENV", "dev")
    from fastapi.testclient import TestClient

    from backend.main import app

    client = TestClient(app)
    response = client.get("/strategies")

    assert response.status_code == 200
    ids = {row["strategy_id"] for row in response.json()}
    assert ids == {"classic_sr_trend_fib", "smc_structure_ob_fvg", "ict_ote_killzone"}
