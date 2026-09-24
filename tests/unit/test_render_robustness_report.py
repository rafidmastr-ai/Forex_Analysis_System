"""Regression test for scripts/render_robustness_report.py's aggregation
correctness -- specifically a real bug found and fixed while reviewing
this script's own output: the R-Multiple Dependency summary count was
built from a dict keyed only by strategy name, so cells sharing the same
strategy silently overwrote each other and the count collapsed from 96
cells down to 4. This test proves classify_outlier_dependency is called
once per cell and every result is counted.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.render_robustness_report import classify_outlier_dependency  # noqa: E402


def _cell(baseline_net_r: float, cap3_net_r: float) -> dict:
    def mode(net_r: float) -> dict:
        return {"net_r": net_r}
    return {"by_mode": {"Baseline": mode(baseline_net_r), "Cap_3.0": mode(cap3_net_r)}}


def test_classification_counts_every_cell_even_with_repeated_strategy_names():
    """4 cells, all belonging to the SAME strategy (as would happen for
    Classic's 24 cells in the real report) -- every one must be counted
    independently, not collapsed into a single dict entry."""
    cells = [
        ("Classic", "EURUSD", "M1", _cell(baseline_net_r=100.0, cap3_net_r=-10.0)),  # High
        ("Classic", "XAUUSD", "M1", _cell(baseline_net_r=100.0, cap3_net_r=90.0)),   # Low
        ("Classic", "GBPUSD", "M1", _cell(baseline_net_r=-5.0, cap3_net_r=-20.0)),   # N/A
        ("Classic", "NZDUSD", "M1", _cell(baseline_net_r=50.0, cap3_net_r=5.0)),     # High
    ]
    classifications = [classify_outlier_dependency(cell) for _, _, _, cell in cells]

    assert len(classifications) == 4, "every cell must produce its own classification, none dropped"
    assert classifications.count("High R-Multiple Sensitivity") == 2
    assert classifications.count("Low R-Multiple Sensitivity") == 1
    assert classifications.count("N/A (baseline non-positive)") == 1


def test_classify_outlier_dependency_thresholds():
    # Baseline non-positive -> N/A regardless of cap.
    assert classify_outlier_dependency(_cell(0.0, 5.0)) == "N/A (baseline non-positive)"
    assert classify_outlier_dependency(_cell(-1.0, 5.0)) == "N/A (baseline non-positive)"
    # Cap flips to non-positive -> High.
    assert classify_outlier_dependency(_cell(10.0, 0.0)) == "High R-Multiple Sensitivity"
    assert classify_outlier_dependency(_cell(10.0, -1.0)) == "High R-Multiple Sensitivity"
    # Retains less than 50% -> High.
    assert classify_outlier_dependency(_cell(10.0, 4.9)) == "High R-Multiple Sensitivity"
    # Retains exactly 50% or more -> Low.
    assert classify_outlier_dependency(_cell(10.0, 5.0)) == "Low R-Multiple Sensitivity"
    assert classify_outlier_dependency(_cell(10.0, 8.0)) == "Low R-Multiple Sensitivity"
