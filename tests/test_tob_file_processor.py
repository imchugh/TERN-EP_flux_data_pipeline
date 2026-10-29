"""Tests for tob_file_processor._archive_tob3 archive naming.

Several different TOB3 files can share a creation date (a logger restart,
or a partial re-collection); each must be archived under its own name
rather than blocking in TMP.
"""

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from services.network import tob_file_processor as tfp

SITE = "AliceSpringsMulga"
FREQ_STR = "100ms"
DATE = dt.date(2025, 11, 30)
STEM = "TOB3_AliceSpringsMulga_100ms_2025_11_30"


class TestArchiveTob3(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.tmp_dir = self.base / "TMP"
        self.tmp_dir.mkdir()
        self.archive_dir = self.base / "TOB3" / "2025_11"

    def tearDown(self):
        self._tmp.cleanup()

    def _archive(self, name: str, content: bytes) -> Path:
        src = self.tmp_dir / name
        src.write_bytes(content)
        tfp._archive_tob3(
            site=SITE,
            file=src,
            freq_str=FREQ_STR,
            creation_date=DATE,
            out_base=self.base,
        )
        return src

    def _archived(self) -> list[str]:
        return sorted(p.name for p in self.archive_dir.iterdir())

    def test_no_collision_uses_daily_name(self):
        src = self._archive("a.dat", b"day")
        self.assertFalse(src.exists())
        self.assertEqual(self._archived(), [f"{STEM}.dat"])

    def test_identical_file_is_removed_as_duplicate(self):
        self._archive("a.dat", b"day")
        src = self._archive("b.dat", b"day")
        self.assertFalse(src.exists())
        self.assertEqual(self._archived(), [f"{STEM}.dat"])

    def test_different_files_get_numeric_suffixes(self):
        self._archive("a.dat", b"morning")
        self._archive("b.dat", b"afternoon")
        src = self._archive("c.dat", b"evening")
        self.assertFalse(src.exists())
        self.assertEqual(
            self._archived(), [f"{STEM}.dat", f"{STEM}_1.dat", f"{STEM}_2.dat"]
        )
        suffixed = self.archive_dir / f"{STEM}_1.dat"
        self.assertEqual(suffixed.read_bytes(), b"afternoon")

    def test_duplicate_of_suffixed_copy_is_removed(self):
        self._archive("a.dat", b"morning")
        self._archive("b.dat", b"afternoon")
        src = self._archive("c.dat", b"afternoon")
        self.assertFalse(src.exists())
        self.assertEqual(self._archived(), [f"{STEM}.dat", f"{STEM}_1.dat"])


if __name__ == "__main__":
    unittest.main()
