"""Optimization Registry — a durable, append-only log of every weight
experiment run, so no experiment (including rejected/overfit ones) is
silently lost. Backed by a JSON-Lines file rather than a database: simple,
diffable, and sufficient for this scale of experimentation.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

DEFAULT_REGISTRY_PATH = Path("data/optimization_registry/experiments.jsonl")
CONFIGURATION_VERSION = "v1-component-scoring"  # bump when the scoring/objective formula changes meaningfully


@dataclass
class ExperimentRecord:
    strategy: str
    symbol: str
    timeframe: str
    dataset: str
    phase: str  # "train" | "validation" | "out_of_sample" | "perturbation" | "ablation" | "combination"
    training_period: tuple[str, str]
    validation_period: tuple[str, str]
    oos_period: tuple[str, str]
    parameters: dict
    component_weights: dict[str, float]
    disabled_components: list[str]
    trade_count: int
    resolved_count: int
    win_rate: float
    tp1_rate: float
    tp2_rate: float
    sl_rate: float
    profit_factor: float
    net_r: float
    expectancy: float
    average_r: float
    max_drawdown_r: float
    instability: float
    composite_objective: float
    status: str  # "Baseline" | "Candidate" | "Robust Candidate" | "Rejected" | "Overfit Risk"
    notes: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    configuration_version: str = CONFIGURATION_VERSION


class OptimizationRegistry:
    def __init__(self, path: Path | str = DEFAULT_REGISTRY_PATH):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, record: ExperimentRecord) -> None:
        with self._path.open("a") as f:
            f.write(json.dumps(asdict(record), default=str) + "\n")

    def all(self) -> list[dict]:
        if not self._path.exists():
            return []
        with self._path.open() as f:
            return [json.loads(line) for line in f if line.strip()]

    def for_strategy(self, strategy: str) -> list[dict]:
        return [r for r in self.all() if r["strategy"] == strategy]
