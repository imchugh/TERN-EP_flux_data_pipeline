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
    _build_site_markers,
    _declutter_markers,
    _project_lonlat,
    band_for_count,
    band_for_pct,
    build_group_matrix,
    build_report_data,
    build_windowed_quality_group,
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
            0.09: "green",
            0.1: "blue",
            0.99: "blue",
            1: "purple",
            1.99: "purple",
            2: "orange",
            4.99: "orange",
            5: "red",
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
            self.assertEqual(boyagin["pct_missing_last_1_days"]["state"], "blue")
            self.assertEqual(boyagin["pct_missing_last_7_days"]["state"], "orange")
            self.assertEqual(boyagin["pct_missing_last_30_days"]["state"], "red")
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


class TestBuildWindowedQualityGroup(unittest.TestCase):
    def _group(self, key):
        return next(g for g in GROUPS if g["key"] == key)

    def test_metadata_matches_group_definition(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = build_windowed_quality_group(
                self._group("variable_quality"), Path(tmp), ["Boyagin"], set(), {}
            )
            self.assertEqual(result["windows"], [1, 7, 30])
            self.assertEqual(result["default_window"], 7)
            self.assertEqual(result["columns"], ["Fco2", "Fh", "Fe", "Fsd"])
            self.assertEqual(result["pct_edges"], [5, 10, 20, 30])
            self.assertNotIn("column_groups", result)

    def test_threshold_quality_shares_the_same_pct_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = build_windowed_quality_group(
                self._group("threshold_quality"), Path(tmp), ["Boyagin"], set(), {}
            )
            self.assertEqual(result["pct_edges"], [5, 10, 20, 30])

    def test_window_selects_the_right_pct_and_band(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            _write_state(
                state_dir,
                "variable_quality",
                {
                    "Boyagin": {
                        "Fco2": {
                            "pct_outside_range_last_1_days": 3.0,
                            "pct_outside_range_last_7_days": 15.0,
                            "pct_outside_range_last_30_days": 35.0,
                        },
                        "Fh": None,
                        "Fe": None,
                        "Fsd": None,
                        "error": None,
                    }
                },
            )
            result = build_windowed_quality_group(
                self._group("variable_quality"), state_dir, ["Boyagin"], set(), {}
            )
            self.assertEqual(result["matrices"][1]["Boyagin"]["Fco2"]["state"], "green")
            self.assertEqual(
                result["matrices"][7]["Boyagin"]["Fco2"]["state"], "purple"
            )
            self.assertEqual(result["matrices"][30]["Boyagin"]["Fco2"]["state"], "red")
            # All three windows are always present as tooltip extras.
            cell_7d = result["matrices"][7]["Boyagin"]["Fco2"]
            self.assertEqual(cell_7d["pct_outside_range_last_1_days"], 3.0)
            self.assertEqual(cell_7d["pct_outside_range_last_30_days"], 35.0)

    def test_missing_state_file_is_no_data_for_every_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            # threshold_quality.json not written at all.
            result = build_windowed_quality_group(
                self._group("threshold_quality"), state_dir, ["Boyagin"], set(), {}
            )
            self.assertIsNone(result["updated_at"])
            matrix_7d = result["matrices"][7]
            self.assertEqual(matrix_7d["Boyagin"]["Vbat"]["state"], STATE_NO_DATA)

    def test_carries_map_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = build_windowed_quality_group(
                self._group("variable_quality"),
                Path(tmp),
                ["Boyagin"],
                set(),
                {"Boyagin": (147.6, -37.0)},
            )
            self.assertIn("Boyagin", result["markers"])
            self.assertEqual(result["default_map_metric"], "Fco2")
            self.assertEqual(
                [opt["key"] for opt in result["map_metric_options"]],
                ["Fco2", "Fh", "Fe", "Fsd"],
            )


class TestProjectLonlat(unittest.TestCase):
    def test_higher_longitude_projects_further_east(self):
        # Perth (~115.9E) is west of Sydney (~151.2E) -> smaller x.
        perth_x, _ = _project_lonlat(115.9, -31.9)
        sydney_x, _ = _project_lonlat(151.2, -33.9)
        self.assertLess(perth_x, sydney_x)

    def test_higher_latitude_projects_further_north(self):
        # Darwin (~-12.5) is north of Hobart (~-42.9) -> smaller y (SVG y
        # increases downward, so "further north" means a smaller y value).
        darwin_lat, hobart_lat = -12.5, -42.9
        _, darwin_y = _project_lonlat(130.8, darwin_lat)
        _, hobart_y = _project_lonlat(147.3, hobart_lat)
        self.assertLess(darwin_y, hobart_y)

    def test_nearby_sites_project_to_distinct_but_close_points(self):
        # MyallValeA/B are ~17km apart -- distinct points, but close relative
        # to the continental scale of the map (confirms zoom is needed to
        # tell them apart, without requiring the exact pixel values).
        ax, ay = _project_lonlat(150.019652, -30.54258001)
        bx, by = _project_lonlat(150.090833, -30.697222)
        self.assertNotEqual((ax, ay), (bx, by))
        self.assertLess(abs(ax - bx), 5)
        self.assertLess(abs(ay - by), 5)


class TestBuildSiteMarkers(unittest.TestCase):
    def test_only_includes_sites_present_in_coords(self):
        markers = _build_site_markers({"Boyagin": (147.6, -37.0)})
        self.assertEqual(set(markers), {"Boyagin"})
        self.assertIn("x", markers["Boyagin"])
        self.assertIn("y", markers["Boyagin"])

    def test_empty_input_gives_empty_output(self):
        self.assertEqual(_build_site_markers({}), {})


def _dist(a, b):
    return ((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2) ** 0.5


class TestDeclutterMarkers(unittest.TestCase):
    def test_two_coincident_markers_land_on_opposite_sides(self):
        markers = {
            "SiteA": {"x": 100.0, "y": 100.0},
            "SiteB": {"x": 100.0, "y": 100.0},
        }
        out = _declutter_markers(markers)
        self.assertAlmostEqual(_dist(out["SiteA"], out["SiteB"]), 12.0, places=3)
        for name in ("SiteA", "SiteB"):
            self.assertAlmostEqual(
                _dist(out[name], {"x": 100.0, "y": 100.0}), 6.0, places=3
            )

    def test_three_coincident_markers_all_separate(self):
        markers = {
            "SiteA": {"x": 50.0, "y": 50.0},
            "SiteB": {"x": 50.1, "y": 50.0},
            "SiteC": {"x": 50.0, "y": 50.1},
        }
        out = _declutter_markers(markers)
        positions = list(out.values())
        for i in range(len(positions)):
            for j in range(i + 1, len(positions)):
                self.assertGreater(_dist(positions[i], positions[j]), 5.0)

    def test_far_apart_markers_are_untouched(self):
        markers = {
            "SiteA": {"x": 0.0, "y": 0.0},
            "SiteB": {"x": 500.0, "y": 500.0},
        }
        self.assertEqual(_declutter_markers(markers), markers)

    def test_silverplains_wedgetail_regression(self):
        # Real coordinates: ~800m apart in reality, ~0.22 SVG units apart
        # when projected -- the exact case that motivated this function.
        markers = _build_site_markers(
            {
                "SilverPlains": (147.0875, -42.090556),
                "Wedgetail": (147.0794444, -42.09138889),
            }
        )
        self.assertGreater(_dist(markers["SilverPlains"], markers["Wedgetail"]), 10.0)


class TestBuildReportData(unittest.TestCase):
    def test_assembles_all_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            data = build_report_data(state_dir, ["Boyagin"], set())
            self.assertEqual(data["sites"], ["Boyagin"])
            self.assertEqual(len(data["groups"]), len(GROUPS))
            self.assertIn("grafana_url", data)
            self.assertIn("logger_status_url", data)

    def test_top_level_payload_carries_band_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = build_report_data(Path(tmp), ["Boyagin"], set())
            self.assertEqual(data["count_edges"], [1, 3, 5, 7])
            self.assertEqual(data["pct_edges"], [0.1, 1, 2, 5])

    def test_column_kinds_classify_count_vs_pct_per_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = build_report_data(Path(tmp), ["Boyagin"], set())
            groups = {g["key"]: g for g in data["groups"]}
            self.assertEqual(
                groups["missing_data"]["column_kinds"]["days_since_last_record"],
                "count",
            )
            self.assertEqual(
                groups["missing_data"]["column_kinds"]["pct_missing_last_1_days"],
                "pct",
            )
            self.assertTrue(
                all(
                    k == "pct"
                    for k in groups["variable_quality"]["column_kinds"].values()
                )
            )
            self.assertTrue(
                all(
                    k == "pct"
                    for k in groups["threshold_quality"]["column_kinds"].values()
                )
            )
            self.assertEqual(
                groups["nc_last_record"]["column_kinds"]["days_since_last_record"],
                "count",
            )
            self.assertTrue(
                all(
                    k == "count"
                    for k in groups["network_connectivity"]["column_kinds"].values()
                )
            )

    def test_missing_data_group_carries_map_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            data = build_report_data(
                state_dir,
                ["Boyagin"],
                set(),
                site_coords={"Boyagin": (147.6, -37.0)},
            )
            missing_data = next(g for g in data["groups"] if g["key"] == "missing_data")
            self.assertIn("Boyagin", missing_data["markers"])
            self.assertEqual(
                missing_data["default_map_metric"], "days_since_last_record"
            )
            self.assertEqual(
                [opt["key"] for opt in missing_data["map_metric_options"]],
                MISSING_DATA_COLUMNS,
            )
            other_group = next(
                g for g in data["groups"] if g["key"] == "nc_last_record"
            )
            self.assertNotIn("markers", other_group)

    def test_network_connectivity_group_carries_map_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            data = build_report_data(
                state_dir,
                ["Boyagin"],
                set(),
                site_coords={"Boyagin": (147.6, -37.0)},
            )
            connectivity = next(
                g for g in data["groups"] if g["key"] == "network_connectivity"
            )
            self.assertIn("Boyagin", connectivity["markers"])
            self.assertEqual(connectivity["default_map_metric"], "gateway")
            self.assertEqual(
                [opt["key"] for opt in connectivity["map_metric_options"]],
                ["gateway", "EC logger"],
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
