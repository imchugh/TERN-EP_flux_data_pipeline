"""Shared read-only helpers for the network-state HTML report tools.

Both `network_health_matrix.py` (metric-group heatmap) and
`logger_status_report.py` (point-in-time logger snapshot) render from the
same per-task state JSON files written by
`services/network/state_task_orchestrator.py`. This module holds the pure
state-loading/eligibility logic shared between them; each tool still renders
its own self-contained HTML page.
"""

import json
from pathlib import Path

STATE_NA = "na"
STATE_NO_DATA = "no_data"
STATE_ERROR = "error"

# Proof-of-concept: same base URL for every site (per-site parameterisation
# deferred). Points at the per-site Grafana dashboard used for historical
# time-series deep-dives; the report tools are the fast "what's wrong now"
# triage view.
GRAFANA_URL = "https://grafana.tern.org.au/d/gwtlbc4/flux-data-dashboard"


def load_state(state_dir: Path, task_name: str) -> dict | None:
    """Read `<task_name>.json` from state_dir, or None if missing/unparsable."""
    path = state_dir / f"{task_name}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def row_state(eligible: bool, result: dict | None) -> str | None:
    """Return row state ('na'/'no_data'/'error'), or None if 'ok' (caller proceeds)."""
    if not eligible:
        return STATE_NA
    if result is None:
        return STATE_NO_DATA
    if result.get("error"):
        return STATE_ERROR
    return None


def uniform_row(
    columns: list[str], state: str, error: str | None = None
) -> dict[str, dict]:
    """Fill every column for a site with the same na/no_data/error cell."""
    cell = {"state": state}
    if error:
        cell["error"] = error
    return {col: dict(cell) for col in columns}
