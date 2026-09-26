# SL DISTANCE INTEGRITY AUDIT

## 1. Executive Summary

Direct follow-up to the R:R Distribution Audit, investigating WHY some winning trades receive an extremely small Entry-to-SL distance. Diagnostic only: no Strategy, Entry, SL, TP, Filter, Threshold, or minimum-SL-distance logic was introduced or changed anywhere in this audit, and every figure below reuses already-captured trade data from `data/optimization_results/trade_level_audit.json` -- no cell was re-run.

- 21319 trades analyzed across all 96 Baseline cells; Baseline integrity independently re-verified with 0 mismatches (Section 4).
- 1092 trades (5.1%) have an SL distance smaller than the symbol's own smallest quotable price increment (`10**-digits`) -- not even one distinguishable price step for that symbol's quoting precision.
- 3223 trades (15.1%) have a stop-loss on the wrong side of entry for their own direction (`inverted`); 0 have SL exactly equal to entry.
- The data-derived `extremely_small` SL-distance bucket (1066 trades, 5.0% of all trades) alone has a Net R of 4217.76, while the other three buckets COMBINED have a Net R of -939.93 -- the entire positive Baseline Net R is concentrated in this one data-derived bucket (Section 5).
- Section 12 traces the mechanism to specific existing code paths: Classic's nearest-support/resistance lookup and SweepDisplacement's post-sweep entry-zone check do not verify that the chosen reference price sits on the geometrically correct side of entry before the SL buffer is subtracted/added -- this is an implementation gap in those two strategies' SL derivation, not a data-quality or backtest-engine issue (Section 12).

## 2. Audit Scope

This audit answers: why are some SL distances extremely small, which strategy logic generates them, whether they are concentrated by symbol/timeframe/strategy, whether they reflect valid market-structure logic or an implementation gap, whether any extreme-R trade is caused by an incorrect (vs. merely tiny) SL, whether there is evidence of lookahead in SL generation, and how much of Baseline Net R depends on these trades. It does not rank strategies, does not propose or apply a fix, and does not change any trading behavior. Section 21 answers each of the 12 questions explicitly.

## 3. Dataset and Methodology

- Source: `data/optimization_results/trade_level_audit.json` (produced by the R:R Distribution Audit's 96-cell run) -- reused verbatim; no signal was regenerated for this audit.
- `absolute_sl_distance = abs(entry_price - stop_loss_price)`, computed per trade after the fact.
- Normalization uses ONLY existing project definitions: `Symbol.pip_size` and `Symbol.digits` (`core/market_data/models.py`, populated in `scripts/optimize_strategy.py`'s `SYMBOLS` table). `Symbol.tick_size` is `None` for every symbol in this dataset (never populated for the batch-script hand-built `SYMBOLS` table), so tick-size-based normalization is not available without inventing a value -- explicitly not attempted. ATR-based normalization is not stored per trade in `trade_level_audit.json` and reconstructing it would require re-running signal generation; per this audit's instruction to avoid re-running cells, it is not computed here, and this limitation is stated explicitly rather than approximated.
- pip distance = `absolute_sl_distance / Symbol.pip_size`; precision-unit distance = `absolute_sl_distance / 10**-Symbol.digits` (how many of the symbol's own smallest quotable price steps the SL distance spans). A distance below one precision unit is labeled `sub_precision`.
- Symbol specs used (existing project definitions, not invented): EURUSD (pip_size=0.0001, digits=5), XAUUSD (pip_size=0.01, digits=2), GBPUSD (pip_size=0.0001, digits=5), NZDUSD (pip_size=0.0001, digits=5).
- Tiny-SL buckets (Section 5) use each symbol's OWN observed P5/P25/P90 of absolute SL distance as boundaries -- never a single cross-symbol threshold; see Section 5 for the actual boundary values.

## 4. Baseline Integrity

Independently recomputed trade_count/resolved_count/TP1/TP2/SL counts/win_rate/net_r/profit_factor/expectancy for all 96 cells directly from the captured trade list (grouped fresh in this script's driver, not by reusing the R:R audit's own cached per-cell summaries) and compared against `data/optimization_results/m1_full_backtest.json` (sha256 `4f98db7195427c11...`, read-only, never opened in write mode by this audit).

**Result: PASSED -- 0 differences across all 96 cells checked**

## 5. Global SL Distance Distribution

Item 5's tiny-SL buckets, using each symbol's OWN P5/P25/P90 of absolute SL distance as boundaries (see `tiny_sl_bucket_boundaries_per_symbol` in the JSON for exact values per symbol). Buckets are NOT a fixed cross-symbol price threshold.

| Bucket | Trade Count | % of All Trades | Winners | Losses | Win Rate | Net R | PF | Mean Win R | Median Win R | P95 Win R | P99 Win R | Max Win R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| extremely_small | 1066 | 5.0% | 76 | 990 | 7.1% | 4217.76 | 5.26 | 68.52 | 15.29 | 198.69 | 773.32 | 1894.81 |
| very_small | 4263 | 20.0% | 614 | 3649 | 14.4% | 477.56 | 1.13 | 6.72 | 4.28 | 17.13 | 53.92 | 131.08 |
| normal | 13854 | 65.0% | 3307 | 10546 | 23.9% | -821.37 | 0.92 | 2.94 | 2.20 | 6.89 | 11.49 | 25.34 |
| large | 2136 | 10.0% | 483 | 1653 | 22.6% | -596.13 | 0.64 | 2.19 | 1.81 | 3.77 | 6.17 | 13.17 |

Sub-precision trades (distance below the symbol's own smallest quotable price increment): 1092 of 21319 (5.1%).

| Group | Trades | Correct | % Correct | Equal | % Equal | Inverted | % Inverted |
|---|---:|---:|---:|---:|---:|---:|---:|
| Global | 21319 | 18096 | 84.9% | 0 | 0.0% | 3223 | 15.1% |

## 6. Symbol-Level Distribution

| Symbol | Trades | Wins | Losses | SL-hit | Sub-precision | Min Dist | P0.1 (pips) | P1 (pips) | P5 (pips) | P25 (pips) | Median (pips) | P75 (pips) | P90 (pips) | P99 (pips) | Max (pips) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| EURUSD | 5597 | 1047 | 4550 | 4550 | 380 | 5.948e-08 | 0.0025 | 0.0158 | 0.077 | 0.405 | 1.024 | 2.60 | 7.27 | 13.01 | 44.50 |
| XAUUSD | 5221 | 1167 | 4054 | 4054 | 11 | 1.238e-03 | 0.3602 | 3.7698 | 13.429 | 64.508 | 160.054 | 414.38 | 864.33 | 3759.81 | 9787.96 |
| GBPUSD | 5215 | 1142 | 4072 | 4072 | 293 | 2.876e-09 | 0.0006 | 0.0164 | 0.090 | 0.469 | 1.242 | 3.01 | 6.90 | 27.42 | 80.11 |
| NZDUSD | 5286 | 1124 | 4162 | 4162 | 408 | 2.860e-08 | 0.0012 | 0.0150 | 0.065 | 0.336 | 0.867 | 1.98 | 4.11 | 10.37 | 32.14 |

| Group | Trades | Correct | % Correct | Equal | % Equal | Inverted | % Inverted |
|---|---:|---:|---:|---:|---:|---:|---:|
| EURUSD | 5597 | 4777 | 85.3% | 0 | 0.0% | 820 | 14.7% |
| XAUUSD | 5221 | 4436 | 85.0% | 0 | 0.0% | 785 | 15.0% |
| GBPUSD | 5215 | 4389 | 84.2% | 0 | 0.0% | 826 | 15.8% |
| NZDUSD | 5286 | 4494 | 85.0% | 0 | 0.0% | 792 | 15.0% |

Note: pip-distance percentiles are NOT directly comparable across symbols -- XAUUSD's pip convention (`pip_size=0.01`) represents a very different fraction of typical price movement than EURUSD/GBPUSD/NZDUSD's (`pip_size=0.0001`); see Section 3.

## 7. Strategy-Level Distribution

| Strategy | Trades | Extremely Small | Very Small | Normal | Large |
|---|---:|---:|---:|---:|---:|
| Classic | 10269 | 921 | 2843 | 6102 | 403 |
| SMC | 6252 | 60 | 971 | 4348 | 873 |
| ICT | 988 | 0 | 6 | 604 | 378 |
| SweepDisplacement | 3810 | 85 | 443 | 2800 | 482 |

| Group | Trades | Correct | % Correct | Equal | % Equal | Inverted | % Inverted |
|---|---:|---:|---:|---:|---:|---:|---:|
| Classic | 10269 | 8001 | 77.9% | 0 | 0.0% | 2268 | 22.1% |
| SMC | 6252 | 6249 | 100.0% | 0 | 0.0% | 3 | 0.0% |
| ICT | 988 | 988 | 100.0% | 0 | 0.0% | 0 | 0.0% |
| SweepDisplacement | 3810 | 2858 | 75.0% | 0 | 0.0% | 952 | 25.0% |

`extremely_small`-bucket trade count, by symbol:

| Strategy | EURUSD | XAUUSD | GBPUSD | NZDUSD |
|---|---:|---:|---:|---:|
| Classic | 248 | 195 | 235 | 243 |
| SMC | 7 | 40 | 6 | 7 |
| ICT | 0 | 0 | 0 | 0 |
| SweepDisplacement | 25 | 26 | 20 | 14 |

`extremely_small`-bucket trade count, by timeframe:

| Strategy | M1 | M5 | M15 | M30 | H1 | H4 |
|---|---:|---:|---:|---:|---:|---:|
| Classic | 660 | 207 | 33 | 12 | 7 | 2 |
| SMC | 59 | 1 | 0 | 0 | 0 | 0 |
| ICT | 0 | 0 | 0 | 0 | 0 | 0 |
| SweepDisplacement | 60 | 21 | 4 | 0 | 0 | 0 |

Descriptive statements only, no ranking: Classic generated 921 trades in the data-derived `extremely_small` SL-distance bucket and 2268 trades with an inverted SL direction; SweepDisplacement generated 85 `extremely_small`-bucket trades and 952 inverted-SL trades; SMC generated 60 `extremely_small`-bucket trades and 3 inverted-SL trades; ICT generated 0 `extremely_small`-bucket trades and 0 inverted-SL trades.

## 8. Timeframe-Level Distribution

| Timeframe | Trades | Tiny-SL Count | Tiny-SL % | Median Dist | P1 Dist | P5 Dist | P99 Dist | R>20 Winners | R>50 Winners |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| M1 | 9012 | 779 | 8.6% | 8.120e-05 | 1.322e-06 | 6.021e-06 | 4.479e+00 | 22 | 5 |
| M5 | 7404 | 229 | 3.1% | 2.131e-04 | 3.010e-06 | 1.676e-05 | 1.110e+01 | 21 | 9 |
| M15 | 2542 | 37 | 1.5% | 3.730e-04 | 5.913e-06 | 3.123e-05 | 4.041e+01 | 5 | 3 |
| M30 | 1491 | 12 | 0.8% | 5.165e-04 | 1.391e-05 | 5.048e-05 | 1.689e+01 | 6 | 1 |
| H1 | 586 | 7 | 1.2% | 5.529e-04 | 9.736e-06 | 5.291e-05 | 2.460e+01 | 1 | 0 |
| H4 | 284 | 2 | 0.7% | 1.195e-03 | 4.179e-05 | 9.762e-05 | 5.579e+01 | 0 | 0 |

| Group | Trades | Correct | % Correct | Equal | % Equal | Inverted | % Inverted |
|---|---:|---:|---:|---:|---:|---:|---:|
| M1 | 9012 | 7611 | 84.5% | 0 | 0.0% | 1401 | 15.5% |
| M5 | 7404 | 6245 | 84.3% | 0 | 0.0% | 1159 | 15.7% |
| M15 | 2542 | 2209 | 86.9% | 0 | 0.0% | 333 | 13.1% |
| M30 | 1491 | 1336 | 89.6% | 0 | 0.0% | 155 | 10.4% |
| H1 | 586 | 476 | 81.2% | 0 | 0.0% | 110 | 18.8% |
| H4 | 284 | 219 | 77.1% | 0 | 0.0% | 65 | 22.9% |

## 9. 96-Cell Analysis

All 96 Strategy x Symbol x Timeframe cells, including any with zero trades -- 1 cell(s) have zero trades in this dataset (SweepDisplacement/EURUSD/H4). The enumeration below is over the full 96-cell set, not merely the cells present in the trade list, so no zero-trade cell is silently omitted.

| Cell | Trades | Min Dist | Median Dist | P1 Dist | P5 Dist | P99 Dist | Tiny-SL | Tiny-SL % | Winners>10R | Winners>20R | Winners>50R | Net R | PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Classic/EURUSD/H1 | 111 | 1.385e-06 | 3.484e-04 | 2.114e-06 | 3.832e-05 | 1.448e-03 | 2 | 1.8% | 1 | 0 | 0 | -14.75 | 0.83 |
| Classic/EURUSD/H4 | 53 | 1.070e-05 | 5.022e-04 | 4.017e-05 | 6.620e-05 | 2.620e-03 | 0 | 0.0% | 0 | 0 | 0 | -32.28 | 0.31 |
| Classic/EURUSD/M1 | 1112 | 5.948e-08 | 2.806e-05 | 6.815e-07 | 2.401e-06 | 2.090e-04 | 179 | 16.1% | 15 | 6 | 3 | 913.92 | 1.99 |
| Classic/EURUSD/M15 | 242 | 1.113e-06 | 1.563e-04 | 2.772e-06 | 9.783e-06 | 7.465e-04 | 7 | 2.9% | 0 | 0 | 0 | -50.05 | 0.75 |
| Classic/EURUSD/M30 | 177 | 7.240e-08 | 2.444e-04 | 6.985e-06 | 2.710e-05 | 1.214e-03 | 3 | 1.7% | 1 | 0 | 0 | -44.35 | 0.70 |
| Classic/EURUSD/M5 | 939 | 1.416e-07 | 8.005e-05 | 7.279e-07 | 6.071e-06 | 4.823e-04 | 57 | 6.1% | 10 | 6 | 4 | 1998.29 | 3.54 |
| Classic/GBPUSD/H1 | 106 | 4.692e-08 | 3.968e-04 | 1.640e-06 | 2.704e-05 | 1.882e-03 | 2 | 1.9% | 0 | 0 | 0 | -36.60 | 0.58 |
| Classic/GBPUSD/H4 | 54 | 4.179e-05 | 7.240e-04 | 4.570e-05 | 1.109e-04 | 3.638e-03 | 0 | 0.0% | 0 | 0 | 0 | -15.53 | 0.65 |
| Classic/GBPUSD/M1 | 1111 | 8.685e-09 | 3.725e-05 | 5.424e-07 | 2.765e-06 | 2.802e-04 | 175 | 15.8% | 23 | 8 | 1 | 640.82 | 1.72 |
| Classic/GBPUSD/M15 | 255 | 2.876e-09 | 1.821e-04 | 1.885e-06 | 1.582e-05 | 9.542e-04 | 9 | 3.5% | 4 | 2 | 2 | 55.44 | 1.26 |
| Classic/GBPUSD/M30 | 141 | 1.845e-06 | 2.877e-04 | 4.229e-06 | 1.578e-05 | 1.250e-03 | 2 | 1.4% | 2 | 2 | 0 | 54.14 | 1.49 |
| Classic/GBPUSD/M5 | 935 | 4.235e-07 | 1.086e-04 | 1.648e-06 | 9.037e-06 | 7.508e-04 | 47 | 5.0% | 11 | 7 | 2 | 23.02 | 1.03 |
| Classic/NZDUSD/H1 | 74 | 5.656e-06 | 2.598e-04 | 1.177e-05 | 2.486e-05 | 1.329e-03 | 1 | 1.4% | 1 | 0 | 0 | 11.68 | 1.21 |
| Classic/NZDUSD/H4 | 44 | 2.042e-06 | 5.591e-04 | 2.042e-06 | 8.703e-05 | 1.567e-03 | 1 | 2.3% | 0 | 0 | 0 | -15.78 | 0.58 |
| Classic/NZDUSD/M1 | 1087 | 5.259e-08 | 2.565e-05 | 4.293e-07 | 2.489e-06 | 1.529e-04 | 172 | 15.8% | 20 | 7 | 1 | 189.31 | 1.22 |
| Classic/NZDUSD/M15 | 322 | 4.606e-07 | 1.379e-04 | 1.198e-06 | 7.456e-06 | 6.789e-04 | 13 | 4.0% | 2 | 1 | 0 | -93.77 | 0.66 |
| Classic/NZDUSD/M30 | 162 | 7.000e-07 | 2.091e-04 | 6.176e-06 | 1.798e-05 | 1.247e-03 | 3 | 1.9% | 1 | 1 | 0 | 21.48 | 1.17 |
| Classic/NZDUSD/M5 | 922 | 2.860e-08 | 6.958e-05 | 1.341e-06 | 5.396e-06 | 3.364e-04 | 53 | 5.7% | 11 | 5 | 2 | -29.89 | 0.96 |
| Classic/XAUUSD/H1 | 63 | 1.028e-01 | 6.227e+00 | 1.119e-01 | 4.608e-01 | 2.189e+01 | 2 | 3.2% | 1 | 0 | 0 | -6.29 | 0.88 |
| Classic/XAUUSD/H4 | 50 | 1.271e-01 | 8.931e+00 | 1.271e-01 | 1.235e+00 | 3.343e+01 | 1 | 2.0% | 0 | 0 | 0 | -22.05 | 0.50 |
| Classic/XAUUSD/M1 | 983 | 2.884e-03 | 5.695e-01 | 1.631e-02 | 5.125e-02 | 4.494e+00 | 134 | 13.6% | 4 | 0 | 0 | -268.45 | 0.67 |
| Classic/XAUUSD/M15 | 284 | 2.917e-02 | 2.393e+00 | 1.087e-01 | 2.846e-01 | 1.277e+01 | 4 | 1.4% | 2 | 0 | 0 | -51.65 | 0.77 |
| Classic/XAUUSD/M30 | 131 | 1.293e-03 | 2.986e+00 | 1.922e-02 | 2.824e-01 | 1.767e+01 | 4 | 3.1% | 0 | 0 | 0 | -76.58 | 0.33 |
| Classic/XAUUSD/M5 | 911 | 1.238e-03 | 1.304e+00 | 3.536e-02 | 1.217e-01 | 1.176e+01 | 50 | 5.5% | 7 | 1 | 1 | 220.14 | 1.30 |
| ICT/EURUSD/H1 | 4 | 6.183e-04 | 6.299e-04 | 6.183e-04 | 6.183e-04 | 4.450e-03 | 0 | 0.0% | 0 | 0 | 0 | -1.48 | 0.51 |
| ICT/EURUSD/H4 | 1 | 1.912e-03 | 1.912e-03 | 1.912e-03 | 1.912e-03 | 1.912e-03 | 0 | 0.0% | 0 | 0 | 0 | 4.38 | inf |
| ICT/EURUSD/M1 | 82 | 8.063e-06 | 1.418e-04 | 3.533e-05 | 6.833e-05 | 4.801e-04 | 0 | 0.0% | 0 | 0 | 0 | 30.32 | 1.65 |
| ICT/EURUSD/M15 | 14 | 2.300e-04 | 3.732e-04 | 2.300e-04 | 2.720e-04 | 5.988e-04 | 0 | 0.0% | 0 | 0 | 0 | -1.70 | 0.83 |
| ICT/EURUSD/M30 | 33 | 3.712e-04 | 8.153e-04 | 3.712e-04 | 4.134e-04 | 2.398e-03 | 0 | 0.0% | 0 | 0 | 0 | -27.30 | 0.12 |
| ICT/EURUSD/M5 | 136 | 6.387e-05 | 1.010e-03 | 6.416e-05 | 1.759e-04 | 1.011e-03 | 0 | 0.0% | 0 | 0 | 0 | -119.69 | 0.08 |
| ICT/GBPUSD/H1 | 4 | 5.895e-04 | 1.180e-03 | 5.895e-04 | 5.895e-04 | 2.836e-03 | 0 | 0.0% | 0 | 0 | 0 | -1.40 | 0.53 |
| ICT/GBPUSD/H4 | 4 | 1.240e-03 | 2.147e-03 | 1.240e-03 | 1.240e-03 | 8.011e-03 | 0 | 0.0% | 0 | 0 | 0 | -4.00 | 0.00 |
| ICT/GBPUSD/M1 | 96 | 6.195e-05 | 1.698e-04 | 6.291e-05 | 7.407e-05 | 7.805e-04 | 0 | 0.0% | 0 | 0 | 0 | 5.97 | 1.09 |
| ICT/GBPUSD/M15 | 12 | 2.963e-04 | 5.590e-04 | 2.963e-04 | 3.418e-04 | 1.072e-03 | 0 | 0.0% | 0 | 0 | 0 | 3.34 | 1.48 |
| ICT/GBPUSD/M30 | 67 | 6.694e-04 | 2.484e-03 | 7.820e-04 | 8.181e-04 | 3.437e-03 | 0 | 0.0% | 0 | 0 | 0 | 7.81 | 1.16 |
| ICT/GBPUSD/M5 | 53 | 6.976e-05 | 4.409e-04 | 1.003e-04 | 1.372e-04 | 1.030e-03 | 0 | 0.0% | 0 | 0 | 0 | -12.20 | 0.70 |
| ICT/NZDUSD/H1 | 5 | 4.957e-04 | 5.240e-04 | 4.957e-04 | 4.957e-04 | 6.083e-04 | 0 | 0.0% | 0 | 0 | 0 | -2.47 | 0.38 |
| ICT/NZDUSD/H4 | 3 | 1.138e-03 | 1.715e-03 | 1.138e-03 | 1.138e-03 | 1.746e-03 | 0 | 0.0% | 0 | 0 | 0 | -3.00 | 0.00 |
| ICT/NZDUSD/M1 | 114 | 2.882e-05 | 1.227e-04 | 2.911e-05 | 5.310e-05 | 3.171e-04 | 0 | 0.0% | 0 | 0 | 0 | 11.90 | 1.16 |
| ICT/NZDUSD/M15 | 14 | 2.636e-04 | 4.020e-04 | 2.636e-04 | 2.842e-04 | 1.059e-03 | 0 | 0.0% | 0 | 0 | 0 | 7.98 | 2.00 |
| ICT/NZDUSD/M30 | 51 | 3.967e-04 | 5.281e-04 | 3.967e-04 | 4.387e-04 | 1.365e-03 | 0 | 0.0% | 0 | 0 | 0 | -41.84 | 0.13 |
| ICT/NZDUSD/M5 | 64 | 7.714e-05 | 2.606e-04 | 1.237e-04 | 1.402e-04 | 8.303e-04 | 0 | 0.0% | 0 | 0 | 0 | -17.80 | 0.64 |
| ICT/XAUUSD/H1 | 7 | 1.632e+01 | 2.129e+01 | 1.632e+01 | 1.632e+01 | 9.788e+01 | 0 | 0.0% | 0 | 0 | 0 | 1.65 | 1.41 |
| ICT/XAUUSD/H4 | 4 | 4.493e+01 | 5.223e+01 | 4.493e+01 | 4.493e+01 | 6.355e+01 | 0 | 0.0% | 0 | 0 | 0 | -4.00 | 0.00 |
| ICT/XAUUSD/M1 | 92 | 8.203e-01 | 2.715e+00 | 1.189e+00 | 1.300e+00 | 1.731e+01 | 0 | 0.0% | 0 | 0 | 0 | 5.65 | 1.09 |
| ICT/XAUUSD/M15 | 60 | 2.757e+00 | 4.038e+01 | 3.560e+00 | 4.083e+00 | 4.106e+01 | 0 | 0.0% | 0 | 0 | 0 | -5.12 | 0.87 |
| ICT/XAUUSD/M30 | 10 | 7.943e+00 | 1.066e+01 | 7.943e+00 | 7.943e+00 | 1.495e+01 | 0 | 0.0% | 0 | 0 | 0 | 9.64 | 3.41 |
| ICT/XAUUSD/M5 | 58 | 1.834e+00 | 6.116e+00 | 2.136e+00 | 2.779e+00 | 1.851e+01 | 0 | 0.0% | 0 | 0 | 0 | -26.31 | 0.45 |
| SMC/EURUSD/H1 | 14 | 2.167e-04 | 6.748e-04 | 2.167e-04 | 2.572e-04 | 2.660e-03 | 0 | 0.0% | 0 | 0 | 0 | 20.49 | 5.10 |
| SMC/EURUSD/H4 | 9 | 2.581e-04 | 7.529e-04 | 2.581e-04 | 2.581e-04 | 1.781e-03 | 0 | 0.0% | 0 | 0 | 0 | -9.00 | 0.00 |
| SMC/EURUSD/M1 | 541 | 5.044e-06 | 6.253e-05 | 6.065e-06 | 1.155e-05 | 3.501e-04 | 7 | 1.3% | 5 | 0 | 0 | 99.20 | 1.25 |
| SMC/EURUSD/M15 | 386 | 3.826e-05 | 1.516e-04 | 6.899e-05 | 8.051e-05 | 1.772e-03 | 0 | 0.0% | 1 | 1 | 0 | -163.80 | 0.48 |
| SMC/EURUSD/M30 | 123 | 8.887e-05 | 5.030e-04 | 1.077e-04 | 1.801e-04 | 2.108e-03 | 0 | 0.0% | 2 | 1 | 0 | -22.03 | 0.79 |
| SMC/EURUSD/M5 | 635 | 1.091e-05 | 2.287e-04 | 2.015e-05 | 4.062e-05 | 8.605e-04 | 0 | 0.0% | 3 | 0 | 0 | -123.13 | 0.76 |
| SMC/GBPUSD/H1 | 37 | 1.720e-04 | 8.897e-04 | 1.720e-04 | 2.084e-04 | 1.974e-03 | 0 | 0.0% | 0 | 0 | 0 | 20.00 | 1.95 |
| SMC/GBPUSD/H4 | 9 | 2.816e-04 | 1.535e-03 | 2.816e-04 | 2.816e-04 | 8.011e-03 | 0 | 0.0% | 0 | 0 | 0 | -5.84 | 0.27 |
| SMC/GBPUSD/M1 | 658 | 7.513e-06 | 7.026e-05 | 9.694e-06 | 1.392e-05 | 4.931e-04 | 6 | 0.9% | 6 | 0 | 0 | 267.08 | 1.60 |
| SMC/GBPUSD/M15 | 122 | 7.091e-05 | 3.919e-04 | 7.813e-05 | 1.193e-04 | 1.316e-03 | 0 | 0.0% | 2 | 0 | 0 | -16.66 | 0.83 |
| SMC/GBPUSD/M30 | 142 | 1.022e-04 | 2.136e-03 | 1.444e-04 | 2.132e-04 | 3.117e-03 | 0 | 0.0% | 1 | 0 | 0 | -105.98 | 0.21 |
| SMC/GBPUSD/M5 | 476 | 1.562e-05 | 2.100e-04 | 2.210e-05 | 4.355e-05 | 8.815e-04 | 0 | 0.0% | 7 | 1 | 0 | 150.20 | 1.43 |
| SMC/NZDUSD/H1 | 31 | 8.851e-05 | 2.484e-04 | 8.851e-05 | 1.282e-04 | 1.488e-03 | 0 | 0.0% | 0 | 0 | 0 | 21.08 | 1.96 |
| SMC/NZDUSD/H4 | 15 | 2.585e-04 | 8.953e-04 | 2.585e-04 | 4.191e-04 | 3.214e-03 | 0 | 0.0% | 1 | 0 | 0 | 19.27 | 2.93 |
| SMC/NZDUSD/M1 | 555 | 5.039e-06 | 5.414e-05 | 6.403e-06 | 1.077e-05 | 3.266e-04 | 7 | 1.3% | 2 | 0 | 0 | 42.21 | 1.11 |
| SMC/NZDUSD/M15 | 162 | 3.124e-05 | 2.337e-04 | 3.770e-05 | 5.228e-05 | 8.639e-04 | 0 | 0.0% | 0 | 0 | 0 | -7.56 | 0.94 |
| SMC/NZDUSD/M30 | 199 | 4.080e-05 | 1.755e-04 | 4.839e-05 | 5.518e-05 | 1.144e-03 | 0 | 0.0% | 2 | 1 | 0 | -81.10 | 0.53 |
| SMC/NZDUSD/M5 | 439 | 1.924e-05 | 1.427e-04 | 2.210e-05 | 3.169e-05 | 7.873e-04 | 0 | 0.0% | 2 | 0 | 0 | 7.40 | 1.02 |
| SMC/XAUUSD/H1 | 25 | 1.294e+00 | 6.530e+00 | 1.294e+00 | 1.745e+00 | 2.287e+01 | 0 | 0.0% | 1 | 1 | 0 | 32.51 | 3.03 |
| SMC/XAUUSD/H4 | 24 | 1.966e+00 | 2.221e+01 | 1.966e+00 | 4.345e+00 | 7.939e+01 | 0 | 0.0% | 0 | 0 | 0 | -5.89 | 0.67 |
| SMC/XAUUSD/M1 | 763 | 9.301e-02 | 9.350e-01 | 9.544e-02 | 1.338e-01 | 6.067e+00 | 39 | 5.1% | 3 | 0 | 0 | 302.59 | 1.56 |
| SMC/XAUUSD/M15 | 299 | 4.318e-01 | 4.839e+00 | 7.994e-01 | 1.524e+00 | 3.744e+01 | 0 | 0.0% | 25 | 0 | 0 | 445.62 | 4.07 |
| SMC/XAUUSD/M30 | 67 | 8.931e-01 | 8.431e+00 | 9.844e-01 | 1.258e+00 | 1.759e+01 | 0 | 0.0% | 0 | 0 | 0 | -10.66 | 0.79 |
| SMC/XAUUSD/M5 | 521 | 1.216e-01 | 2.384e+00 | 2.066e-01 | 4.031e-01 | 1.870e+01 | 1 | 0.2% | 5 | 1 | 0 | -134.91 | 0.68 |
| SweepDisplacement/EURUSD/H1 | 22 | 7.338e-05 | 6.094e-04 | 7.338e-05 | 1.244e-04 | 4.450e-03 | 0 | 0.0% | 0 | 0 | 0 | 7.95 | 1.57 |
| SweepDisplacement/EURUSD/H4 | 0 | n/a | n/a | n/a | n/a | n/a | 0 | 0.0% | 0 | 0 | 0 | 0.00 | 0.00 |
| SweepDisplacement/EURUSD/M1 | 513 | 6.423e-07 | 8.747e-05 | 1.958e-06 | 1.009e-05 | 5.481e-04 | 21 | 4.1% | 5 | 1 | 0 | -111.29 | 0.74 |
| SweepDisplacement/EURUSD/M15 | 88 | 1.821e-06 | 4.647e-04 | 6.419e-06 | 2.001e-05 | 1.974e-03 | 2 | 2.3% | 1 | 1 | 1 | 37.71 | 1.49 |
| SweepDisplacement/EURUSD/M30 | 58 | 1.045e-05 | 5.690e-04 | 3.592e-05 | 7.886e-05 | 1.813e-03 | 0 | 0.0% | 0 | 0 | 0 | -13.95 | 0.70 |
| SweepDisplacement/EURUSD/M5 | 304 | 1.084e-06 | 2.237e-04 | 9.870e-06 | 4.208e-05 | 1.226e-03 | 2 | 0.7% | 2 | 0 | 0 | -40.44 | 0.83 |
| SweepDisplacement/GBPUSD/H1 | 27 | 5.288e-05 | 7.638e-04 | 5.288e-05 | 8.230e-05 | 3.062e-03 | 0 | 0.0% | 0 | 0 | 0 | -20.60 | 0.18 |
| SweepDisplacement/GBPUSD/H4 | 7 | 1.285e-03 | 2.266e-03 | 1.285e-03 | 1.285e-03 | 2.717e-03 | 0 | 0.0% | 0 | 0 | 0 | -1.40 | 0.72 |
| SweepDisplacement/GBPUSD/M1 | 451 | 4.282e-07 | 1.196e-04 | 1.141e-06 | 1.163e-05 | 7.743e-04 | 17 | 3.8% | 2 | 0 | 0 | -69.98 | 0.81 |
| SweepDisplacement/GBPUSD/M15 | 86 | 1.624e-05 | 5.374e-04 | 1.865e-05 | 4.531e-05 | 2.519e-03 | 0 | 0.0% | 1 | 0 | 0 | 16.49 | 1.25 |
| SweepDisplacement/GBPUSD/M30 | 49 | 3.774e-05 | 7.208e-04 | 3.774e-05 | 6.644e-05 | 2.742e-03 | 0 | 0.0% | 0 | 0 | 0 | -21.13 | 0.48 |
| SweepDisplacement/GBPUSD/M5 | 313 | 1.690e-07 | 2.939e-04 | 1.154e-05 | 3.286e-05 | 1.589e-03 | 3 | 1.0% | 2 | 0 | 0 | -54.65 | 0.78 |
| SweepDisplacement/NZDUSD/H1 | 37 | 2.115e-05 | 5.424e-04 | 2.115e-05 | 1.016e-04 | 1.314e-03 | 0 | 0.0% | 0 | 0 | 0 | -11.99 | 0.61 |
| SweepDisplacement/NZDUSD/H4 | 4 | 5.645e-04 | 7.248e-04 | 5.645e-04 | 5.645e-04 | 1.124e-03 | 0 | 0.0% | 0 | 0 | 0 | -4.00 | 0.00 |
| SweepDisplacement/NZDUSD/M1 | 454 | 1.328e-06 | 8.118e-05 | 5.362e-06 | 1.082e-05 | 3.072e-04 | 6 | 1.3% | 1 | 0 | 0 | -8.54 | 0.97 |
| SweepDisplacement/NZDUSD/M15 | 104 | 4.455e-06 | 3.924e-04 | 1.409e-05 | 5.766e-05 | 2.335e-03 | 1 | 1.0% | 0 | 0 | 0 | -42.77 | 0.49 |
| SweepDisplacement/NZDUSD/M30 | 39 | 2.966e-05 | 5.316e-04 | 2.966e-05 | 6.166e-05 | 1.805e-03 | 0 | 0.0% | 1 | 1 | 1 | 84.07 | 4.82 |
| SweepDisplacement/NZDUSD/M5 | 385 | 5.938e-07 | 2.321e-04 | 4.485e-06 | 2.176e-05 | 9.006e-04 | 7 | 1.8% | 1 | 0 | 0 | -110.47 | 0.64 |
| SweepDisplacement/XAUUSD/H1 | 19 | 3.947e-01 | 1.188e+01 | 3.947e-01 | 2.673e+00 | 4.759e+01 | 0 | 0.0% | 0 | 0 | 0 | -6.41 | 0.57 |
| SweepDisplacement/XAUUSD/H4 | 3 | 2.381e+00 | 9.416e+00 | 2.381e+00 | 2.381e+00 | 9.894e+00 | 0 | 0.0% | 0 | 0 | 0 | -3.00 | 0.00 |
| SweepDisplacement/XAUUSD/M1 | 400 | 1.057e-02 | 1.433e+00 | 3.131e-02 | 2.073e-01 | 6.264e+00 | 16 | 4.0% | 2 | 0 | 0 | -115.34 | 0.64 |
| SweepDisplacement/XAUUSD/M15 | 92 | 9.764e-02 | 5.387e+00 | 1.343e-01 | 4.161e-01 | 3.738e+01 | 1 | 1.1% | 0 | 0 | 0 | -42.05 | 0.46 |
| SweepDisplacement/XAUUSD/M30 | 42 | 6.025e-01 | 8.866e+00 | 6.025e-01 | 1.089e+00 | 5.156e+01 | 0 | 0.0% | 0 | 0 | 0 | -13.62 | 0.61 |
| SweepDisplacement/XAUUSD/M5 | 313 | 2.619e-02 | 3.811e+00 | 5.596e-02 | 2.232e-01 | 3.988e+01 | 9 | 2.9% | 1 | 0 | 0 | -108.40 | 0.58 |

## 10. Tiny-SL Trade Analysis

1066 trades fall in the data-derived `extremely_small` bucket (5.0% of all trades), of which 1092 across all buckets are `sub_precision` (smaller than the symbol's own smallest quotable price increment -- necessarily a subset concentrated in the smaller buckets).

- Win rate in `extremely_small`: 7.1% -- LOWER than every other bucket (Section 5) -- consistent with an SL distance so small that whether price closes on the TP or SL side is dominated by noise rather than the setup's directional edge.
- Despite the lower win rate, `extremely_small` has the highest Profit Factor (5.26) and by far the largest Net R (4217.76) of any bucket, because realized R = planned reward / risk distance, and a very small risk distance mechanically produces a very large R on the rare win (Section 15 examines this relationship directly).

## 11. Extreme-R Trade Analysis

55 winning trades have realized R > 20; 18 have realized R > 50.

- By strategy (R>20): {'Classic': 46, 'SweepDisplacement': 3, 'SMC': 6}
- By symbol (R>20): {'EURUSD': 16, 'GBPUSD': 20, 'XAUUSD': 3, 'NZDUSD': 16}
- By timeframe (R>20): {'M5': 21, 'M1': 22, 'M15': 5, 'M30': 6, 'H1': 1}
- Of the 55 R>20 winners, 11 have a structurally-inverted stop-loss and 30 have a sub-precision SL distance (a trade can be both, neither, or either).

### All winning trades with realized R > 50 (full detail)

| Strategy/Symbol/TF | Opened At | Direction | Entry | SL | TP1 | TP2 | Hit | Realized R | Abs SL Dist | Pip SL Dist | SL Direction |
|---|---|---|---:|---:|---:|---:|---|---:|---:|---:|---|
| Classic/EURUSD/M5 | 2026-05-22T10:20:00+00:00 | SELL | 1.16025 | 1.16025 | 1.15958 | 1.15932 | TP1 | 1894.81 | 3.510e-07 | 0.0035 | correct |
| Classic/EURUSD/M1 | 2026-07-24T04:43:00+00:00 | SELL | 1.13783 | 1.13783 | 1.13778 | 1.13771 | TP1 | 773.32 | 5.948e-08 | 0.0006 | inverted |
| Classic/GBPUSD/M1 | 2026-07-23T20:59:00+00:00 | SELL | 1.33134 | 1.33134 | 1.33129 | 1.33117 | TP2 | 497.19 | 3.419e-07 | 0.0034 | inverted |
| Classic/XAUUSD/M5 | 2025-11-07T07:50:00+00:00 | BUY | 4005.40500 | 4005.40234 | 4006.42500 | 4009.38167 | TP1 | 382.79 | 2.665e-03 | 0.2665 | correct |
| Classic/EURUSD/M1 | 2026-08-25T18:56:00+00:00 | BUY | 1.16731 | 1.16731 | 1.16743 | 1.16752 | TP1 | 198.69 | 5.905e-07 | 0.0059 | inverted |
| Classic/EURUSD/M5 | 2026-04-07T17:25:00+00:00 | BUY | 1.15684 | 1.15683 | 1.15748 | 1.15788 | TP2 | 131.08 | 7.934e-06 | 0.0793 | correct |
| Classic/EURUSD/M5 | 2025-10-24T14:05:00+00:00 | BUY | 1.16242 | 1.16242 | 1.16278 | 1.16369 | TP1 | 114.63 | 3.141e-06 | 0.0314 | inverted |
| Classic/NZDUSD/M1 | 2026-08-17T18:19:00+00:00 | SELL | 0.59011 | 0.59011 | 0.58996 | 0.58987 | TP1 | 104.17 | 1.440e-06 | 0.0144 | correct |
| Classic/EURUSD/M5 | 2026-02-11T05:50:00+00:00 | BUY | 1.19164 | 1.19164 | 1.19195 | 1.19266 | TP1 | 87.62 | 3.538e-06 | 0.0354 | correct |
| SweepDisplacement/EURUSD/M15 | 2026-06-19T20:00:00+00:00 | SELL | 1.14765 | 1.14767 | 1.14571 | 1.14569 | TP2 | 87.08 | 2.255e-05 | 0.2255 | correct |
| Classic/GBPUSD/M15 | 2026-06-23T06:15:00+00:00 | SELL | 1.32404 | 1.32405 | 1.32398 | 1.32323 | TP2 | 82.41 | 9.864e-06 | 0.0986 | correct |
| Classic/NZDUSD/M5 | 2026-05-04T03:40:00+00:00 | BUY | 0.59130 | 0.59129 | 0.59136 | 0.59196 | TP2 | 79.50 | 8.239e-06 | 0.0824 | correct |
| Classic/EURUSD/M1 | 2026-07-24T04:40:00+00:00 | SELL | 1.13798 | 1.13798 | 1.13791 | 1.13786 | TP2 | 71.57 | 1.677e-06 | 0.0168 | inverted |
| Classic/NZDUSD/M5 | 2026-03-17T11:00:00+00:00 | BUY | 0.58375 | 0.58375 | 0.58405 | 0.58446 | TP1 | 67.65 | 4.375e-06 | 0.0438 | correct |
| Classic/GBPUSD/M5 | 2026-06-17T20:55:00+00:00 | SELL | 1.32905 | 1.32907 | 1.32786 | 1.32619 | TP1 | 58.55 | 2.032e-05 | 0.2032 | correct |
| SweepDisplacement/NZDUSD/M30 | 2026-07-13T21:30:00+00:00 | BUY | 0.57460 | 0.57457 | 0.57627 | 0.57746 | TP1 | 56.30 | 2.966e-05 | 0.2966 | correct |
| Classic/GBPUSD/M5 | 2026-07-21T10:35:00+00:00 | SELL | 1.34256 | 1.34257 | 1.34198 | 1.34163 | TP1 | 53.92 | 1.076e-05 | 0.1076 | correct |
| Classic/GBPUSD/M15 | 2026-05-19T23:45:00+00:00 | SELL | 1.33955 | 1.33956 | 1.33915 | 1.33801 | TP1 | 51.91 | 7.775e-06 | 0.0777 | correct |

## 12. SL Generation Source by Strategy

Traced directly from the current strategy implementations (read-only inspection; nothing below was modified). Each subsection answers the audit's 15-point checklist for that strategy.

### Classic (`core/strategies/classic/classic_strategy.py`)

1. Function: `ClassicStrategy.analyze` (lines 89-186).
2. File: `core/strategies/classic/classic_strategy.py`.
3. SL is set at line 148: `stop_loss = (nearest.price - sl_buffer) if BUY else (nearest.price + sl_buffer)`.
4. Inputs: `nearest` (closest Support/Resistance level to current price, from `find_support_resistance_levels`), `current_atr` (ATR(14) on entry-timeframe candles), `SL_BUFFER_ATR_MULTIPLIER = 0.5`.
5. Price level used: an S/R level built by `core/algorithms/trend/support_resistance.py:find_support_resistance_levels`, which clusters ALL historical swing lows into "support" and ALL swing highs into "resistance" **independent of the current price's position relative to that level**.
6. SL is not adjusted after initial generation (no trailing/breakeven logic in the backtest path).
7. No minimum distance exists: after computing `risk_distance = abs(entry - stop_loss)`, the only check is `if risk_distance <= 0: return None` (line 154) -- this rejects an EXACT-zero distance but accepts any distance greater than zero, however small.
8. Spread is not considered (Section 17).
9. ATR is considered (`sl_buffer = current_atr * 0.5`), but only as an offset from `nearest.price`, not as a floor on the final distance from entry.
10. Symbol tick size is not considered (`Symbol.tick_size` is `None` for every symbol in this dataset).
11. No price rounding is applied to `stop_loss` before it is stored.
12. Timeframe affects SL indirectly: ATR and swing points are computed on `context.entry_timeframe.candles`, so a smaller entry timeframe (M1/M5) with a low-volatility ATR reading produces a proportionally smaller `sl_buffer` and swing-cluster tolerance.
13. SL can equal Entry only if `nearest.price - sl_buffer == entry` exactly (a measure-zero case in float arithmetic, and `risk_distance <= 0` would reject the exact-equal case; a value arbitrarily close to it is NOT rejected).
14. **SL CAN cross Entry**: the proximity gate at line 119 only checks `abs(nearest.price - current_price) > current_atr * PROXIMITY_ATR_MULTIPLIER` (1.0x ATR) -- it accepts a "support" level up to 1.0x ATR ABOVE current price for a BUY (or a "resistance" level up to 1.0x ATR below current price for a SELL), which the S/R clustering algorithm can legitimately produce since it labels levels purely by swing type, not by their position relative to the current price. Since `SL_BUFFER_ATR_MULTIPLIER` (0.5) is smaller than `PROXIMITY_ATR_MULTIPLIER` (1.0), a "support" level found more than 0.5x ATR above current price produces `stop_loss = nearest.price - 0.5*ATR` that is STILL above entry -- an inverted SL for a BUY. When the level sits close to exactly 0.5x ATR above price, the same arithmetic produces a near-zero (not inverted) distance instead.
15. Floating-point precision CAN produce near-zero distances in the boundary case described in item 14, but the dominant mechanism observed in this dataset is the geometric one above, not float rounding error itself (the `abs_sl_distance` values found, e.g. 3.5e-7, are consistent with a near-exact arithmetic cancellation of two independently-computed floats -- `nearest.price - sl_buffer` landing extremely close to `entry` -- rather than a rounding artifact of a single value).


### SMC (`core/strategies/smc/smc_strategy.py`)

1. Function: `SMCStrategy.analyze` (lines 80-193).
2. File: `core/strategies/smc/smc_strategy.py`.
3. SL is set at line 142: `stop_loss = ob.zone.low - sl_buffer if BUY else ob.zone.high + sl_buffer`.
4. Inputs: `ob` (the most recent Order Block from `find_order_blocks`), `current_atr`, `SL_BUFFER_ATR_MULTIPLIER = 0.3`.
5. Price level used: `ob.zone.low`/`ob.zone.high` (the Order Block's own price zone).
6. SL is not adjusted after initial generation.
7. No explicit minimum distance; same `risk_distance <= 0` guard as Classic (line 147).
8. Spread is not considered.
9. ATR is considered for the SL buffer (0.3x ATR) and separately for the entry-zone tolerance (`OB_ENTRY_BUFFER_ATR_MULTIPLIER = 0.2`, line 125-126).
10. Symbol tick size is not considered.
11. No price rounding is applied.
12. Timeframe affects SL indirectly via ATR and the Order Block detection window, same as Classic.
13. SL equal to Entry is a measure-zero case, rejected by the `risk_distance <= 0` guard if exact.
14. SL is structurally HARDER to cross for the primary (`in_ob`) entry path: entry is bounded to `[ob.zone.low - 0.2*ATR, ob.zone.high + 0.2*ATR]`, while SL sits at `ob.zone.low - 0.3*ATR` (BUY) -- since the entry-zone buffer (0.2x ATR) is SMALLER than the SL buffer (0.3x ATR), an entry at the extreme low edge of its allowed zone still keeps a minimum ~0.1x ATR of risk distance above the SL. This matches the observed data: SMC has only 3 inverted-SL trades out of 6252 (0.05%). The alternate `in_fvg` entry path (line 127-128) is NOT bounded relative to `ob.zone` at all, since a Fair Value Gap is an independent structure -- this is the plausible source of SMC's rare exceptions, though this audit did not trace an `in_fvg`-triggered SMC trade individually to confirm it.
15. A very small (but correctly-sided) `ob.zone` height, combined with an entry very close to `ob.zone.low`, can still produce a small ATR-scaled buffer as the entire remaining risk distance -- on a low-ATR M1/M5 window this buffer itself can be a very small absolute price value without any float-precision artifact.


### ICT (`core/strategies/ict/ict_strategy.py`)

1. Function: `ICTStrategy.analyze` (lines 78-198).
2. File: `core/strategies/ict/ict_strategy.py`.
3. SL is set at line 147: `stop_loss = swing_low - sl_buffer if BUY else swing_high + sl_buffer`.
4. Inputs: `swing_low`/`swing_high` (the impulse-start and structure-break swing prices), `current_atr`, `SL_BUFFER_ATR_MULTIPLIER = 0.3`.
5. Price level used: the swing point that starts the impulse leg (`_find_impulse_start`).
6. SL is not adjusted after initial generation.
7. No explicit minimum distance; same `risk_distance <= 0` guard (line 149).
8. Spread is not considered.
9. ATR is considered for the SL buffer and the displacement-candle gate.
10. Symbol tick size is not considered.
11. No price rounding is applied.
12. Timeframe affects SL indirectly via ATR and swing detection, same pattern as the other strategies.
13. SL equal to Entry is a measure-zero case, rejected if exact.
14. Entry is bounded to the OTE zone (`zone_ote`, a fixed 62%-79% retracement of `swing_high`-`swing_low`, always strictly between the two swing prices) OR to a matching Fair Value Gap (`in_fvg`, line 124-125) -- the OTE path keeps entry well away from `swing_low` (BUY) by construction, but the FVG path is NOT bounded relative to `swing_low`/`swing_high`, so a FVG located unusually close to (or, in principle, past) the swing extreme could produce a small or inverted distance. This dataset shows ZERO inverted-SL trades for ICT (0 of 988), indicating this potential path did not manifest in practice over this dataset, though it is not structurally excluded by the code.
15. As with SMC, a small `swing_high - swing_low` range on a low-ATR window can produce a small absolute SL buffer without float-precision error being the cause.


### SweepDisplacement (`core/strategies/sweep_displacement/sweep_displacement_strategy.py`)

1. Function: `SweepDisplacementStrategy.analyze` (lines 105-206).
2. File: `core/strategies/sweep_displacement/sweep_displacement_strategy.py`.
3. SL is set at line 163: `stop_loss = sweep_candle.low - sl_buffer if BUY else sweep_candle.high + sl_buffer`.
4. Inputs: `sweep_candle` (the candle that swept a liquidity pool, from `_find_most_recent_sweep`), `current_atr`, `SL_BUFFER_ATR_MULTIPLIER = 0.3`.
5. Price level used: the low/high of the specific candle where a liquidity sweep was detected.
6. SL is not adjusted after initial generation.
7. No explicit minimum distance; same `risk_distance <= 0` guard (line 165).
8. Spread is not considered.
9. ATR is considered for the SL buffer and the displacement-candle gate.
10. Symbol tick size is not considered.
11. No price rounding is applied.
12. Timeframe affects SL indirectly via ATR and the sweep/displacement detection window.
13. SL equal to Entry is a measure-zero case, rejected if exact.
14. **SL CAN cross Entry**: entry is validated only against `in_fvg` (a Fair Value Gap after the displacement) OR `in_displacement_body` (`min(open,close) <= current_price <= max(open,close)` of the DISPLACEMENT candle -- a LATER candle than `sweep_candle`, lines 138-146). Neither check requires the displacement candle's body, or the matching FVG, to stay on the correct side of `sweep_candle.low`/`sweep_candle.high` (the SL anchor). If the displacement candle's body retraces back down to (BUY case) at or below `sweep_candle.low - sl_buffer`, entry ends up at or below the SL level -- inverted. If it retraces to just above that level, the distance is near-zero. This matches the observed data: SweepDisplacement has 952 inverted-SL trades out of 3810 (25.0%), the second-highest rate after Classic.
15. As with the other strategies, a small ATR-scaled buffer on a low-volatility M1/M5 window can independently produce a small (but correctly-sided) absolute distance without float-precision error.

## 13. SL Direction Validation

BUY requires SL < Entry, SELL requires SL > Entry (item 13). Classified independently in this audit from the raw stored Entry/SL/direction, not reused from the R:R audit's own count.

| Group | Trades | Correct | % Correct | Equal | % Equal | Inverted | % Inverted |
|---|---:|---:|---:|---:|---:|---:|---:|
| Global | 21319 | 18096 | 84.9% | 0 | 0.0% | 3223 | 15.1% |

By symbol:

| Group | Trades | Correct | % Correct | Equal | % Equal | Inverted | % Inverted |
|---|---:|---:|---:|---:|---:|---:|---:|
| EURUSD | 5597 | 4777 | 85.3% | 0 | 0.0% | 820 | 14.7% |
| XAUUSD | 5221 | 4436 | 85.0% | 0 | 0.0% | 785 | 15.0% |
| GBPUSD | 5215 | 4389 | 84.2% | 0 | 0.0% | 826 | 15.8% |
| NZDUSD | 5286 | 4494 | 85.0% | 0 | 0.0% | 792 | 15.0% |

By strategy:

| Group | Trades | Correct | % Correct | Equal | % Equal | Inverted | % Inverted |
|---|---:|---:|---:|---:|---:|---:|---:|
| Classic | 10269 | 8001 | 77.9% | 0 | 0.0% | 2268 | 22.1% |
| SMC | 6252 | 6249 | 100.0% | 0 | 0.0% | 3 | 0.0% |
| ICT | 988 | 988 | 100.0% | 0 | 0.0% | 0 | 0.0% |
| SweepDisplacement | 3810 | 2858 | 75.0% | 0 | 0.0% | 952 | 25.0% |

By timeframe:

| Group | Trades | Correct | % Correct | Equal | % Equal | Inverted | % Inverted |
|---|---:|---:|---:|---:|---:|---:|---:|
| M1 | 9012 | 7611 | 84.5% | 0 | 0.0% | 1401 | 15.5% |
| M5 | 7404 | 6245 | 84.3% | 0 | 0.0% | 1159 | 15.7% |
| M15 | 2542 | 2209 | 86.9% | 0 | 0.0% | 333 | 13.1% |
| M30 | 1491 | 1336 | 89.6% | 0 | 0.0% | 155 | 10.4% |
| H1 | 586 | 476 | 81.2% | 0 | 0.0% | 110 | 18.8% |
| H4 | 284 | 219 | 77.1% | 0 | 0.0% | 65 | 22.9% |

3223 trades are inverted globally. Inversion rate is roughly consistent across symbols (14.7%-15.8%), indicating the inversion mechanism is NOT symbol-specific (not a data-quality or price-precision artifact of any one symbol). It is concentrated almost entirely in two strategies: Classic (2268 of 10269, 22.1%) and SweepDisplacement (952 of 3810, 25.0%), while SMC (3 of 6252) and ICT (0 of 988) are rarely or never affected. Section 12 traces the exact code mechanism for each strategy. This independently confirms, with a fresh direct calculation on the raw stored prices, the R:R Distribution Audit's finding that all 3194 SL-hit discrepancies plus the 29 structurally-inverted winning trades it found (3194 + 29 = 3223) sum exactly to this audit's global inverted count.

## 14. Lookahead / Point-in-Time Validation

Checked by reading the actual SL-generation code paths (Section 12) for references to data beyond `context.entry_timeframe.candles`, which is itself already point-in-time sliced to the signal's own `as_of` timestamp by `BacktestEngine`/`AnalysisContext` (fixed and regression-tested in an earlier phase of this project -- see `tests/unit/test_point_in_time_multi_timeframe.py`).

- `core/algorithms/structure/swings.py:find_swing_points` only classifies a swing at index `i` using a window of `lookback` (2) candles on EACH side, entirely within the already-available `candles` list (`range(lookback, n - lookback)`) -- no index ever exceeds `len(candles) - 1`.
- `core/strategies/sweep_displacement/sweep_displacement_strategy.py:_find_most_recent_sweep` scans backward from `len(candles) - 2` (explicitly excluding the current/last candle) -- backward only, no future reference.
- `core/strategies/sweep_displacement/sweep_displacement_strategy.py:_find_displacement_after` scans forward from `sweep_index + 1` to `len(candles)` -- but `candles` is the already point-in-time-sliced series, so `len(candles) - 1` is the CURRENT (signal-time) candle, not a future one; no index beyond the currently available series is ever read.
- `core/algorithms/trend/support_resistance.py:find_support_resistance_levels`, `core/algorithms/structure/order_blocks.py:find_order_blocks`, and `core/algorithms/structure/liquidity.py:find_liquidity_pools` all operate purely on the `swings` list already derived from the point-in-time-sliced candles -- no additional candle indexing beyond what `find_swing_points` already produced.
- All four strategies' `analyze()` methods reference only `candles[-1]`, `candles[-2]`, `atr_values[-1]`, and the already-filtered `swings`/`events`/`order_blocks`/`pools` lists -- no strategy indexes `candles` with a positive offset from the end, and none references `context.higher_timeframe`/`context.middle_timeframe` for SL calculation (SL is derived from entry-timeframe structure only in all four strategies).

**Result: confirmed no lookahead** in any of the SL-generation code paths inspected. The tiny/inverted SL distances found in this audit are not explained by future-data leakage; they are explained by the geometric relationship between the reference price used for SL and the current entry price at signal time (Section 12).

## 15. SL Distance vs Realized R

Winning trades bucketed by pip-normalized SL distance (pooled across symbols; see Section 6's caveat on cross-symbol pip comparability).

| SL Distance Bucket | Winners | Mean R | Median R | P95 R | P99 R | Max R | Gross Winning R |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0-1pips | 1358 | 8.26 | 3.00 | 17.13 | 58.55 | 1894.81 | 11214.90 |
| 1-5pips | 1553 | 2.70 | 2.14 | 5.74 | 9.57 | 20.52 | 4199.77 |
| 5-10pips | 307 | 2.29 | 1.95 | 4.01 | 6.63 | 13.17 | 703.37 |
| 10-25pips | 115 | 3.58 | 2.12 | 9.98 | 17.80 | 22.55 | 412.18 |
| 25-50pips | 118 | 5.21 | 4.90 | 10.26 | 12.74 | 15.95 | 614.68 |
| 50-100pips | 138 | 3.45 | 2.80 | 6.84 | 11.77 | 18.86 | 476.13 |
| >100pips | 891 | 2.80 | 1.97 | 8.24 | 10.19 | 25.34 | 2494.80 |

The 0-1 pip bucket has the highest mean R and the largest share of gross winning R of any bucket. This is consistent with the definitional relationship `realized_R = reward / risk` -- a smaller risk (SL distance) denominator mechanically produces a larger R for a similar or even smaller reward. The data does not distinguish, and this report does not claim, any causal mechanism beyond this arithmetic relationship.

## 16. Planned RR vs Realized R

For the 55 winning trades with realized R > 20: the planned RR matching the actual TP hit (`planned_rr_tp1` for a TP1 hit, `planned_rr_tp2` for a TP2 hit) is available for 55 of them.

- 55 of 55 already have a planned RR > 20 BEFORE the trade was simulated -- for these, the extreme realized R was already present in the plan at signal time (case B in the audit's own terms: a correctly-sided but tiny SL distance, since planned RR = reward / SL distance at signal time, is what makes the PLAN itself extreme).
- 0 of 55 have realized R > 20 while the matching planned RR was NOT already above 20 at signal time -- for these, the extreme value would have emerged only during outcome simulation rather than being present in the plan. None were found in this dataset: every R>20 winner's realized R already matches an equally extreme planned RR.
- Since `TradeOutcome.r_multiple` for a TP1/TP2 hit is stored as EXACTLY `setup.risk_reward_tp1`/`risk_reward_tp2` (`backtesting/engine.py:_simulate_outcome`), realized R for a winning trade is by construction identical to the planned RR for whichever target was hit -- there is no separate 'realized' computation that could diverge from the plan. The extreme values therefore originate entirely at signal time, from the planned-RR calculation itself (`reward_distance / abs(entry - stop_loss)`), not from anything that happens during trade simulation.

## 17. Spread / Cost Limitations

- No spread data exists anywhere in this dataset: `data/market/*.csv` and the generated `data/historical/*.csv` files have no spread column at all (`candle.spread` is always `None`).
- Spread is not used when generating Entry, SL, or TP in any of the four strategies -- all four use `context.current_price` (the current candle's close, per `AnalysisContext`) as `entry`, with no bid/ask spread adjustment anywhere in `analyze()`.
- Spread is not used when validating a trade or computing R: `risk_reward_tp1`/`risk_reward_tp2` (`core/signals/selected_setup.py`) and `BacktestEngine._simulate_outcome` both operate on raw OHLC prices only.
- `ValidatingMarketDataProvider` (the only component in this codebase that reads `max_spread`) is wired only into the live `/analyze` backend path (`backend/dependencies.py`), never into any batch backtest or audit script.
- No spread value is invented or assumed anywhere in this audit.

## 18. Post-Trade Counterfactual Analysis

**POST-TRADE DIAGNOSTIC ONLY -- NOT A STRATEGY CHANGE.** Thresholds are the GLOBAL (all-symbol-pooled) percentiles of absolute SL distance actually observed in this dataset -- not a proposed rule.

| Excluded Below | Threshold (abs) | Trades Removed | Winners Removed | Losses Removed | Remaining Trades | Win Rate | Net R | PF | Expectancy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| P0.1 | 2.387e-07 | 21 | 1 | 20 | 21298 | 21.0% | 2524.51 | 1.15 | 0.1185 |
| P0.5 | 1.119e-06 | 107 | 5 | 102 | 21212 | 21.1% | -2.61 | 1.00 | -0.0001 |
| P1 | 2.039e-06 | 213 | 11 | 202 | 21106 | 21.2% | -183.26 | 0.99 | -0.0087 |
| P5 | 9.892e-06 | 1066 | 102 | 964 | 20253 | 21.6% | -1100.83 | 0.93 | -0.0544 |

**POST-TRADE DIAGNOSTIC ONLY -- NOT A STRATEGY CHANGE.** These figures describe what the already-captured trade list would show under a hypothetical exclusion; no trade was regenerated, and no minimum-SL-distance rule was added to any Strategy.

## 19. Findings

- SL distances span from sub-precision (below the symbol's own smallest quotable price step) to over 9,700 pips (XAUUSD), confirming price-scale differences across symbols must be normalized before comparison (Section 6).
- 1092 of 21319 trades (5.1%) have an SL distance below the symbol's own smallest representable price increment.
- The `extremely_small` bucket, though a minority of trades, holds a Net R (4217.76) larger than the entire Baseline's Net R, while the other three buckets combined are net negative (-939.93).
- SL-direction inversion (3223 trades) is concentrated in Classic and SweepDisplacement, traced in Section 12 to each strategy's own SL-reference-selection code not verifying the reference price's side relative to entry before applying the ATR buffer; SMC and ICT's entry-zone constructions make this far rarer or (for ICT, in this dataset) absent.
- No lookahead was found in any SL-generation code path inspected (Section 14).
- Every winning trade's realized R for R>20 traces to a planned RR that was ALREADY >20 at signal time -- the extremeness is present in the plan, not introduced during outcome simulation (Section 16).
- Counterfactually excluding trades below the P0.5 SL-distance percentile (107 of 21319 trades, 0.5%) is sufficient to turn the global Baseline Net R negative (Section 18) -- a small fraction of trades by count carries a disproportionate share of the measured Net R.

## 20. Conclusions

This section states only what the data and code demonstrate. It contains no ranking, no best/worst/recommended/superior/inferior strategy, and no change was made to any Strategy, Entry, SL, TP, or Filter logic to produce or in response to these findings.

- 1092 trades have an SL distance below the symbol's own smallest quotable price increment; this is a direct, traceable consequence of the SL-reference-selection code described in Section 12, not a data-quality defect in the OHLC dataset itself.
- SL-distance inversion and extreme tininess are concentrated in Classic and SweepDisplacement, and are traced to specific lines of code in each (Section 12), not to any one symbol or timeframe.
- No lookahead was found in the SL-generation code paths inspected.
- The Baseline's positive Net R is concentrated in a small, data-identifiable subset of trades with unusually small SL distance; removing a small fraction of those trades (Section 18) is sufficient to turn the measured Net R negative.

## 21. Answers to the Required Final Questions

1. **Why are some SL distances extremely small?** Because the reference price used to compute SL (a Support/Resistance level for Classic, a sweep candle's high/low for SweepDisplacement) can sit very close to, or on the wrong side of, the current entry price, and the code only rejects an EXACT-zero distance (`risk_distance <= 0`), not a small one (Section 12).
2. **Which strategy logic generates them?** Classic's nearest-Support/Resistance lookup (`classic_strategy.py:113,148`) and SweepDisplacement's post-sweep entry-zone check (`sweep_displacement_strategy.py:138-146,163`); SMC and ICT are far less exposed by construction (Section 12).
3. **Are they concentrated in specific symbols?** No -- the inversion rate is roughly consistent (14.7%-15.8%) across EURUSD, XAUUSD, GBPUSD, and NZDUSD (Section 13).
4. **Are they concentrated in specific timeframes?** Mildly -- inversion ranges from 10.4% (M30) to 22.9% (H4) across timeframes, with no single timeframe standing out as dominant (Section 13).
5. **Are they concentrated in specific strategies?** Yes -- Classic and SweepDisplacement account for the large majority; SMC is rare (3 trades) and ICT has none in this dataset (Section 13).
6. **Valid market-structure logic or implementation issue?** An implementation gap: the underlying market-structure concepts (S/R levels, liquidity sweeps) are valid, but the code that turns a selected reference level into an SL price does not verify the reference sits on the geometrically correct side of entry before applying the buffer (Section 12).
7. **Are any extreme-R trades caused by an incorrect SL?** Not in the sense of an SL-multiple-formula error: the R:R Distribution Audit found 0 discrepancies between the stored `r_multiple` and an independently recomputed value for every winning trade. Some ARE caused by a structurally-inverted SL (11 of the 55 R>20 winners; Section 11), which is itself a distinct implementation-traceable condition, not a calculation bug.
8. **Are any extreme-R trades caused by a correctly-sided but nearly-zero SL distance?** Yes -- 44 of the 55 R>20 winners (and 13 of the 18 R>50 winners) have a correctly-sided SL with an extremely small distance (Section 11).
9. **Is there evidence of lookahead in SL generation?** No -- confirmed no lookahead in every SL-generation code path inspected (Section 14).
10. **How much of Baseline Net R depends on these tiny-SL trades?** The `extremely_small` bucket alone has a Net R of 4217.76 against a global Baseline Net R of approximately 3277.83 (R:R Distribution Audit) -- i.e. more than the entire measured Baseline edge; excluding trades below just the P0.5 SL-distance percentile (107 trades) is enough to turn Net R negative (Section 18).
11. **Data issue, calculation issue, strategy behavior, or unresolved design decision?** Strategy behavior arising from an unresolved design decision: each strategy's SL-generation code only guards against an exact-zero risk distance, not a small or wrong-signed one (Section 12) -- this is neither a data-quality defect nor an R-multiple calculation bug (both independently ruled out by this and the prior audit).
12. **What exact code path creates the SL?** `classic_strategy.py:148`, `smc_strategy.py:142`, `ict_strategy.py:147`, and `sweep_displacement_strategy.py:163` -- see Section 12 for the full trace of each.
