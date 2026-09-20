# Architecture

This document consolidates the approved design. It is descriptive of what
Phase 1 built and prescriptive for what later phases must preserve.

## Guiding principle

The Core Analysis Engine (`core/`) has zero knowledge of MetaTrader5. Every
data source implements `MarketDataProvider`; adapters are swappable without
touching strategies, algorithms, filters, confidence scoring, selection,
risk management, or backtesting.

## Layers

```
Web Interface
    -> Backend API (FastAPI)
        -> Strategy Selection Engine / Backtesting Engine / Risk Management
            -> Core Analysis Engine (strategies -> StrategySignal -> Confidence Engine -> SelectedSetup)
                -> AnalysisContext
                    -> Market Data Models + MarketDataProvider (interface)
                        -> Data Validation Layer (decorator)
                            -> Mock Adapter | Historical File Adapter | MT5 Adapter (Windows only)
```

## Key models

- **Market Data**: `Symbol`, `Timeframe`, `Candle`, `CandleSeries`, `Tick` —
  `core/market_data/models.py`. No adapter-specific fields.
- **AnalysisContext** (`core/context/analysis_context.py`): symbol, current
  bid/ask, spread, session, higher/middle/entry timeframe series, `as_of`.
  Timeframes are chosen internally (config-driven); the user never selects
  a timeframe.
- **StrategySignal** (`core/signals/strategy_signal.py`): a single
  strategy's raw, unsized opinion — direction, suggested entry zone, SL,
  TP1, TP2, rationale. Never touches capital or lot size.
- **SelectedSetup** (`core/signals/selected_setup.py`): the resolved
  outcome after comparing all strategies — winning signal, agreeing
  signals, conflicting signals, confidence score/label/breakdown, final
  entry/SL/TP1/TP2, dynamic `risk_reward_tp1`/`risk_reward_tp2`.
- **TradePlan** (`core/risk/trade_plan.py`): sizing and money layered on
  top of a `SelectedSetup` — lot size, lot source (AUTO/MANUAL), capital
  basis, risk amount, expected profit at TP1 and TP2 independently,
  expected loss. Never invents a lot size; if capital and manual lot are
  both absent, financial fields are `None` with an explicit disclaimer.
- **AnalysisResult** (`core/results/analysis_result.py`): the API-facing
  payload. Adds `analysis_timestamp`/`current_bid`/`current_ask`/`spread`
  (market snapshot at analysis time) and `created_at`/`valid_until`/
  `status` (computed, not monitored — no background job in v1).

## Confidence Score

`confidence_score` is 0–100. It is a relative measure of rule confluence
(strategy agreement, filter strength), **not a probability of winning**.
No UI or API text may describe a signal as "guaranteed."

## Risk / Reward is dynamic

TP1/TP2 come from each strategy's own technical read of the market
(structure, liquidity, order blocks, FVG, S/R, Fibonacci — implemented per
strategy in a later phase). `config.risk.min_risk_reward` (currently 1.5)
is a rejection floor applied in `StrategySelectionEngine`, never a forced
target — the resulting R:R can be 1.5, 1.7, 2, 2.5, 3... depending on where
the real levels are. A setup below the floor is marked
`SetupStatus.REJECTED_MIN_RR`.

## Data Validation Layer

`core/market_data/validation.py` wraps any `MarketDataProvider` and checks:
missing data, duplicate timestamps, invalid OHLC, ordering, timezone
(UTC only), spread sanity, and gaps. Critical failures raise
`DataQualityError` before Core ever sees the data — regardless of which
adapter produced it.

## Backtesting — Point-in-Time

`backtesting/clock.py` provides `get_data_as_of`, the single mechanism for
slicing a `CandleSeries` at a simulated "now." The engine
(`backtesting/engine.py`) builds each step's `AnalysisContext` from data
sliced at that candle's close only; future candles are used exclusively to
score the outcome of an already-opened setup, never to decide whether to
open one. `backtesting/run_config.py` parameterizes `strategy_set` so the
same engine tests Classic, SMC, ICT, and every pairwise/triple combination
without code changes (`combinations_runner.py` runs all seven in one call).

## Risk Management — capital vs. account

`UserCapitalConfig` (manual, user-entered) and `AccountState` (MT5 account,
when connected) are separate models. Sizing defaults to the manual capital
basis in v1 regardless of whether MT5 is connected for data.

- **AUTO lot + capital present** → lot computed from capital, risk %,
  entry/SL distance, symbol contract size.
- **AUTO lot + no capital** → no lot, no financial figures, explicit
  disclaimer; technical fields (direction/entry/TP1/TP2/SL/confidence/
  strategy/timeframe) are still returned.
- **MANUAL lot** → profit/loss figures always computable from the lot
  itself; risk-percent-of-capital only if capital was also entered.

## Execution — not enabled in v1

`adapters/mt5/mt5_execution_adapter.py` defines the future order-execution
interface; every method raises `NotImplementedError`. No code path can
place a real trade in this version.

## Security

MT5 credentials and any API keys are read from environment variables only
(`.env`, never committed — see `.env.example`). No endpoint returns
connection secrets to the frontend.

## Deployment path

```
Web Browser (any device) --HTTPS--> Frontend --HTTPS/API--> Backend API
    --> Analysis Engine --> MT5 Adapter --> MT5 Terminal
```

`backend/main.py` binds to `0.0.0.0`, never `localhost`, so the same code
runs unmodified on a personal Windows PC today and a Windows VPS later —
only the reverse proxy/DNS and the `.env` change.

## What Phase 1 deliberately left out

- Concrete Classic/SMC/ICT strategy implementations (`core/strategies/{classic,smc,ict}/`
  are empty packages, ready for the next phase).
- The internal Timeframe Selector that maps session/volatility to concrete
  HTF/MTF/LTF choices (currently a static default from config; see the
  `NOTE` in `backtesting/engine.py`).
- Session detection (`AnalysisContext.session` is passed through, not yet
  computed from `config.session.definitions`).
- Parameter optimization, walk-forward analysis, out-of-sample enforcement,
  and confidence calibration — the data shapes (`parameters` dicts,
  `train_range`/`test_range`, `confidence_breakdown`) already support
  adding these without breaking changes.
