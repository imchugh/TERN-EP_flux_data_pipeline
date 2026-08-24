#!/usr/bin/env python3
"""Build a site x metric health report from the network state-task snapshot files.

Reads the per-task state JSON files that `services/network/state_task_orchestrator.py`
writes to its state directory (one `<task_name>.json` per task, refreshed by manually
running `python run.py construct_status_geojson` — this tool does not trigger that
itself, see the module's own docstring), and renders a self-contained HTML report:
a dropdown selects one of six health-metric groups (missing_data, variable_quality,
threshold_quality, nc_last_record, gateway_connectivity, ec_logger_connectivity),
each rendered as a site x sub-metric heatmap. logger_status is a point-in-time device
snapshot with no natural severity model — trend/rolling-window health vs. "is the
device reachable right now" are different questions, so it has its own page,
`logger_status_report.py`, cross-linked from this one's header.

Cells are classified `na` (site not eligible for this task), `no_data` (eligible,
but missing from the state file), `error` (the task's own `error` field is
populated), or a 5-band severity ramp (green/blue/purple/orange/red) computed from
the metric value — day-count metrics (`days_since_last_record`,
`consecutive_failures`) and percentage metrics (`pct_missing_*`,
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
# this is the window used to colour the cell, with the other two windows shown
# in the tooltip.
PRIMARY_WINDOW_DAYS = 7

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
NC_LAST_RECORD_COLUMNS = ["days_since_last_record"]
CONNECTIVITY_COLUMNS = ["consecutive_failures"]


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


def _fmt_count(value: float | int | None) -> str:
    return "" if value is None else f"{value:.0f}"


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


def _nested_quality_row(result: dict, variables: list[str]) -> dict[str, dict]:
    row = {}
    for var in variables:
        sub = result.get(var)
        if sub is None:
            row[var] = {"state": STATE_NO_DATA, "value": None, "display": ""}
            continue
        primary = sub.get(f"pct_outside_range_last_{PRIMARY_WINDOW_DAYS}_days")
        row[var] = {
            "state": band_for_pct(primary) or STATE_NO_DATA,
            "value": primary,
            "display": _fmt_pct(primary),
            "pct_outside_range_last_1_days": sub.get("pct_outside_range_last_1_days"),
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


def _connectivity_row(result: dict) -> dict[str, dict]:
    failures = result.get("consecutive_failures")
    return {
        "consecutive_failures": {
            "state": band_for_count(failures) or STATE_NO_DATA,
            "value": failures,
            "display": _fmt_count(failures),
            "last_success": result.get("last_success"),
            "last_attempt": result.get("last_attempt"),
            "last_latency_ms": result.get("last_latency_ms"),
        }
    }


GROUPS = [
    {
        "key": "missing_data",
        "label": "Missing data",
        "columns": MISSING_DATA_COLUMNS,
        "row_fn": _missing_data_row,
        "scoped": False,
    },
    {
        "key": "variable_quality",
        "label": "Variable quality",
        "columns": VARIABLE_QUALITY_VARS,
        "row_fn": lambda result: _nested_quality_row(result, VARIABLE_QUALITY_VARS),
        "scoped": False,
    },
    {
        "key": "threshold_quality",
        "label": "Threshold quality",
        "columns": THRESHOLD_QUALITY_VARS,
        "row_fn": lambda result: _nested_quality_row(result, THRESHOLD_QUALITY_VARS),
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
        "key": "gateway_connectivity",
        "label": "Gateway connectivity",
        "columns": CONNECTIVITY_COLUMNS,
        "row_fn": _connectivity_row,
        "scoped": True,
    },
    {
        "key": "ec_logger_connectivity",
        "label": "EC logger connectivity",
        "columns": CONNECTIVITY_COLUMNS,
        "row_fn": _connectivity_row,
        "scoped": True,
    },
]


def build_group_matrix(
    group: dict,
    state_dir: Path,
    sites: list[str],
    connectivity_eligible: set[str],
) -> tuple[dict[str, dict[str, dict]], str | None]:
    """Build {site: {column: cell}} for one group, plus its state file's updated_at."""
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


def build_report_data(
    state_dir: Path,
    sites: list[str],
    connectivity_eligible: set[str],
) -> dict:
    """Assemble the full report payload: every group's matrix."""
    groups_out = []
    for group in GROUPS:
        matrix, updated_at = build_group_matrix(
            group, state_dir, sites, connectivity_eligible
        )
        groups_out.append(
            {
                "key": group["key"],
                "label": group["label"],
                "columns": group["columns"],
                "updated_at": updated_at,
                "matrix": matrix,
            }
        )

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
  .grid-wrap { overflow: auto; max-width: 100%; border: 1px solid var(--border); border-radius: 6px; }
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
    height: 110px; vertical-align: bottom; z-index: 2;
    border-bottom: 1px solid var(--border);
  }
  th.col-header span {
    display: inline-block; transform: rotate(-45deg); transform-origin: left bottom;
    white-space: nowrap; font-size: 12px; font-weight: 500; color: var(--text-secondary);
  }
  th.site-header { z-index: 3; top: 0; }
  td.cell {
    width: 46px; height: 28px; min-width: 46px; border-radius: 4px;
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
  </div>
  <div class="legend" id="legend"></div>
  <div class="grid-wrap"><table id="grid"></table></div>
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

  function renderGroup(key) {
    var group = data.groups.filter(function (g) { return g.key === key; })[0];
    table.textContent = "";

    document.getElementById("meta").textContent =
      data.sites.length + " sites \\u00d7 " + group.columns.length + " metrics \\u2014 " +
      (group.updated_at ? "state updated " + group.updated_at : "no state file found") +
      " \\u2014 report generated " + data.generated_at;

    var thead = document.createElement("thead");
    var headRow = document.createElement("tr");
    var corner = document.createElement("th");
    corner.className = "site-header";
    headRow.appendChild(corner);
    group.columns.forEach(function (col) {
      var th = document.createElement("th");
      th.className = "col-header";
      var span = document.createElement("span");
      span.textContent = col;
      th.appendChild(span);
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    var tbody = document.createElement("tbody");
    data.sites.forEach(function (site) {
      var row = document.createElement("tr");
      var th = document.createElement("th");
      th.className = "site-header site-name";
      th.appendChild(siteLink(site));
      row.appendChild(th);

      group.columns.forEach(function (col) {
        var cellData = group.matrix[site][col];
        var td = document.createElement("td");
        td.className = "cell " + cellData.state;
        td.tabIndex = 0;
        td.textContent = BAND_SYMBOL[cellData.state] !== undefined ? BAND_SYMBOL[cellData.state] : (cellData.display || "");

        var describe = function () { showTooltip(td, site + " \\u2014 " + col, cellData.state, cellData); };
        td.addEventListener("pointerenter", describe);
        td.addEventListener("focus", describe);
        td.addEventListener("pointerleave", hideTooltip);
        td.addEventListener("blur", hideTooltip);

        row.appendChild(td);
      });
      tbody.appendChild(row);
    });
    table.appendChild(tbody);
  }

  select.addEventListener("change", function () { renderGroup(select.value); });
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

    data = build_report_data(state_dir, sites, eligible)
    html = render_html(data, generated_at=datetime.now(UTC))
    args.output.write_text(html, encoding="utf-8")

    print(_SEP)
    print(f"{len(sites)} sites  (state dir: {state_dir})")
    print(_SEP)
    for group in data["groups"]:
        counts: dict[str, int] = {}
        for site_row in group["matrix"].values():
            for cell in site_row.values():
                counts[cell["state"]] = counts.get(cell["state"], 0) + 1
        updated = group["updated_at"] or "no state file"
        print(f"  {group['label']:<24} updated {updated}")
        print(f"    {counts}")
    print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()
