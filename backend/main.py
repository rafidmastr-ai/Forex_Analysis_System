"""FastAPI entrypoint.

Runs on any host/port (uvicorn backend.main:app --host 0.0.0.0 --port 8000)
— never hardcoded to localhost, so it can be reverse-proxied and reached
from any device once deployed on Windows/VPS. The Web Interface (web/) is
a separate static app that may be hosted on a different origin (e.g. a
CDN) than this API, so CORS is enabled; set CORS_ALLOWED_ORIGINS to a
comma-separated list of real origins in production instead of the "*"
dev default.
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import account, backtest, market_data, risk, signals, strategies

app = FastAPI(title="Forex Analysis System API")

_allowed_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _allowed_origins == "*" else [o.strip() for o in _allowed_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market_data.router)
app.include_router(strategies.router)
app.include_router(signals.router)
app.include_router(backtest.router)
app.include_router(risk.router)
app.include_router(account.router)


@app.get("/health")
def health():
    return {"status": "ok"}
