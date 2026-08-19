"""Tests for the file-selection and retry logic in nc_monitor."""

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from services.network import nc_monitor


class TestGetLatestNcFile(unittest.TestCase):
    def test_picks_most_recent_stable_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            site_dir = Path(tmp) / "Boyagin"
            site_dir.mkdir()
            old_year = 100
            (site_dir / "Boyagin_2024_L1.nc").touch()
            (site_dir / "Boyagin_2025_L1.nc").touch()
            for f in site_dir.iterdir():
                os.utime(f, (time.time() - old_year, time.time() - old_year))

            with patch.object(nc_monitor, "get_nc_site_dir", return_value=site_dir):
                latest = nc_monitor.get_latest_nc_file(site="Boyagin")

            self.assertEqual(latest.name, "Boyagin_2025_L1.nc")

    def test_no_files_raises_file_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            site_dir = Path(tmp) / "Boyagin"
            site_dir.mkdir()

            with patch.object(nc_monitor, "get_nc_site_dir", return_value=site_dir):
                with self.assertRaises(FileNotFoundError):
                    nc_monitor.get_latest_nc_file(site="Boyagin")

    def test_only_recently_modified_file_raises_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            site_dir = Path(tmp) / "Boyagin"
            site_dir.mkdir()
            (site_dir / "Boyagin_2026_L1.nc").touch()

            with patch.object(nc_monitor, "get_nc_site_dir", return_value=site_dir):
                with self.assertRaises(TimeoutError):
                    nc_monitor.get_latest_nc_file(site="Boyagin")

    def test_stale_file_excluded_when_newer_stable_file_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            site_dir = Path(tmp) / "Boyagin"
            site_dir.mkdir()
            old_year = site_dir / "Boyagin_2025_L1.nc"
            old_year.touch()
            os.utime(old_year, (time.time() - 100, time.time() - 100))
            (site_dir / "Boyagin_2026_L1.nc").touch()  # freshly "written"

            with patch.object(nc_monitor, "get_nc_site_dir", return_value=site_dir):
                latest = nc_monitor.get_latest_nc_file(site="Boyagin")

            self.assertEqual(latest.name, "Boyagin_2025_L1.nc")


class TestOpenDatasetWithRetry(unittest.TestCase):
    def test_succeeds_first_try_without_sleeping(self):
        with patch.object(nc_monitor.xr, "open_dataset", return_value="ds") as m_open:
            with patch.object(nc_monitor.time, "sleep") as m_sleep:
                result = nc_monitor._open_dataset_with_retry(Path("f.nc"))

        self.assertEqual(result, "ds")
        self.assertEqual(m_open.call_count, 1)
        m_sleep.assert_not_called()

    def test_retries_once_then_succeeds(self):
        with patch.object(
            nc_monitor.xr,
            "open_dataset",
            side_effect=[OSError("unknown file format"), "ds"],
        ) as m_open:
            with patch.object(nc_monitor.time, "sleep") as m_sleep:
                result = nc_monitor._open_dataset_with_retry(Path("f.nc"))

        self.assertEqual(result, "ds")
        self.assertEqual(m_open.call_count, 2)
        m_sleep.assert_called_once_with(nc_monitor._OPEN_RETRY_DELAY_SECS)

    def test_raises_after_exhausting_retries(self):
        exc = OSError("unknown file format")
        with patch.object(nc_monitor.xr, "open_dataset", side_effect=[exc, exc]):
            with patch.object(nc_monitor.time, "sleep"):
                with self.assertRaises(OSError):
                    nc_monitor._open_dataset_with_retry(Path("f.nc"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
