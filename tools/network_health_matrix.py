#!/usr/bin/env python3
"""Build a site x metric health report from the network state-task snapshot files.

Reads the per-task state JSON files that `services/network/state_task_orchestrator.py`
writes to its state directory (one `<task_name>.json` per task, refreshed by manually
running `python run.py construct_status_geojson` — this tool does not trigger that
itself, see the module's own docstring), and renders a self-contained HTML report:
a dropdown selects one of four health-metric groups (missing_data, data_quality,
nc_last_record, network_connectivity), each rendered as a site x sub-metric
heatmap. logger_status is a point-in-time device snapshot with no natural severity
model — trend/rolling-window health vs. "is the device reachable right now" are
different questions, so it has its own page, `logger_status_report.py`,
cross-linked from this one's header.

`network_connectivity` combines the `gateway_connectivity` and
`ec_logger_connectivity` state tasks into one group with two columns ("gateway",
"EC logger") side by side, so the two reachability checks for a site can be
compared at a glance instead of living behind separate dropdown entries. Its
metric is `days_since_last_success` (derived here from each state file's
`last_success` timestamp), not the raw `consecutive_failures` count the state
files store — a wall-clock metric reads the same regardless of how often the
underlying check runs, the same reasoning `nc_last_record` already applies.

`data_quality` similarly combines the `variable_quality` and `threshold_quality`
state tasks into one group, rendered as two labelled column groups ("Variable
quality" / "Threshold quality") side by side rather than flattened into one
undifferentiated row. Both underlying tasks report per-window figures
(`pct_outside_range_last_{1,7,30}_days`); a second "Time range" dropdown (default
7 days) lets the user pick which window colours the grid, instead of hardcoding
one window and relegating the rest to the tooltip. This is the only group with a
second dropdown — every other group's cells map onto one fixed metric already.

Cells are classified `na` (site not eligible for this task), `no_data` (eligible,
but missing from the state file), `error` (the task's own `error` field is
populated), or a 5-band severity ramp (green/blue/purple/orange/red) computed from
the metric value — day-count metrics (`days_since_last_record`,
`days_since_last_success`) and percentage metrics (`pct_missing_*`,
`pct_outside_range_*`) each have their own band edges, see `band_for_count`/
`band_for_pct`.

This tool only reads existing state files (via `state_task_orchestrator.STATE_DIR`/
`SITE_REGISTRY` and `connectivity.connectivity_sites()`) and does not modify or
execute any of the underlying monitoring tasks — see the "Layering constraint" note
in the project plan this was built from: `services/network/*.py` stays untouched,
all report-specific logic (thresholds, HTML, the Grafana link) lives here.

Usage (from project root, with ep_cntl activated):
    python -m tools.network_health_matrix [--output PATH] [--state-dir PATH]

Default --output: ./network_health_matrix.html
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure project root is on path when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.network_state_common import (
    GRAFANA_URL,
    STATE_NO_DATA,
    load_state,
    row_state,
    uniform_row,
)

_SEP = "─" * 64

# Cross-link to the logger-status page; both tools default to writing into
# the same directory, so a relative filename is enough.
LOGGER_STATUS_URL = "logger_status.html"

BANDS = ["green", "blue", "purple", "orange", "red"]
BAND_LABELS = {
    "green": "Good",
    "blue": "Fair",
    "purple": "Elevated",
    "orange": "Poor",
    "red": "Critical",
}

# Day-count bands (days_since_last_record, consecutive_failures): <1 green,
# 1-2 blue, 3-4 purple, 5-6 orange, 7+ red.
_COUNT_EDGES = [1, 3, 5, 7]

# Percentage bands (pct_missing_*, pct_outside_range_*): proposed defaults,
# <1% green, 1-5% blue, 5-15% purple, 15-30% orange, 30%+ red. Easy to retune.
_PCT_EDGES = [1, 5, 15, 30]

# Nested quality tasks report per-window (1/7/30-day) figures per sub-variable;
# the Data quality group's time-range dropdown picks which window colours the
# cell, defaulting to this. The other two windows always ride along as tooltip
# extras regardless of which one is selected.
DEFAULT_WINDOW_DAYS = 7

# Mirrors data_monitor.MONITOR_VARS / THRESHOLD_SPECS.keys() — duplicated
# rather than imported so this tool's pure logic doesn't pull in the heavier
# services.network import chain (pandas/xarray et al.) at module level; these
# are stable domain constants, not expected to drift silently.
VARIABLE_QUALITY_VARS = ["Fco2", "Fh", "Fe", "Fsd"]
THRESHOLD_QUALITY_VARS = ["Vbat", "Diag_IRGA", "Diag_SONIC"]

MISSING_DATA_COLUMNS = [
    "days_since_last_record",
    "pct_missing_last_1_days",
    "pct_missing_last_7_days",
    "pct_missing_last_30_days",
]
MISSING_DATA_MAP_METRIC_LABELS = {
    "days_since_last_record": "Days since last record",
    "pct_missing_last_1_days": "% missing (last 1 day)",
    "pct_missing_last_7_days": "% missing (last 7 days)",
    "pct_missing_last_30_days": "% missing (last 30 days)",
}
NC_LAST_RECORD_COLUMNS = ["days_since_last_record"]

NETWORK_CONNECTIVITY_COLUMNS = ["gateway", "EC logger"]
# Column label -> the state task file backing it (see the multi-source branch
# in build_group_matrix).
NETWORK_CONNECTIVITY_SOURCES = {
    "gateway": "gateway_connectivity",
    "EC logger": "ec_logger_connectivity",
}

# Australia's bounding box (mainland + Tasmania), from Natural Earth's
# 110m-resolution admin-0 countries dataset (public domain, no attribution
# required: naturalearthdata.com/about/terms-of-use). Both AUSTRALIA_OUTLINE_PATH
# below and every report's site markers (_project_lonlat) are projected through
# these same constants, so they always stay co-registered.
_MAP_LON_MIN = 113.338953
_MAP_LAT_MAX = -10.668186
_MAP_COS_FACTOR = 0.8898038451619625  # cos(mean latitude): corrects the x-scale
_MAP_SCALE = 20.0
_MAP_PAD = 20.0
MAP_VIEWBOX_WIDTH = 755.9
MAP_VIEWBOX_HEIGHT = 699.3

# Two subpaths (mainland, Tasmania) generated once from the dataset above via
# the same projection as _project_lonlat — not regenerated at runtime.
AUSTRALIA_OUTLINE_PATH = (
    "M631.3,622.8 L642.0,624.1 L643.2,647.9 L637.1,654.8 L635.3,670.9 "
    "L629.1,665.4 L616.7,679.3 L613.0,678.3 L602.1,677.6 L591.1,660.5 "
    "L588.7,647.3 L578.4,629.9 L578.9,620.7 L590.5,622.5 L607.7,629.4 "
    "L617.4,626.6 L631.3,622.8 Z M248.0,451.0 L229.1,461.2 L213.7,465.8 "
    "L210.2,476.3 L203.7,484.4 L188.6,484.9 L177.4,486.7 L161.7,483.1 "
    "L148.9,485.2 L136.6,486.2 L126.1,496.8 L120.9,495.9 L111.9,501.6 "
    "L103.4,507.9 L90.4,507.1 L78.5,507.1 L59.6,494.4 L50.0,490.6 L50.4,479.1 "
    "L59.3,476.4 L62.3,471.8 L61.7,464.6 L63.8,450.7 L61.8,438.9 L52.4,418.7 "
    "L49.5,407.3 L50.3,395.9 L43.2,382.8 L42.7,377.0 L34.9,369.0 L32.6,353.3 "
    "L22.5,337.5 L20.0,329.0 L27.8,337.6 L21.8,319.1 L30.6,324.9 L35.9,332.6 "
    "L35.6,322.4 L26.8,306.6 L25.1,300.3 L21.0,294.3 L22.9,282.8 L26.5,277.8 "
    "L29.0,267.8 L27.1,256.1 L34.4,241.8 L35.8,257.0 L43.3,243.2 L57.7,236.5 "
    "L66.4,228.0 L80.0,220.7 L88.1,219.1 L93.0,221.6 L107.0,214.1 L117.8,211.9 "
    "L120.5,207.5 L125.2,205.7 L135.1,206.2 L153.8,200.3 L163.5,191.4 "
    "L168.0,180.7 L178.4,170.6 L179.2,162.6 L179.7,151.7 L192.2,134.7 "
    "L199.6,152.0 L207.2,148.0 L200.9,138.6 L206.5,128.9 L214.3,133.2 "
    "L216.5,118.0 L226.2,108.1 L230.5,100.2 L239.4,96.8 L239.7,91.2 L247.5,93.6 "
    "L247.9,88.6 L255.7,85.7 L264.3,83.0 L277.4,92.2 L287.3,104.0 L298.4,104.2 "
    "L309.8,106.0 L306.0,95.0 L314.5,79.0 L322.5,73.8 L319.8,68.8 L327.5,57.4 "
    "L338.3,50.3 L347.4,52.7 L362.3,48.9 L362.0,38.7 L349.0,32.1 L358.5,29.2 "
    "L370.2,34.2 L379.7,42.4 L394.7,47.5 L399.8,45.5 L410.8,51.6 L421.2,45.9 "
    "L427.9,47.6 L432.0,43.8 L440.2,53.7 L435.5,64.4 L428.7,72.5 L422.6,73.1 "
    "L424.7,81.1 L419.4,91.1 L413.1,100.9 L414.4,106.6 L428.5,117.6 "
    "L442.2,124.1 L451.4,130.9 L464.3,142.8 L469.3,142.8 L478.6,147.9 "
    "L481.3,154.1 L498.3,160.9 L510.0,154.0 L513.5,143.3 L517.1,134.4 "
    "L519.3,123.4 L524.8,107.5 L522.3,97.9 L523.6,92.0 L521.5,80.6 L523.8,65.5 "
    "L527.3,61.5 L524.5,54.8 L528.8,44.2 L532.2,33.2 L532.6,27.5 L539.2,20.0 "
    "L544.2,29.8 L545.5,42.3 L549.9,44.7 L550.7,53.1 L557.1,63.3 L558.5,74.6 "
    "L557.8,81.9 L564.3,97.6 L575.7,90.1 L581.6,98.5 L590.1,106.3 L588.3,115.2 "
    "L592.1,132.3 L594.8,142.3 L599.3,144.8 L604.1,161.9 L602.4,172.2 "
    "L608.1,185.8 L627.4,196.3 L640.0,205.8 L651.9,214.5 L649.6,219.3 "
    "L659.8,231.8 L666.7,253.5 L673.8,249.1 L681.0,257.8 L685.4,254.7 "
    "L688.4,275.9 L701.1,288.2 L709.3,295.8 L723.2,312.0 L728.2,328.1 "
    "L728.7,339.5 L727.5,351.8 L735.9,368.8 L734.9,386.5 L731.8,395.8 "
    "L727.0,413.6 L727.4,425.1 L723.9,439.4 L716.0,457.6 L702.8,467.5 "
    "L696.3,483.0 L690.4,492.8 L685.1,510.1 L678.3,520.1 L673.8,535.0 "
    "L671.5,548.8 L672.4,555.1 L662.2,562.1 L642.3,562.8 L625.8,571.0 "
    "L617.6,578.8 L606.9,587.4 L592.2,578.5 L581.3,575.0 L584.0,564.6 "
    "L574.3,568.3 L558.7,582.8 L543.3,577.4 L533.2,574.2 L523.1,572.8 "
    "L505.8,567.0 L494.3,554.7 L491.0,539.5 L486.9,529.4 L478.1,521.3 "
    "L461.0,518.9 L466.9,509.2 L462.6,494.3 L453.9,508.2 L438.0,511.8 "
    "L447.3,500.8 L450.0,489.2 L456.9,479.4 L455.5,464.6 L441.0,481.7 "
    "L429.9,488.5 L423.1,504.4 L409.2,496.2 L409.7,485.6 L398.6,471.1 "
    "L389.2,463.6 L392.6,459.0 L369.7,446.9 L357.2,446.3 L340.1,436.6 "
    "L308.2,438.4 L285.2,445.6 L264.9,452.3 L248.0,451.0 Z"
)


def _project_lonlat(lon: float, lat: float) -> tuple[float, float]:
    """Project (lon, lat) into the Australia outline's SVG viewBox.

    A simple equirectangular projection with a cos(mean-latitude) x-scale
    correction — Australia's small extent makes this a reasonable schematic
    approximation, not a claim of cartographic precision.
    """
    x = _MAP_PAD + (lon - _MAP_LON_MIN) * _MAP_COS_FACTOR * _MAP_SCALE
    y = _MAP_PAD + (_MAP_LAT_MAX - lat) * _MAP_SCALE
    return round(x, 1), round(y, 1)


def _build_site_markers(
    site_coords: dict[str, tuple[float, float]],
) -> dict[str, dict[str, float]]:
    """Project each site's (lon, lat) into the Australia outline's viewBox."""
    markers: dict[str, dict[str, float]] = {}
    for site, (lon, lat) in site_coords.items():
        x, y = _project_lonlat(lon, lat)
        markers[site] = {"x": x, "y": y}
    return markers


def _band_from_edges(value: float | None, edges: list[float]) -> str | None:
    """Map value to BANDS via ascending edges: value < edges[i] gives BANDS[i]."""
    if value is None:
        return None
    for edge, band in zip(edges, BANDS, strict=False):
        if value < edge:
            return band
    return BANDS[-1]


def band_for_count(value: float | int | None) -> str | None:
    """Return the severity band for a day-count/failure-count metric, or None."""
    return _band_from_edges(value, _COUNT_EDGES)


def band_for_pct(value: float | None) -> str | None:
    """Return the severity band for a percentage metric, or None."""
    return _band_from_edges(value, _PCT_EDGES)


def _fmt_days(value: float | int | None) -> str:
    return "" if value is None else f"{value:.0f}d"


def _fmt_pct(value: float | None) -> str:
    return "" if value is None else f"{value:.1f}%"


def _missing_data_row(result: dict) -> dict[str, dict]:
    days = result.get("days_since_last_record")
    row = {
        "days_since_last_record": {
            "state": band_for_count(days) or STATE_NO_DATA,
            "value": days,
            "display": _fmt_days(days),
        }
    }
    for window in (1, 7, 30):
        key = f"pct_missing_last_{window}_days"
        value = result.get(key)
        row[key] = {
            "state": band_for_pct(value) or STATE_NO_DATA,
            "value": value,
            "display": _fmt_pct(value),
        }
    return row


def _nested_quality_row(
    result: dict, variables: list[str], window: int
) -> dict[str, dict]:
    """Build one column-group's cells, coloured by `window`'s pct_outside_range.

    All three windows are always included as tooltip extras, regardless of
    which one is currently selected — only `state`/`value`/`display` depend
    on `window`.
    """
    row = {}
    for var in variables:
        sub = result.get(var)
        if sub is None:
            row[var] = {"state": STATE_NO_DATA, "value": None, "display": ""}
            continue
        primary = sub.get(f"pct_outside_range_last_{window}_days")
        row[var] = {
            "state": band_for_pct(primary) or STATE_NO_DATA,
            "value": primary,
            "display": _fmt_pct(primary),
            "pct_outside_range_last_1_days": sub.get("pct_outside_range_last_1_days"),
            "pct_outside_range_last_7_days": sub.get("pct_outside_range_last_7_days"),
            "pct_outside_range_last_30_days": sub.get("pct_outside_range_last_30_days"),
        }
    return row


def _nc_last_record_row(result: dict) -> dict[str, dict]:
    days = result.get("days_since_last_record")
    return {
        "days_since_last_record": {
            "state": band_for_count(days) or STATE_NO_DATA,
            "value": days,
            "display": _fmt_days(days),
        }
    }


def _connectivity_cell(result: dict, now: datetime) -> dict:
    """Build one gateway/EC-logger connectivity cell: days since last_success.

    A `last_success` of None means the site has never once succeeded since its
    state block was created — forced to the worst band ("red"/"never") rather
    than falling through to `no_data`, which is reserved for a site missing
    from the state file entirely (a different, less alarming situation).
    """
    last_success = result.get("last_success")
    if last_success is None:
        days: int | None = None
        state = "red"
        display = "never"
    else:
        days = (now - datetime.fromisoformat(last_success)).days
        state = band_for_count(days) or "red"
        display = _fmt_days(days)
    return {
        "state": state,
        "value": days,
        "display": display,
        "consecutive_failures": result.get("consecutive_failures"),
        "last_success": last_success,
        "last_attempt": result.get("last_attempt"),
        "last_latency_ms": result.get("last_latency_ms"),
    }


GROUPS = [
    {
        "key": "missing_data",
        "label": "Missing data",
        "columns": MISSING_DATA_COLUMNS,
        "row_fn": _missing_data_row,
        "scoped": False,
        "has_map": True,
    },
    {
        "key": "data_quality",
        "label": "Data quality",
        "column_groups": [
            {
                "key": "variable_quality",
                "label": "Variable quality",
                "columns": VARIABLE_QUALITY_VARS,
            },
            {
                "key": "threshold_quality",
                "label": "Threshold quality",
                "columns": THRESHOLD_QUALITY_VARS,
            },
        ],
        "columns": VARIABLE_QUALITY_VARS + THRESHOLD_QUALITY_VARS,
        "windows": [1, 7, 30],
        "default_window": DEFAULT_WINDOW_DAYS,
        "scoped": False,
    },
    {
        "key": "nc_last_record",
        "label": "NetCDF last record",
        "columns": NC_LAST_RECORD_COLUMNS,
        "row_fn": _nc_last_record_row,
        "scoped": False,
    },
    {
        "key": "network_connectivity",
        "label": "Network connectivity",
        "columns": NETWORK_CONNECTIVITY_COLUMNS,
        "sources": NETWORK_CONNECTIVITY_SOURCES,
        "scoped": True,
    },
]


def _build_connectivity_matrix(
    group: dict,
    state_dir: Path,
    sites: list[str],
    connectivity_eligible: set[str],
    now: datetime,
) -> tuple[dict[str, dict[str, dict]], str]:
    """Build {site: {column: cell}} for a multi-source group (network_connectivity).

    Each column is backed by its own state file (`group["sources"]`), unlike
    single-source groups where every column comes from one state file.
    """
    sites_data: dict[str, dict] = {}
    updated_parts: list[str] = []
    for column, source_key in group["sources"].items():
        state = load_state(state_dir, source_key)
        sites_data[column] = state.get("sites", {}) if state else {}
        source_updated = state.get("updated_at") if state else None
        updated_parts.append(f"{column}: {source_updated or 'no state file'}")
    updated_at = "; ".join(updated_parts)

    matrix: dict[str, dict[str, dict]] = {}
    for site in sites:
        eligible = site in connectivity_eligible if group["scoped"] else True
        row: dict[str, dict] = {}
        for column in group["columns"]:
            result = sites_data[column].get(site)
            base = row_state(eligible, result)
            if base is not None:
                row[column] = uniform_row(
                    [column], base, result.get("error") if result else None
                )[column]
            else:
                row[column] = _connectivity_cell(result, now)
        matrix[site] = row

    return matrix, updated_at


def build_group_matrix(
    group: dict,
    state_dir: Path,
    sites: list[str],
    connectivity_eligible: set[str],
    now: datetime | None = None,
) -> tuple[dict[str, dict[str, dict]], str | None]:
    """Build {site: {column: cell}} for one group, plus its state file's updated_at."""
    if "sources" in group:
        return _build_connectivity_matrix(
            group, state_dir, sites, connectivity_eligible, now or datetime.now(UTC)
        )

    state = load_state(state_dir, group["key"])
    sites_data = state.get("sites", {}) if state else {}
    updated_at = state.get("updated_at") if state else None

    matrix: dict[str, dict[str, dict]] = {}
    for site in sites:
        eligible = site in connectivity_eligible if group["scoped"] else True
        result = sites_data.get(site)
        base = row_state(eligible, result)
        if base is not None:
            matrix[site] = uniform_row(
                group["columns"], base, result.get("error") if result else None
            )
        else:
            matrix[site] = group["row_fn"](result)

    return matrix, updated_at


def build_data_quality_group(
    group: dict,
    state_dir: Path,
    sites: list[str],
    connectivity_eligible: set[str],
) -> dict:
    """Build the full report entry for the data_quality group: one matrix per window.

    Unlike `build_group_matrix`, this returns the complete groups_out entry
    (not a `(matrix, updated_at)` pair) since its shape genuinely differs from
    every other group — multiple precomputed matrices, one per time-range
    window, rather than one.
    """
    sub_sites_data: dict[str, dict] = {}
    updated_parts: list[str] = []
    for cg in group["column_groups"]:
        state = load_state(state_dir, cg["key"])
        sub_sites_data[cg["key"]] = state.get("sites", {}) if state else {}
        source_updated = state.get("updated_at") if state else None
        updated_parts.append(f"{cg['label']}: {source_updated or 'no state file'}")
    updated_at = "; ".join(updated_parts)

    matrices: dict[int, dict[str, dict[str, dict]]] = {}
    for window in group["windows"]:
        matrix: dict[str, dict[str, dict]] = {}
        for site in sites:
            eligible = site in connectivity_eligible if group["scoped"] else True
            row: dict[str, dict] = {}
            for cg in group["column_groups"]:
                result = sub_sites_data[cg["key"]].get(site)
                base = row_state(eligible, result)
                if base is not None:
                    row.update(
                        uniform_row(
                            cg["columns"],
                            base,
                            result.get("error") if result else None,
                        )
                    )
                else:
                    row.update(_nested_quality_row(result, cg["columns"], window))
            matrix[site] = row
        matrices[window] = matrix

    return {
        "key": group["key"],
        "label": group["label"],
        "columns": group["columns"],
        "column_groups": [
            {"label": cg["label"], "columns": cg["columns"]}
            for cg in group["column_groups"]
        ],
        "windows": group["windows"],
        "default_window": group["default_window"],
        "updated_at": updated_at,
        "matrices": matrices,
    }


def build_report_data(
    state_dir: Path,
    sites: list[str],
    connectivity_eligible: set[str],
    now: datetime | None = None,
    site_coords: dict[str, tuple[float, float]] | None = None,
) -> dict:
    """Assemble the full report payload: every group's matrix."""
    now = now or datetime.now(UTC)
    site_coords = site_coords or {}
    groups_out = []
    for group in GROUPS:
        if "column_groups" in group:
            groups_out.append(
                build_data_quality_group(group, state_dir, sites, connectivity_eligible)
            )
            continue
        matrix, updated_at = build_group_matrix(
            group, state_dir, sites, connectivity_eligible, now
        )
        group_entry = {
            "key": group["key"],
            "label": group["label"],
            "columns": group["columns"],
            "updated_at": updated_at,
            "matrix": matrix,
        }
        if group.get("has_map"):
            group_entry["markers"] = _build_site_markers(site_coords)
            group_entry["map_outline"] = AUSTRALIA_OUTLINE_PATH
            group_entry["map_viewbox"] = f"0 0 {MAP_VIEWBOX_WIDTH} {MAP_VIEWBOX_HEIGHT}"
            group_entry["map_metric_options"] = [
                {"key": col, "label": MISSING_DATA_MAP_METRIC_LABELS[col]}
                for col in group["columns"]
            ]
            group_entry["default_map_metric"] = "days_since_last_record"
        groups_out.append(group_entry)

    return {
        "sites": sites,
        "groups": groups_out,
        "grafana_url": GRAFANA_URL,
        "logger_status_url": LOGGER_STATUS_URL,
        "band_labels": BAND_LABELS,
    }


_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Network health matrix</title>
<style>
  :root {
    color-scheme: light;
    --surface-1:      #fcfcfb;
    --page:           #f9f9f7;
    --text-primary:   #0b0b0b;
    --text-secondary: #52514e;
    --muted:          #898781;
    --gridline:       #e1e0d9;
    --border:         rgba(11,11,11,0.10);
    --band-green:     #187114;
    --band-blue:      #5090f7;
    --band-purple:    #7031b5;
    --band-orange:    #d36e37;
    --band-red:       #9c0038;
    --state-na:       #e1e0d9;
    --state-no-data:  #f2f1ec;
    --state-error:    #9c0038;
    --map-land:       #eceae3;
  }
  @media (prefers-color-scheme: dark) {
    :root:where(:not([data-theme="light"])) {
      color-scheme: dark;
      --surface-1:      #1a1a19;
      --page:           #0d0d0d;
      --text-primary:   #ffffff;
      --text-secondary: #c3c2b7;
      --muted:          #898781;
      --gridline:       #2c2c2a;
      --border:         rgba(255,255,255,0.10);
      --band-green:     #4fa830;
      --band-blue:      #2b93c5;
      --band-purple:    #7c3fe3;
      --band-orange:    #c58544;
      --band-red:       #c2426f;
      --state-na:       #383835;
      --state-no-data:  #232322;
      --state-error:    #c2426f;
      --map-land:       #26261f;
    }
  }
  :root[data-theme="dark"] {
    color-scheme: dark;
    --surface-1:      #1a1a19;
    --page:           #0d0d0d;
    --text-primary:   #ffffff;
    --text-secondary: #c3c2b7;
    --muted:          #898781;
    --gridline:       #2c2c2a;
    --border:         rgba(255,255,255,0.10);
    --band-green:     #4fa830;
    --band-blue:      #2b93c5;
    --band-purple:    #7c3fe3;
    --band-orange:    #c58544;
    --band-red:       #c2426f;
    --state-na:       #383835;
    --state-no-data:  #232322;
    --state-error:    #c2426f;
    --map-land:       #26261f;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--page);
    color: var(--text-primary);
    font: 14px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif;
    padding: 24px;
  }
  h1 { font-size: 18px; margin: 0 0 4px; }
  h2 { font-size: 15px; margin: 28px 0 8px; }
  .meta { color: var(--text-secondary); margin: 0 0 16px; font-size: 13px; }
  .controls { display: flex; gap: 10px; align-items: center; margin-bottom: 16px; }
  .controls label { font-size: 13px; color: var(--text-secondary); }
  .controls select {
    font: inherit; font-size: 13px; padding: 6px 10px; border-radius: 6px;
    border: 1px solid var(--border); background: var(--surface-1); color: var(--text-primary);
  }
  .legend {
    display: flex; flex-wrap: wrap; gap: 16px; align-items: center;
    margin-bottom: 16px; font-size: 13px; color: var(--text-secondary);
  }
  .legend-item { display: flex; gap: 6px; align-items: center; }
  .swatch {
    width: 16px; height: 16px; border-radius: 4px;
    display: flex; align-items: center; justify-content: center;
    font-size: 10px; font-weight: 600; color: #ffffff;
  }
  .content-row { display: flex; flex-wrap: wrap; align-items: stretch; gap: 20px; }
  .grid-wrap {
    overflow: auto; max-width: 100%; border: 1px solid var(--border);
    border-radius: 6px; flex: 1 1 400px; min-width: 300px;
  }
  table { border-collapse: separate; border-spacing: 2px; background: var(--surface-1); }
  th, td { padding: 0; }
  th.site-header, td.site-name {
    position: sticky; left: 0; background: var(--surface-1);
    text-align: right; padding: 0 10px 0 6px; white-space: nowrap;
    font-size: 12px; color: var(--text-primary);
    border-right: 1px solid var(--border);
  }
  td.site-name a { color: var(--text-primary); text-decoration: none; border-bottom: 1px dotted var(--muted); }
  td.site-name a:hover { color: var(--band-blue); }
  th.col-header {
    position: sticky; top: 0; background: var(--surface-1);
    height: 110px; z-index: 2; border-bottom: 1px solid var(--border);
    width: 140px; min-width: 140px; max-width: 140px;
  }
  th.col-header span {
    position: absolute; bottom: 6px; left: 8px;
    transform: rotate(-45deg); transform-origin: left bottom;
    white-space: nowrap; font-size: 12px; font-weight: 500; color: var(--text-secondary);
  }
  th.site-header { z-index: 3; top: 0; }
  th.group-header {
    position: sticky; top: 0; height: 28px; background: var(--surface-1);
    text-align: center; font-size: 12px; font-weight: 600; z-index: 3;
    color: var(--text-secondary); border-bottom: 1px solid var(--border);
    border-left: 1px solid var(--border);
  }
  table.two-row-header th.col-header { top: 28px; }
  th.group-spacer, td.group-spacer { width: 14px; min-width: 14px; border: none; }
  th.group-spacer {
    position: sticky; top: 0; z-index: 3; background: var(--surface-1);
  }
  .hidden { display: none; }
  td.cell {
    width: 140px; height: 28px; min-width: 140px; border-radius: 4px;
    text-align: center; vertical-align: middle; cursor: default;
    font-size: 11px; font-weight: 700; outline-offset: 2px; color: #ffffff;
  }
  td.cell.green  { background: var(--band-green); }
  td.cell.blue   { background: var(--band-blue); }
  td.cell.purple { background: var(--band-purple); }
  td.cell.orange { background: var(--band-orange); }
  td.cell.red    { background: var(--band-red); }
  td.cell.na      { background: var(--state-na); color: var(--muted); }
  td.cell.no_data { background: var(--state-no-data); color: var(--muted); border: 1px dashed var(--gridline); }
  td.cell.error   { background: var(--state-error); }
  td.cell:hover, td.cell:focus-visible { outline: 2px solid var(--text-primary); }
  .page-nav { margin: 0 0 12px; font-size: 13px; }
  .page-nav a { color: var(--band-blue); text-decoration: none; }
  .page-nav a:hover { text-decoration: underline; }
  #tooltip {
    position: fixed; pointer-events: none; z-index: 10;
    background: var(--text-primary); color: var(--surface-1);
    padding: 8px 10px; border-radius: 6px; font-size: 12px; line-height: 1.5;
    max-width: 340px; box-shadow: 0 4px 12px var(--border);
    display: none; white-space: pre-line;
  }
  #tooltip .tt-value { font-weight: 700; }
  td.cell.ghost, th.col-header.ghost span { opacity: 0.35; }
  #map-wrap {
    flex: 1.3 1 400px; min-width: 320px; max-width: 100%;
    display: flex; flex-direction: column;
  }
  .map-toolbar {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 8px; font-size: 13px; color: var(--text-secondary);
  }
  .map-toolbar button {
    font: inherit; font-size: 12px; padding: 4px 10px; border-radius: 6px;
    border: 1px solid var(--border); background: var(--surface-1);
    color: var(--text-primary); cursor: pointer;
  }
  .map-toolbar button:hover { background: var(--page); }
  .map-frame {
    border: 1px solid var(--border); border-radius: 6px;
    background: var(--surface-1); overflow: hidden;
    flex: 1 1 auto; min-height: 300px;
  }
  #map-svg { width: 100%; height: 100%; touch-action: none; cursor: grab; }
  #map-svg.dragging { cursor: grabbing; }
  #map-outline { fill: var(--map-land); stroke: var(--border); stroke-width: 1; }
  .marker {
    stroke: var(--surface-1); stroke-width: 1.5; cursor: default;
    outline-offset: 2px;
  }
  .marker.green  { fill: var(--band-green); }
  .marker.blue   { fill: var(--band-blue); }
  .marker.purple { fill: var(--band-purple); }
  .marker.orange { fill: var(--band-orange); }
  .marker.red    { fill: var(--band-red); }
  .marker.na      { fill: var(--state-na); }
  .marker.no_data { fill: var(--state-no-data); }
  .marker.error   { fill: var(--state-error); }
  .marker:hover, .marker:focus-visible { stroke: var(--text-primary); }
  footer { margin-top: 12px; color: var(--muted); font-size: 12px; }
</style>
</head>
<body>
  <h1>Network health matrix</h1>
  <p class="page-nav"><a id="logger-status-link" href="#">Logger status →</a></p>
  <p class="meta" id="meta"></p>
  <div class="controls">
    <label for="group-select">Metric group</label>
    <select id="group-select"></select>
    <label for="window-select" id="window-label" class="hidden">Time range</label>
    <select id="window-select" class="hidden"></select>
    <label for="map-metric-select" id="map-metric-label" class="hidden">
      Map metric
    </label>
    <select id="map-metric-select" class="hidden"></select>
  </div>
  <div class="legend" id="legend"></div>
  <div class="content-row">
    <div class="grid-wrap"><table id="grid"></table></div>
    <div id="map-wrap" class="hidden">
      <div class="map-toolbar">
        <span id="map-caption"></span>
        <button type="button" id="map-reset">Reset view</button>
      </div>
      <div class="map-frame">
        <svg id="map-svg" xmlns="http://www.w3.org/2000/svg">
          <path id="map-outline"></path>
          <g id="map-markers"></g>
        </svg>
      </div>
    </div>
  </div>
  <footer id="footer"></footer>

  <div id="tooltip"></div>

<script id="report-data" type="application/json">__DATA_JSON__</script>
<script>
(function () {
  var BAND_SYMBOL = { na: "\\u2013", no_data: "?", error: "!" };
  var STATE_LABEL = { na: "Not applicable", no_data: "No data", error: "Task error" };

  var data = JSON.parse(document.getElementById("report-data").textContent);
  var tooltip = document.getElementById("tooltip");
  document.getElementById("logger-status-link").href = data.logger_status_url;

  function addRow(container, label, value) {
    var div = document.createElement("div");
    var strong = document.createElement("span");
    strong.className = "tt-value";
    strong.textContent = value;
    div.appendChild(document.createTextNode(label + ": "));
    div.appendChild(strong);
    container.appendChild(div);
  }

  function showTooltip(el, title, state, cellData) {
    tooltip.textContent = "";
    var titleEl = document.createElement("div");
    titleEl.className = "tt-value";
    titleEl.textContent = title;
    tooltip.appendChild(titleEl);

    var label = data.band_labels[state] || STATE_LABEL[state] || state;
    addRow(tooltip, "Status", label);
    if (cellData.value !== undefined && cellData.value !== null) addRow(tooltip, "Value", cellData.display || String(cellData.value));
    if (cellData.error) addRow(tooltip, "Error", cellData.error);
    Object.keys(cellData).forEach(function (key) {
      if (["state", "value", "display", "error"].indexOf(key) !== -1) return;
      if (cellData[key] === null || cellData[key] === undefined) return;
      addRow(tooltip, key, String(cellData[key]));
    });

    tooltip.style.display = "block";
    var rect = el.getBoundingClientRect();
    var top = rect.bottom + 8;
    var left = rect.left;
    if (left + 340 > window.innerWidth) left = window.innerWidth - 348;
    tooltip.style.top = top + "px";
    tooltip.style.left = Math.max(8, left) + "px";
  }

  function hideTooltip() { tooltip.style.display = "none"; }

  function siteLink(site) {
    var a = document.createElement("a");
    a.href = data.grafana_url;
    a.target = "_blank";
    a.rel = "noopener";
    a.textContent = site;
    return a;
  }

  // ---- metric group matrix ----

  var select = document.getElementById("group-select");
  data.groups.forEach(function (g) {
    var opt = document.createElement("option");
    opt.value = g.key;
    opt.textContent = g.label;
    select.appendChild(opt);
  });

  var legend = document.getElementById("legend");
  ["green", "blue", "purple", "orange", "red"].forEach(function (band) {
    var item = document.createElement("div");
    item.className = "legend-item";
    var sw = document.createElement("span");
    sw.className = "swatch";
    sw.style.background = "var(--band-" + band + ")";
    item.appendChild(sw);
    item.appendChild(document.createTextNode(data.band_labels[band]));
    legend.appendChild(item);
  });
  [["na", "\\u2013", "Not applicable"], ["no_data", "?", "No data"], ["error", "!", "Task error"]].forEach(function (t) {
    var item = document.createElement("div");
    item.className = "legend-item";
    var sw = document.createElement("span");
    sw.className = "swatch " + t[0];
    sw.style.background = "var(--state-" + t[0].replace("_", "-") + ")";
    sw.textContent = t[1];
    item.appendChild(sw);
    item.appendChild(document.createTextNode(t[2]));
    legend.appendChild(item);
  });

  var table = document.getElementById("grid");
  var windowLabel = document.getElementById("window-label");
  var windowSelect = document.getElementById("window-select");
  var currentWindow = null;

  function populateWindowSelect(group) {
    windowSelect.textContent = "";
    group.windows.forEach(function (w) {
      var opt = document.createElement("option");
      opt.value = w;
      opt.textContent = "Last " + w + (w === 1 ? " day" : " days");
      windowSelect.appendChild(opt);
    });
    var selected = currentWindow !== null && group.windows.indexOf(currentWindow) !== -1
      ? currentWindow : group.default_window;
    windowSelect.value = selected;
    currentWindow = selected;
  }

  // ---- map (missing_data only) ----

  var mapMetricLabel = document.getElementById("map-metric-label");
  var mapMetricSelect = document.getElementById("map-metric-select");
  var mapWrap = document.getElementById("map-wrap");
  var mapCaption = document.getElementById("map-caption");
  var mapResetBtn = document.getElementById("map-reset");
  var mapSvg = document.getElementById("map-svg");
  var mapOutline = document.getElementById("map-outline");
  var mapMarkersGroup = document.getElementById("map-markers");
  var currentMapMetric = null;
  var mapInitializedForKey = null;
  var mapViewBox = null;
  var mapBaseViewBox = null;

  function populateMapMetricSelect(group) {
    mapMetricSelect.textContent = "";
    group.map_metric_options.forEach(function (opt) {
      var o = document.createElement("option");
      o.value = opt.key;
      o.textContent = opt.label;
      mapMetricSelect.appendChild(o);
    });
    var known = group.map_metric_options.some(function (o) {
      return o.key === currentMapMetric;
    });
    var selected = currentMapMetric !== null && known
      ? currentMapMetric : group.default_map_metric;
    mapMetricSelect.value = selected;
    currentMapMetric = selected;
  }

  function setMapViewBoxAttr() {
    mapSvg.setAttribute(
      "viewBox",
      mapViewBox.x + " " + mapViewBox.y + " " + mapViewBox.w + " " + mapViewBox.h
    );
  }

  function resetMapView() {
    if (!mapBaseViewBox) return;
    mapViewBox = {
      x: mapBaseViewBox.x, y: mapBaseViewBox.y,
      w: mapBaseViewBox.w, h: mapBaseViewBox.h,
    };
    setMapViewBoxAttr();
  }

  function mapPointFromEvent(evt) {
    var rect = mapSvg.getBoundingClientRect();
    var px = (evt.clientX - rect.left) / rect.width;
    var py = (evt.clientY - rect.top) / rect.height;
    return { x: mapViewBox.x + px * mapViewBox.w, y: mapViewBox.y + py * mapViewBox.h };
  }

  mapSvg.addEventListener("wheel", function (evt) {
    if (!mapViewBox) return;
    evt.preventDefault();
    var zoomFactor = evt.deltaY > 0 ? 1.15 : 1 / 1.15;
    var pt = mapPointFromEvent(evt);
    var newW = Math.min(
      mapBaseViewBox.w, Math.max(mapBaseViewBox.w / 20, mapViewBox.w * zoomFactor)
    );
    var newH = Math.min(
      mapBaseViewBox.h, Math.max(mapBaseViewBox.h / 20, mapViewBox.h * zoomFactor)
    );
    mapViewBox.x = pt.x - (pt.x - mapViewBox.x) * (newW / mapViewBox.w);
    mapViewBox.y = pt.y - (pt.y - mapViewBox.y) * (newH / mapViewBox.h);
    mapViewBox.w = newW;
    mapViewBox.h = newH;
    setMapViewBoxAttr();
  }, { passive: false });

  var mapDragging = false;
  var mapDragLast = null;
  mapSvg.addEventListener("pointerdown", function (evt) {
    mapDragging = true;
    mapDragLast = { x: evt.clientX, y: evt.clientY };
    mapSvg.classList.add("dragging");
    mapSvg.setPointerCapture(evt.pointerId);
  });
  mapSvg.addEventListener("pointermove", function (evt) {
    if (!mapDragging || !mapViewBox) return;
    var rect = mapSvg.getBoundingClientRect();
    mapViewBox.x -= (evt.clientX - mapDragLast.x) / rect.width * mapViewBox.w;
    mapViewBox.y -= (evt.clientY - mapDragLast.y) / rect.height * mapViewBox.h;
    mapDragLast = { x: evt.clientX, y: evt.clientY };
    setMapViewBoxAttr();
  });
  function endMapDrag() {
    mapDragging = false;
    mapSvg.classList.remove("dragging");
  }
  mapSvg.addEventListener("pointerup", endMapDrag);
  mapSvg.addEventListener("pointercancel", endMapDrag);
  mapResetBtn.addEventListener("click", resetMapView);

  function renderMap(group) {
    var metric = currentMapMetric;
    var metricLabel = group.map_metric_options.filter(function (o) {
      return o.key === metric;
    })[0].label;

    if (mapInitializedForKey !== group.key) {
      mapOutline.setAttribute("d", group.map_outline);
      var parts = group.map_viewbox.split(" ").map(Number);
      mapBaseViewBox = { x: parts[0], y: parts[1], w: parts[2], h: parts[3] };
      resetMapView();
      mapInitializedForKey = group.key;
    }

    mapMarkersGroup.textContent = "";
    data.sites.forEach(function (site) {
      var pos = group.markers[site];
      if (!pos) return;
      var cellData = group.matrix[site][metric];
      var circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      circle.setAttribute("cx", pos.x);
      circle.setAttribute("cy", pos.y);
      circle.setAttribute("r", 5);
      circle.setAttribute("class", "marker " + cellData.state);
      circle.setAttribute("tabindex", "0");
      var describe = function () {
        showTooltip(circle, site + " \\u2014 " + metricLabel, cellData.state, cellData);
      };
      circle.addEventListener("pointerenter", describe);
      circle.addEventListener("focus", describe);
      circle.addEventListener("pointerleave", hideTooltip);
      circle.addEventListener("blur", hideTooltip);
      mapMarkersGroup.appendChild(circle);
    });

    mapCaption.textContent = metricLabel + " \\u2014 " + data.sites.length + " sites";
  }

  function renderGroup(key) {
    var group = data.groups.filter(function (g) { return g.key === key; })[0];
    table.textContent = "";
    table.classList.toggle("two-row-header", !!group.column_groups);

    var windowed = !!group.matrices;
    windowLabel.classList.toggle("hidden", !windowed);
    windowSelect.classList.toggle("hidden", !windowed);
    var matrix;
    if (windowed) {
      populateWindowSelect(group);
      matrix = group.matrices[windowSelect.value];
    } else {
      matrix = group.matrix;
    }

    var hasMap = !!group.markers;
    mapMetricLabel.classList.toggle("hidden", !hasMap);
    mapMetricSelect.classList.toggle("hidden", !hasMap);
    mapWrap.classList.toggle("hidden", !hasMap);
    if (hasMap) {
      populateMapMetricSelect(group);
    }

    document.getElementById("meta").textContent =
      data.sites.length + " sites \\u00d7 " + group.columns.length + " metrics \\u2014 " +
      (group.updated_at ? "state updated " + group.updated_at : "no state file found") +
      " \\u2014 report generated " + data.generated_at;

    var thead = document.createElement("thead");

    if (group.column_groups) {
      var groupHeadRow = document.createElement("tr");
      var groupCorner = document.createElement("th");
      groupCorner.className = "site-header";
      groupCorner.rowSpan = 2;
      groupHeadRow.appendChild(groupCorner);
      group.column_groups.forEach(function (cg, i) {
        var th = document.createElement("th");
        th.className = "group-header";
        th.colSpan = cg.columns.length;
        th.textContent = cg.label;
        groupHeadRow.appendChild(th);
        if (i < group.column_groups.length - 1) {
          var spacer = document.createElement("th");
          spacer.className = "group-spacer";
          spacer.rowSpan = 2;
          groupHeadRow.appendChild(spacer);
        }
      });
      thead.appendChild(groupHeadRow);
    }

    var headRow = document.createElement("tr");
    if (!group.column_groups) {
      var corner = document.createElement("th");
      corner.className = "site-header";
      headRow.appendChild(corner);
    }
    group.columns.forEach(function (col) {
      var th = document.createElement("th");
      var ghostHeader = hasMap && col !== currentMapMetric ? " ghost" : "";
      th.className = "col-header" + ghostHeader;
      var span = document.createElement("span");
      span.textContent = col;
      th.appendChild(span);
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    function buildCell(site, col) {
      var cellData = matrix[site][col];
      var td = document.createElement("td");
      var ghostCell = hasMap && col !== currentMapMetric ? " ghost" : "";
      td.className = "cell " + cellData.state + ghostCell;
      td.tabIndex = 0;
      td.textContent = BAND_SYMBOL[cellData.state] !== undefined ? BAND_SYMBOL[cellData.state] : (cellData.display || "");

      var describe = function () { showTooltip(td, site + " \\u2014 " + col, cellData.state, cellData); };
      td.addEventListener("pointerenter", describe);
      td.addEventListener("focus", describe);
      td.addEventListener("pointerleave", hideTooltip);
      td.addEventListener("blur", hideTooltip);

      return td;
    }

    var tbody = document.createElement("tbody");
    data.sites.forEach(function (site) {
      var row = document.createElement("tr");
      var th = document.createElement("th");
      th.className = "site-header site-name";
      th.appendChild(siteLink(site));
      row.appendChild(th);

      if (group.column_groups) {
        group.column_groups.forEach(function (cg, i) {
          cg.columns.forEach(function (col) {
            row.appendChild(buildCell(site, col));
          });
          if (i < group.column_groups.length - 1) {
            var spacer = document.createElement("td");
            spacer.className = "group-spacer";
            row.appendChild(spacer);
          }
        });
      } else {
        group.columns.forEach(function (col) {
          row.appendChild(buildCell(site, col));
        });
      }
      tbody.appendChild(row);
    });
    table.appendChild(tbody);

    if (hasMap) {
      renderMap(group);
    }
  }

  select.addEventListener("change", function () {
    currentWindow = null;
    currentMapMetric = null;
    renderGroup(select.value);
  });
  windowSelect.addEventListener("change", function () {
    currentWindow = Number(windowSelect.value);
    renderGroup(select.value);
  });
  mapMetricSelect.addEventListener("change", function () {
    currentMapMetric = mapMetricSelect.value;
    renderGroup(select.value);
  });
  renderGroup(data.groups[0].key);

  document.getElementById("footer").textContent =
    "State source: services/network/state_task_orchestrator.py per-task state files " +
    "(read as-is, not re-run by this report). Site names link to Grafana (base URL, " +
    "not yet site-parameterised). Hover or focus a cell for detail.";
})();
</script>
</body>
</html>
"""


def render_html(data: dict, generated_at: datetime) -> str:
    """Render the report payload as a self-contained HTML page."""
    payload = dict(data)
    payload["generated_at"] = generated_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    data_json = json.dumps(payload).replace("</", "<\\/")
    return _HTML_TEMPLATE.replace("__DATA_JSON__", data_json)


def main() -> None:
    """CLI entry point: build the report from the on-disk state snapshot, write HTML."""
    parser = argparse.ArgumentParser(
        description="Build a site x metric network health report from state-task files."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("network_health_matrix.html"),
        help="Path to write the HTML report (default: ./network_health_matrix.html)",
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=None,
        help="Override the state directory (default: orchestrator's STATE_DIR)",
    )
    args = parser.parse_args()

    # Deferred: state_task_orchestrator pulls in the full services.network import
    # chain (SiteRegistry, connectivity, data_monitor, logger_monitor, nc_monitor)
    # at module level, which is unnecessary overhead for --help and keeps the pure
    # logic above unit-testable without it — same reasoning as tasks.tasks.mngr in
    # task_status_matrix.py.
    from services.network.connectivity import connectivity_sites
    from services.network.state_task_orchestrator import SITE_REGISTRY, STATE_DIR

    state_dir = args.state_dir or STATE_DIR
    sites = SITE_REGISTRY.names()
    eligible = set(connectivity_sites())

    site_coords: dict[str, tuple[float, float]] = {}
    for site in sites:
        try:
            metadata = SITE_REGISTRY.get_context(site=site).metadata
            site_coords[site] = (
                float(metadata["longitude"]),
                float(metadata["latitude"]),
            )
        except Exception as exc:
            print(f"  (skipping map marker for {site!r}: {exc})")

    now = datetime.now(UTC)
    data = build_report_data(
        state_dir, sites, eligible, now=now, site_coords=site_coords
    )
    html = render_html(data, generated_at=now)
    args.output.write_text(html, encoding="utf-8")

    print(_SEP)
    print(f"{len(sites)} sites  (state dir: {state_dir})")
    print(_SEP)
    for group in data["groups"]:
        matrix = (
            group["matrices"][group["default_window"]]
            if "matrices" in group
            else group["matrix"]
        )
        counts: dict[str, int] = {}
        for site_row in matrix.values():
            for cell in site_row.values():
                counts[cell["state"]] = counts.get(cell["state"], 0) + 1
        updated = group["updated_at"] or "no state file"
        window_note = (
            f" (default {group['default_window']}d)" if "matrices" in group else ""
        )
        print(f"  {group['label']:<24}{window_note} updated {updated}")
        print(f"    {counts}")
    print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()
