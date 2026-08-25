#!/usr/bin/env python3
"""Render the logger_status state-task snapshot as a standalone HTML page.

Split out of `network_health_matrix.py`: `logger_status` is a point-in-time
device snapshot (battery, card status, watchdog counters, ...) with no
severity/trend model, unlike the other state tasks, which are all rolling
health metrics over time (missing data, variable/threshold quality, NetCDF
freshness, connectivity). That's a different question — "is the logger
itself reachable and healthy right now" vs. "is data quality degrading" —
so it gets its own page rather than a tab bolted onto the trend matrix. Each
page links to the other via a header nav link.

Reads `logger_status.json` from the state directory written by
`services/network/state_task_orchestrator.py` (refreshed by manually running
`python run.py construct_status_geojson` — this tool does not trigger that
itself) and renders a self-contained HTML table: one row per site, a flag
column (ok / na / no_data / error), and the raw logger fields.

This tool only reads existing state files (via
`state_task_orchestrator.STATE_DIR`/`SITE_REGISTRY` and
`connectivity.connectivity_sites()`) and does not modify or execute any of
the underlying monitoring tasks — same layering constraint as
`network_health_matrix.py`: `services/network/*.py` stays untouched, all
report-specific logic (HTML, the Grafana link) lives here.

Usage (from project root, with ep_cntl activated):
    python -m tools.logger_status_report [--output PATH] [--state-dir PATH]

Default --output: ./logger_status.html
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure project root is on path when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.network_state_common import GRAFANA_URL, STATE_ERROR, load_state, row_state

_SEP = "─" * 64

# Cross-link to the metric-group heatmap page; both tools default to writing
# into the same directory, so a relative filename is enough.
NETWORK_HEALTH_MATRIX_URL = "network_health_matrix.html"

LOGGER_FIELDS = [
    "model",
    "SerialNumber",
    "OSVersion",
    "ProgName",
    "CardStatus",
    "Battery",
    "LithiumBattery",
    "SkippedScan",
    "WatchdogErrors",
]


def build_logger_table(
    state_dir: Path,
    sites: list[str],
    connectivity_eligible: set[str],
) -> tuple[dict[str, dict], str | None]:
    """Build {site: {row_state, error?, fields}} for the logger status table."""
    state = load_state(state_dir, "logger_status")
    sites_data = state.get("sites", {}) if state else {}
    updated_at = state.get("updated_at") if state else None

    rows: dict[str, dict] = {}
    for site in sites:
        result = sites_data.get(site)
        base = row_state(site in connectivity_eligible, result)
        if base is not None:
            row = {"row_state": base}
            if base == STATE_ERROR:
                row["error"] = result.get("error")
        else:
            row = {"row_state": "ok"}
        row["fields"] = {k: result.get(k) for k in LOGGER_FIELDS} if result else {}
        rows[site] = row

    return rows, updated_at


def build_report_data(
    state_dir: Path,
    sites: list[str],
    connectivity_eligible: set[str],
) -> dict:
    """Assemble the full report payload for the logger status page."""
    rows, updated_at = build_logger_table(state_dir, sites, connectivity_eligible)
    return {
        "sites": sites,
        "updated_at": updated_at,
        "fields": LOGGER_FIELDS,
        "rows": rows,
        "grafana_url": GRAFANA_URL,
        "network_health_matrix_url": NETWORK_HEALTH_MATRIX_URL,
    }


_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Logger status</title>
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
    /* Matches network_health_matrix.py's colourblind-validated severity
       colours -- keep the two pages' palettes in sync. */
    --band-green:     #0e8a6d;
    --band-blue:      #2a78d6;
    --state-na:       #e1e0d9;
    --state-no-data:  #f2f1ec;
    --state-error:    #a01330;
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
      --band-green:     #1fa87e;
      --band-blue:      #4a90d8;
      --state-na:       #383835;
      --state-no-data:  #232322;
      --state-error:    #d94d5f;
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
    --band-green:     #1fa87e;
    --band-blue:      #4a90d8;
    --state-na:       #383835;
    --state-no-data:  #232322;
    --state-error:    #d94d5f;
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
  .meta { color: var(--text-secondary); margin: 0 0 16px; font-size: 13px; }
  .page-nav { margin: 0 0 12px; font-size: 13px; }
  .page-nav a { color: var(--band-blue); text-decoration: none; }
  .page-nav a:hover { text-decoration: underline; }
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
  .grid-wrap {
    overflow: auto; max-width: 100%;
    border: 1px solid var(--border); border-radius: 6px;
  }
  table {
    border-collapse: separate; border-spacing: 2px; background: var(--surface-1);
  }
  th, td { padding: 4px 8px; font-size: 12px; }
  th { text-align: left; color: var(--text-secondary); font-weight: 500; }
  td.site-name a {
    color: var(--text-primary); text-decoration: none;
    border-bottom: 1px dotted var(--muted);
  }
  td.site-name a:hover { color: var(--band-blue); }
  td.logger-flag {
    text-align: center; width: 24px; border-radius: 4px; color: #fff;
    font-weight: 700; cursor: default; outline-offset: 2px;
  }
  td.logger-flag.error   { background: var(--state-error); }
  td.logger-flag.na      { background: var(--state-na); color: var(--muted); }
  td.logger-flag.no_data { background: var(--state-no-data); color: var(--muted); }
  td.logger-flag.ok      { background: var(--band-green); }
  td.logger-flag:hover, td.logger-flag:focus-visible {
    outline: 2px solid var(--text-primary);
  }
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
  <h1>Logger status</h1>
  <p class="page-nav"><a id="matrix-link" href="#">← Network health matrix</a></p>
  <p class="meta" id="meta"></p>
  <div class="legend" id="legend"></div>
  <div class="grid-wrap"><table id="grid"></table></div>
  <footer id="footer"></footer>

  <div id="tooltip"></div>

<script id="report-data" type="application/json">__DATA_JSON__</script>
<script>
(function () {
  var BAND_SYMBOL = { na: "\\u2013", no_data: "?", error: "!" };
  var STATE_LABEL = {
    na: "Not applicable", no_data: "No data", error: "Task error", ok: "OK"
  };

  var data = JSON.parse(document.getElementById("report-data").textContent);
  var tooltip = document.getElementById("tooltip");
  document.getElementById("matrix-link").href = data.network_health_matrix_url;

  function addRow(container, label, value) {
    var div = document.createElement("div");
    var strong = document.createElement("span");
    strong.className = "tt-value";
    strong.textContent = value;
    div.appendChild(document.createTextNode(label + ": "));
    div.appendChild(strong);
    container.appendChild(div);
  }

  function showTooltip(el, title, state, extra) {
    tooltip.textContent = "";
    var titleEl = document.createElement("div");
    titleEl.className = "tt-value";
    titleEl.textContent = title;
    tooltip.appendChild(titleEl);

    addRow(tooltip, "Status", STATE_LABEL[state] || state);
    if (extra.error) addRow(tooltip, "Error", extra.error);

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

  document.getElementById("meta").textContent =
    data.sites.length + " sites \\u2014 " +
    (data.updated_at ? "state updated " + data.updated_at : "no state file found") +
    " \\u2014 report generated " + data.generated_at;

  var STATE_COLOR_VAR = {
    ok: "--band-green", na: "--state-na",
    no_data: "--state-no-data", error: "--state-error"
  };
  var legend = document.getElementById("legend");
  var LEGEND_ITEMS = [
    ["ok", "\\u2713", "OK"],
    ["na", "\\u2013", "Not applicable"],
    ["no_data", "?", "No data"],
    ["error", "!", "Task error"],
  ];
  LEGEND_ITEMS.forEach(function (t) {
    var item = document.createElement("div");
    item.className = "legend-item";
    var sw = document.createElement("span");
    sw.className = "swatch";
    sw.style.background = "var(" + STATE_COLOR_VAR[t[0]] + ")";
    if (t[0] === "na" || t[0] === "no_data") sw.style.color = "var(--muted)";
    sw.textContent = t[1];
    item.appendChild(sw);
    item.appendChild(document.createTextNode(t[2]));
    legend.appendChild(item);
  });

  var table = document.getElementById("grid");
  var thead = document.createElement("thead");
  var headRow = document.createElement("tr");
  ["Site", ""].concat(data.fields).forEach(function (label) {
    var th = document.createElement("th");
    th.textContent = label;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);

  var tbody = document.createElement("tbody");
  data.sites.forEach(function (site) {
    var row = document.createElement("tr");
    var siteTd = document.createElement("td");
    siteTd.className = "site-name";
    siteTd.appendChild(siteLink(site));
    row.appendChild(siteTd);

    var rowData = data.rows[site];
    var flagTd = document.createElement("td");
    flagTd.className = "logger-flag " + rowData.row_state;
    flagTd.textContent = rowData.row_state === "ok"
      ? "\\u2713" : (BAND_SYMBOL[rowData.row_state] || "");
    flagTd.tabIndex = 0;
    var describeRow = function () {
      var extra = rowData.error ? { error: rowData.error } : {};
      showTooltip(flagTd, site + " \\u2014 logger status", rowData.row_state, extra);
    };
    flagTd.addEventListener("pointerenter", describeRow);
    flagTd.addEventListener("focus", describeRow);
    flagTd.addEventListener("pointerleave", hideTooltip);
    flagTd.addEventListener("blur", hideTooltip);
    row.appendChild(flagTd);

    data.fields.forEach(function (field) {
      var td = document.createElement("td");
      var val = rowData.fields[field];
      td.textContent = (val === null || val === undefined) ? "" : String(val);
      row.appendChild(td);
    });
    tbody.appendChild(row);
  });
  table.appendChild(tbody);

  document.getElementById("footer").textContent =
    "State source: services/network/state_task_orchestrator.py logger_status.json " +
    "(read as-is, not re-run by this report). Site names link to Grafana (base URL, " +
    "not yet site-parameterised). Hover or focus a flag for detail.";
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
        description="Render the logger_status state-task snapshot as a standalone "
        "HTML page."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("logger_status.html"),
        help="Path to write the HTML report (default: ./logger_status.html)",
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
    # logic above unit-testable without it — same reasoning as network_health_matrix.py.
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
    counts: dict[str, int] = {}
    for row in data["rows"].values():
        counts[row["row_state"]] = counts.get(row["row_state"], 0) + 1
    updated = data["updated_at"] or "no state file"
    print(f"  {'Logger status':<24} updated {updated}")
    print(f"    {counts}")
    print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()
