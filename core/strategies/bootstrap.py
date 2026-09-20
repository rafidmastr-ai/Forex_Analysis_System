"""Importing this module registers every concrete strategy with the
StrategyRegistry (each strategy module's @register_strategy decorator runs
on import). A strategy package is otherwise inert until something imports
it — this is the one place that has to know they all exist, so
backend/dependencies.py (and anything else that needs the full registry
populated, e.g. a backtest script) only has to import this module once.
"""
from __future__ import annotations

import core.strategies.classic  # noqa: F401
import core.strategies.ict  # noqa: F401
import core.strategies.smc  # noqa: F401
