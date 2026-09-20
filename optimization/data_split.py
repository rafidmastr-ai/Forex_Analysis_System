"""Point-in-Time chronological Train/Validation/Out-of-Sample split.

Splits are computed purely from the (start, end) boundary — never from
looking at trade outcomes or data content — so nothing about the split
point can leak information from later periods into earlier ones. Weight
search only ever runs against `train`; `validation` and `out_of_sample`
are read strictly after a candidate is already fixed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DataSplit:
    train: tuple[datetime, datetime]
    validation: tuple[datetime, datetime]
    out_of_sample: tuple[datetime, datetime]


def chronological_split(start: datetime, end: datetime, train_frac: float = 0.6, validation_frac: float = 0.2) -> DataSplit:
    if not (0 < train_frac < 1) or not (0 < validation_frac < 1) or train_frac + validation_frac >= 1:
        raise ValueError("train_frac and validation_frac must be positive and leave room for an OOS slice")
    total = end - start
    train_end = start + total * train_frac
    validation_end = train_end + total * validation_frac
    return DataSplit(train=(start, train_end), validation=(train_end, validation_end), out_of_sample=(validation_end, end))
