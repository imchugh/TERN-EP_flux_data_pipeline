"""Tests for tob_codec.split_by_interval day selection.

A ring-buffer TOB3 file can hold a few stale records from an earlier day;
the split must follow the day most records belong to, not the first record.
"""

import datetime as dt
import unittest

import pandas as pd

from infrastructure import tob_codec as tob

FREQ_HZ = 10
INTERVAL = 30


def _records(start: str, end: str) -> pd.DataFrame:
    """10 Hz records from start to end inclusive, Campbell-style (first at +0.1 s)."""
    index = pd.date_range(start, end, freq="100ms", name="TIMESTAMP")
    return pd.DataFrame({"x": range(len(index))}, index=index)


def _split(df: pd.DataFrame) -> list[tuple[dt.datetime, pd.DataFrame]]:
    return list(tob.split_by_interval(df, INTERVAL, FREQ_HZ))


class TestSplitByInterval(unittest.TestCase):
    def test_full_day_gives_48_blocks_ending_at_midnight(self):
        blocks = _split(_records("2025-12-02 00:00:00.1", "2025-12-03 00:00:00"))
        self.assertEqual(len(blocks), 48)
        self.assertEqual(blocks[0][0], dt.datetime(2025, 12, 2, 0, 30))
        self.assertEqual(blocks[-1][0], dt.datetime(2025, 12, 3, 0, 0))
        self.assertTrue(all(len(sub) == 18000 for _, sub in blocks))

    def test_stale_records_from_earlier_day_are_dropped(self):
        stale = _records("2026-01-14 00:09:30.1", "2026-01-14 00:09:33")
        day = _records("2026-02-12 16:00:00.1", "2026-02-12 18:00:00")
        df = pd.concat([stale, day])
        with self.assertLogs(tob.logger, "WARNING") as logs:
            blocks = _split(df)
        self.assertEqual([end.date() for end, _ in blocks], [dt.date(2026, 2, 12)] * 4)
        self.assertEqual(sum(len(sub) for _, sub in blocks), len(day))
        self.assertIn("stray_records_dropped", logs.output[0])

    def test_midnight_record_counts_toward_previous_day(self):
        # Only the last window's records, ending on the next day's midnight:
        # the day is still the one the window covers.
        blocks = _split(_records("2025-12-02 23:30:00.1", "2025-12-03 00:00:00"))
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0][0], dt.datetime(2025, 12, 3, 0, 0))
        self.assertEqual(len(blocks[0][1]), 18000)

    def test_no_warning_without_strays(self):
        with self.assertNoLogs(tob.logger, "WARNING"):
            _split(_records("2025-12-02 10:00:00.1", "2025-12-02 11:00:00"))

    def test_data_day_follows_most_records(self):
        stale = _records("2026-01-14 00:09:30.1", "2026-01-14 00:09:33")
        day = _records("2026-02-12 16:00:00.1", "2026-02-12 18:00:00")
        self.assertEqual(tob.data_day(pd.concat([stale, day])), dt.date(2026, 2, 12))

    def test_data_day_counts_midnight_record_toward_previous_day(self):
        df = _records("2025-12-02 23:59:59.9", "2025-12-03 00:00:00")
        self.assertEqual(tob.data_day(df), dt.date(2025, 12, 2))

    def test_empty_frame_yields_nothing(self):
        self.assertEqual(_split(_records("2025-12-02", "2025-12-02").iloc[:0]), [])


if __name__ == "__main__":
    unittest.main()
