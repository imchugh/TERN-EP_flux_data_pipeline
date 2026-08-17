"""Tests for the pure log-parsing/classification logic in task_status_matrix.

Rendering and the CLI (which imports tasks.tasks and hits the real log/config
paths) are exercised via manual verification, not here.
"""

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tools.task_status_matrix import (
    STATE_FAILURE,
    STATE_NA,
    STATE_NO_DATA,
    STATE_SUCCESS,
    _iter_result_records,
    _latest_record,
    build_matrix,
    classify_cell,
)

NOW = datetime(2026, 8, 17, 12, 0, 0, tzinfo=UTC)


def _ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class TestClassifyCell(unittest.TestCase):
    def test_disabled_task_is_na_even_with_a_record(self):
        latest = {"status": STATE_SUCCESS, "timestamp": _ts(NOW), "run_id": "r1"}
        cell = classify_cell(enabled=False, latest=latest)
        self.assertEqual(cell, {"state": STATE_NA})

    def test_enabled_task_no_record_is_no_data(self):
        cell = classify_cell(enabled=True, latest=None)
        self.assertEqual(cell, {"state": STATE_NO_DATA})

    def test_enabled_task_success_record(self):
        latest = {
            "status": STATE_SUCCESS,
            "timestamp": _ts(NOW),
            "run_id": "r1",
            "task": "construct_L1_nc",
            "site": "Boyagin",
            "files_written": ["/store/x.nc"],
        }
        cell = classify_cell(enabled=True, latest=latest)
        self.assertEqual(cell["state"], STATE_SUCCESS)
        self.assertEqual(cell["timestamp"], _ts(NOW))
        self.assertEqual(cell["run_id"], "r1")
        self.assertNotIn("reason", cell)
        self.assertEqual(cell["details"], {"files_written": ["/store/x.nc"]})

    def test_enabled_task_failure_record_carries_reason(self):
        latest = {
            "status": STATE_FAILURE,
            "timestamp": _ts(NOW),
            "run_id": "r2",
            "reason": "exception",
        }
        cell = classify_cell(enabled=True, latest=latest)
        self.assertEqual(cell["state"], STATE_FAILURE)
        self.assertEqual(cell["reason"], "exception")


class TestLatestRecord(unittest.TestCase):
    def test_empty_returns_none(self):
        self.assertIsNone(_latest_record([]))

    def test_picks_max_timestamp(self):
        older = {"timestamp": _ts(NOW - timedelta(days=1)), "status": STATE_FAILURE}
        newer = {"timestamp": _ts(NOW), "status": STATE_SUCCESS}
        self.assertEqual(_latest_record([older, newer]), newer)
        self.assertEqual(_latest_record([newer, older]), newer)


class TestIterResultRecords(unittest.TestCase):
    def _write(self, log_dir: Path, name: str, lines: list[str]) -> None:
        (log_dir / name).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_filters_message_type_and_cutoff_and_skips_bad_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            in_window = json.dumps(
                {
                    "message": "task_site_result",
                    "timestamp": _ts(NOW),
                    "site": "Boyagin",
                    "status": "success",
                    "run_id": "r1",
                }
            )
            out_of_window = json.dumps(
                {
                    "message": "task_site_result",
                    "timestamp": _ts(NOW - timedelta(days=30)),
                    "site": "Boyagin",
                    "status": "failure",
                    "run_id": "r0",
                }
            )
            other_message = json.dumps(
                {
                    "message": "task_start",
                    "timestamp": _ts(NOW),
                    "task": "construct_L1_nc",
                }
            )
            self._write(
                log_dir,
                "construct_L1_nc.jsonl",
                [in_window, out_of_window, other_message, "{not valid json"],
            )

            records, skipped = _iter_result_records(
                log_dir, "construct_L1_nc", cutoff=NOW - timedelta(days=7)
            )

            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["run_id"], "r1")
            self.assertEqual(skipped, 1)

    def test_reads_rotated_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            current = json.dumps(
                {
                    "message": "task_site_result",
                    "timestamp": _ts(NOW),
                    "site": "Boyagin",
                    "status": "success",
                    "run_id": "current",
                }
            )
            backup = json.dumps(
                {
                    "message": "task_site_result",
                    "timestamp": _ts(NOW - timedelta(days=1)),
                    "site": "Litchfield",
                    "status": "success",
                    "run_id": "backup",
                }
            )
            self._write(log_dir, "construct_L1_nc.jsonl", [current])
            self._write(log_dir, "construct_L1_nc.jsonl.1", [backup])

            records, _ = _iter_result_records(
                log_dir, "construct_L1_nc", cutoff=NOW - timedelta(days=7)
            )

            run_ids = {r["run_id"] for r in records}
            self.assertEqual(run_ids, {"current", "backup"})


class TestBuildMatrix(unittest.TestCase):
    def test_combines_enablement_and_logs_across_sites_and_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            (log_dir / "construct_L1_nc.jsonl").write_text(
                json.dumps(
                    {
                        "message": "task_site_result",
                        "timestamp": _ts(NOW),
                        "site": "Boyagin",
                        "status": "failure",
                        "run_id": "r1",
                        "reason": "exception",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (log_dir / "push_slow_flux.jsonl").write_text("", encoding="utf-8")

            sites = ["Boyagin", "Litchfield"]
            tasks = ["construct_L1_nc", "push_slow_flux"]
            enabled = {
                ("Boyagin", "construct_L1_nc"): True,
                ("Boyagin", "push_slow_flux"): True,
                ("Litchfield", "construct_L1_nc"): True,
                ("Litchfield", "push_slow_flux"): False,
            }

            matrix, skipped = build_matrix(log_dir, sites, tasks, enabled, days=7)

            self.assertEqual(matrix["Boyagin"]["construct_L1_nc"]["state"], STATE_FAILURE)
            self.assertEqual(matrix["Boyagin"]["push_slow_flux"]["state"], STATE_NO_DATA)
            self.assertEqual(matrix["Litchfield"]["construct_L1_nc"]["state"], STATE_NO_DATA)
            self.assertEqual(matrix["Litchfield"]["push_slow_flux"]["state"], STATE_NA)
            self.assertEqual(skipped, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
