from datetime import datetime, timezone

import pytest

from optimization.data_split import chronological_split

START = datetime(2025, 1, 1, tzinfo=timezone.utc)
END = datetime(2026, 1, 1, tzinfo=timezone.utc)  # 365 days


def test_split_covers_the_whole_range_with_no_gaps_or_overlaps():
    split = chronological_split(START, END, train_frac=0.6, validation_frac=0.2)

    assert split.train[0] == START
    assert split.train[1] == split.validation[0]
    assert split.validation[1] == split.out_of_sample[0]
    assert split.out_of_sample[1] == END


def test_split_fractions_are_respected():
    split = chronological_split(START, END, train_frac=0.6, validation_frac=0.2)
    total = (END - START).total_seconds()

    train_len = (split.train[1] - split.train[0]).total_seconds()
    val_len = (split.validation[1] - split.validation[0]).total_seconds()
    oos_len = (split.out_of_sample[1] - split.out_of_sample[0]).total_seconds()

    assert train_len / total == pytest.approx(0.6, abs=0.01)
    assert val_len / total == pytest.approx(0.2, abs=0.01)
    assert oos_len / total == pytest.approx(0.2, abs=0.01)


def test_invalid_fractions_rejected():
    with pytest.raises(ValueError):
        chronological_split(START, END, train_frac=0.7, validation_frac=0.4)  # sums to > 1, no room for OOS
    with pytest.raises(ValueError):
        chronological_split(START, END, train_frac=0, validation_frac=0.5)
