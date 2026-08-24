"""Tests for the pure state-loading logic in logger_status_report.

Rendering and the CLI (which imports services.network.state_task_orchestrator and
hits the real state directory) are exercised via manual verification, not here.
"""

import json
import tempfile
import unittest
from pathlib import Path

from tools.logger_status_report import (
    build_logger_table,
    build_report_data,
)
from tools.network_state_common import STATE_ERROR, STATE_NA, STATE_NO_DATA


def _write_state(state_dir: Path, task_name: str, sites: dict) -> None:
    payload = {"updated_at": "2026-08-17T07:00:00+00:00", "sites": sites}
    (state_dir / f"{task_name}.json").write_text(json.dumps(payload), encoding="utf-8")


class TestBuildLoggerTable(unittest.TestCase):
    def test_na_no_data_error_ok_layering(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            _write_state(
                state_dir,
                "logger_status",
                {
                    "Boyagin": {"model": "CR1000", "Battery": 13.1, "error": None},
                    "Litchfield": {"model": None, "error": "timeout"},
                },
            )
            rows, updated_at = build_logger_table(
                state_dir,
                ["Boyagin", "Litchfield", "Yanco", "NotScoped"],
                {"Boyagin", "Litchfield", "Yanco"},
            )
            self.assertEqual(updated_at, "2026-08-17T07:00:00+00:00")
            self.assertEqual(rows["Boyagin"]["row_state"], "ok")
            self.assertEqual(rows["Boyagin"]["fields"]["model"], "CR1000")
            self.assertEqual(rows["Litchfield"]["row_state"], STATE_ERROR)
            self.assertEqual(rows["Litchfield"]["error"], "timeout")
            self.assertEqual(rows["Yanco"]["row_state"], STATE_NO_DATA)
            self.assertEqual(rows["NotScoped"]["row_state"], STATE_NA)

    def test_missing_state_file_is_no_data_for_every_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            rows, updated_at = build_logger_table(state_dir, ["Boyagin"], {"Boyagin"})
            self.assertIsNone(updated_at)
            self.assertEqual(rows["Boyagin"]["row_state"], STATE_NO_DATA)


class TestBuildReportData(unittest.TestCase):
    def test_assembles_rows_and_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            data = build_report_data(state_dir, ["Boyagin"], set())
            self.assertEqual(data["sites"], ["Boyagin"])
            self.assertIn("Boyagin", data["rows"])
            self.assertIn("grafana_url", data)
            self.assertIn("network_health_matrix_url", data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
