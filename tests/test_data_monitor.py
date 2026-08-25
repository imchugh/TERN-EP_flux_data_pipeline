"""Regression tests for services.data.data_monitor.get_missing_records.

These guard against a real bug: a gapless file was reporting nonzero
pct_missing because the rolling window handed to analyse_data_gaps was
built from a live "now" reference (not an actual expected timestamp), so
pd.date_range's inclusive-both-ends behaviour counted one phantom slot too
many. See infrastructure.datetime_utils.floor_to_interval.
"""

import unittest
from datetime import datetime, timedelta

import pandas as pd

from services.data.data_monitor import get_missing_records


def _gapless_series(end: datetime, days: int, interval_minutes: int = 30) -> pd.Series:
    """A gapless 30-min-cadence series ending exactly at `end`, spanning `days`."""
    periods = days * 24 * 60 // interval_minutes + 1
    index = pd.date_range(end=end, periods=periods, freq=f"{interval_minutes}min")
    return pd.Series(range(len(index)), index=index)


class TestGetMissingRecords(unittest.TestCase):
    def test_gapless_data_with_grid_aligned_reference_is_zero(self):
        end = datetime(2026, 8, 25, 12, 0, 0)
        series = _gapless_series(end=end, days=31)
        result = get_missing_records(df=series, reference_date=end, interval_minutes=30)
        self.assertEqual(result["pct_missing_last_1_days"], 0.0)
        self.assertEqual(result["pct_missing_last_7_days"], 0.0)
        self.assertEqual(result["pct_missing_last_30_days"], 0.0)

    def test_gapless_data_with_non_aligned_reference_is_still_zero(self):
        # reference_date has arbitrary seconds/microseconds, replicating a
        # live "now" check -- this is the exact case that triggered the bug.
        last_record = datetime(2026, 8, 25, 12, 0, 0)
        reference_date = last_record + timedelta(
            minutes=6, seconds=8, microseconds=744667
        )
        series = _gapless_series(end=last_record, days=31)
        result = get_missing_records(
            df=series, reference_date=reference_date, interval_minutes=30
        )
        self.assertEqual(result["pct_missing_last_1_days"], 0.0)
        self.assertEqual(result["pct_missing_last_7_days"], 0.0)
        self.assertEqual(result["pct_missing_last_30_days"], 0.0)

    def test_a_genuine_gap_is_still_detected(self):
        end = datetime(2026, 8, 25, 12, 0, 0)
        series = _gapless_series(end=end, days=31)
        # Drop one record from within the trailing 1-day window.
        series = series.drop(series.index[-2])
        result = get_missing_records(df=series, reference_date=end, interval_minutes=30)
        self.assertAlmostEqual(result["pct_missing_last_1_days"], 100 / 48, places=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
