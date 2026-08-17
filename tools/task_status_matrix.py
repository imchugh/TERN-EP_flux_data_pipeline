#!/usr/bin/env python3
"""Build a site x task status heatmap from task-run JSONL logs.

Reads the `task_site_result` records that `tasks.tasks` writes to the
per-task JSONL logs under the `logs`/`network_logs` stream, cross-references
`configs/tasks.csv` (via `tasks.tasks.mngr`) to distinguish "not enabled for
this site" from "enabled but no recent run", and renders a self-contained
HTML heatmap: one row per site, one column per task, colour-coded by the
most recent run's status. Failure cells are enriched with the matching
`task_site_exception` record's traceback (same run_id + site, logged by
`tasks.tasks._run_single_site_task` immediately before the result line).

Usage (from project root, with ep_cntl activated):
    python -m tools.task_status_matrix [--output PATH] [--days N]

Default --output: ./task_status_matrix.html
Default --days:   14 (lookback window for "latest run")
"""

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Ensure project root is on path when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from infrastructure import paths

_SEP = "─" * 64
_RESULT_MESSAGE = "task_site_result"
_EXCEPTION_MESSAGE = "task_site_exception"
_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_TRACEBACK_TAIL_LINES = 12

STATE_SUCCESS = "success"
STATE_FAILURE = "failure"
STATE_NA = "na"
STATE_NO_DATA = "no_data"

# Fixed fields JsonFormatter/tasks.py always attach to a task_site_result
# record — anything else came from the task function's own result dict.
_FIXED_RECORD_KEYS = {
    "timestamp",
    "level",
    "name",
    "message",
    "task",
    "site",
    "status",
    "run_id",
    "reason",
    "taskName",
}


def _iter_task_records(
    log_dir: Path, task: str, cutoff: datetime
) -> tuple[list[dict], list[dict], int]:
    """Return (task_site_result records, task_site_exception records, skipped count).

    Reads the task's current log file plus any rotated backups
    (`{task}.jsonl*`), at/after cutoff. Root-logger noise from other modules
    and other message types (task_start, task_end, ...) are filtered out
    here; only `task_site_result` and `task_site_exception` lines are kept.
    The latter carries the formatted traceback (`exception` key) that
    `tasks.tasks._run_single_site_task` logs immediately before the
    corresponding result line, for the same run_id + site.
    """
    results: list[dict] = []
    exceptions: list[dict] = []
    skipped = 0
    cutoff_str = cutoff.strftime(_TS_FORMAT)

    for log_file in sorted(log_dir.glob(f"{task}.jsonl*")):
        with log_file.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    skipped += 1
                    continue
                message = record.get("message")
                if message not in (_RESULT_MESSAGE, _EXCEPTION_MESSAGE):
                    continue
                if record.get("timestamp", "") < cutoff_str:
                    continue
                (results if message == _RESULT_MESSAGE else exceptions).append(record)

    return results, exceptions, skipped


def _traceback_tail(exception_text: str, max_lines: int = _TRACEBACK_TAIL_LINES) -> str:
    """Return the last `max_lines` lines of a formatted traceback.

    The most actionable part of a Python traceback (the exception type and
    message) is at the end, so tail-truncate rather than head-truncate. Adds
    a note when lines were dropped.
    """
    lines = exception_text.rstrip("\n").split("\n")
    if len(lines) <= max_lines:
        return exception_text.rstrip("\n")
    dropped = len(lines) - max_lines
    return f"... ({dropped} earlier line(s) omitted) ...\n" + "\n".join(lines[-max_lines:])


def _latest_record(records: list[dict]) -> dict | None:
    """Return the record with the max timestamp, or None if `records` is empty."""
    if not records:
        return None
    return max(records, key=lambda r: r["timestamp"])


def classify_cell(
    enabled: bool, latest: dict | None, traceback: str | None = None
) -> dict:
    """Classify one (site, task) cell from its enablement flag and latest record.

    Returns a dict with at least a "state" key
    (success | failure | na | no_data), plus timestamp/run_id/reason/details
    when a record is available, and a tail-truncated "traceback" when a
    matching task_site_exception record was found for a failure.
    """
    if not enabled:
        return {"state": STATE_NA}
    if latest is None:
        return {"state": STATE_NO_DATA}

    cell = {
        "state": latest["status"],
        "timestamp": latest.get("timestamp"),
        "run_id": latest.get("run_id"),
    }
    if latest["status"] == STATE_FAILURE:
        cell["reason"] = latest.get("reason")
        if traceback:
            cell["traceback"] = _traceback_tail(traceback)
    details = {k: v for k, v in latest.items() if k not in _FIXED_RECORD_KEYS}
    if details:
        cell["details"] = details
    return cell


def build_matrix(
    log_dir: Path,
    sites: list[str],
    tasks: list[str],
    enabled: dict[tuple[str, str], bool],
    days: int,
) -> tuple[dict[str, dict[str, dict]], int]:
    """Build {site: {task: cell}} for every site/task pair, plus skipped-line count."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    matrix: dict[str, dict[str, dict]] = {site: {} for site in sites}
    total_skipped = 0

    for task in tasks:
        records, exception_records, skipped = _iter_task_records(log_dir, task, cutoff)
        total_skipped += skipped

        by_site: dict[str, list[dict]] = {}
        for record in records:
            by_site.setdefault(record.get("site"), []).append(record)

        # run_id is stamped per process run (RunIDFilter), shared across every
        # site processed in that run, so key on (run_id, site) to pick the
        # exception that belongs to this specific site's failure.
        traceback_by_run_site = {
            (exc.get("run_id"), exc.get("site")): exc.get("exception")
            for exc in exception_records
        }

        for site in sites:
            latest = _latest_record(by_site.get(site, []))
            traceback = None
            if latest is not None:
                traceback = traceback_by_run_site.get((latest.get("run_id"), site))
            matrix[site][task] = classify_cell(enabled[(site, task)], latest, traceback)

    return matrix, total_skipped


_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Task status matrix</title>
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
    --state-success:  #0ca30c;
    --state-failure:  #d03b3b;
    --state-na:       #e1e0d9;
    --state-no-data:  #f2f1ec;
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
      --state-na:       #383835;
      --state-no-data:  #232322;
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
    --state-na:       #383835;
    --state-no-data:  #232322;
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
  .legend {
    display: flex; gap: 20px; align-items: center;
    margin-bottom: 16px; font-size: 13px; color: var(--text-secondary);
  }
  .legend-item { display: flex; gap: 6px; align-items: center; }
  .swatch {
    width: 16px; height: 16px; border-radius: 4px;
    display: flex; align-items: center; justify-content: center;
    font-size: 11px; font-weight: 600;
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
  th.task-header {
    position: sticky; top: 0; background: var(--surface-1);
    height: 110px; vertical-align: bottom; z-index: 2;
    border-bottom: 1px solid var(--border);
  }
  th.task-header span {
    display: inline-block; transform: rotate(-45deg); transform-origin: left bottom;
    white-space: nowrap; font-size: 12px; font-weight: 500; color: var(--text-secondary);
  }
  th.site-header { z-index: 3; top: 0; }
  td.cell {
    width: 28px; height: 28px; min-width: 28px; border-radius: 4px;
    text-align: center; vertical-align: middle; cursor: default;
    font-size: 13px; font-weight: 700; outline-offset: 2px;
  }
  td.cell.success { background: var(--state-success); color: #ffffff; }
  td.cell.failure { background: var(--state-failure); color: #ffffff; }
  td.cell.na { background: var(--state-na); color: var(--muted); }
  td.cell.no_data { background: var(--state-no-data); color: var(--muted); border: 1px dashed var(--gridline); }
  td.cell:hover, td.cell:focus-visible { outline: 2px solid var(--text-primary); }
  #tooltip {
    position: fixed; pointer-events: none; z-index: 10;
    background: var(--text-primary); color: var(--surface-1);
    padding: 8px 10px; border-radius: 6px; font-size: 12px; line-height: 1.5;
    max-width: 480px; box-shadow: 0 4px 12px var(--border);
    display: none; white-space: pre-line;
  }
  #tooltip .tt-value { font-weight: 700; }
  #tooltip .tt-traceback-label { margin-top: 6px; }
  #tooltip pre {
    margin: 4px 0 0; font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
    font-size: 11px; line-height: 1.4; white-space: pre-wrap; word-break: break-word;
  }
  footer { margin-top: 12px; color: var(--muted); font-size: 12px; }
</style>
</head>
<body>
  <h1>Task status matrix</h1>
  <p class="meta" id="meta"></p>
  <div class="legend">
    <div class="legend-item"><span class="swatch" style="background:var(--state-success);color:#fff;">&#10003;</span> Success</div>
    <div class="legend-item"><span class="swatch" style="background:var(--state-failure);color:#fff;">&#10007;</span> Failure</div>
    <div class="legend-item"><span class="swatch" style="background:var(--state-na);color:var(--muted);">&#8211;</span> Not enabled</div>
    <div class="legend-item"><span class="swatch" style="background:var(--state-no-data);color:var(--muted);border:1px dashed var(--gridline);">?</span> No data in window</div>
  </div>
  <div class="grid-wrap"><table id="grid"></table></div>
  <footer id="footer"></footer>
  <div id="tooltip"></div>

<script id="matrix-data" type="application/json">__DATA_JSON__</script>
<script>
(function () {
  var SYMBOL = { success: "\\u2713", failure: "\\u2717", na: "\\u2013", no_data: "?" };
  var LABEL = { success: "Success", failure: "Failure", na: "Not enabled", no_data: "No data in window" };

  var data = JSON.parse(document.getElementById("matrix-data").textContent);

  document.getElementById("meta").textContent =
    data.sites.length + " sites \\u00d7 " + data.tasks.length + " tasks \\u2014 " +
    "latest run in the last " + data.days + " day(s), generated " + data.generated_at;

  var table = document.getElementById("grid");

  var thead = document.createElement("thead");
  var headRow = document.createElement("tr");
  var corner = document.createElement("th");
  corner.className = "site-header";
  headRow.appendChild(corner);
  data.tasks.forEach(function (task) {
    var th = document.createElement("th");
    th.className = "task-header";
    var span = document.createElement("span");
    span.textContent = task;
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
    th.textContent = site;
    row.appendChild(th);

    data.tasks.forEach(function (task) {
      var cellData = data.cells[site][task];
      var td = document.createElement("td");
      td.className = "cell " + cellData.state;
      td.tabIndex = 0;
      td.textContent = SYMBOL[cellData.state] || "";

      var describe = function () { showTooltip(td, site, task, cellData); };
      td.addEventListener("pointerenter", describe);
      td.addEventListener("focus", describe);
      td.addEventListener("pointerleave", hideTooltip);
      td.addEventListener("blur", hideTooltip);

      row.appendChild(td);
    });
    tbody.appendChild(row);
  });
  table.appendChild(tbody);

  document.getElementById("footer").textContent =
    "Log source: task_site_result records (failures enriched with the matching " +
    "task_site_exception traceback). Latest run only; hover or focus a cell for detail.";

  var tooltip = document.getElementById("tooltip");

  function addRow(container, label, value) {
    var div = document.createElement("div");
    var strong = document.createElement("span");
    strong.className = "tt-value";
    strong.textContent = value;
    div.appendChild(document.createTextNode(label + ": "));
    div.appendChild(strong);
    container.appendChild(div);
  }

  function showTooltip(el, site, task, cellData) {
    tooltip.textContent = "";

    var title = document.createElement("div");
    title.className = "tt-value";
    title.textContent = site + " \\u2014 " + task;
    tooltip.appendChild(title);

    addRow(tooltip, "Status", LABEL[cellData.state] || cellData.state);
    if (cellData.timestamp) addRow(tooltip, "Last run", cellData.timestamp);
    if (cellData.run_id) addRow(tooltip, "Run id", cellData.run_id);
    if (cellData.reason) addRow(tooltip, "Reason", cellData.reason);
    if (cellData.traceback) {
      var tbLabel = document.createElement("div");
      tbLabel.className = "tt-traceback-label";
      tbLabel.textContent = "Traceback:";
      tooltip.appendChild(tbLabel);
      var pre = document.createElement("pre");
      pre.textContent = cellData.traceback;
      tooltip.appendChild(pre);
    }
    if (cellData.details) {
      Object.keys(cellData.details).forEach(function (key) {
        addRow(tooltip, key, JSON.stringify(cellData.details[key]));
      });
    }

    tooltip.style.display = "block";
    var rect = el.getBoundingClientRect();
    var top = rect.bottom + 8;
    var left = rect.left;
    if (left + 480 > window.innerWidth) left = window.innerWidth - 488;
    tooltip.style.top = top + "px";
    tooltip.style.left = Math.max(8, left) + "px";
  }

  function hideTooltip() {
    tooltip.style.display = "none";
  }
})();
</script>
</body>
</html>
"""


def render_html(
    sites: list[str],
    tasks: list[str],
    matrix: dict[str, dict[str, dict]],
    days: int,
    generated_at: datetime,
) -> str:
    """Render the site x task matrix as a self-contained HTML heatmap."""
    payload = {
        "generated_at": generated_at.strftime(_TS_FORMAT),
        "days": days,
        "sites": sites,
        "tasks": tasks,
        "cells": matrix,
    }
    data_json = json.dumps(payload).replace("</", "<\\/")
    return _HTML_TEMPLATE.replace("__DATA_JSON__", data_json)


def main() -> None:
    """CLI entry point: build the matrix from live logs and write the HTML report."""
    parser = argparse.ArgumentParser(
        description="Build a site x task status heatmap from task-run logs."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("task_status_matrix.html"),
        help="Path to write the HTML report (default: ./task_status_matrix.html)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=14,
        help="Lookback window in days for the latest-run status (default: 14)",
    )
    args = parser.parse_args()

    # Deferred: importing tasks.tasks registers every task module and
    # validates tasks.csv against SITE_REGISTRY, which is unnecessary
    # overhead for --help and makes the pure logic above easy to unit test
    # without that chain.
    from tasks.tasks import mngr

    sites = mngr.get_site_list()
    tasks = mngr.get_task_list()
    enabled = {
        (site, task): mngr.get_site_task_status(site, task)
        for site in sites
        for task in tasks
    }

    log_dir = paths.get_local_stream_path(resource="logs", stream="network_logs")
    matrix, skipped = build_matrix(log_dir, sites, tasks, enabled, args.days)

    generated_at = datetime.now(UTC)
    html = render_html(sites, tasks, matrix, days=args.days, generated_at=generated_at)
    args.output.write_text(html, encoding="utf-8")

    counts = {STATE_SUCCESS: 0, STATE_FAILURE: 0, STATE_NA: 0, STATE_NO_DATA: 0}
    for site_row in matrix.values():
        for cell in site_row.values():
            counts[cell["state"]] += 1

    print(_SEP)
    print(f"{len(sites)} sites x {len(tasks)} tasks  (log dir: {log_dir})")
    print(_SEP)
    for state, n in counts.items():
        print(f"  {state:<10} {n}")
    if skipped:
        print(f"\n  WARNING: skipped {skipped} unparsable log line(s)", file=sys.stderr)
    print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()
