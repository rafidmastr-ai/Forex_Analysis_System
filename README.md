# Forex Analysis System

A multi-strategy (Classic / SMC / ICT) forex analysis engine with a market
data layer that is fully decoupled from any single data source. The Core
Analysis Engine never imports MetaTrader5 — it consumes a `MarketDataProvider`
interface, so it runs identically whether the data comes from a mock
generator (Linux Cloud development), historical files (backtesting), or a
live MT5 terminal (Windows runtime).

## Why this split exists

MetaTrader5's Python package only works on Windows with a running MT5
Terminal. Development and testing happen in a Linux cloud environment where
MT5 cannot run at all. The architecture is built so that fact never leaks
into strategy code: `adapters/mt5/` is the only place `MetaTrader5` is ever
imported.

## Repository layout

```
core/           Pure analysis engine — models, strategies, algorithms,
                filters, confidence scoring, selection, risk. Zero MT5
                dependency, runs anywhere.
adapters/       Implementations of MarketDataProvider: mock, historical
                file, and MT5 (Windows-only).
backtesting/    Point-in-Time backtesting engine (no look-ahead / data
                leakage) supporting every strategy-category combination.
backend/        FastAPI app. The only layer that decides which adapter is
                wired in, based on config/settings.<env>.yaml.
web/            Frontend (separate app, consumes the Backend API only —
                never talks to MT5 directly).
config/         Environment-specific settings (risk presets, lot presets,
                confidence thresholds, timeframe rules, symbol specs...).
tests/unit,
tests/integration_mock   Run entirely in Linux Cloud, no MT5 required.
tests/mt5_integration    Requires a real MT5 terminal — Windows runtime only.
```

## Running in Linux Cloud (development)

```bash
pip install -r requirements/dev.txt
pytest
./scripts/run_backend_dev.sh   # APP_ENV=dev -> mock data adapter
```

## Running on Windows with MT5

```powershell
pip install -r requirements/windows.txt
# Set MT5_LOGIN / MT5_PASSWORD / MT5_SERVER as environment variables first —
# never put them in a config file that gets committed.
./scripts/run_backend_windows.ps1
```

## Status

Phase 1 (foundation) — models, interfaces, mock adapter, validation layer,
confidence/selection/risk engines, backtesting skeleton, and the FastAPI
scaffold with the `/analyze` freshness flow are in place. Concrete
Classic/SMC/ICT strategy implementations are not yet written, so `/analyze`
currently returns `NO_SETUP_FOUND` until strategies are registered.

See `docs/architecture.md` for the full approved design.
