"""Tests for the pure classification/band logic in network_health_matrix.

Rendering and the CLI (which imports services.network.state_task_orchestrator and
hits the real state directory) are exercised via manual verification, not here.
"""

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from tools.network_health_matrix import (
    GROUPS,
    MISSING_DATA_COLUMNS,
    band_for_count,
    band_for_pct,
    build_group_matrix,
    build_report_data,
)
from tools.network_state_common import STATE_ERROR, STATE_NA, STATE_NO_DATA

_NOW = datetime(2026, 8, 17, 8, 0, tzinfo=UTC)


class TestBandForCount(unittest.TestCase):
    def test_none_is_none(self):
        self.assertIsNone(band_for_count(None))

    def test_boundaries(self):
        cases = {
            0: "green",
            0.9: "green",
            1: "blue",
            2: "blue",
            2.9: "blue",
            3: "purple",
            4: "purple",
            4.9: "purple",
            5: "orange",
            6: "orange",
            6.9: "orange",
            7: "red",
            50: "red",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(band_for_count(value), expected)


class TestBandForPct(unittest.TestCase):
    def test_none_is_none(self):
        self.assertIsNone(band_for_pct(None))

    def test_boundaries(self):
        cases = {
            0: "green",
            0.99: "green",
            1: "blue",
            4.99: "blue",
            5: "purple",
            14.99: "purple",
            15: "orange",
            29.99: "orange",
            30: "red",
            100: "red",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(band_for_pct(value), expected)


def _write_state(state_dir: Path, task_name: str, sites: dict) -> None:
    payload = {"updated_at": "2026-08-17T07:00:00+00:00", "sites": sites}
    (state_dir / f"{task_name}.json").write_text(json.dumps(payload), encoding="utf-8")


class TestBuildGroupMatrix(unittest.TestCase):
    def _group(self, key):
        return next(g for g in GROUPS if g["key"] == key)

    def test_missing_data_flat_group_bands_and_no_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            _write_state(
                state_dir,
                "missing_data",
                {
                    "Boyagin": {
                        "days_since_last_record": 0,
                        "pct_missing_last_1_days": 0.5,
                        "pct_missing_last_7_days": 2.0,
                        "pct_missing_last_30_days": 20.0,
                        "error": None,
                    }
                },
            )
            matrix, updated_at = build_group_matrix(
                self._group("missing_data"), state_dir, ["Boyagin", "Litchfield"], set()
            )
            self.assertEqual(updated_at, "2026-08-17T07:00:00+00:00")
            boyagin = matrix["Boyagin"]
            self.assertEqual(boyagin["days_since_last_record"]["state"], "green")
            self.assertEqual(boyagin["pct_missing_last_1_days"]["state"], "green")
            self.assertEqual(boyagin["pct_missing_last_7_days"]["state"], "blue")
            self.assertEqual(boyagin["pct_missing_last_30_days"]["state"], "orange")
            # Litchfield never ran -> no_data on every column.
            for col in MISSING_DATA_COLUMNS:
                self.assertEqual(matrix["Litchfield"][col]["state"], STATE_NO_DATA)

    def test_error_field_wins_over_severity(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            _write_state(
                state_dir,
                "missing_data",
                {
                    "Boyagin": {
                        "days_since_last_record": 0,
                        "pct_missing_last_1_days": 0.0,
                        "pct_missing_last_7_days": 0.0,
                        "pct_missing_last_30_days": 0.0,
                        "error": "boom",
                    }
                },
            )
            matrix, _ = build_group_matrix(
                self._group("missing_data"), state_dir, ["Boyagin"], set()
            )
            for col in MISSING_DATA_COLUMNS:
                self.assertEqual(matrix["Boyagin"][col]["state"], STATE_ERROR)
                self.assertEqual(matrix["Boyagin"][col]["error"], "boom")

    def test_connectivity_na_for_ineligible_site_even_with_a_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            _write_state(
                state_dir,
                "gateway_connectivity",
                {
                    "Boyagin": {
                        "consecutive_failures": 0,
                        "last_success": _NOW.isoformat(),
                        "last_attempt": _NOW.isoformat(),
                        "last_latency_ms": 5,
                    }
                },
            )
            matrix, _ = build_group_matrix(
                self._group("network_connectivity"),
                state_dir,
                ["Boyagin"],
                connectivity_eligible=set(),
                now=_NOW,
            )
            self.assertEqual(matrix["Boyagin"]["gateway"]["state"], STATE_NA)
            self.assertEqual(matrix["Boyagin"]["EC logger"]["state"], STATE_NA)

    def test_connectivity_eligible_site_gets_days_since_last_success_severity(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            _write_state(
                state_dir,
                "gateway_connectivity",
                {
                    "Boyagin": {
                        "consecutive_failures": 0,
                        "last_success": _NOW.isoformat(),
                        "last_attempt": _NOW.isoformat(),
                        "last_latency_ms": 5,
                    }
                },
            )
            _write_state(
                state_dir,
                "ec_logger_connectivity",
                {
                    "Boyagin": {
                        "consecutive_failures": 8,
                        "last_success": None,
                        "last_attempt": _NOW.isoformat(),
                        "last_latency_ms": None,
                    }
                },
            )
            matrix, _ = build_group_matrix(
                self._group("network_connectivity"),
                state_dir,
                ["Boyagin"],
                connectivity_eligible={"Boyagin"},
                now=_NOW,
            )
            gateway = matrix["Boyagin"]["gateway"]
            self.assertEqual(gateway["state"], "green")
            self.assertEqual(gateway["value"], 0)
            ec_logger = matrix["Boyagin"]["EC logger"]
            self.assertEqual(ec_logger["state"], "red")
            self.assertEqual(ec_logger["display"], "never")
            self.assertIsNone(ec_logger["value"])

    def test_connectivity_missing_from_one_source_is_no_data_for_that_column_only(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            _write_state(
                state_dir,
                "gateway_connectivity",
                {
                    "Boyagin": {
                        "consecutive_failures": 0,
                        "last_success": _NOW.isoformat(),
                        "last_attempt": _NOW.isoformat(),
                        "last_latency_ms": 5,
                    }
                },
            )
            # ec_logger_connectivity.json not written at all.
            matrix, updated_at = build_group_matrix(
                self._group("network_connectivity"),
                state_dir,
                ["Boyagin"],
                connectivity_eligible={"Boyagin"},
                now=_NOW,
            )
            self.assertEqual(matrix["Boyagin"]["gateway"]["state"], "green")
            self.assertEqual(matrix["Boyagin"]["EC logger"]["state"], STATE_NO_DATA)
            self.assertIn("gateway:", updated_at)
            self.assertIn("EC logger: no state file", updated_at)

    def test_missing_state_file_is_no_data_for_every_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            matrix, updated_at = build_group_matrix(
                self._group("missing_data"), state_dir, ["Boyagin"], set()
            )
            self.assertIsNone(updated_at)
            for col in MISSING_DATA_COLUMNS:
                self.assertEqual(matrix["Boyagin"][col]["state"], STATE_NO_DATA)

    def test_nested_quality_variable_not_configured_is_no_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            _write_state(
                state_dir,
                "variable_quality",
                {
                    "Boyagin": {
                        "Fco2": {"pct_outside_range_last_7_days": 2.0},
                        "Fh": None,
                        "Fe": None,
                        "Fsd": None,
                        "error": None,
                    }
                },
            )
            matrix, _ = build_group_matrix(
                self._group("variable_quality"), state_dir, ["Boyagin"], set()
            )
            self.assertEqual(matrix["Boyagin"]["Fco2"]["state"], "blue")
            self.assertEqual(matrix["Boyagin"]["Fh"]["state"], STATE_NO_DATA)


class TestBuildReportData(unittest.TestCase):
    def test_assembles_all_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            data = build_report_data(state_dir, ["Boyagin"], set())
            self.assertEqual(data["sites"], ["Boyagin"])
            self.assertEqual(len(data["groups"]), len(GROUPS))
            self.assertIn("grafana_url", data)
            self.assertIn("logger_status_url", data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
