# Strategy Research Registry

Every trading idea investigated during the Research & Strategy Development
phase, whether implemented or not. **Nothing here is deleted** — an entry
that is never implemented, or implemented and rejected, stays in this file
with its reasoning. No published result below is treated as proof that an
idea works in our system; each is a **testable hypothesis**, and its
`Status` reflects only what our own Point-in-Time backtests on real
EURUSD/XAUUSD MT5 data actually showed.

**A note on sourcing**: `WebFetch` (direct page retrieval) is blocked by
this environment's network egress policy for every domain tested,
including SSRN, arXiv mirrors, Wikipedia, StatOasis and BuildAlpha — this
is an environment constraint, not a choice. Research below relies on
`WebSearch`'s synthesized summaries of these sources, which do surface
concrete figures (sample sizes, p-values, effect sizes) from the
underlying papers along with their URLs. URLs are given so the user can
verify any claim directly; nothing here is taken as more certain than
"a search summary of a paper said X."

**Status vocabulary** (used in the strategy-level Status column, §2):
`Research Candidate` (found, not yet implemented) · `Implemented` ·
`Testing` · `Candidate` · `Robust Candidate` · `Rejected` · `Overfit Risk`.

---

## 1. Research entries

### SRR-001 — Fair Value Gap quantification
- **Source**: Kondapally, "Quantifying Fair Value Gaps: A Novel Metric for Price Reaction Prediction in Financial Markets," SSRN.
- **Link**: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6032676
- **Date**: 2026 (recent working paper).
- **Markets**: 4 asset classes (not fully specified in the available summary).
- **Timeframes**: intraday, using tick data during FVG formation.
- **Data type**: tick data.
- **Entry/Exit rules**: not a full trading strategy — a *measurement* study proposing an FVG "degree" (steepness) metric.
- **Filters**: FVGs filtered by degree ≤ 0.00015 price units/second.
- **Risk/Reward**: not reported (not a trading strategy).
- **Published results**: 32,202 FVG events analyzed; low-degree (shallower) FVGs generate 3.2× stronger subsequent price reactions than steep ones (p < 0.001).
- **In-sample or OOS**: not stated in the available summary — treat as unverified.
- **Transaction costs**: not applicable (measurement study, not a strategy).
- **Walk-forward**: not stated.
- **Data-snooping control**: not stated.
- **Strengths**: large sample (32k events), a concrete, reproducible-sounding metric (gap steepness) beyond the binary "FVG exists".
- **Weaknesses**: requires tick data (we only have OHLC); "reaction" ≠ "profitable trade after costs"; single recent working paper, not yet a body of literature.
- **Can we rebuild it?**: **No, not the "degree" metric specifically** — needs tick data we don't have (see §3, Tick Data Assessment). We CAN and do use the qualitative finding ("not all FVGs are equal") indirectly: our existing SMC/ICT `fvg` component is already binary, matching the "popular" interpretation this paper's own related search results explicitly contrasted with more rigorous filtering.
- **Also found in the same search**: an independent 4-futures-market study concluding "the reaction is real, but the tradeable edge is not," and a cross-index/metal study finding the FVG reaction rate beat random in 34/36 tested cells by ~5 percentage points — i.e., a real but small, filter-dependent effect, not a standalone edge. This directly supports NOT treating "FVG present" as a strong signal on its own, consistent with our own component-weighting framework already giving `fvg` no special primacy.
- **Status**: Research Candidate (informs weighting philosophy; not separately implemented as its own strategy).

### SRR-002 — Mechanical ICT/SMC backtest ("what survives")
- **Source**: StatOasis, "I Backtested ICT / Smart Money Concepts — What Survives."
- **Link**: https://statoasis.com/overfit/research/ict-backtest-what-survives
- **Date**: not stated (page not directly retrievable; see sourcing note above).
- **Markets/Timeframes/Data**: multiple markets, mechanical rules for order blocks, FVG, liquidity sweeps, OTE (per search summary).
- **Entry/Exit/Filters**: ICT's four core entries "codified into explicit mechanical rules."
- **Published results (per search summary)**: none of the four core entries showed a statistically significant forward-return edge.
- **In-sample/OOS, transaction costs, walk-forward, data-snooping control**: not available without direct page access — flagged as unverified detail, only the headline finding is used.
- **Strengths**: explicitly mechanical (not discretionary), tests the four ICT primitives separately rather than only as a bundle — same philosophy as our own ablation testing.
- **Weaknesses**: cannot verify methodology directly (WebFetch blocked); "no significant edge" on ITS rule definitions doesn't prove no edge exists under different definitions.
- **Can we rebuild it?**: Partially — our SMC/ICT ablation testing (Task 36) already tests each primitive's removal independently on our own data, which is the same spirit even though not the identical rule-set.
- **Status**: Research Candidate (methodological inspiration for ablation approach, already applied).

### SRR-003 — Liquidity sweep / stop-hunt reversal
- **Sources**: multiple practitioner/quant-education sources (LuxAlgo, Medium/Yavuz Akbay, quantum-algo.com, backtrex.com) — **explicitly NOT academic**, flagged as lower-rigor per the user's own instruction not to treat trading blogs as proof.
- **Links**: https://medium.com/@yavuzakbay/stop-hunts-in-financial-markets-789a240f64f3 ; https://www.quantum-algo.com/blog/guides/liquidity-sweep-trading-complete-guide/ ; https://www.luxalgo.com/library/concept/liquidity-sweep/
- **Markets**: major FX pairs and large indices, emphasized during London/New York sessions.
- **Timeframes**: multi-timeframe (sweep identified on 1H/4H, entry on 15M/5M).
- **Entry rule**: retest of the order block/FVG formed after a sweep.
- **Exit rule**: SL beyond the sweep extreme; target at the next liquidity level.
- **Risk/Reward**: claimed 2.5:1–5:1 (unverified, practitioner-sourced).
- **Published results**: claimed 65–75% win rate standalone, 80%+ with OB/FVG confluence — **explicitly called out by the same sources as sensitive to pivot length/stop distance and NOT statistically meaningful on small samples**.
- **In-sample/OOS, transaction costs, walk-forward, data-snooping control**: none stated — these are marketing-adjacent claims, not backtested research.
- **Strengths**: mechanically clear enough to reproduce exactly (sweep → confluence → retest is a precise sequence).
- **Weaknesses**: no credible statistical backing for the quoted win rates; likely survivorship/cherry-picked examples.
- **Can we rebuild it?**: **Yes** — the mechanical sequence itself (sweep → displacement → retracement) is precisely reproducible without needing to trust any of the quoted win rates.
- **Status**: **Implemented** as `core/strategies/sweep_displacement/sweep_displacement_strategy.py` — see §2. Its own backtested numbers on OUR data supersede the unverifiable claims above.

### SRR-004 — FX session/volatility microstructure
- **Sources**: Andersen & Bollerslev (1998); Dacorogna et al. (2001); Ito & Yamada (2017); Evans & Lyons (2002) — cited via a search summary (fxeresearch.substack.com, quanthedge.substack.com), not read directly.
- **Links**: https://fxeresearch.substack.com/p/session-volatility-in-fx-where-price ; https://quanthedge.substack.com/p/seasonality-of-intraday-volatility
- **Market**: DM/USD and general major FX pairs.
- **Data type**: intraday (tick/high-frequency in the original papers).
- **Finding**: strong, stable intraday periodicity in volatility; the London-New York overlap is the dominant volatility window (~1.21× the London-only level); pattern reported as essentially unchanged between 2005-2009 and 2020-2024, attributed to institutional session structure rather than technical trading-cost effects.
- **In-sample/OOS**: these are descriptive microstructure findings across decades of data, not a single backtested strategy — the "stability across 15+ years" claim is itself a form of out-of-sample robustness.
- **Strengths**: multiple independent, decades-old, foundational citations (Andersen & Bollerslev is a canonical volatility paper); directly corroborated by our OWN Task-37 regime/session breakdown (low-vol clearly outperforms high-vol on both EURUSD and XAUUSD).
- **Weaknesses**: describes WHERE volatility concentrates, not that trading during/around it is profitable — a separate question our own backtests must answer.
- **Can we rebuild it?**: **Yes** — directly operationalized as `core/filters/volatility_regime_filter.py` (regime side) and as the timing gate in `session_breakout_strategy.py` (session side).
- **Status**: **Implemented** — see §2.

### SRR-005 — Opening Range Breakout (academic)
- **Sources**: Holmberg, Lönnbark & Lundström, "Assessing the profitability of intraday opening range breakout strategies" (published, ScienceDirect / umu.se working paper); a cited 2023 5-minute-ORB study on index ETFs.
- **Links**: https://www.sciencedirect.com/science/article/abs/pii/S1544612312000438 ; http://www.econ.umu.se/ueslpnr/ues845.pdf
- **Market**: index futures (5 major markets in one cited study), US equities/ETFs in another.
- **Timeframe**: intraday (opening range of varying length, breakout traded same session).
- **Entry rule**: break of the opening range high/low.
- **Filters**: volatility, volume, and trend-alignment filtering — explicitly stated as necessary ("raw signal is weak on its own but strengthens materially once filtered").
- **Risk/Reward**: not uniformly stated across the cited studies.
- **Published results**: >8% annualized return with p<3% in all 5 tested index futures markets (one study); 2.4 Sharpe ratio, beta≈0 vs buy-and-hold (a more recent US-equities study).
- **In-sample/OOS**: the index-futures study reports results "in all five markets," suggesting cross-market (not single-market-cherry-picked) validation — a meaningfully stronger design than a single-market backtest, though we cannot confirm a held-out OOS split without the full paper.
- **Transaction costs / Walk-forward / Data-snooping control**: not confirmed from the summary alone.
- **Strengths**: peer-reviewed / published academic work, cross-market replication, explicit statistical significance testing.
- **Weaknesses**: equity/futures market microstructure (single daily open) doesn't map 1:1 onto FX's 24-hour market — required a genuine adaptation, not a literal transplant (see SRR-006).
- **Can we rebuild it?**: **Yes**, adapted — FX has no single "market open," so the Asian session (00:00-07:00 UTC) stands in for the opening range, breaking at the London session's own open, per SRR-006.
- **Status**: **Implemented** as `core/strategies/session_breakout/session_breakout_strategy.py` — see §2.

### SRR-006 — FX session effects reinforcing the London-open breakout window
- Same sources as SRR-004; included separately here because it specifically justifies WHERE in FX's 24-hour cycle an opening-range-style breakout should be anchored (Asian range → London open), rather than just describing volatility clustering in general.
- **Status**: Implemented (informs `session_breakout_strategy.py`'s London-window gate — see §2).

### SRR-007 — Time Series Momentum
- **Source**: Moskowitz, Ooi & Pedersen, "Time Series Momentum," *Journal of Financial Economics*, 2012.
- **Link**: https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID2089463_code753937.pdf?abstractid=2089463&mirid=1 (also on ScienceDirect: https://www.sciencedirect.com/science/article/pii/S0304405X11002613)
- **Date**: 2012 (data 1985–2009).
- **Markets**: 58 futures/forward contracts across equity indices, currencies, commodities, sovereign bonds.
- **Timeframe**: monthly signals, 1–12 month look-back, with reversal over longer horizons.
- **Entry/Exit rule**: sign of trailing N-month return determines long/short; no discretionary filter.
- **Risk/Reward**: not a per-trade R:R design — a diversified, volatility-scaled portfolio approach.
- **Published results**: large, statistically significant alpha across asset classes over 25 years; low exposure to standard risk factors; strongest during extreme markets.
- **In-sample/OOS**: 25-year, multi-asset-class sample is one of the more robust designs in this registry — genuinely diversified across markets, not one instrument's history.
- **Transaction costs**: the original paper does address costs in its full text (not confirmed in this summary — flagged for follow-up if implemented).
- **Walk-forward / Data-snooping control**: foundational academic paper with extensive robustness checks in its full text (again, not independently re-verified here — WebFetch blocked).
- **Strengths**: arguably the single most robust, most-cited entry in this registry; directly relevant since it's a currencies-inclusive dataset.
- **Weaknesses**: designed for monthly/cross-asset portfolio construction, not single-symbol intraday M15 forex trading — porting it down to our timeframe and single-symbol setting is a real adaptation, not a direct replication, and wasn't completed in this pass.
- **Can we rebuild it?**: Yes, mechanically simple (MA-slope or N-period-return-sign continuation) — **not implemented this pass** due to scope/time; logged here so the next research pass starts from a documented, well-sourced candidate rather than nothing.
- **Status**: Research Candidate (not implemented).

### SRR-008 — Mean Reversion (RSI / Bollinger Bands)
- **Sources**: general quant-education sources (QuantInsti, AvaTrade, Grokipedia) — practitioner-level, not peer-reviewed.
- **Link**: https://blog.quantinsti.com/mean-reversion-strategies-introduction-building-blocks/
- **Entry rule**: Bollinger Band touch + RSI(7–9) < 30/35 (oversold) or > 70/65 (overbought).
- **Published results**: no controlled backtest results cited; explicit warning found in the same search that "parameter over-tuning... typically adds 30-50% to backtest Sharpe Ratios but... evaporate[s] in live trading" — i.e., the search itself surfaced a data-snooping warning about this exact strategy family.
- **Strengths**: mechanically trivial to implement and test.
- **Weaknesses**: weak evidentiary base (no academic citation found), explicitly flagged overfitting risk in its own parameter space, and conceptually opposed to our momentum/structure-following existing strategies (would need its own regime filter to avoid fighting trends).
- **Can we rebuild it?**: Yes, trivially — **not implemented this pass**; the weak evidence base makes it a lower priority than SRR-003/005 given limited time.
- **Status**: Research Candidate (not implemented).

### SRR-009 — False Breakout / Failed Breakout Reversal
- **Sources**: practitioner sources only (LuxAlgo, dailypriceaction.com, priceaction.com) — no academic citation surfaced despite a dedicated search.
- **Published results**: none quantified; qualitative description only ("ADX may be used as confirmation").
- **Strengths**: conceptually complements our existing strategies (a literal inverse of Classic's breakout-continuation assumption).
- **Weaknesses**: essentially no credible quantitative backing found — the weakest evidence base of any entry in this registry.
- **Can we rebuild it?**: Yes, mechanically (fits our existing S/R + liquidity-sweep primitives) — **not implemented this pass**, precisely because of the weak evidence base; would need to be built and tested on its own merits with no literature-based prior on parameters.
- **Status**: Research Candidate (not implemented).

### SRR-010 — XAUUSD-specific academic literature
- **Sources**: ResearchGate papers on XAU/USD technical analysis; mostly ANN/Genetic-Algorithm prediction studies, not mechanical rule-based strategies.
- **Finding**: academic XAUUSD-specific research is thin and skews toward black-box prediction models (ANN, GA) rather than reproducible mechanical rules.
- **Can we rebuild it?**: **No** — ANN/GA prediction models are out of scope here (would require a training/serving pipeline this project doesn't have, and risk exactly the kind of unvalidated complexity the spec warns against for "ML only where it can be implemented and tested without leakage"). We instead rely on SRR-003/004/005/006 (liquidity, volatility regime, session/breakout), which were all tested on XAUUSD as well as EURUSD in this project already.
- **Status**: Research Candidate (descoped — no mechanical rule found worth reproducing).

### SRR-011 — Deflated Sharpe Ratio / Probability of Backtest Overfitting
- **Source**: Bailey & Lopez de Prado, "The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting and Non-Normality," *Journal of Portfolio Management*, 2014.
- **Link**: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551 (mirror: https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)
- **Finding**: the probability that a strategy selected from N trials is actually overfit grows rapidly with N; correcting the Sharpe ratio's significance threshold for the number of trials, skewness and kurtosis addresses this.
- **Used how in this project**: methodological framing, not a literally-computed DSR figure — see §3 (Data-Snooping Control) for why a literal DSR/PBO computation was judged not statistically meaningful at our current sample sizes (tens of trades per split), and what we did instead.
- **Status**: Research Candidate (methodology reference, informs §3 rather than being separately "implemented").

### SRR-012 — Combinatorial Purged Cross-Validation (CPCV)
- **Source**: López de Prado (2017); a 2024 *Knowledge-Based Systems* comparison study finding CPCV outperforms k-fold/purged-k-fold/walk-forward on PBO and DSR.
- **Link**: https://www.sciencedirect.com/science/article/abs/pii/S0950705124011110
- **Used how in this project**: **deliberately not applied** — CPCV's combinatorial folds are designed for datasets with enough independent observations that purging/embargoing individual folds still leaves each fold statistically meaningful. Our real dataset is ~1 year of M15 data producing 19-548 resolved trades per strategy/config depending on filters; splitting that further into CPCV's combinatorial folds would produce folds too small to be meaningful, manufacturing false precision rather than removing it. The existing chronological Train/Validation/OOS split plus explicit trade-count reporting is the honest choice at this data volume.
- **Status**: Research Candidate (methodology reference; consciously not used, with reasoning).

### SRR-013 — False Discovery Rate / multiple-testing correction
- **Sources**: Benjamini & Hochberg (foundational FDR method); Harvey, Liu & Zhu "...and the Cross-Section of Expected Returns" lineage; a cited large-scale (21,000 rules, 30 currencies) mfFDR study.
- **Link**: https://arxiv.org/pdf/2006.04269 (survey: "False (and Missed) Discoveries in Financial Economics")
- **Finding**: most backtested strategies are false discoveries under Selection Bias under Multiple Testing; naive strategy-selection-by-best-backtest inflates apparent skill.
- **Used how in this project**: directly shapes §3's data-snooping-control practice — every experiment (successful or not) is logged to the Optimization Registry rather than only the winners being reported, and no strategy/weight is "selected" purely because it had the highest score among many trials without also passing the independent Validation/OOS/perturbation/cross-symbol checks.
- **Status**: Research Candidate (methodology reference, not a strategy).

---

## 2. Strategy-level registry

| Strategy ID | Source | Market | Timeframe | Entry Logic | Exit Logic | Filters | Required Data | Implementation Status | Test Status | Baseline Result | Validation Result | OOS Result | Robustness Result | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `classic_sr_trend_fib` | pre-existing | EURUSD/XAUUSD | M15/H1/H4 | Trend + S/R pullback + candlestick | Dynamic S/R/ATR TP/SL | trend, S/R proximity, candlestick | OHLC | Implemented | Tested (Task 36) | net R −8.27 (Train) | −2.65 (Val, candidate) | −3.88 (OOS, candidate) | Collapsed (min obj −19.55) | Overfit Risk (candidate weights; DEFAULT_WEIGHTS kept) |
| `smc_structure_ob_fvg` | pre-existing | EURUSD/XAUUSD | M15/H1/H4 | BOS + OB + FVG retracement | Dynamic liquidity/ATR TP/SL | displacement, OB, entry zone, prem/disc | OHLC | Implemented | Tested (Task 36) | net R −64.59 (Train) | +62.12 (Val, candidate) | +1.09 (OOS, candidate) | Collapsed (min obj −3.30) | Overfit Risk (candidate weights; DEFAULT_WEIGHTS kept) |
| `ict_ote_killzone` | pre-existing | EURUSD/XAUUSD | M15/H1/H4 | Kill zone + BOS + OTE/FVG | Dynamic liquidity/ATR TP/SL | kill zone, displacement, entry zone, prem/disc | OHLC | Implemented | Tested (Task 36) | net R +0.14 (Train) | −2.07 (Val, candidate) | +11.14 (OOS, candidate) | Stable but sample-starved | Rejected (candidate underperforms baseline OOS; DEFAULT_WEIGHTS kept) |
| `liquidity_sweep_displacement_retracement` | SRR-003 (adapted) | EURUSD/XAUUSD | M15/H1/H4 | Liquidity sweep sets direction, displacement confirms, retracement into FVG/body triggers entry | Dynamic liquidity/ATR TP/SL (SL beyond sweep extreme) | displacement, entry zone, prem/disc | OHLC | Implemented | Testing (Task 44, in progress) | pending | pending | pending | pending | Testing |
| `session_breakout_asian_range` | SRR-005/006 (adapted) | EURUSD/XAUUSD | M15 (needs full-day Asian-session candles) | Asian range breakout during London window | Dynamic liquidity/ATR TP/SL (SL opposite range side) | session window, displacement | OHLC | Implemented | Testing (Task 44, in progress) | pending | pending | pending | pending | Testing |
| Time Series Momentum (MA-slope continuation) | SRR-007 | — | — | N/A | N/A | N/A | OHLC | Research Candidate | Not started | — | — | — | — | Research Candidate |
| RSI+Bollinger Mean Reversion | SRR-008 | — | — | N/A | N/A | N/A | OHLC | Research Candidate | Not started | — | — | — | — | Research Candidate |
| False Breakout Reversal | SRR-009 | — | — | N/A | N/A | N/A | OHLC | Research Candidate | Not started | — | — | — | — | Research Candidate |
| VolatilityRegimeFilter (cross-cutting) | SRR-004 (+ our own Task-37 finding) | EURUSD/XAUUSD | any | N/A (filter, not a strategy) | N/A | rejects "high" ATR-percentile regime | OHLC | Implemented | Testing (Task 45, in progress) | pending | pending | pending | pending | Testing |

Pending rows will be filled in as Tasks 44-46 complete (this file is updated in place, not duplicated, as each phase finishes — see the git history for the evolution if needed).

---

## 3. Data-snooping control practices used in this phase

1. **Reused, not redefined, OOS**: the same chronological Train(60%)/Validation(20%)/Out-of-Sample(20%) boundary over 2025-09-15→2026-09-16 established in the earlier weight-optimization phase is reused for every new strategy — never redrawn per-strategy, and never inspected before a candidate is fixed.
2. **Everything logged**: every experiment (every weight sample, every ablation, every perturbation, every rejected strategy) is appended to `data/optimization_registry/experiments.jsonl` — nothing is filtered out of the record because it performed poorly.
3. **Bounded search, not brute force**: weight search stays at the same small, fixed budget (16-18 samples) used in the prior phase — never scaled up just because more strategies exist to search over.
4. **No literal DSR/PBO/CPCV computation** (SRR-011/012): with 19-550 resolved trades per configuration depending on filters, computing a Deflated Sharpe Ratio or running Combinatorial Purged CV would produce numbers with more decimal precision than the underlying sample supports — false rigor, not real rigor. Instead: (a) the composite objective's own trade-count-sufficiency factor already down-weights small samples, (b) every candidate must pass Validation AND OOS AND perturbation AND cross-symbol checks (a cruder but honest substitute for a formal multiple-testing correction), and (c) this registry's job is exactly the FDR literature's (SRR-013) core recommendation: report every trial, not just winners.
5. **No changing OOS after seeing results**: no strategy's OOS window, weight, or threshold is adjusted once the OOS period's numbers have been seen — a violation would be visible in the git history (every commit is timestamped and incremental) and in the Optimization Registry's append-only log.
