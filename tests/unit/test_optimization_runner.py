"""End-to-end smoke test for the optimization runner against the real
converted MT5 data. Skipped automatically when that data isn't present
(it's gitignored — a fresh checkout won't have it) rather than failing;
the weight-search/ablation/robustness modules that depend on this runner
are otherwise covered by unit tests with synthetic evaluate functions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

DATA_DIR = Path("data/historical")
pytestmark = pytest.mark.skipif(not DATA_DIR.exists(), reason="real converted MT5 data not present in this checkout")


def test_evaluate_metrics_runs_end_to_end_on_real_data():
    from adapters.historical_file.file_adapter import HistoricalFileMarketDataProvider
    from core.confidence.component_scoring import ComponentWeights
    from core.confidence.confidence_engine import ConfidenceEngine
    from core.market_data.models import Symbol, Timeframe
    from core.selection.strategy_selection_engine import StrategySelectionEngine
    from core.strategies.classic.classic_strategy import ClassicStrategy
    from optimization.runner import evaluate_metrics

    symbols = {"EURUSD": Symbol(name="EURUSD", pip_size=0.0001, digits=5, contract_size=100000)}
    provider = HistoricalFileMarketDataProvider(data_dir=DATA_DIR, symbols=symbols)
    confidence_engine = ConfidenceEngine(thresholds={"weak_max": 49, "medium_max": 74}, multi_strategy_agreement_bonus=10)
    selection_engine = StrategySelectionEngine(confidence_engine=confidence_engine, filters=[], min_risk_reward=1.5)
    strategy = ClassicStrategy(weights=ComponentWeights({"trend_strength": 0.5, "fibonacci": 0.5}))

    metrics = evaluate_metrics(
        strategies=[strategy], provider=provider, selection_engine=selection_engine,
        symbol_name="EURUSD", timeframe=Timeframe.M15,
        start=datetime(2025, 9, 15, tzinfo=timezone.utc), end=datetime(2025, 10, 15, tzinfo=timezone.utc),
        timeframes_config={"default_mapping": {"higher": "H4", "middle": "H1", "entry": "M15"}, "selection_rules": []},
        lookback_bars={"higher": 200, "middle": 300, "entry": 500}, min_confidence=None,
    )

    assert metrics.trade_count >= 0  # just proving the whole pipeline executes without error
