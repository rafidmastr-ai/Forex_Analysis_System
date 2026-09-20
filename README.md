# Forex Analysis System

A multi-strategy (Classic / SMC / ICT) forex analysis engine with a market
data layer that is fully decoupled from any single data source. The Core
Analysis Engine never imports MetaTrader5 — it consumes a `MarketDataProvider`
interface, so it runs identically whether the data comes from a mock
generator (Linux Cloud development), historical files (backtesting), or a
live MT5 terminal (Windows runtime).

This system produces a rules-based technical analysis and a signal. It does
**not** guarantee any trading outcome, and Confidence Score (0–100) is a
relative measure of rule confluence — never a probability of winning.

## Why this split exists

MetaTrader5's Python package only works on Windows with a running MT5
Terminal. Development and testing happen in a Linux cloud environment where
MT5 cannot run at all. The architecture is built so that fact never leaks
into strategy code: `adapters/mt5/` is the only place `MetaTrader5` is ever
imported (enforced by a static test — see Testing below).

## Repository layout

```
core/           Pure analysis engine — models, strategies (Classic/SMC/ICT),
                algorithms, filters, confidence scoring, selection, risk,
                results. Zero MT5 dependency, runs anywhere.
adapters/       Implementations of MarketDataProvider: mock, historical
                file, and MT5 (Windows-only). mt5_execution_adapter.py is an
                interface stub only — no real order ever gets sent in v1.
backtesting/    Point-in-Time backtesting engine (no look-ahead / data
                leakage) supporting every strategy-category combination.
backend/        FastAPI app. The only layer that decides which adapter is
                wired in, based on config/settings.<env>.yaml.
web/            Static Web Interface (plain HTML/CSS/JS, no build step).
                Consumes the Backend API only — never talks to MT5 directly.
config/         Environment-specific settings (risk presets, lot presets,
                confidence thresholds, timeframe rules, symbol specs...).
tests/unit,
tests/integration_mock   Run entirely in Linux Cloud, no MT5 required.
tests/mt5_integration    Requires a real MT5 terminal — Windows runtime only
                         (currently empty; see Limitations).
```

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements/dev.txt      # Linux Cloud / development
# or: pip install -r requirements/windows.txt   # Windows + MT5 runtime
# or: pip install -r requirements/base.txt      # production, no MT5, no dev tools
```

## Configuration

All tunable behavior lives in `config/settings.<env>.yaml` (`dev`, `windows`,
`prod` — selected by the `APP_ENV` environment variable, default `dev`).
Nothing here is hardcoded in the frontend or in strategy code:

| Section | Controls |
|---|---|
| `data_source.provider` | `mock` \| `historical_file` \| `mt5` |
| `risk.presets_percent` / `allow_custom_risk_percent` | Risk % choices offered to the user |
| `risk.min_risk_reward` / `max_risk_reward` | The R:R **floor** (currently 1.5) below which a setup is rejected — never a forced target, and `max_risk_reward: null` means no ceiling |
| `lots.presets` / `allow_custom_lot` | Lot size choices |
| `confidence.thresholds` | Weak (0–49) / Medium (50–74) / Strong (75–100) |
| `timeframes.default_mapping` / `selection_rules` | Internal Higher/Middle/Entry timeframe selection — the user never picks a timeframe |
| `tp_rules.sources` / `sl_rules.sources` | Which technical factors may drive TP/SL (S/R, liquidity, order blocks, FVG, structure, Fibonacci, ATR) |
| `symbols` | Fallback specs (pip size, contract size...) — MT5's own `symbol_info()` is used instead whenever MT5 is the active source |
| `session.definitions` | Session windows |
| `data.lookback_bars` / `max_spread` | How much history to fetch per timeframe role, and spread sanity limits enforced by the Data Validation Layer |
| `analysis.validity` | How long an `AnalysisResult` stays `ACTIVE` before it's `EXPIRED` |

Secrets (`MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`, `MT5_TERMINAL_PATH`) are
**never** in these files — see Security below.

## Local Development (Linux Cloud, no MT5)

```bash
pytest                                  # 130 tests, all run here, no MT5 needed
./scripts/run_backend_dev.sh            # APP_ENV=dev -> mock data adapter, http://0.0.0.0:8000
python3 -m http.server 8080 --directory web   # serve the Web Interface separately
```

Open `http://localhost:8080`, click the ⚙ settings icon, and point it at
`http://localhost:8000` (the default). The mock adapter generates a random
walk, so most Analyze calls will correctly return `NO_SETUP_FOUND` — that's
expected; the strategies are intentionally strict and never fabricate a
signal just to have something to show.

## Windows + MT5 Setup

1. Install the MetaTrader 5 terminal and log into a (demo or live) broker
   account through the terminal itself at least once.
2. `pip install -r requirements/windows.txt` (this is the **only**
   requirements file that includes the `MetaTrader5` package).
3. Set environment variables (do not put these in any committed file):
   ```powershell
   $env:MT5_LOGIN = "12345678"
   $env:MT5_PASSWORD = "..."
   $env:MT5_SERVER = "YourBroker-Demo"
   $env:MT5_TERMINAL_PATH = "C:\Program Files\MetaTrader 5\terminal64.exe"  # optional
   ```
4. `./scripts/run_backend_windows.ps1` (sets `APP_ENV=windows`, which selects
   `data_source.provider: mt5` in `config/settings.windows.yaml`).

`MT5ExecutionAdapter` (`adapters/mt5/mt5_execution_adapter.py`) is wired as
an interface only — every method raises `NotImplementedError`. No version of
this system places a real order.

## Testing

```bash
pytest                          # everything in tests/unit + tests/integration_mock
ruff check .                    # lint — currently zero issues
mypy core adapters backtesting backend --ignore-missing-imports   # type-check — currently zero issues
```

130 tests, all passing, all runnable on Linux Cloud:
- **Unit** (`tests/unit/`): every algorithm, every strategy's branching logic,
  the Data Validation Layer's checks (missing data, duplicate timestamps,
  invalid OHLC, ordering, UTC normalization, spread, gaps), the MT5 adapter's
  MT5→unified-model conversion (via a stub `MetaTrader5` module — never a
  real terminal), Risk Manager's Auto/Manual/no-capital paths, Kill Zone DST
  behavior, and static architecture-boundary guards (MT5 only imported from
  `adapters/mt5/`, `core/` never imports `adapters`/`backend`).
- **Integration** (`tests/integration_mock/`): the real `/analyze` HTTP
  endpoint end-to-end (real confidence engine, real selection engine, real
  risk manager) with a controllable fake market-data provider and strategy
  registry, covering BUY/SELL/NO_TRADE, R:R below/at/above the 1.5 floor,
  manual/auto lot with and without capital, agreeing/conflicting strategies,
  invalid data surfacing as HTTP 502, and the analysis validity window.
- **MT5 integration** (`tests/mt5_integration/`): reserved for tests that
  need a *real* running MT5 terminal. Empty in this version — see
  Limitations.

## Backtesting

```bash
curl -X POST http://localhost:8000/backtest/run -H "Content-Type: application/json" -d '{
  "symbol": "EURUSD", "entry_timeframe": "M15", "strategy_set": "All",
  "start": "2026-01-01T00:00:00Z", "end": "2026-02-01T00:00:00Z"
}'
# or "strategy_set": "AllCombinations" to run all 7 combinations in one call
```

`strategy_set` accepts `Classic`, `SMC`, `ICT`, `Classic+SMC`, `Classic+ICT`,
`SMC+ICT`, `All`, or `AllCombinations`. The engine is strictly Point-in-Time:
at each simulated step, only candles closed at or before that step exist for
the strategies (`CandleSeries.sliced_as_of`); future candles are used
exclusively to score what happened to a signal already generated, never to
decide whether to generate one (verified by
`tests/unit/test_backtesting_engine.py`). No performance figure is invented
— `/backtest/run` only returns numbers from an actual run over the data you
give it, and the mock adapter's random-walk data has no real-world
predictive meaning (use `historical_file` with real exported data for a
meaningful result).

## Security

- MT5 credentials and any future API keys are read from environment
  variables only (`.env`, listed in `.gitignore`; `.env.example` documents
  the names). None are stored in any file this repository tracks.
- No backend endpoint returns MT5 connection details to the frontend —
  `GET /account` returns only balance-type figures, and only when MT5 is
  the active provider.
- `backend/main.py` enables CORS (`CORS_ALLOWED_ORIGINS`, comma-separated);
  restrict this to the real frontend origin(s) in production instead of the
  dev-only `*` default.

## Deployment paths

- **Local Mode**: `run_backend_dev.sh` + serving `web/` locally — for
  development only, mock data.
- **Windows PC + MT5**: the setup above, run on a personal machine. Good for
  validating the MT5 integration and live signals before renting a VPS.
- **Windows VPS + MT5**: identical setup, run on a Windows VPS that supports
  installing the MT5 terminal. Because `MT5DataMarketDataProvider` is fully
  isolated behind `MarketDataProvider`, moving from a PC to a VPS is an
  infrastructure change only (install steps, environment variables, a
  process supervisor like NSSM/Task Scheduler, a reverse proxy for HTTPS) —
  **zero changes to Core, strategies, or the backtesting engine.**
- **Public Web**: `backend/main.py` binds to `0.0.0.0` and never assumes
  `localhost`, so it can sit behind any reverse proxy/HTTPS termination.
  The recommended topology is Backend + MT5 co-located on the same Windows
  VPS, with `web/` hosted separately (any static host/CDN) pointed at the
  VPS's public API URL via the Web Interface's own Settings panel.

The path is always `Web Browser → Frontend → Backend API → Analysis Engine
→ MT5 Adapter → MT5 Terminal` — the frontend never talks to MT5 directly.

### Future extensibility (not implemented, not precluded)

The current design does not implement authentication, multi-user support,
subscriptions, or a native mobile app — but nothing here blocks adding them:
the Backend API is a normal FastAPI app (middleware/auth dependencies can be
layered on per-route), `UserCapitalConfig` is already a per-request value
rather than global state (ready to become per-account), and the Web
Interface is a thin API client (a native app is just another client of the
same `/analyze` contract).

## Known limitations (honest, as of this version)

- **No live win-rate or performance claim exists anywhere in this system.**
  Any number `/backtest/run` returns is only ever the result of an actual
  run you triggered, over data you supplied.
- Classic's "chart pattern" confirmation is candlestick-based (engulfing,
  pin bar) — full geometric pattern recognition (head & shoulders,
  triangles, trendline breaks) is not implemented.
  Correlation analysis across symbols is not implemented (single-symbol
  analysis only).
- ICT Kill Zone windows are fixed, sensible defaults in
  `core/algorithms/session/kill_zones.py` (DST-aware via `zoneinfo`), not
  yet wired to a per-environment config override.
- Session detection (`AnalysisContext.session`) is passed through as a
  placeholder string in the live `/analyze` flow and in backtesting; it is
  not yet computed from `config.session.definitions`.
- `tests/mt5_integration/` is intentionally empty — those tests require a
  real MT5 terminal connection, which this Linux Cloud environment cannot
  provide by design; they should be written and run on the Windows runtime.
- Parameter optimization, walk-forward analysis, enforced out-of-sample
  splitting, and confidence calibration are designed for (declarative
  algorithm parameters, `train_range`/`test_range` on `BacktestRunConfig`,
  `confidence_breakdown` retained per setup) but not implemented as
  standalone tools yet.

See `docs/architecture.md` for the full design this was built against.
