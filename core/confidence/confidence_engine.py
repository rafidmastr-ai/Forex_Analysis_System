"""ConfidenceEngine — turns one or more agreeing StrategySignals into a
Confidence Score.

IMPORTANT: confidence_score (0-100) is a relative measure of internal
confluence and rule strength. It is NOT a probability of winning the
trade and must never be presented or labeled as one.
"""
from __future__ import annotations

from core.signals.enums import ConfidenceLabel, StrategyCategory
from core.signals.strategy_signal import StrategySignal


class ConfidenceEngine:
    def __init__(self, thresholds: dict[str, int], multi_strategy_agreement_bonus: int):
        self._weak_max = thresholds["weak_max"]
        self._medium_max = thresholds["medium_max"]
        self._agreement_bonus = multi_strategy_agreement_bonus

    def score_group(
        self,
        primary: StrategySignal,
        agreeing: list[StrategySignal],
        filter_adjustment: int = 0,
    ) -> tuple[int, ConfidenceLabel, dict[str, bool], list[str]]:
        base = int(primary.raw_score_components.get("base_confidence", 50))
        base += self._agreement_bonus * len(agreeing)  # counted once per agreeing strategy, never per rationale line
        base += filter_adjustment
        score = max(0, min(100, base))
        label = self._label(score)
        breakdown = self._breakdown(primary, agreeing)
        reasons = self._reasons(primary, agreeing)
        return score, label, breakdown, reasons

    def _label(self, score: int) -> ConfidenceLabel:
        if score <= self._weak_max:
            return ConfidenceLabel.WEAK
        if score <= self._medium_max:
            return ConfidenceLabel.MEDIUM
        return ConfidenceLabel.STRONG

    def _breakdown(self, primary: StrategySignal, agreeing: list[StrategySignal]) -> dict[str, bool]:
        contributors = [primary, *agreeing]
        breakdown: dict[str, bool] = {
            f"{StrategyCategory.CLASSIC.value.lower()}_confirmation": any(
                s.category == StrategyCategory.CLASSIC for s in contributors
            ),
            f"{StrategyCategory.SMC.value.lower()}_confirmation": any(
                s.category == StrategyCategory.SMC for s in contributors
            ),
            f"{StrategyCategory.ICT.value.lower()}_confirmation": any(
                s.category == StrategyCategory.ICT for s in contributors
            ),
        }
        # Optional confirmations any strategy may report via raw_score_components.
        for key in ("trend_alignment", "liquidity_confirmation", "fvg_confirmation"):
            breakdown[key] = any(bool(s.raw_score_components.get(key)) for s in contributors)
        return breakdown

    @staticmethod
    def _reasons(primary: StrategySignal, agreeing: list[StrategySignal]) -> list[str]:
        """Human-readable evidence backing the score — each distinct piece
        of rationale counted once even if multiple contributing strategies
        happen to state it identically (no double counting)."""
        reasons: list[str] = []
        seen: set[str] = set()
        for signal in (primary, *agreeing):
            for line in signal.rationale:
                if line not in seen:
                    seen.add(line)
                    reasons.append(line)
        return reasons
