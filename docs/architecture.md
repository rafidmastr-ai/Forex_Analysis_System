# Architecture

This document consolidates the approved design and reflects the system's
final built state (Phases 1–14). It is both descriptive (what exists) and
prescriptive (what any future change must preserve).

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
(structure, liquidity, order blocks, FVG, S/R, Fibonacci, ATR — see
Strategies below). `config.risk.min_risk_reward` (1.5) is a rejection floor
applied in `StrategySelectionEngine`, never a forced target — the resulting
R:R can be 1.5, 1.7, 2, 2.5, 3... depending on where the real levels are. A
setup below the floor is marked `SetupStatus.REJECTED_MIN_RR`, and the
`StrategySelectionEngine` never adjusts TP to manufacture a ratio.

## Strategies

Each strategy composes the shared algorithms in `core/algorithms/` — none
reimplements swing detection, structure breaks, ATR, etc. All three produce
`StrategySignal` (never `None` unless every gate is satisfied) with an
explainable `rationale` list and `raw_score_components` the Confidence
Engine reads.

- **Classic** (`core/strategies/classic/classic_strategy.py`): EMA20/EMA50
  slope + ADX trend filter, clustered swing-point Support/Resistance,
  candlestick confirmation (engulfing/pin bar) at the level, optional
  Fibonacci 38.2–61.8% confluence. SL beyond the S/R level (ATR-buffered);
  TP1/TP2 from the next opposing S/R levels or an ATR projection.
- **SMC** (`core/strategies/smc/smc_strategy.py`): BOS/CHoCH confirmed by a
  displacement candle, the Order Block that produced it, entry only on a
  retracement into that block or a matching Fair Value Gap, a
  premium/discount filter (no buying from premium, no selling from
  discount), an optional liquidity-sweep confidence bonus.
- **ICT** (`core/strategies/ict/ict_strategy.py`): gated by an active Kill
  Zone (`core/algorithms/session/kill_zones.py`, New York time via
  `zoneinfo` — DST-correct, never the user's own timezone), the same
  displacement-confirmed structure break, entry inside the OTE (62–79%)
  zone or a matching FVG, the same premium/discount filter, an optional
  Breaker Block (`core/algorithms/structure/breaker_blocks.py`) confidence
  bonus.

Strategies self-register via `@register_strategy` on import; nothing runs
until something imports the module. `core/strategies/bootstrap.py` is the
one place that imports all three, and `backend/dependencies.py` imports
`bootstrap` — this was a real Phase-1-through-10 gap (strategies existed
and passed their own tests, but the running backend never actually loaded
them) fixed in Phase 11 and guarded by
`tests/unit/test_backend_wiring.py`.

## Internal Timeframe Selection

`core/context/timeframe_selector.py`'s `TimeframeSelector` resolves
Higher/Middle/Entry from `config.timeframes` (a default mapping plus
volatility-driven override rules) — the user never supplies a timeframe.
Both the live `/analyze` flow and the Backtesting Engine classify current
volatility from ATR (`classify_volatility_from_candles`) the same way
before resolving final timeframes, so they pick timeframes identically.

## Confidence Score, reasons, and no double counting

`confidence_score` is 0–100: a relative measure of rule confluence
(strategy agreement, filter strength), **not a probability of winning**. No
UI or API text describes a signal as "guaranteed." `ConfidenceEngine`
(`core/confidence/confidence_engine.py`) also returns:
- `confidence_breakdown`: booleans per category/confirmation (OR'd across
  contributing signals, never summed — a fact confirmed by two agreeing
  strategies is one `true`, not two).
- `confidence_reasons`: the deduplicated rationale lines from every
  contributing signal (winning + agreeing) — the human-readable evidence
  behind the score, with a rationale line stated identically by two
  strategies counted once.

`SelectedSetup.contributing_signals` exposes winning+agreeing explicitly
(excluding conflicting signals). Strategy selection has no fixed priority
order — the primary signal in a direction group is whichever has the
highest `base_confidence`, not whichever category "usually wins."

## Data Validation Layer

`core/market_data/validation.py` wraps any `MarketDataProvider` and checks:
missing data, duplicate timestamps, invalid OHLC, ordering, timezone
(UTC only), spread sanity, and gaps. Critical failures raise
`DataQualityError` before Core ever sees the data — regardless of which
adapter produced it.

## Backtesting — Point-in-Time

`backtesting/clock.py` provides `get_data_as_of`, the single mechanism for
slicing a `CandleSeries` at a simulated "now" (`CandleSeries.sliced_as_of`).
The engine (`backtesting/engine.py`) builds each step's `AnalysisContext`
from data sliced at that candle's close only; future candles are used
exclusively to score the outcome of an already-opened setup, never to
decide whether to open one — verified directly by
`tests/unit/test_backtesting_engine.py` (a recording strategy asserts it is
never shown a candle timestamped after the simulated "now"). When
`timeframes_config` is supplied, Higher/Middle are fetched via
`TimeframeSelector` as genuinely different series from Entry (an earlier
gap where all three roles silently reused the entry series). 
`backtesting/run_config.py` parameterizes `strategy_set` so the same engine
tests Classic, SMC, ICT, and every pairwise/triple combination without code
changes (`combinations_runner.py` runs all seven in one call).

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
connection secrets to the frontend — `GET /account` returns only
balance-type figures (`AccountState`), and only when MT5 is the active
provider.

## Web Interface

`web/` is a static, dependency-free page (`index.html`/`styles.css`/`app.js`,
no build step) that calls only the Backend API — it never imports or
contacts MT5. Its only inputs are Symbol, Risk % (from `/config/risk`
presets, with a Custom option gated by `allow_custom_risk_percent`),
optional Capital, Lot Mode (Auto/Manual) with presets from `/config/lots`,
and Analyze — no timeframe field. It renders every `AnalysisResult` field
and treats `NO_SETUP_FOUND`/`REJECTED_MIN_RISK_REWARD` as plain notices with
zero fabricated levels; a `null` financial field renders as "N/A" next to
the backend's own disclaimer text, never an invented number. Because
Frontend and Backend may be hosted on different origins in production,
`backend/main.py` enables CORS (`CORS_ALLOWED_ORIGINS`).

## Deployment path

```
Web Browser (any device) --HTTPS--> Frontend --HTTPS/API--> Backend API
    --> Analysis Engine --> MT5 Adapter --> MT5 Terminal
```

`backend/main.py` binds to `0.0.0.0`, never `localhost`, so the same code
runs unmodified on a personal Windows PC today and a Windows VPS later —
only the reverse proxy/DNS and the `.env` change. See the README's
Deployment paths section for the concrete Local/Windows-PC/Windows-VPS/
Public-Web instructions.

## Final-state summary and honest limitations

Everything above is implemented and tested (130 tests: unit + integration,
zero ruff/mypy issues). What remains open, stated plainly rather than
glossed over:

- Classic's "chart pattern" confirmation is candlestick-based, not full
  geometric pattern recognition (head & shoulders, triangles, trendline
  breaks). Correlation analysis across symbols is not implemented.
- ICT Kill Zone windows are DST-correct fixed defaults, not yet
  config-overridable per environment.
- `AnalysisContext.session` is a placeholder string, not yet computed from
  `config.session.definitions`.
- `tests/mt5_integration/` is intentionally empty — those tests require a
  real MT5 terminal, impossible in this Linux Cloud environment by design;
  they belong on the Windows runtime.
- Parameter optimization, walk-forward analysis, enforced out-of-sample
  splitting, and confidence calibration are designed for (declarative
  `parameters` dicts on algorithms/strategies, `train_range`/`test_range`
  on `BacktestRunConfig`, retained `confidence_breakdown`) but not built as
  standalone tools.
- No performance/win-rate claim is hardcoded or implied anywhere — any
  number the system reports comes from an actual `/backtest/run` you
  triggered, over data you supplied.
