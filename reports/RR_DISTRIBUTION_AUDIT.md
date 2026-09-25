# R:R DISTRIBUTION AUDIT

## 1. Executive Summary

This audit determines whether the current-version Baseline backtest's performance (`data/optimization_results/m1_full_backtest.json`) depends on a small number of trades with extremely large realized R multiples. It is purely diagnostic: no Strategy, Weight, Filter, Threshold, Entry, TP, SL, Confidence, Timeframe-mapping, Lookback, Dataset, or same-candle-policy logic was changed to produce or in response to these results, and no strategy/symbol/timeframe is ranked or recommended anywhere in this report.

- 96/96 Baseline cells executed successfully (0 failed).
- Baseline integrity check: PASSED (0 mismatches across all cells).
- 21319 total trades captured across all executed cells (4480 wins, 16838 losses, 1 unresolved).
- Global Net R = 3277.83, Profit Factor = 1.19.
- R-multiple independent validation: 4480/4480 WINNING trades independently re-derive their stored realized R exactly (0 discrepancies) -- see Section 13. Separately, 3194 of 16838 SL-hit (losing) trades have a stop-loss placed on the wrong side of entry for their own direction -- an already-documented condition, not a new R-multiple computation bug (Section 13).
- 0 resolved trades had an undefined (zero-distance) stop-loss.

## 2. Dataset and Methodology

- Dataset: identical to the Baseline -- `data/market/{SYMBOL}.csv` (raw M1 OHLC) and the `data/historical/{SYMBOL}_{TF}.csv` files generated from it by `scripts/build_m1_historical_data.py`.
- 96 configurations: 4 strategies (Classic, SMC, ICT, SweepDisplacement) x 4 symbols (EURUSD, XAUUSD, GBPUSD, NZDUSD) x 6 entry timeframes (M1, M5, M15, M30, H1, H4).
- Each cell's signals are generated EXACTLY ONCE via `scripts.robustness_backtest.run_one_signal_generation` (identical production wiring to the Baseline: same filters, `min_confidence=None`, `min_risk_reward=1.5`, timeframe mapping, lookback, dataset, same-candle policy). All analysis below is computed AFTER `BacktestEngine` has already produced each `TradeOutcome` -- no trade is re-simulated and no decision logic is exercised by this audit.
- "Signal score" (per the audit's Section 3 requirement) is captured as `confidence_score` (the only single-number score `SelectedSetup` exposes) plus the winning signal's raw `raw_score_components` dict, both stored verbatim per trade in `data/optimization_results/trade_level_audit.json` for further inspection.
- R:R bins for winning trades: 1.5-2R, 2-3R, 3-4R, 4-5R, 5-10R, 10-20R, 20-50R, 50R+, plus an explicit `below_1.5R` bucket for winners under the production minimum-R:R floor -- losses and unresolved (NONE) trades are tracked separately and never dropped from any total.

## 3. Baseline Integrity Check

Cells checked: 96/96. All cells matched data/optimization_results/m1_full_backtest.json exactly (trade count, resolved count, wins, losses, TP1, TP2, SL, win rate, net R, profit factor, expectancy).

## 4. Global R:R Distribution

R:R distribution of WINNING trades only (bins), with explicit accounting for winners below the 1.5R floor, losses, and unresolved trades in the same table.

| Bucket | Trade Count | % of Winning Trades | Total Realized R | % of Gross Winning R | Mean R | Median R |
|---|---:|---:|---:|---:|---:|---:|
| below_1.5R | 91 | 2.0% | 136.50 | 0.7% | 1.50 | 1.50 |
| 1.5-2R | 1599 | 35.7% | 2711.32 | 13.5% | 1.70 | 1.68 |
| 2-3R | 1239 | 27.7% | 2974.61 | 14.8% | 2.40 | 2.34 |
| 3-4R | 591 | 13.2% | 1971.61 | 9.8% | 3.34 | 3.27 |
| 4-5R | 280 | 6.2% | 1252.14 | 6.2% | 4.47 | 4.46 |
| 5-10R | 477 | 10.6% | 3279.13 | 16.3% | 6.87 | 6.52 |
| 10-20R | 148 | 3.3% | 1941.09 | 9.6% | 13.12 | 12.21 |
| 20-50R | 37 | 0.8% | 1056.26 | 5.3% | 28.55 | 26.55 |
| 50R+ | 18 | 0.4% | 4793.18 | 23.8% | 266.29 | 87.35 |
| losses (SL) | 16838 | -- | -16838.00 | -- | -- | -- |
| unresolved (NONE) | 1 | -- | 0.00 | -- | -- | -- |

### Global summary statistics

- Total trades: 21319 (wins: 4480, losses: 16838, unresolved: 1).
- Gross winning R: 20115.83, Gross losing R: 16838.00, Net R: 3277.83, Profit Factor: 1.19.
- Mean winning R: 4.49, Median winning R: 2.30.
- P75/P90/P95/P99 winning R: 3.54 / 6.45 / 9.73 / 22.01.
- Maximum winning R: 1894.81.

| Threshold | Trade Count | Total Realized R | % of Gross Winning R |
|---|---:|---:|---:|
| >5R | 680 | 11069.65 | 55.0% |
| >10R | 203 | 7790.53 | 38.7% |
| >20R | 55 | 5849.44 | 29.1% |
| >50R | 18 | 4793.18 | 23.8% |

## 5. Profit Concentration

How much of total gross winning R comes from the top N% of winning trades by count (sorted by realized R, descending).

| Top Fraction | N Trades | Total Realized R | % of Gross Winning R |
|---|---:|---:|---:|
| 0.1% | 4 | 3548.10 | 17.6% |
| 0.5% | 22 | 4973.04 | 24.7% |
| 1% | 45 | 5638.21 | 28.0% |
| 2% | 90 | 6458.02 | 32.1% |
| 5% | 224 | 7998.15 | 39.8% |
| 10% | 448 | 9759.38 | 48.5% |

## 6. Trim Analysis

Post-trade, analytical-only trim: removes the top N% highest-realized-R WINNING trades (by count) and recomputes summary metrics over the remaining population. This does NOT re-run the strategy and does NOT alter trade generation -- it is a pure arithmetic exclusion over already-decided trades, shown for comparison against the untrimmed Baseline figures in Section 4.

Untrimmed baseline for reference: 21319 trades, Net R = 3277.83, PF = 1.19.

| Trim | Trades Removed | Trade Count | Wins | Losses | Win Rate | Gross Win R | Gross Loss R | Net R | PF | Expectancy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.1% | 4 | 21315 | 4476 | 16838 | 21.0% | 16567.73 | 16838.00 | -270.27 | 0.98 | -0.01 |
| 0.5% | 22 | 21297 | 4458 | 16838 | 20.9% | 15142.79 | 16838.00 | -1695.21 | 0.90 | -0.08 |
| 1% | 45 | 21274 | 4435 | 16838 | 20.8% | 14477.61 | 16838.00 | -2360.39 | 0.86 | -0.11 |
| 2% | 90 | 21229 | 4390 | 16838 | 20.7% | 13657.81 | 16838.00 | -3180.19 | 0.81 | -0.15 |
| 5% | 224 | 21095 | 4256 | 16838 | 20.2% | 12117.68 | 16838.00 | -4720.32 | 0.72 | -0.22 |

## 7. Strategy-Level Distribution

| Group | Trades | Wins | Losses | Win Rate | Net R | PF | Mean Win R | Median Win R | P90 | P95 | P99 | Max Win R | Share >5R | Share >10R | Share >20R | Share >50R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Classic | 10269 | 1843 | 8425 | 17.9% | 3370.22 | 1.40 | 6.40 | 2.50 | 7.33 | 11.78 | 41.98 | 1894.81 | 68.2% | 55.2% | 47.0% | 39.4% |
| ICT | 988 | 253 | 735 | 25.6% | -179.68 | 0.76 | 2.19 | 1.89 | 3.02 | 3.25 | 4.47 | 9.92 | 4.2% | 0.0% | 0.0% | 0.0% |
| SMC | 6252 | 1619 | 4633 | 25.9% | 741.10 | 1.16 | 3.32 | 2.25 | 6.61 | 9.76 | 15.46 | 25.34 | 40.6% | 16.7% | 2.5% | 0.0% |
| SweepDisplacement | 3810 | 765 | 3045 | 20.1% | -653.82 | 0.79 | 3.13 | 2.18 | 5.29 | 7.18 | 13.08 | 87.08 | 34.0% | 16.1% | 7.4% | 6.0% |

## 8. Symbol-Level Distribution

| Group | Trades | Wins | Losses | Win Rate | Net R | PF | Mean Win R | Median Win R | P90 | P95 | P99 | Max Win R | Share >5R | Share >10R | Share >20R | Share >50R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| EURUSD | 5597 | 1047 | 4550 | 18.7% | 2337.01 | 1.51 | 6.58 | 2.27 | 6.49 | 9.28 | 30.53 | 1894.81 | 69.1% | 57.7% | 51.8% | 48.8% |
| GBPUSD | 5215 | 1142 | 4072 | 21.9% | 878.34 | 1.22 | 4.33 | 2.40 | 6.46 | 10.47 | 29.29 | 497.19 | 53.1% | 35.5% | 23.8% | 15.0% |
| NZDUSD | 5286 | 1124 | 4162 | 21.3% | -54.61 | 0.99 | 3.65 | 2.26 | 6.00 | 9.06 | 24.70 | 104.17 | 43.4% | 26.4% | 16.3% | 7.5% |
| XAUUSD | 5221 | 1167 | 4054 | 22.4% | 117.09 | 1.03 | 3.57 | 2.20 | 6.76 | 9.82 | 11.77 | 382.79 | 45.6% | 23.5% | 10.3% | 9.2% |

## 9. Timeframe-Level Distribution

| Group | Trades | Wins | Losses | Win Rate | Net R | PF | Mean Win R | Median Win R | P90 | P95 | P99 | Max Win R | Share >5R | Share >10R | Share >20R | Share >50R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| M1 | 9012 | 2056 | 6956 | 22.8% | 1935.37 | 1.28 | 4.32 | 2.37 | 6.73 | 9.43 | 20.63 | 773.32 | 54.0% | 34.4% | 24.1% | 18.5% |
| M5 | 7404 | 1416 | 5988 | 19.1% | 1621.18 | 1.27 | 5.37 | 2.31 | 6.03 | 9.18 | 26.55 | 1894.81 | 60.8% | 49.0% | 41.9% | 37.7% |
| M15 | 2542 | 573 | 1969 | 22.5% | 91.44 | 1.05 | 3.60 | 2.02 | 7.37 | 10.11 | 18.86 | 87.08 | 48.1% | 32.0% | 13.4% | 10.7% |
| M30 | 1491 | 256 | 1235 | 17.2% | -281.40 | 0.77 | 3.72 | 2.31 | 5.72 | 7.40 | 32.96 | 56.30 | 42.9% | 28.0% | 22.5% | 5.9% |
| H1 | 586 | 137 | 448 | 23.4% | 13.37 | 1.03 | 3.37 | 2.31 | 5.66 | 7.18 | 15.89 | 25.34 | 41.0% | 14.1% | 5.5% | 0.0% |
| H4 | 284 | 42 | 242 | 14.8% | -102.13 | 0.58 | 3.33 | 2.11 | 7.18 | 9.28 | 13.17 | 13.17 | 38.6% | 9.4% | 0.0% | 0.0% |

## 10. 96-Cell Results

| Group | Trades | Wins | Losses | Win Rate | Net R | PF | Mean Win R | Median Win R | P90 | P95 | P99 | Max Win R | Share >5R | Share >10R | Share >20R | Share >50R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Classic/EURUSD/H1 | 111 | 23 | 88 | 20.7% | -14.75 | 0.83 | 3.18 | 2.36 | 5.20 | 5.51 | 12.47 | 12.47 | 31.6% | 17.0% | 0.0% | 0.0% |
| Classic/EURUSD/H4 | 53 | 6 | 47 | 11.3% | -32.28 | 0.31 | 2.45 | 2.10 | 2.29 | 4.83 | 4.83 | 4.83 | 0.0% | 0.0% | 0.0% | 0.0% |
| Classic/EURUSD/M1 | 1112 | 192 | 920 | 17.3% | 913.92 | 1.99 | 9.55 | 2.71 | 8.96 | 13.12 | 71.57 | 773.32 | 79.9% | 68.2% | 61.2% | 56.9% |
| Classic/EURUSD/M15 | 242 | 45 | 197 | 18.6% | -50.05 | 0.75 | 3.27 | 2.29 | 6.41 | 7.06 | 8.57 | 8.57 | 36.0% | 0.0% | 0.0% | 0.0% |
| Classic/EURUSD/M30 | 177 | 29 | 148 | 16.4% | -44.35 | 0.70 | 3.57 | 2.63 | 4.85 | 6.96 | 18.84 | 18.84 | 31.6% | 18.2% | 0.0% | 0.0% |
| Classic/EURUSD/M5 | 939 | 152 | 787 | 16.2% | 1998.29 | 3.54 | 18.32 | 2.49 | 8.55 | 14.36 | 114.63 | 1894.81 | 89.1% | 84.1% | 81.9% | 80.0% |
| Classic/GBPUSD/H1 | 106 | 17 | 88 | 16.2% | -36.60 | 0.58 | 3.02 | 2.95 | 4.78 | 4.98 | 5.26 | 5.26 | 10.2% | 0.0% | 0.0% | 0.0% |
| Classic/GBPUSD/H4 | 54 | 9 | 45 | 16.7% | -15.53 | 0.65 | 3.27 | 3.46 | 4.06 | 7.18 | 7.18 | 7.18 | 24.4% | 0.0% | 0.0% | 0.0% |
| Classic/GBPUSD/M1 | 1111 | 227 | 884 | 20.4% | 640.82 | 1.72 | 6.72 | 2.50 | 9.99 | 16.10 | 39.02 | 497.19 | 71.7% | 60.2% | 46.2% | 32.6% |
| Classic/GBPUSD/M15 | 255 | 43 | 212 | 16.9% | 55.44 | 1.26 | 6.22 | 2.46 | 7.16 | 11.97 | 82.41 | 82.41 | 65.2% | 58.6% | 50.2% | 50.2% |
| Classic/GBPUSD/M30 | 141 | 30 | 111 | 21.3% | 54.14 | 1.49 | 5.50 | 2.64 | 6.00 | 32.96 | 48.89 | 48.89 | 61.9% | 49.6% | 49.6% | 0.0% |
| Classic/GBPUSD/M5 | 935 | 172 | 763 | 18.4% | 23.02 | 1.03 | 4.57 | 2.57 | 7.20 | 11.10 | 29.29 | 58.55 | 54.6% | 37.1% | 30.5% | 14.3% |
| Classic/NZDUSD/H1 | 74 | 18 | 56 | 24.3% | 11.68 | 1.21 | 3.76 | 2.20 | 6.27 | 9.05 | 15.89 | 15.89 | 53.5% | 23.5% | 0.0% | 0.0% |
| Classic/NZDUSD/H4 | 44 | 6 | 38 | 13.6% | -15.78 | 0.58 | 3.70 | 2.31 | 6.17 | 8.14 | 8.14 | 8.14 | 64.4% | 0.0% | 0.0% | 0.0% |
| Classic/NZDUSD/M1 | 1087 | 208 | 879 | 19.1% | 189.31 | 1.22 | 5.14 | 2.69 | 9.56 | 16.24 | 37.66 | 104.17 | 62.1% | 44.7% | 26.5% | 9.8% |
| Classic/NZDUSD/M15 | 322 | 46 | 276 | 14.3% | -93.77 | 0.66 | 3.96 | 2.35 | 5.56 | 9.95 | 33.55 | 33.55 | 46.9% | 28.0% | 18.4% | 0.0% |
| Classic/NZDUSD/M30 | 162 | 37 | 125 | 22.8% | 21.48 | 1.17 | 3.96 | 2.86 | 6.05 | 6.86 | 34.78 | 34.78 | 46.0% | 23.7% | 23.7% | 0.0% |
| Classic/NZDUSD/M5 | 922 | 148 | 774 | 16.1% | -29.89 | 0.96 | 5.03 | 2.49 | 7.73 | 11.34 | 67.65 | 79.50 | 59.9% | 42.4% | 32.5% | 19.8% |
| Classic/XAUUSD/H1 | 63 | 10 | 53 | 15.9% | -6.29 | 0.88 | 4.67 | 3.39 | 8.97 | 11.31 | 11.31 | 11.31 | 67.3% | 24.2% | 0.0% | 0.0% |
| Classic/XAUUSD/H4 | 50 | 6 | 44 | 12.0% | -22.05 | 0.50 | 3.66 | 2.18 | 4.67 | 9.28 | 9.28 | 9.28 | 42.3% | 0.0% | 0.0% | 0.0% |
| Classic/XAUUSD/M1 | 983 | 171 | 812 | 17.4% | -268.45 | 0.67 | 3.18 | 2.39 | 5.47 | 7.44 | 10.41 | 12.74 | 33.1% | 8.3% | 0.0% | 0.0% |
| Classic/XAUUSD/M15 | 284 | 56 | 228 | 19.7% | -51.65 | 0.77 | 3.15 | 2.30 | 4.79 | 6.84 | 11.67 | 18.86 | 29.0% | 17.3% | 0.0% | 0.0% |
| Classic/XAUUSD/M30 | 131 | 16 | 115 | 12.2% | -76.58 | 0.33 | 2.40 | 1.91 | 5.79 | 5.79 | 5.91 | 5.91 | 30.4% | 0.0% | 0.0% | 0.0% |
| Classic/XAUUSD/M5 | 911 | 176 | 735 | 19.3% | 220.14 | 1.30 | 5.43 | 2.50 | 5.94 | 7.50 | 11.71 | 382.79 | 61.3% | 47.6% | 40.1% | 40.1% |
| ICT/EURUSD/H1 | 4 | 1 | 3 | 25.0% | -1.48 | 0.51 | 1.52 | 1.52 | 1.52 | 1.52 | 1.52 | 1.52 | 0.0% | 0.0% | 0.0% | 0.0% |
| ICT/EURUSD/H4 | 1 | 1 | 0 | 100.0% | 4.38 | inf | 4.38 | 4.38 | 4.38 | 4.38 | 4.38 | 4.38 | 0.0% | 0.0% | 0.0% | 0.0% |
| ICT/EURUSD/M1 | 82 | 35 | 47 | 42.7% | 30.32 | 1.65 | 2.21 | 1.85 | 3.03 | 3.25 | 9.92 | 9.92 | 12.8% | 0.0% | 0.0% | 0.0% |
| ICT/EURUSD/M15 | 14 | 4 | 10 | 28.6% | -1.70 | 0.83 | 2.07 | 1.96 | 2.57 | 2.57 | 2.57 | 2.57 | 0.0% | 0.0% | 0.0% | 0.0% |
| ICT/EURUSD/M30 | 33 | 2 | 31 | 6.1% | -27.30 | 0.12 | 1.85 | 1.85 | 1.91 | 1.91 | 1.91 | 1.91 | 0.0% | 0.0% | 0.0% | 0.0% |
| ICT/EURUSD/M5 | 136 | 6 | 130 | 4.4% | -119.69 | 0.08 | 1.72 | 1.66 | 1.81 | 2.10 | 2.10 | 2.10 | 0.0% | 0.0% | 0.0% | 0.0% |
| ICT/GBPUSD/H1 | 4 | 1 | 3 | 25.0% | -1.40 | 0.53 | 1.60 | 1.60 | 1.60 | 1.60 | 1.60 | 1.60 | 0.0% | 0.0% | 0.0% | 0.0% |
| ICT/GBPUSD/H4 | 4 | 0 | 4 | 0.0% | -4.00 | 0.00 | n/a | n/a | n/a | n/a | n/a | n/a | 0.0% | 0.0% | 0.0% | 0.0% |
| ICT/GBPUSD/M1 | 96 | 31 | 65 | 32.3% | 5.97 | 1.09 | 2.29 | 1.76 | 3.12 | 4.28 | 8.06 | 8.06 | 18.7% | 0.0% | 0.0% | 0.0% |
| ICT/GBPUSD/M15 | 12 | 5 | 7 | 41.7% | 3.34 | 1.48 | 2.07 | 2.07 | 2.56 | 2.56 | 2.56 | 2.56 | 0.0% | 0.0% | 0.0% | 0.0% |
| ICT/GBPUSD/M30 | 67 | 19 | 48 | 28.4% | 7.81 | 1.16 | 2.94 | 3.00 | 3.11 | 3.12 | 3.13 | 3.13 | 0.0% | 0.0% | 0.0% | 0.0% |
| ICT/GBPUSD/M5 | 53 | 13 | 40 | 24.5% | -12.20 | 0.70 | 2.14 | 1.83 | 3.51 | 3.51 | 4.47 | 4.47 | 0.0% | 0.0% | 0.0% | 0.0% |
| ICT/NZDUSD/H1 | 5 | 1 | 4 | 20.0% | -2.47 | 0.38 | 1.53 | 1.53 | 1.53 | 1.53 | 1.53 | 1.53 | 0.0% | 0.0% | 0.0% | 0.0% |
| ICT/NZDUSD/H4 | 3 | 0 | 3 | 0.0% | -3.00 | 0.00 | n/a | n/a | n/a | n/a | n/a | n/a | 0.0% | 0.0% | 0.0% | 0.0% |
| ICT/NZDUSD/M1 | 114 | 39 | 75 | 34.2% | 11.90 | 1.16 | 2.23 | 2.06 | 2.98 | 3.18 | 3.72 | 3.72 | 0.0% | 0.0% | 0.0% | 0.0% |
| ICT/NZDUSD/M15 | 14 | 6 | 8 | 42.9% | 7.98 | 2.00 | 2.66 | 2.57 | 3.44 | 3.62 | 3.62 | 3.62 | 0.0% | 0.0% | 0.0% | 0.0% |
| ICT/NZDUSD/M30 | 51 | 3 | 48 | 5.9% | -41.84 | 0.13 | 2.05 | 2.22 | 2.44 | 2.44 | 2.44 | 2.44 | 0.0% | 0.0% | 0.0% | 0.0% |
| ICT/NZDUSD/M5 | 64 | 15 | 49 | 23.4% | -17.80 | 0.64 | 2.08 | 2.02 | 2.57 | 2.57 | 3.01 | 3.01 | 0.0% | 0.0% | 0.0% | 0.0% |
| ICT/XAUUSD/H1 | 7 | 3 | 4 | 42.9% | 1.65 | 1.41 | 1.88 | 1.82 | 2.05 | 2.05 | 2.05 | 2.05 | 0.0% | 0.0% | 0.0% | 0.0% |
| ICT/XAUUSD/H4 | 4 | 0 | 4 | 0.0% | -4.00 | 0.00 | n/a | n/a | n/a | n/a | n/a | n/a | 0.0% | 0.0% | 0.0% | 0.0% |
| ICT/XAUUSD/M1 | 92 | 32 | 60 | 34.8% | 5.65 | 1.09 | 2.05 | 1.84 | 2.95 | 3.00 | 3.00 | 3.00 | 0.0% | 0.0% | 0.0% | 0.0% |
| ICT/XAUUSD/M15 | 60 | 20 | 40 | 33.3% | -5.12 | 0.87 | 1.74 | 1.59 | 2.37 | 2.65 | 2.69 | 2.69 | 0.0% | 0.0% | 0.0% | 0.0% |
| ICT/XAUUSD/M30 | 10 | 6 | 4 | 60.0% | 9.64 | 3.41 | 2.27 | 2.07 | 2.64 | 3.44 | 3.44 | 3.44 | 0.0% | 0.0% | 0.0% | 0.0% |
| ICT/XAUUSD/M5 | 58 | 10 | 48 | 17.2% | -26.31 | 0.45 | 2.17 | 2.20 | 2.51 | 2.59 | 2.59 | 2.59 | 0.0% | 0.0% | 0.0% | 0.0% |
| SMC/EURUSD/H1 | 14 | 9 | 5 | 64.3% | 20.49 | 5.10 | 2.83 | 3.00 | 3.26 | 5.35 | 5.35 | 5.35 | 21.0% | 0.0% | 0.0% | 0.0% |
| SMC/EURUSD/H4 | 9 | 0 | 9 | 0.0% | -9.00 | 0.00 | n/a | n/a | n/a | n/a | n/a | n/a | 0.0% | 0.0% | 0.0% | 0.0% |
| SMC/EURUSD/M1 | 541 | 150 | 391 | 27.7% | 99.20 | 1.25 | 3.27 | 2.40 | 6.06 | 7.16 | 15.21 | 16.49 | 35.3% | 14.3% | 0.0% | 0.0% |
| SMC/EURUSD/M15 | 386 | 68 | 318 | 17.6% | -163.80 | 0.48 | 2.27 | 1.50 | 2.96 | 3.44 | 9.58 | 22.01 | 25.4% | 14.3% | 14.3% | 0.0% |
| SMC/EURUSD/M30 | 123 | 19 | 104 | 15.4% | -22.03 | 0.79 | 4.31 | 2.49 | 7.22 | 10.06 | 20.52 | 20.52 | 59.3% | 37.3% | 25.0% | 0.0% |
| SMC/EURUSD/M5 | 635 | 119 | 516 | 18.7% | -123.13 | 0.76 | 3.30 | 2.39 | 5.80 | 8.03 | 11.42 | 11.49 | 35.9% | 8.4% | 0.0% | 0.0% |
| SMC/GBPUSD/H1 | 37 | 16 | 21 | 43.2% | 20.00 | 1.95 | 2.56 | 1.85 | 5.64 | 5.64 | 6.28 | 6.28 | 29.1% | 0.0% | 0.0% | 0.0% |
| SMC/GBPUSD/H4 | 9 | 1 | 8 | 11.1% | -5.84 | 0.27 | 2.16 | 2.16 | 2.16 | 2.16 | 2.16 | 2.16 | 0.0% | 0.0% | 0.0% | 0.0% |
| SMC/GBPUSD/M1 | 658 | 210 | 448 | 31.9% | 267.08 | 1.60 | 3.41 | 2.35 | 6.46 | 9.15 | 15.46 | 18.11 | 40.9% | 12.3% | 0.0% | 0.0% |
| SMC/GBPUSD/M15 | 122 | 22 | 100 | 18.0% | -16.66 | 0.83 | 3.79 | 2.32 | 4.85 | 14.28 | 16.41 | 16.41 | 36.8% | 36.8% | 0.0% | 0.0% |
| SMC/GBPUSD/M30 | 142 | 8 | 134 | 5.6% | -105.98 | 0.21 | 3.50 | 2.15 | 5.08 | 10.82 | 10.82 | 10.82 | 56.7% | 38.6% | 0.0% | 0.0% |
| SMC/GBPUSD/M5 | 476 | 130 | 346 | 27.3% | 150.20 | 1.43 | 3.82 | 2.66 | 6.60 | 10.24 | 17.92 | 20.50 | 45.5% | 21.7% | 4.1% | 0.0% |
| SMC/NZDUSD/H1 | 31 | 9 | 22 | 29.0% | 21.08 | 1.96 | 4.79 | 4.15 | 7.18 | 9.47 | 9.47 | 9.47 | 65.2% | 0.0% | 0.0% | 0.0% |
| SMC/NZDUSD/H4 | 15 | 5 | 10 | 33.3% | 19.27 | 2.93 | 5.85 | 2.48 | 13.17 | 13.17 | 13.17 | 13.17 | 79.1% | 45.0% | 0.0% | 0.0% |
| SMC/NZDUSD/M1 | 555 | 160 | 395 | 28.8% | 42.21 | 1.11 | 2.73 | 2.04 | 4.57 | 6.16 | 9.73 | 13.84 | 25.4% | 5.7% | 0.0% | 0.0% |
| SMC/NZDUSD/M15 | 162 | 40 | 122 | 24.7% | -7.56 | 0.94 | 2.86 | 2.05 | 4.50 | 6.12 | 9.73 | 9.73 | 25.3% | 0.0% | 0.0% | 0.0% |
| SMC/NZDUSD/M30 | 199 | 27 | 172 | 13.6% | -81.10 | 0.53 | 3.37 | 1.57 | 4.70 | 12.69 | 20.97 | 20.97 | 47.7% | 37.0% | 23.1% | 0.0% |
| SMC/NZDUSD/M5 | 439 | 120 | 319 | 27.3% | 7.40 | 1.02 | 2.72 | 2.09 | 4.20 | 4.94 | 16.54 | 17.13 | 13.8% | 10.3% | 0.0% | 0.0% |
| SMC/XAUUSD/H1 | 25 | 9 | 16 | 36.0% | 32.51 | 3.03 | 5.39 | 2.69 | 5.07 | 25.34 | 25.34 | 25.34 | 62.7% | 52.2% | 52.2% | 0.0% |
| SMC/XAUUSD/H4 | 24 | 6 | 18 | 25.0% | -5.89 | 0.67 | 2.02 | 1.71 | 1.83 | 3.81 | 3.81 | 3.81 | 0.0% | 0.0% | 0.0% | 0.0% |
| SMC/XAUUSD/M1 | 763 | 227 | 536 | 29.8% | 302.59 | 1.56 | 3.69 | 2.95 | 7.94 | 8.76 | 10.08 | 10.75 | 49.6% | 3.7% | 0.0% | 0.0% |
| SMC/XAUUSD/M15 | 299 | 154 | 145 | 51.5% | 445.62 | 4.07 | 3.84 | 1.75 | 10.12 | 10.17 | 10.19 | 18.19 | 64.5% | 44.2% | 0.0% | 0.0% |
| SMC/XAUUSD/M30 | 67 | 16 | 51 | 23.9% | -10.66 | 0.79 | 2.52 | 2.13 | 4.86 | 4.86 | 4.98 | 4.98 | 0.0% | 0.0% | 0.0% | 0.0% |
| SMC/XAUUSD/M5 | 521 | 94 | 427 | 18.0% | -134.91 | 0.68 | 3.11 | 2.15 | 4.32 | 7.22 | 17.80 | 22.55 | 31.8% | 27.4% | 7.7% | 0.0% |
| SweepDisplacement/EURUSD/H1 | 22 | 8 | 14 | 36.4% | 7.95 | 1.57 | 2.74 | 2.23 | 3.27 | 5.69 | 5.69 | 5.69 | 25.9% | 0.0% | 0.0% | 0.0% |
| SweepDisplacement/EURUSD/H4 | 0 | 0 | 0 | 0.0% | 0.00 | 0.00 | n/a | n/a | n/a | n/a | n/a | n/a | 0.0% | 0.0% | 0.0% | 0.0% |
| SweepDisplacement/EURUSD/M1 | 513 | 89 | 424 | 17.3% | -111.29 | 0.74 | 3.51 | 2.32 | 6.55 | 10.31 | 12.17 | 34.03 | 44.3% | 24.7% | 10.9% | 0.0% |
| SweepDisplacement/EURUSD/M15 | 88 | 11 | 77 | 12.5% | 37.71 | 1.49 | 10.43 | 2.30 | 4.95 | 87.08 | 87.08 | 87.08 | 75.9% | 75.9% | 75.9% | 75.9% |
| SweepDisplacement/EURUSD/M30 | 58 | 12 | 46 | 20.7% | -13.95 | 0.70 | 2.67 | 2.21 | 4.12 | 4.12 | 6.63 | 6.63 | 20.7% | 0.0% | 0.0% | 0.0% |
| SweepDisplacement/EURUSD/M5 | 304 | 66 | 238 | 21.7% | -40.44 | 0.83 | 2.99 | 2.49 | 3.75 | 6.06 | 11.07 | 15.76 | 23.6% | 13.6% | 0.0% | 0.0% |
| SweepDisplacement/GBPUSD/H1 | 27 | 2 | 25 | 7.4% | -20.60 | 0.18 | 2.20 | 2.20 | 2.21 | 2.21 | 2.21 | 2.21 | 0.0% | 0.0% | 0.0% | 0.0% |
| SweepDisplacement/GBPUSD/H4 | 7 | 2 | 5 | 28.6% | -1.40 | 0.72 | 1.80 | 1.80 | 1.81 | 1.81 | 1.81 | 1.81 | 0.0% | 0.0% | 0.0% | 0.0% |
| SweepDisplacement/GBPUSD/M1 | 451 | 92 | 359 | 20.4% | -69.98 | 0.81 | 3.14 | 2.25 | 5.80 | 6.63 | 13.08 | 15.77 | 40.2% | 10.0% | 0.0% | 0.0% |
| SweepDisplacement/GBPUSD/M15 | 86 | 19 | 67 | 22.1% | 16.49 | 1.25 | 4.39 | 2.75 | 8.17 | 8.38 | 19.70 | 19.70 | 64.0% | 23.6% | 0.0% | 0.0% |
| SweepDisplacement/GBPUSD/M30 | 49 | 8 | 41 | 16.3% | -21.13 | 0.48 | 2.48 | 2.29 | 2.79 | 3.80 | 3.80 | 3.80 | 0.0% | 0.0% | 0.0% | 0.0% |
| SweepDisplacement/GBPUSD/M5 | 313 | 65 | 248 | 20.8% | -54.65 | 0.78 | 2.97 | 2.21 | 5.29 | 9.09 | 10.90 | 11.56 | 30.3% | 11.6% | 0.0% | 0.0% |
| SweepDisplacement/NZDUSD/H1 | 37 | 6 | 31 | 16.2% | -11.99 | 0.61 | 3.17 | 1.99 | 5.64 | 6.10 | 6.10 | 6.10 | 61.8% | 0.0% | 0.0% | 0.0% |
| SweepDisplacement/NZDUSD/H4 | 4 | 0 | 4 | 0.0% | -4.00 | 0.00 | n/a | n/a | n/a | n/a | n/a | n/a | 0.0% | 0.0% | 0.0% | 0.0% |
| SweepDisplacement/NZDUSD/M1 | 454 | 117 | 337 | 25.8% | -8.54 | 0.97 | 2.81 | 2.36 | 4.08 | 5.93 | 9.99 | 15.95 | 22.7% | 4.9% | 0.0% | 0.0% |
| SweepDisplacement/NZDUSD/M15 | 104 | 20 | 84 | 19.2% | -42.77 | 0.49 | 2.06 | 1.82 | 3.13 | 3.16 | 4.31 | 4.31 | 0.0% | 0.0% | 0.0% | 0.0% |
| SweepDisplacement/NZDUSD/M30 | 39 | 17 | 22 | 43.6% | 84.07 | 4.82 | 6.24 | 2.11 | 5.98 | 7.51 | 56.30 | 56.30 | 71.2% | 53.1% | 53.1% | 53.1% |
| SweepDisplacement/NZDUSD/M5 | 385 | 76 | 309 | 19.7% | -110.47 | 0.64 | 2.61 | 2.06 | 4.34 | 4.58 | 8.83 | 11.17 | 13.5% | 5.6% | 0.0% | 0.0% |
| SweepDisplacement/XAUUSD/H1 | 19 | 4 | 15 | 21.1% | -6.41 | 0.57 | 2.15 | 2.03 | 3.01 | 3.01 | 3.01 | 3.01 | 0.0% | 0.0% | 0.0% | 0.0% |
| SweepDisplacement/XAUUSD/H4 | 3 | 0 | 3 | 0.0% | -3.00 | 0.00 | n/a | n/a | n/a | n/a | n/a | n/a | 0.0% | 0.0% | 0.0% | 0.0% |
| SweepDisplacement/XAUUSD/M1 | 400 | 76 | 324 | 19.0% | -115.34 | 0.64 | 2.75 | 2.00 | 4.71 | 6.16 | 11.27 | 15.95 | 25.4% | 13.0% | 0.0% | 0.0% |
| SweepDisplacement/XAUUSD/M15 | 92 | 14 | 78 | 15.2% | -42.05 | 0.46 | 2.57 | 2.11 | 3.54 | 3.54 | 7.18 | 7.18 | 20.0% | 0.0% | 0.0% | 0.0% |
| SweepDisplacement/XAUUSD/M30 | 42 | 7 | 35 | 16.7% | -13.62 | 0.61 | 3.05 | 2.44 | 4.35 | 5.09 | 5.09 | 5.09 | 23.8% | 0.0% | 0.0% | 0.0% |
| SweepDisplacement/XAUUSD/M5 | 313 | 54 | 259 | 17.3% | -108.40 | 0.58 | 2.79 | 1.96 | 5.75 | 7.08 | 8.24 | 12.29 | 31.3% | 8.2% | 0.0% | 0.0% |

## 11. Extreme-R Trade Investigation

Descriptive language only -- these notes describe what the numbers show, not which cell is "best" or "worst".

### Cells named for special attention

- **Classic/EURUSD/M1**: 1112 trades, 192 wins, Net R = 913.92, mean winning R = 9.55, median winning R = 2.71, max winning R = 773.32.
  - mean winning R (9.55) is more than 3x the median winning R (2.71)
  - P99 winning R (71.57) is more than 2x P95 winning R (13.12)
  - winners above 20R alone account for 61.2% of gross winning R
  - maximum realized winning R is 773.32
- **Classic/EURUSD/M5**: 939 trades, 152 wins, Net R = 1998.29, mean winning R = 18.32, median winning R = 2.49, max winning R = 1894.81.
  - mean winning R (18.32) is more than 3x the median winning R (2.49)
  - P99 winning R (114.63) is more than 2x P95 winning R (14.36)
  - winners above 20R alone account for 81.9% of gross winning R
  - maximum realized winning R is 1894.81

### All cells meeting at least one flagged condition

Flag conditions (applied identically to every cell, not a comparison between cells): mean winning R > 3x median winning R; P99 winning R > 2x P95 winning R; winners above 20R account for over 40% of gross winning R; or maximum winning R exceeds 50R.

- **Classic/EURUSD/H1**: P99 winning R (12.47) is more than 2x P95 winning R (5.51)
- **Classic/EURUSD/M1**: mean winning R (9.55) is more than 3x the median winning R (2.71); P99 winning R (71.57) is more than 2x P95 winning R (13.12); winners above 20R alone account for 61.2% of gross winning R; maximum realized winning R is 773.32
- **Classic/EURUSD/M30**: P99 winning R (18.84) is more than 2x P95 winning R (6.96)
- **Classic/EURUSD/M5**: mean winning R (18.32) is more than 3x the median winning R (2.49); P99 winning R (114.63) is more than 2x P95 winning R (14.36); winners above 20R alone account for 81.9% of gross winning R; maximum realized winning R is 1894.81
- **Classic/GBPUSD/M1**: P99 winning R (39.02) is more than 2x P95 winning R (16.10); winners above 20R alone account for 46.2% of gross winning R; maximum realized winning R is 497.19
- **Classic/GBPUSD/M15**: P99 winning R (82.41) is more than 2x P95 winning R (11.97); winners above 20R alone account for 50.2% of gross winning R; maximum realized winning R is 82.41
- **Classic/GBPUSD/M30**: winners above 20R alone account for 49.6% of gross winning R
- **Classic/GBPUSD/M5**: P99 winning R (29.29) is more than 2x P95 winning R (11.10); maximum realized winning R is 58.55
- **Classic/NZDUSD/M1**: P99 winning R (37.66) is more than 2x P95 winning R (16.24); maximum realized winning R is 104.17
- **Classic/NZDUSD/M15**: P99 winning R (33.55) is more than 2x P95 winning R (9.95)
- **Classic/NZDUSD/M30**: P99 winning R (34.78) is more than 2x P95 winning R (6.86)
- **Classic/NZDUSD/M5**: P99 winning R (67.65) is more than 2x P95 winning R (11.34); maximum realized winning R is 79.50
- **Classic/XAUUSD/M5**: winners above 20R alone account for 40.1% of gross winning R; maximum realized winning R is 382.79
- **ICT/EURUSD/M1**: P99 winning R (9.92) is more than 2x P95 winning R (3.25)
- **SMC/EURUSD/M1**: P99 winning R (15.21) is more than 2x P95 winning R (7.16)
- **SMC/EURUSD/M15**: P99 winning R (9.58) is more than 2x P95 winning R (3.44)
- **SMC/EURUSD/M30**: P99 winning R (20.52) is more than 2x P95 winning R (10.06)
- **SMC/NZDUSD/M5**: P99 winning R (16.54) is more than 2x P95 winning R (4.94)
- **SMC/XAUUSD/H1**: winners above 20R alone account for 52.2% of gross winning R
- **SMC/XAUUSD/M5**: P99 winning R (17.80) is more than 2x P95 winning R (7.22)
- **SweepDisplacement/EURUSD/M15**: mean winning R (10.43) is more than 3x the median winning R (2.30); winners above 20R alone account for 75.9% of gross winning R; maximum realized winning R is 87.08
- **SweepDisplacement/GBPUSD/M15**: P99 winning R (19.70) is more than 2x P95 winning R (8.38)
- **SweepDisplacement/NZDUSD/M30**: P99 winning R (56.30) is more than 2x P95 winning R (7.51); winners above 20R alone account for 53.1% of gross winning R; maximum realized winning R is 56.30
- **SweepDisplacement/XAUUSD/M15**: P99 winning R (7.18) is more than 2x P95 winning R (3.54)

## 12. Planned RR vs Realized R

Compares the planned R:R at signal time (`SelectedSetup.risk_reward_tp1`/`risk_reward_tp2`, computed from Entry/SL/TP BEFORE the trade is simulated) against the REALIZED R of winning trades, to determine whether extreme realized R values correspond to genuinely extreme planned setups or are only created during outcome simulation.

| Series | N | Mean | Median | P90 | P95 | P99 | Max |
|---|---:|---:|---:|---:|---:|---:|---:|
| Planned RR (TP1), winning trades | 4480 | 4.12 | 2.20 | 5.80 | 8.97 | 18.77 | 1894.81 |
| Planned RR (TP2), winning trades | 4480 | 9.26 | 4.77 | 13.09 | 19.95 | 58.42 | 2640.38 |
| Realized R, winning trades | 4480 | 4.49 | 2.30 | 6.45 | 9.73 | 22.01 | 1894.81 |

Note: for a TP2-hit trade, realized R equals planned RR (TP2) exactly by construction (see Section 13) -- the comparison above is informative mainly for TP1-hit trades and for showing whether the planned-RR distribution at signal time already contains the same extreme tail seen in realized R.

## 13. R-Multiple Validation

Independent recomputation of realized R directly from each trade's stored Entry/SL/exit price (`optimization.rr_distribution.independent_r_multiple`, using the BUY/SELL formulas: `R = (exit - entry) / abs(entry - SL)` for BUY, `R = (entry - exit) / abs(entry - SL)` for SELL), compared against the project's own stored `r_multiple` -- deliberately not calling `SelectedSetup.risk_reward_tp1`/`risk_reward_tp2` again, which would be a circular self-comparison.

- Resolved trades checked: 21318.
- Trades with an undefined (zero-distance) stop-loss: 0.
- **WINNING (TP1/TP2) trades**: 0 discrepancies out of 4480 checked -- every winning trade's realized R independently reproduces the stored value exactly. This directly answers the audit's central question about the realized-R distribution in Sections 4-11: the winning-trade R-multiple numbers analyzed throughout this report are not the product of a computation bug.
- **SL (losing) trades**: 3194 discrepancies out of 16838 SL-hit trades. `BacktestEngine._simulate_outcome` stores exactly `-1.0` for every SL hit as a fixed convention, rather than computing it from price -- so this figure compares that convention against the geometric formula above, not one computed value against another.
  - Of those 3194 SL-trade discrepancies, 3194 (100.0%) have a stop-loss placed on the wrong side of entry for the trade's own direction (SL above entry on a BUY, or below entry on a SELL) -- checkable directly from the stored prices, independent of whether SL was ever hit. This is consistent with, and independently confirms via this audit's own numeric check (not a re-diagnosis from scratch), the previously documented S/R and sweep-anchoring proximity-gate finding in `CURRENT_VERSION_LOSS_DIAGNOSTIC_REPORT.md`, which found those gates check absolute distance only, not directional correctness.
  - The remaining 0 have a correctly-sided but very small stop-loss distance, which the -1.0 convention also does not reflect geometrically (it is a fixed loss-of-risked-capital convention, not a per-trade price computation).

### Structurally-inverted stop-loss among WINNING trades

A stop-loss can be checked for wrong-side placement on ANY trade from its stored prices alone, whether or not SL was the outcome that occurred -- this isolates whether extreme WINNING R values are linked to the same inverted-SL condition found above, or to something else.

- Of 4480 winning trades, 29 have a structurally-inverted stop-loss.
- Of 55 winning trades with realized R > 20, 11 have a structurally-inverted stop-loss (44 do not).
- Of 18 winning trades with realized R > 50, 5 have a structurally-inverted stop-loss (13 do not).
- Among the R>20 winners with a correctly-sided (non-inverted) stop-loss, the SL distance (in raw price units) ranges down to 3.51e-07 (median 1.18e-05) -- i.e. most extreme winning R values in this dataset come from a correctly-directed but extremely small stop-loss distance relative to the take-profit distance, not from an inverted SL, an incorrect trade direction, or a unit/pip-conversion error.

### Manual verification sample: top 10 highest-realized-R winning trades

| Strategy/Symbol/TF | Direction | Entry | SL | SL Distance | Exit (TP hit) | Stored R | Independent R | Match | Inverted SL |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| Classic/EURUSD/M5 | SELL | 1.16025 | 1.16025 | 0.000000 | 1.15958 | 1894.81 | 1894.81 | yes | no |
| Classic/EURUSD/M1 | SELL | 1.13783 | 1.13783 | 0.000000 | 1.13778 | 773.32 | 773.32 | yes | yes |
| Classic/GBPUSD/M1 | SELL | 1.33134 | 1.33134 | 0.000000 | 1.33117 | 497.19 | 497.19 | yes | yes |
| Classic/XAUUSD/M5 | BUY | 4005.40500 | 4005.40234 | 0.002665 | 4006.42500 | 382.79 | 382.79 | yes | no |
| Classic/EURUSD/M1 | BUY | 1.16731 | 1.16731 | 0.000001 | 1.16743 | 198.69 | 198.69 | yes | yes |
| Classic/EURUSD/M5 | BUY | 1.15684 | 1.15683 | 0.000008 | 1.15788 | 131.08 | 131.08 | yes | no |
| Classic/EURUSD/M5 | BUY | 1.16242 | 1.16242 | 0.000003 | 1.16278 | 114.63 | 114.63 | yes | yes |
| Classic/NZDUSD/M1 | SELL | 0.59011 | 0.59011 | 0.000001 | 0.58996 | 104.17 | 104.17 | yes | no |
| Classic/EURUSD/M5 | BUY | 1.19164 | 1.19164 | 0.000004 | 1.19195 | 87.62 | 87.62 | yes | no |
| SweepDisplacement/EURUSD/M15 | SELL | 1.14765 | 1.14767 | 0.000023 | 1.14569 | 87.08 | 87.08 | yes | no |

Discrepancies were found (see above) and are NOT auto-fixed -- see `discrepancy_samples` in `data/optimization_results/trade_level_audit.json` for the full list of affected SL-hit trades. No Strategy/SL/Entry/TP logic was changed in response to this finding.

## 14. Data/Backtest Limitations

- OHLC-only backtesting: no tick data or intrabar path is available for any timeframe; true intrabar ordering between a candle's high and low cannot be established from OHLC data alone.
- Same-candle policy: `BacktestEngine._simulate_outcome` checks SL before TP1/TP2 whenever both would be touched within the same candle -- a deterministic, conservative convention, not a simulation of real intrabar price path.
- Exit price is always exactly the setup's stored TP1/TP2/SL price (never a slippage-adjusted or partially-filled price), so realized R is a theoretical value assuming perfect fills at the planned levels.
- No spread data exists anywhere in this dataset: `data/market/*.csv` and the generated `data/historical/*.csv` files have no spread column at all (`candle.spread` is always `None`).
- Spread filtering is not active in any batch backtest script: `ValidatingMarketDataProvider` (the component that would filter on `max_spread`) is wired only into the live `/analyze` backend path (`backend/dependencies.py`), never into `m1_full_backtest.py`, `robustness_backtest.py`, or this audit's `rr_distribution_audit.py`.
- H4 entry-timeframe cells map Higher=Middle=Entry=H4 (`config/settings.backtest.yaml`'s `entry_mapping`), since no D1 timeframe is generated by this data pipeline -- H4 cells therefore have less genuine multi-timeframe context than other entry timeframes.
- H1 entry-timeframe cells map Middle=Entry=H1 for the same reason (no timeframe between H1 and H4 in this pipeline).
- `closed_at` is the OPEN timestamp of the candle on which the exit condition was met, not a precise intrabar exit instant.
- "Signal score" is reported as `confidence_score` (0-100, a relative confidence score, explicitly NOT a win probability per its own field documentation) since no other single-number score is stored on `SelectedSetup`.

## 15. Conclusions

This section states only what the data demonstrates. It contains no ranking, no best/worst/recommended strategy, symbol, timeframe, or configuration, and no change was made to any Strategy, Weight, Filter, Threshold, Entry, TP, or SL logic to produce or in response to these results.

- Across 21319 captured trades, 4480 were winners; the top 0.1% of winning trades by count (4 trades) account for 17.6% of total gross winning R, the top 1% (45 trades) account for 28.0%, and the top 5% (224 trades) account for 39.8%.
- Removing the top 1% highest-realized-R winning trades changes global Net R from 3277.83 to -2360.39, and removing the top 5% changes it to -4720.32.
- Independent recomputation of realized R from stored Entry/SL/Exit prices matched the project's stored `r_multiple` for all 4480 winning trades checked (0 discrepancies). All discrepancies found (see Section 13) are on SL-hit (losing) trades, where the engine stores a fixed `-1.0` by convention rather than a computed value; 3194 of those 3194 SL-trade cases have a stop-loss on the wrong side of entry for the trade's own direction.
- Extreme realized-R WINNING trades in this dataset are associated with a small, correctly-sided stop-loss distance relative to the take-profit distance (see Section 13): among winners with realized R > 20, 44 of 55 have a correctly-sided (non-inverted) stop-loss, meaning most of this dataset's extreme winning R values are not explained by a zero/negative SL distance, incorrect trade direction, or a unit/pip-conversion error.
- Baseline reproducibility: the audit reproduced data/optimization_results/m1_full_backtest.json exactly for every checked cell.
