"""FastAPI entrypoint.

Runs on any host/port (uvicorn backend.main:app --host 0.0.0.0 --port 8000)
— never hardcoded to localhost, so it can be reverse-proxied and reached
from any device once deployed on Windows/VPS.
"""
from __future__ import annotations

from fastapi import FastAPI

from backend.routers import account, backtest, market_data, risk, signals, strategies

app = FastAPI(title="Forex Analysis System API")

app.include_router(market_data.router)
app.include_router(strategies.router)
app.include_router(signals.router)
app.include_router(backtest.router)
app.include_router(risk.router)
app.include_router(account.router)


@app.get("/health")
def health():
    return {"status": "ok"}
