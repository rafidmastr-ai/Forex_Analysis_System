# ROBUSTNESS BACKTEST REPORT

## 1. Test Objective

Tests whether the current-version Baseline's edge (data/optimization_results/m1_full_backtest.json, the 96-run current-version backtest) is real and stable, or depends heavily on a small number of trades with an extreme realized R:R. This is descriptive only -- no ranking, no "best" strategy, no Optimization or parameter tuning was performed at any point in this test.

## 2. Baseline Configuration

- Run status: 96/96 successful, 0 failed, 93.6 minutes total.
- Baseline reproducibility check: PASSED (0 mismatches across all cells).
- Dataset source: data/market/{SYMBOL}.csv
- Strategies: Classic, SMC, ICT, SweepDisplacement
- Symbols: EURUSD, XAUUSD, GBPUSD, NZDUSD
- Timeframes: M1, M5, M15, M30, H1, H4
- Timeframe mapping (entry_mapping): `{"M1": {"higher": "M15", "middle": "M5"}, "M5": {"higher": "H1", "middle": "M15"}, "M15": {"higher": "H4", "middle": "H1"}, "M30": {"higher": "H4", "middle": "H1"}, "H1": {"higher": "H4", "middle": "H1"}, "H4": {"higher": "H4", "middle": "H4"}}`
- Lookback configuration: `{"higher": 200, "middle": 300, "entry": 500}`
- Same-candle policy: SL checked before TP1/TP2 whenever both would be touched within the same OHLC candle (backtesting/engine.py:_simulate_outcome) -- a deterministic, conservative convention; intrabar order cannot be established from OHLC data.
- Baseline reference file: `data/optimization_results/m1_full_backtest.json`
- Filters, min_confidence, minimum R:R, Entry/TP/SL/Strategy logic, weights: identical, unchanged production wiring -- see scripts/robustness_backtest.py and scripts/m1_full_backtest.py.

**ROBUSTNESS BACKTEST COMPLETE**

## 3. Cap Methodology

Each mode's cap is applied to the REALIZED R (`TradeOutcome.r_multiple`, never `planned_rr_tp1`/`planned_rr_tp2`) of each trade, strictly AFTER BacktestEngine has already decided that trade's outcome (hit/opened_at/closed_at/setup are always identical across modes). `capped_r = min(realized_r, cap)`. A losing trade's -1.0R and an unresolved trade's 0.0R are always <= any positive cap here, so they pass through every mode completely unchanged -- only a winning trade whose realized R already exceeds the cap is reduced, and only down to the cap value; its Outcome (TP1/TP2), Entry, SL, and TP are never altered. Modes: Baseline, Cap_5.0, Cap_4.0, Cap_3.0, Cap_2.5, Cap_2.0. Proven by 55 regression tests (tests/unit/test_robustness.py) -- see section 11.

## 4. Global Results (all 96 cells combined, per mode)

| Mode | Trades | Wins | Losses | Win Rate | Net R | PF | Expectancy | Max DD range | Positive Cells | Negative Cells |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| Baseline | 21319 | 4480 | 16838 | 21.0% | 3277.83 | 1.19 | 0.15 | 0.00-283.88 | 36/96 | 59 |
| Cap_5.0 | 21319 | 4480 | 16838 | 21.0% | -4391.82 | 0.74 | -0.21 | 0.00-345.92 | 23/96 | 72 |
| Cap_4.0 | 21319 | 4480 | 16838 | 21.0% | -5203.96 | 0.69 | -0.24 | 0.00-379.41 | 22/96 | 73 |
| Cap_3.0 | 21319 | 4480 | 16838 | 21.0% | -6362.57 | 0.62 | -0.30 | 0.00-448.66 | 19/96 | 76 |
| Cap_2.5 | 21319 | 4480 | 16838 | 21.0% | -7239.05 | 0.57 | -0.34 | 0.00-496.05 | 16/96 | 79 |
| Cap_2.0 | 21319 | 4480 | 16838 | 21.0% | -8410.18 | 0.50 | -0.39 | 0.00-553.01 | 12/96 | 83 |

## 5. Strategy Results (24 cells per strategy, per mode)

### Classic

| Mode | Trades | Wins | Losses | Win Rate | Net R | PF | Expectancy | Max DD range | Positive Cells | Negative Cells |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| Baseline | 10269 | 1843 | 8425 | 17.9% | 3370.22 | 1.40 | 0.33 | 10.00-283.88 | 10/24 | 14 |
| Cap_5.0 | 10269 | 1843 | 8425 | 17.9% | -2952.68 | 0.65 | -0.29 | 11.86-345.92 | 0/24 | 24 |
| Cap_4.0 | 10269 | 1843 | 8425 | 17.9% | -3368.97 | 0.60 | -0.33 | 13.07-379.41 | 0/24 | 24 |
| Cap_3.0 | 10269 | 1843 | 8425 | 17.9% | -3954.94 | 0.53 | -0.39 | 17.07-448.66 | 0/24 | 24 |
| Cap_2.5 | 10269 | 1843 | 8425 | 17.9% | -4369.26 | 0.48 | -0.43 | 19.33-496.05 | 0/24 | 24 |
| Cap_2.0 | 10269 | 1843 | 8425 | 17.9% | -4904.66 | 0.42 | -0.48 | 22.68-553.01 | 0/24 | 24 |

### SMC

| Mode | Trades | Wins | Losses | Win Rate | Net R | PF | Expectancy | Max DD range | Positive Cells | Negative Cells |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| Baseline | 6252 | 1619 | 4633 | 25.9% | 741.10 | 1.16 | 0.12 | 3.00-247.49 | 12/24 | 12 |
| Cap_5.0 | 6252 | 1619 | 4633 | 25.9% | -198.44 | 0.96 | -0.03 | 3.00-247.49 | 11/24 | 13 |
| Cap_4.0 | 6252 | 1619 | 4633 | 25.9% | -491.46 | 0.89 | -0.08 | 3.00-247.49 | 10/24 | 14 |
| Cap_3.0 | 6252 | 1619 | 4633 | 25.9% | -901.76 | 0.81 | -0.14 | 3.00-256.00 | 8/24 | 16 |
| Cap_2.5 | 6252 | 1619 | 4633 | 25.9% | -1209.29 | 0.74 | -0.19 | 3.00-277.80 | 6/24 | 18 |
| Cap_2.0 | 6252 | 1619 | 4633 | 25.9% | -1616.34 | 0.65 | -0.26 | 3.00-307.52 | 4/24 | 20 |

### ICT

| Mode | Trades | Wins | Losses | Win Rate | Net R | PF | Expectancy | Max DD range | Positive Cells | Negative Cells |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| Baseline | 988 | 253 | 735 | 25.6% | -179.68 | 0.76 | -0.18 | 0.00-119.88 | 10/24 | 14 |
| Cap_5.0 | 988 | 253 | 735 | 25.6% | -187.88 | 0.74 | -0.19 | 0.00-119.88 | 10/24 | 14 |
| Cap_4.0 | 988 | 253 | 735 | 25.6% | -192.01 | 0.74 | -0.19 | 0.00-119.88 | 10/24 | 14 |
| Cap_3.0 | 988 | 253 | 735 | 25.6% | -203.24 | 0.72 | -0.21 | 0.00-119.88 | 9/24 | 15 |
| Cap_2.5 | 988 | 253 | 735 | 25.6% | -228.71 | 0.69 | -0.23 | 0.00-119.88 | 8/24 | 16 |
| Cap_2.0 | 988 | 253 | 735 | 25.6% | -273.84 | 0.63 | -0.28 | 0.00-119.97 | 6/24 | 18 |

### SweepDisplacement

| Mode | Trades | Wins | Losses | Win Rate | Net R | PF | Expectancy | Max DD range | Positive Cells | Negative Cells |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| Baseline | 3810 | 765 | 3045 | 20.1% | -653.82 | 0.79 | -0.17 | 0.00-158.86 | 4/24 | 19 |
| Cap_5.0 | 3810 | 765 | 3045 | 20.1% | -1052.81 | 0.65 | -0.28 | 0.00-187.94 | 2/24 | 21 |
| Cap_4.0 | 3810 | 765 | 3045 | 20.1% | -1151.52 | 0.62 | -0.30 | 0.00-199.90 | 2/24 | 21 |
| Cap_3.0 | 3810 | 765 | 3045 | 20.1% | -1302.63 | 0.57 | -0.34 | 0.00-218.89 | 2/24 | 21 |
| Cap_2.5 | 3810 | 765 | 3045 | 20.1% | -1431.79 | 0.53 | -0.38 | 0.00-235.29 | 2/24 | 21 |
| Cap_2.0 | 3810 | 765 | 3045 | 20.1% | -1615.35 | 0.47 | -0.42 | 0.00-258.52 | 2/24 | 21 |

## 6. Timeframe Results (16 cells per timeframe, per mode)

### M1

| Mode | Trades | Wins | Losses | Win Rate | Net R | PF | Expectancy | Max DD range | Positive Cells | Negative Cells |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| Baseline | 9012 | 2056 | 6956 | 22.8% | 1935.37 | 1.28 | 0.21 | 12.00-283.88 | 11/16 | 5 |
| Cap_5.0 | 9012 | 2056 | 6956 | 22.8% | -1155.40 | 0.83 | -0.13 | 12.00-334.03 | 8/16 | 8 |
| Cap_4.0 | 9012 | 2056 | 6956 | 22.8% | -1549.48 | 0.78 | -0.17 | 12.00-378.92 | 7/16 | 9 |
| Cap_3.0 | 9012 | 2056 | 6956 | 22.8% | -2091.84 | 0.70 | -0.23 | 12.00-448.66 | 5/16 | 11 |
| Cap_2.5 | 9012 | 2056 | 6956 | 22.8% | -2507.11 | 0.64 | -0.28 | 12.00-496.05 | 4/16 | 12 |
| Cap_2.0 | 9012 | 2056 | 6956 | 22.8% | -3070.43 | 0.56 | -0.34 | 12.49-553.01 | 1/16 | 15 |

### M5

| Mode | Trades | Wins | Losses | Win Rate | Net R | PF | Expectancy | Max DD range | Positive Cells | Negative Cells |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| Baseline | 7404 | 1416 | 5988 | 19.1% | 1621.18 | 1.27 | 0.22 | 14.16-215.02 | 5/16 | 11 |
| Cap_5.0 | 7404 | 1416 | 5988 | 19.1% | -2034.08 | 0.66 | -0.27 | 14.16-345.92 | 1/16 | 15 |
| Cap_4.0 | 7404 | 1416 | 5988 | 19.1% | -2278.56 | 0.62 | -0.31 | 14.55-379.41 | 1/16 | 15 |
| Cap_3.0 | 7404 | 1416 | 5988 | 19.1% | -2651.57 | 0.56 | -0.36 | 16.06-427.39 | 0/16 | 16 |
| Cap_2.5 | 7404 | 1416 | 5988 | 19.1% | -2934.37 | 0.51 | -0.40 | 17.06-460.17 | 0/16 | 16 |
| Cap_2.0 | 7404 | 1416 | 5988 | 19.1% | -3307.85 | 0.45 | -0.45 | 18.44-501.02 | 0/16 | 16 |

### M15

| Mode | Trades | Wins | Losses | Win Rate | Net R | PF | Expectancy | Max DD range | Positive Cells | Negative Cells |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| Baseline | 2542 | 573 | 1969 | 22.5% | 91.44 | 1.05 | 0.04 | 3.00-247.49 | 6/16 | 10 |
| Cap_5.0 | 2542 | 573 | 1969 | 22.5% | -489.76 | 0.75 | -0.19 | 3.00-247.49 | 3/16 | 13 |
| Cap_4.0 | 2542 | 573 | 1969 | 22.5% | -585.99 | 0.70 | -0.23 | 3.00-247.49 | 3/16 | 13 |
| Cap_3.0 | 2542 | 573 | 1969 | 22.5% | -715.20 | 0.64 | -0.28 | 3.00-247.49 | 3/16 | 13 |
| Cap_2.5 | 2542 | 573 | 1969 | 22.5% | -805.02 | 0.59 | -0.32 | 3.00-247.49 | 3/16 | 13 |
| Cap_2.0 | 2542 | 573 | 1969 | 22.5% | -925.81 | 0.53 | -0.36 | 3.00-247.49 | 3/16 | 13 |

### M30

| Mode | Trades | Wins | Losses | Win Rate | Net R | PF | Expectancy | Max DD range | Positive Cells | Negative Cells |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| Baseline | 1491 | 256 | 1235 | 17.2% | -281.40 | 0.77 | -0.19 | 4.00-117.70 | 5/16 | 11 |
| Cap_5.0 | 1491 | 256 | 1235 | 17.2% | -530.59 | 0.57 | -0.36 | 4.00-120.13 | 3/16 | 13 |
| Cap_4.0 | 1491 | 256 | 1235 | 17.2% | -571.80 | 0.54 | -0.38 | 4.00-121.33 | 3/16 | 13 |
| Cap_3.0 | 1491 | 256 | 1235 | 17.2% | -633.83 | 0.49 | -0.43 | 4.00-123.33 | 3/16 | 13 |
| Cap_2.5 | 1491 | 256 | 1235 | 17.2% | -686.28 | 0.44 | -0.46 | 4.00-124.84 | 2/16 | 14 |
| Cap_2.0 | 1491 | 256 | 1235 | 17.2% | -754.41 | 0.39 | -0.51 | 4.00-127.59 | 2/16 | 14 |

### H1

| Mode | Trades | Wins | Losses | Win Rate | Net R | PF | Expectancy | Max DD range | Positive Cells | Negative Cells |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| Baseline | 586 | 137 | 448 | 23.4% | 13.37 | 1.03 | 0.02 | 3.00-40.26 | 7/16 | 9 |
| Cap_5.0 | 586 | 137 | 448 | 23.4% | -55.94 | 0.88 | -0.10 | 3.00-40.52 | 6/16 | 10 |
| Cap_4.0 | 586 | 137 | 448 | 23.4% | -84.14 | 0.81 | -0.14 | 3.00-43.29 | 6/16 | 10 |
| Cap_3.0 | 586 | 137 | 448 | 23.4% | -123.67 | 0.72 | -0.21 | 3.00-47.29 | 6/16 | 10 |
| Cap_2.5 | 586 | 137 | 448 | 23.4% | -152.40 | 0.66 | -0.26 | 3.00-51.24 | 5/16 | 11 |
| Cap_2.0 | 586 | 137 | 448 | 23.4% | -188.51 | 0.58 | -0.32 | 3.00-55.72 | 5/16 | 11 |

### H4

| Mode | Trades | Wins | Losses | Win Rate | Net R | PF | Expectancy | Max DD range | Positive Cells | Negative Cells |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| Baseline | 284 | 42 | 242 | 14.8% | -102.13 | 0.58 | -0.36 | 0.00-32.28 | 2/16 | 13 |
| Cap_5.0 | 284 | 42 | 242 | 14.8% | -126.05 | 0.48 | -0.44 | 0.00-32.28 | 2/16 | 13 |
| Cap_4.0 | 284 | 42 | 242 | 14.8% | -133.99 | 0.45 | -0.47 | 0.00-33.12 | 2/16 | 13 |
| Cap_3.0 | 284 | 42 | 242 | 14.8% | -146.46 | 0.39 | -0.52 | 0.00-34.12 | 2/16 | 13 |
| Cap_2.5 | 284 | 42 | 242 | 14.8% | -153.87 | 0.36 | -0.54 | 0.00-34.62 | 2/16 | 13 |
| Cap_2.0 | 284 | 42 | 242 | 14.8% | -163.18 | 0.33 | -0.57 | 0.00-35.61 | 1/16 | 14 |

## 7. Symbol Results (24 cells per symbol, per mode)

### EURUSD

| Mode | Trades | Wins | Losses | Win Rate | Net R | PF | Expectancy | Max DD range | Positive Cells | Negative Cells |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| Baseline | 5597 | 1047 | 4550 | 18.7% | 2337.01 | 1.51 | 0.42 | 0.00-247.49 | 8/24 | 15 |
| Cap_5.0 | 5597 | 1047 | 4550 | 18.7% | -1615.56 | 0.64 | -0.29 | 0.00-345.92 | 5/24 | 18 |
| Cap_4.0 | 5597 | 1047 | 4550 | 18.7% | -1812.71 | 0.60 | -0.32 | 0.00-379.41 | 5/24 | 18 |
| Cap_3.0 | 5597 | 1047 | 4550 | 18.7% | -2097.01 | 0.54 | -0.37 | 0.00-448.66 | 4/24 | 19 |
| Cap_2.5 | 5597 | 1047 | 4550 | 18.7% | -2308.13 | 0.49 | -0.41 | 0.00-496.05 | 4/24 | 19 |
| Cap_2.0 | 5597 | 1047 | 4550 | 18.7% | -2579.99 | 0.43 | -0.46 | 0.00-553.01 | 4/24 | 19 |

### XAUUSD

| Mode | Trades | Wins | Losses | Win Rate | Net R | PF | Expectancy | Max DD range | Positive Cells | Negative Cells |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| Baseline | 5221 | 1167 | 4054 | 22.4% | 117.09 | 1.03 | 0.02 | 3.00-283.88 | 7/24 | 17 |
| Cap_5.0 | 5221 | 1167 | 4054 | 22.4% | -874.59 | 0.78 | -0.17 | 3.00-333.10 | 6/24 | 18 |
| Cap_4.0 | 5221 | 1167 | 4054 | 22.4% | -1088.40 | 0.73 | -0.21 | 3.00-363.84 | 6/24 | 18 |
| Cap_3.0 | 5221 | 1167 | 4054 | 22.4% | -1372.48 | 0.66 | -0.26 | 3.00-410.14 | 6/24 | 18 |
| Cap_2.5 | 5221 | 1167 | 4054 | 22.4% | -1590.12 | 0.61 | -0.30 | 3.00-444.12 | 5/24 | 19 |
| Cap_2.0 | 5221 | 1167 | 4054 | 22.4% | -1876.78 | 0.54 | -0.36 | 3.00-489.37 | 4/24 | 20 |

### GBPUSD

| Mode | Trades | Wins | Losses | Win Rate | Net R | PF | Expectancy | Max DD range | Positive Cells | Negative Cells |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| Baseline | 5215 | 1142 | 4072 | 21.9% | 878.34 | 1.22 | 0.17 | 3.00-111.05 | 11/24 | 13 |
| Cap_5.0 | 5215 | 1142 | 4072 | 21.9% | -786.45 | 0.81 | -0.15 | 3.00-277.10 | 6/24 | 18 |
| Cap_4.0 | 5215 | 1142 | 4072 | 21.9% | -1012.67 | 0.75 | -0.19 | 3.00-312.10 | 6/24 | 18 |
| Cap_3.0 | 5215 | 1142 | 4072 | 21.9% | -1335.84 | 0.67 | -0.26 | 3.00-362.90 | 4/24 | 20 |
| Cap_2.5 | 5215 | 1142 | 4072 | 21.9% | -1577.01 | 0.61 | -0.30 | 3.00-399.32 | 3/24 | 21 |
| Cap_2.0 | 5215 | 1142 | 4072 | 21.9% | -1901.58 | 0.53 | -0.36 | 3.00-456.08 | 2/24 | 22 |

### NZDUSD

| Mode | Trades | Wins | Losses | Win Rate | Net R | PF | Expectancy | Max DD range | Positive Cells | Negative Cells |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| Baseline | 5286 | 1124 | 4162 | 21.3% | -54.61 | 0.99 | -0.01 | 3.00-121.25 | 10/24 | 14 |
| Cap_5.0 | 5286 | 1124 | 4162 | 21.3% | -1115.22 | 0.73 | -0.21 | 3.00-325.57 | 6/24 | 18 |
| Cap_4.0 | 5286 | 1124 | 4162 | 21.3% | -1290.18 | 0.69 | -0.24 | 3.00-361.97 | 5/24 | 19 |
| Cap_3.0 | 5286 | 1124 | 4162 | 21.3% | -1557.23 | 0.63 | -0.29 | 3.00-412.89 | 5/24 | 19 |
| Cap_2.5 | 5286 | 1124 | 4162 | 21.3% | -1763.80 | 0.58 | -0.33 | 3.00-447.38 | 4/24 | 20 |
| Cap_2.0 | 5286 | 1124 | 4162 | 21.3% | -2051.83 | 0.51 | -0.39 | 3.00-489.37 | 2/24 | 22 |

## 8. Sensitivity Analysis

How Net R, PF, and Expectancy change from Baseline through each cap, per strategy (24-cell combined figures, exact recombination as described above).

### Net R

| Strategy | Baseline | Cap 5.0 | Cap 4.0 | Cap 3.0 | Cap 2.5 | Cap 2.0 |
|---|---:|---:|---:|---:|---:|---:|
| Classic | 3370.22 | -2952.68 | -3368.97 | -3954.94 | -4369.26 | -4904.66 |
| SMC | 741.10 | -198.44 | -491.46 | -901.76 | -1209.29 | -1616.34 |
| ICT | -179.68 | -187.88 | -192.01 | -203.24 | -228.71 | -273.84 |
| SweepDisplacement | -653.82 | -1052.81 | -1151.52 | -1302.63 | -1431.79 | -1615.35 |

### Profit Factor

| Strategy | Baseline | Cap 5.0 | Cap 4.0 | Cap 3.0 | Cap 2.5 | Cap 2.0 |
|---|---:|---:|---:|---:|---:|---:|
| Classic | 1.40 | 0.65 | 0.60 | 0.53 | 0.48 | 0.42 |
| SMC | 1.16 | 0.96 | 0.89 | 0.81 | 0.74 | 0.65 |
| ICT | 0.76 | 0.74 | 0.74 | 0.72 | 0.69 | 0.63 |
| SweepDisplacement | 0.79 | 0.65 | 0.62 | 0.57 | 0.53 | 0.47 |

### Expectancy

| Strategy | Baseline | Cap 5.0 | Cap 4.0 | Cap 3.0 | Cap 2.5 | Cap 2.0 |
|---|---:|---:|---:|---:|---:|---:|
| Classic | 0.33 | -0.29 | -0.33 | -0.39 | -0.43 | -0.48 |
| SMC | 0.12 | -0.03 | -0.08 | -0.14 | -0.19 | -0.26 |
| ICT | -0.18 | -0.19 | -0.19 | -0.21 | -0.23 | -0.28 |
| SweepDisplacement | -0.17 | -0.28 | -0.30 | -0.34 | -0.38 | -0.42 |

## 9. R-Multiple Dependency

Per-cell classification (not a trading recommendation -- a statistical description of this test's own numbers). Method: comparing each cell's Baseline Net R to its Cap_3.0 Net R. If Baseline Net R <= 0, the concept doesn't apply ("N/A (baseline non-positive)"). Otherwise, if Cap_3.0 Net R <= 0, or Cap_3.0 Net R retains less than 50% of Baseline Net R, the cell is tagged "High R-Multiple Sensitivity"; otherwise "Low R-Multiple Sensitivity".

| Classification | Count (of 96) |
|---|---:|
| High R-Multiple Sensitivity | 24 |
| Low R-Multiple Sensitivity | 12 |
| N/A (baseline non-positive) | 60 |

Cells tagged "High R-Multiple Sensitivity":

| Strategy | Symbol | Timeframe | Baseline Net R | Cap 3.0 Net R | Retained Fraction |
|---|---|---|---:|---:|---:|
| Classic | EURUSD | M1 | 913.92 | -447.30 | -48.9% |
| Classic | EURUSD | M5 | 1998.29 | -421.83 | -21.1% |
| Classic | XAUUSD | M5 | 220.14 | -311.71 | -141.6% |
| Classic | GBPUSD | M1 | 640.82 | -332.79 | -51.9% |
| Classic | GBPUSD | M5 | 23.02 | -342.55 | -1487.8% |
| Classic | GBPUSD | M15 | 55.44 | -105.72 | -190.7% |
| Classic | GBPUSD | M30 | 54.14 | -37.41 | -69.1% |
| Classic | NZDUSD | M1 | 189.31 | -362.34 | -191.4% |
| Classic | NZDUSD | M30 | 21.48 | -32.63 | -151.9% |
| Classic | NZDUSD | H1 | 11.68 | -15.00 | -128.4% |
| SMC | EURUSD | M1 | 99.20 | -33.83 | -34.1% |
| SMC | XAUUSD | M1 | 302.59 | 28.86 | 9.5% |
| SMC | XAUUSD | M15 | 445.62 | 174.14 | 39.1% |
| SMC | XAUUSD | H1 | 32.51 | 6.31 | 19.4% |
| SMC | GBPUSD | M1 | 267.08 | 57.19 | 21.4% |
| SMC | GBPUSD | M5 | 150.20 | -28.50 | -19.0% |
| SMC | NZDUSD | M1 | 42.21 | -43.93 | -104.1% |
| SMC | NZDUSD | M5 | 7.40 | -49.14 | -663.7% |
| SMC | NZDUSD | H1 | 21.08 | 2.63 | 12.5% |
| SMC | NZDUSD | H4 | 19.27 | 2.12 | 11.0% |
| ICT | GBPUSD | M1 | 5.97 | -2.72 | -45.5% |
| SweepDisplacement | EURUSD | M15 | 37.71 | -50.07 | -132.8% |
| SweepDisplacement | GBPUSD | M15 | 16.49 | -19.75 | -119.8% |
| SweepDisplacement | NZDUSD | M30 | 84.07 | 17.00 | 20.2% |

## 10. Stability Analysis

Cells (of 96) with Net R > 0, per mode:

| Mode | Positive Cells (/96) |
|---|---:|
| Baseline | 36/96 |
| Cap_5.0 | 23/96 |
| Cap_4.0 | 22/96 |
| Cap_3.0 | 19/96 |
| Cap_2.5 | 16/96 |
| Cap_2.0 | 12/96 |

Per strategy (of 24):

| Strategy | Baseline | Cap_5.0 | Cap_4.0 | Cap_3.0 | Cap_2.5 | Cap_2.0 |
|---|---:|---:|---:|---:|---:|---:|
| Classic | 10/24 | 0/24 | 0/24 | 0/24 | 0/24 | 0/24 |
| SMC | 12/24 | 11/24 | 10/24 | 8/24 | 6/24 | 4/24 |
| ICT | 10/24 | 10/24 | 10/24 | 9/24 | 8/24 | 6/24 |
| SweepDisplacement | 4/24 | 2/24 | 2/24 | 2/24 | 2/24 | 2/24 |

## 11. Regression Test Results

55 regression tests in `tests/unit/test_robustness.py` (part of the project's 290-test suite, all passing) directly verify: Baseline is an exact identity transform; trade count, win rate, and TP1/TP2/SL counts are invariant across every cap; a cap never increases Net R or Average Winning R; a cap never changes Average Losing R (always exactly -1.0); Cap 2.0/3.0 never produce a winning trade above their own cap; Outcome, Entry, SL, and TP are never altered by any cap; no NaN is ever introduced. ruff and mypy (`core adapters backtesting backend`) are clean.

## 12. Limitations

- Max Drawdown is reported per-cell only in rollup tables (as a min-max range across the combined cells) -- it is sequence-dependent and not meaningfully additive across independent Strategy x Symbol x Timeframe runs, unlike Net R, wins, and losses.
- The "High/Low R-Multiple Sensitivity" classification uses Cap 3.0 as its single reference point (a mid-range cap among the five tested); a cell's status at other caps can differ and is fully visible in the per-strategy/per-symbol/per-timeframe sensitivity tables above.
- This test does not establish causality for WHY a given cell is outlier-dependent (e.g. which specific trades) -- data/optimization_results/robustness_backtest.json retains full per-cell, per-mode metrics for further analysis if needed.
- OHLC-only data, no tick data, same-candle SL-before-TP convention -- identical to the Baseline's own already-disclosed limitations (see M1_DATA_QUALITY_REPORT.md and FINAL_BACKTEST_INDEX.md).

## 13. Factual Conclusion

- Global Baseline: 21319 trades, Net R = 3277.83, PF = 1.19, 36/96 cells positive.
- Global Cap 2.0: Net R = -8410.18, PF = 0.50, 12/96 cells positive.
- Of 96 cells with a positive Baseline Net R, 24 are classified High R-Multiple Sensitivity, 12 Low R-Multiple Sensitivity (60 cells had a non-positive Baseline Net R, to which this classification does not apply).

This is a factual summary of this test's own numbers only. It contains no ranking, no "best" or "recommended" strategy/symbol/timeframe/cap, and no change was made to any Strategy, Weight, Filter, Threshold, Entry, TP, or SL logic to produce or in response to these results.
