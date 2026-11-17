"""Tests for toa5_concatenator.write_toa5_patch / next_patch_path."""

import tempfile
import unittest
from pathlib import Path

import pandas as pd
import yaml

from fluxtools import file_io, toa5_writer
from fluxtools import toa5_concatenator as tc

HEADERS = [["RECORD", "Ta"], ["RN", "degC"], ["", "Avg"]]


def _write(path: Path, start: str, n: int, value: float, drop=(), headers=HEADERS):
    idx = pd.date_range(start, periods=n, freq="30min", name="TIMESTAMP")
    df = pd.DataFrame({"RECORD": range(n), "Ta": value}, index=idx)
    df = df.drop(pd.to_datetime(list(drop)))
    toa5_writer.write_toa5(data=df, headers=headers, file_path=path)


def _read(path: Path) -> pd.DataFrame:
    return tc.load_raw_data(file_path=path, file_format="TOA5")


class WriteToa5PatchTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self.raw, self.patch_dir = tmp / "Slow", tmp / "Slow_patch"
        self.raw.mkdir()
        self.master = self.raw / "Site_EC_flux.dat"
        # Master: 2026-01-02 00:00 .. 04:30, missing 01:00 and 01:30.
        _write(
            self.master,
            "2026-01-02",
            10,
            1.0,
            drop=["2026-01-02 01:00", "2026-01-02 01:30"],
        )
        self.slave = tmp / "card_dump.dat"
        # Slave spans 2026-01-01 23:00 .. 2026-01-02 05:30.
        _write(self.slave, "2026-01-01 23:00", 14, 9.0)

    def _patch(self, **kwargs):
        kwargs.setdefault("reason", "comms outage")
        return tc.write_toa5_patch(
            self.master, [self.slave], self.patch_dir, author="tester", **kwargs
        )

    def test_writes_only_uncovered_records_and_leaves_raw_alone(self):
        before = file_io.file_sha256(self.master)
        report = self._patch()

        self.assertEqual(report["patch_file"].name, "Site_EC_flux.dat.patch")
        patch = _read(report["patch_file"])
        # 2 before the master, its 2 gaps, 2 after it.
        self.assertEqual(
            [str(t) for t in patch.index],
            [
                "2026-01-01 23:00:00",
                "2026-01-01 23:30:00",
                "2026-01-02 01:00:00",
                "2026-01-02 01:30:00",
                "2026-01-02 05:00:00",
                "2026-01-02 05:30:00",
            ],
        )
        self.assertTrue((patch["Ta"] == 9.0).all())
        self.assertEqual(file_io.file_sha256(self.master), before)
        self.assertEqual(
            sorted(p.name for p in self.raw.iterdir()), ["Site_EC_flux.dat"]
        )

        sidecar = yaml.safe_load(
            (self.patch_dir / "Site_EC_flux.dat.patch.yml").read_text()
        )
        self.assertEqual(sidecar["reason"], "comms outage")
        self.assertEqual(sidecar["author"], "tester")
        self.assertEqual(sidecar["records"], 6)
        self.assertEqual(sidecar["sources"][0]["records"], 6)
        self.assertEqual(
            sidecar["sources"][0]["sha256"], file_io.file_sha256(self.slave)
        )

    def test_backups_and_existing_patches_count_as_covered(self):
        _write(self.raw / "Site_EC_flux.dat.backup", "2026-01-02 01:00", 1, 5.0)
        first = self._patch()
        self.assertEqual(first["records"], 5)
        self.assertIn("Site_EC_flux.dat.backup", first["checked_against"])

        # Same slave again: everything is now covered, so nothing is written.
        again = self._patch()
        self.assertIsNone(again["patch_file"])
        self.assertEqual(len(list(self.patch_dir.iterdir())), 2)

    def test_next_patch_is_numbered(self):
        self._patch()
        later = self.raw.parent / "later.dat"
        _write(later, "2026-01-02 06:00", 2, 7.0)
        report = tc.write_toa5_patch(
            self.master, [later], self.patch_dir, reason="second"
        )
        self.assertEqual(report["patch_file"].name, "Site_EC_flux.dat.1.patch")
        self.assertEqual(
            tc.next_patch_path(self.master, self.patch_dir).name,
            "Site_EC_flux.dat.2.patch",
        )

    def test_min_timestamp_and_dry_run(self):
        report = self._patch(min_timestamp="2026-01-02", dry_run=True)
        self.assertEqual(report["records"], 4)
        self.assertEqual(report["dropped_below_min"], 2)
        self.assertFalse(self.patch_dir.exists())

    def test_rejects_blank_reason_and_mismatched_headers(self):
        with self.assertRaises(ValueError):
            self._patch(reason="  ")
        other = [["RECORD", "Tb"], ["RN", "degC"], ["", "Avg"]]
        _write(self.slave, "2026-01-02", 4, 9.0, headers=other)
        with self.assertRaises(ValueError):
            self._patch()
        self.assertFalse(self.patch_dir.exists())


if __name__ == "__main__":
    unittest.main()
