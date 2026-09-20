"""Support/Resistance levels, built from clustering swing points — shared
foundation, not duplicated per strategy."""
from __future__ import annotations

from dataclasses import dataclass

from core.algorithms.structure.swings import SwingPoint


@dataclass(frozen=True)
class SRLevel:
    price: float
    touches: int
    kind: str  # "support" | "resistance"


def find_support_resistance_levels(swings: list[SwingPoint], tolerance: float) -> list[SRLevel]:
    """Clusters swing highs into resistance and swing lows into support.

    `tolerance` is an absolute price distance (e.g. a handful of pips for
    the symbol) — two swings within it are treated as the same level.
    """
    levels: list[SRLevel] = []
    for kind, points in (("resistance", [s for s in swings if s.kind == "high"]),
                         ("support", [s for s in swings if s.kind == "low"])):
        clusters: list[list[float]] = []
        for point in sorted(points, key=lambda s: s.price):
            if clusters and abs(point.price - clusters[-1][-1]) <= tolerance:
                clusters[-1].append(point.price)
            else:
                clusters.append([point.price])
        for cluster in clusters:
            levels.append(SRLevel(price=sum(cluster) / len(cluster), touches=len(cluster), kind=kind))
    return levels
