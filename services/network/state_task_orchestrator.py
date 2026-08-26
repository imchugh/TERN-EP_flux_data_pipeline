#!/usr/bin/env python3
"""Orchestrates network-status tasks across all configured pipeline sites.

Each task is a callable with the signature:

    task(site: str) -> dict

The orchestrator fans the task out concurrently using a thread pool and
returns a payload keyed by task name.

Persistence is pluggable via the ``persist`` parameter of
``run_task_for_all_sites``:

- ``write_state`` (the default) writes a fresh snapshot JSON file on every
  run. Use this for stateless tasks such as missing-data analysis.
- A module-specific function (e.g.
  ``connectivity.persist_connectivity_state``) handles tasks that need a
  stateful read-modify-write cycle, preserving history across runs.
- ``None`` suppresses all I/O — useful in tests.

Example:
    # Run a single registered task and write its state file:
    run_task('missing_data')

    # Run all tasks then aggregate to both output formats:
    aggregate(run_tasks=True)

    # Re-aggregate from existing state files without re-running tasks:
    aggregate(output='geojson')

    # Low-level: run a task not in the registry (e.g. ad-hoc gateway scan):
    from services.network.connectivity import (
        connectivity_sites,
        persist_connectivity_state,
    )

    run_task_for_all_sites(
        task=make_connectivity_task(hardware='gateway'),
        task_name='gateway',
        sites=connectivity_sites(),
        persist=persist_connectivity_state,
    )
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from infrastructure import paths
from infrastructure.datetime_utils import get_utc_now
from infrastructure.file_io import read_json, write_json
from infrastructure.parallel_executor import run_concurrent
from services.data.data_monitor import (
    NULL_RESULT as MISSING_DATA_NULL_RESULT,
)
from services.data.data_monitor import (
    THRESHOLD_NULL_RESULT,
    VARIABLE_QUALITY_NULL_RESULT,
    analyse_missing_data,
    analyse_threshold_quality,
    analyse_variable_quality,
)
from services.metadata.tern.site_registry import SiteRegistry
from services.network.connectivity import (
    connectivity_sites,
    persist_connectivity_state,
    run_site_connectivity,
)

# Status is read from each site's locally mirrored status file rather than
# hit over the network — some sites block the HTTP API this module's
# check_logger_status hits, but all sites can deliver a status file.
# logger_monitor.py (API-based) is sidelined, not removed: kept for
# reference/fallback if file delivery ever breaks for a site.
from services.network.logger_monitor_by_file import check_logger_status
from services.network.nc_monitor import check_nc_last_record

logger = logging.getLogger(__name__)

STATE_DIR = paths.get_local_stream_path(resource="network", stream="state")
GEOJSON_PATH = STATE_DIR / "network_state.json"
SITE_SUMMARY_PATH = STATE_DIR / "site_summary.json"

# Shared type alias for the two-argument persist-callback contract.
type PersistFn = Callable[[dict[str, Any], str], None]

# Shared registry — built once at import time, metadata cache pre-warmed
# before each concurrent run.

SITE_REGISTRY = SiteRegistry()

# Task adapters
#
# Each adapter wraps an existing task function so that it conforms to the
# task(site: str) -> dict contract expected by the orchestrator.
# Add one adapter here for each new task; keep adapters thin.


def missing_data_task(site: str) -> dict[str, Any]:
    """Adapter: analyse_missing_data -> site-name interface.

    Args:
        site: Site name as registered in the pipeline site registry.

    Returns:
        Missing-data analysis result dict for the site, with ``error: null``
        on success or all data fields set to ``null`` and ``error`` populated
        on failure.
    """
    context = SITE_REGISTRY.get_context(site=site)
    try:
        return analyse_missing_data(context=context) | {"error": None}
    except Exception as exc:
        logger.warning(
            "missing_data_failed",
            extra={"site": site, "error": str(exc)},
        )
        return MISSING_DATA_NULL_RESULT | {"error": str(exc)}


def variable_quality_task(site: str) -> dict[str, Any]:
    """Adapter: analyse_variable_quality -> site-name interface.

    Args:
        site: Site name as registered in the pipeline site registry.

    Returns:
        Per-variable quality result dict for the site, with ``error: null``
        on success or all variable fields set to ``null`` and ``error``
        populated on failure.
    """
    context = SITE_REGISTRY.get_context(site=site)
    try:
        return analyse_variable_quality(context=context) | {"error": None}
    except Exception as exc:
        logger.warning(
            "variable_quality_failed",
            extra={"site": site, "error": str(exc)},
        )
        return VARIABLE_QUALITY_NULL_RESULT | {"error": str(exc)}


def threshold_quality_task(site: str) -> dict[str, Any]:
    """Adapter: analyse_threshold_quality -> site-name interface.

    Args:
        site: Site name as registered in the pipeline site registry.

    Returns:
        Per-variable threshold-quality result dict for the site, with
        ``error: null`` on success or all variable fields set to ``null``
        and ``error`` populated on failure.
    """
    context = SITE_REGISTRY.get_context(site=site)
    try:
        return analyse_threshold_quality(context=context) | {"error": None}
    except Exception as exc:
        logger.warning(
            "threshold_quality_failed",
            extra={"site": site, "error": str(exc)},
        )
        return THRESHOLD_NULL_RESULT | {"error": str(exc)}


def logger_status_task(site: str) -> dict[str, Any]:
    """Adapter: check_logger_status -> site-name interface.

    Args:
        site: Site name as registered in the pipeline site registry.

    Returns:
        Logger status result dict for the site.
    """
    return check_logger_status(site=site)


def nc_last_record_task(site: str) -> dict[str, Any]:
    """Adapter: check_nc_last_record -> site-name interface.

    Args:
        site: Site name as registered in the pipeline site registry.

    Returns:
        NetCDF last-record result dict for the site.
    """
    return check_nc_last_record(site=site)


def make_connectivity_task(
    hardware: str = "gateway",
) -> Callable[[str], dict[str, Any]]:
    """Factory: return a per-site connectivity task for the given hardware type.

    The returned callable conforms to the ``task(site: str) -> dict`` contract
    and is intended to be passed directly to ``run_task_for_all_sites``.

    Args:
        hardware: Hardware type to scan. One of 'gateway', 'ec', 'soil',
            'profile'. Defaults to 'gateway'.

    Returns:
        A callable ``task(site: str) -> dict[str, Any]``.
    """

    def _task(site: str) -> dict[str, Any]:
        return run_site_connectivity(site=site, hardware=hardware)

    return _task


# Persistence helpers


def write_state(
    results: dict[str, Any],
    task_name: str,
    state_dir: Path = STATE_DIR,
) -> None:
    """Write a snapshot state file for a completed task.

    Wraps per-site results in the standard envelope and writes to
    ``<state_dir>/<task_name>.json``, matching the structure used by the
    connectivity state file::

        {
            "updated_at": "<ISO-8601 UTC>",
            "sites": { "<site>": <result>, ... }
        }

    Matches the ``PersistFn`` interface expected by ``run_task_for_all_sites``.

    Args:
        results: Per-site result dict as returned by run_task_for_all_sites.
        task_name: Used as the JSON filename stem.
        state_dir: Directory to write into. Defaults to the configured
            network state path.
    """
    payload = {
        "updated_at": get_utc_now(as_iso=True),
        "sites": results,
    }

    out_path = state_dir / f"{task_name}.json"
    write_json(file_path=out_path, data=payload, sort_keys=True)

    logger.info("state_written", extra={"path": str(out_path)})


# State task registry
#
# Each entry maps directly to the kwargs of run_task_for_all_sites.
# Add one dict here to register a new state task — nothing else changes.
# sites=None means run_task_for_all_sites uses the full pipeline registry.
# connectivity_sites() is evaluated at import time; it reads a static config
# so this is safe for a daily cron job.

_CONNECTIVITY_SITES = connectivity_sites()

STATE_TASK_SPECS: list[dict[str, Any]] = [
    dict(
        task=missing_data_task,
        task_name="missing_data",
    ),
    dict(
        task=variable_quality_task,
        task_name="variable_quality",
    ),
    dict(
        task=threshold_quality_task,
        task_name="threshold_quality",
    ),
    dict(
        task=nc_last_record_task,
        task_name="nc_last_record",
    ),
    dict(
        task=logger_status_task,
        task_name="logger_status",
    ),
    dict(
        task=make_connectivity_task("gateway"),
        task_name="gateway_connectivity",
        sites=_CONNECTIVITY_SITES,
        persist=persist_connectivity_state,
    ),
    dict(
        task=make_connectivity_task("ec"),
        task_name="ec_logger_connectivity",
        sites=_CONNECTIVITY_SITES,
        persist=persist_connectivity_state,
    ),
]


# Orchestration


def run_task_for_all_sites(
    task: Callable[[str], dict[str, Any]],
    task_name: str,
    sites: list[str] | None = None,
    max_workers: int = 8,
    persist: PersistFn | None = write_state,
) -> dict[str, dict[str, Any]]:
    """Run task concurrently for every configured pipeline site.

    Args:
        task: A callable conforming to ``task(site: str) -> dict[str, Any]``. Tasks are
            responsible for resolving their own context from the site name.
        task_name: Label used as the top-level key in the returned payload and
            passed as the second argument to ``persist``.
        sites: Explicit list of site names to iterate. When ``None`` (default),
            the shared pipeline registry supplies the list and its metadata
            cache is pre-warmed before launching threads.
        max_workers: Thread pool size passed to the executor (default 8).
        persist: Callable invoked as ``persist(results, task_name)`` after all
            sites complete. Defaults to ``write_state``, which writes a fresh
            snapshot JSON file. Pass
            ``connectivity.persist_connectivity_state`` for stateful
            read-modify-write tasks, or ``None`` to suppress all I/O (e.g. in
            tests).

    Returns:
        Dict of the form ``{task_name: {site: result_or_error, ...}}``.
    """
    if sites is None:
        # Pre-warm the shared metadata cache before launching threads so that
        # all threads see a populated cache rather than racing to load the same
        # YAML file.
        SITE_REGISTRY.get_all_metadata()
        sites = SITE_REGISTRY.names()

    logger.info(
        "task_run_start",
        extra={"task": task_name, "site_count": len(sites)},
    )

    results = run_concurrent(task=task, items=sites, max_workers=max_workers)

    logger.info(
        "task_run_complete",
        extra={"task": task_name, "site_count": len(results)},
    )

    if persist is not None:
        persist(results, task_name)

    return {task_name: results}


def compile_geojson(
    task_names: list[str] | None = None,
    state_dir: Path = STATE_DIR,
) -> None:
    """Read per-task state files and write a site-pivoted GeoJSON FeatureCollection.

    Reads each ``<task_name>.json`` from ``state_dir``, pivots from task-first
    to site-first, then assembles one GeoJSON Feature per pipeline-registry site.
    Coordinates are sourced from the site registry; task results are nested in
    ``properties`` under their task name. Writes ``network_state.json`` to
    ``state_dir``.

    Missing or unreadable task files are skipped with a warning. Sites without
    resolvable geometry are omitted from the output.

    Args:
        task_names: Ordered list of task names to include.
        state_dir: Directory containing per-task state files and output.
    """
    if task_names is None:
        task_names = [spec["task_name"] for spec in STATE_TASK_SPECS]

    site_results: dict[str, dict[str, Any]] = {}

    for task_name in task_names:
        path = state_dir / f"{task_name}.json"
        try:
            payload = read_json(file_path=path)
            for site, result in payload.get("sites", {}).items():
                site_results.setdefault(site, {})[task_name] = result
        except Exception as exc:
            logger.warning(
                "geojson_read_failed",
                extra={"task": task_name, "error": str(exc)},
            )

    features = []
    for site_name in SITE_REGISTRY.names():
        try:
            metadata = SITE_REGISTRY.get_context(site=site_name).metadata
            lat = metadata["latitude"]
            lon = metadata["longitude"]
        except Exception as exc:
            logger.warning(
                "geojson_geometry_failed",
                extra={"site": site_name, "error": str(exc)},
            )
            continue

        features.append(
            {
                "type": "Feature",
                "id": site_name,
                "geometry": {
                    "type": "Point",
                    "coordinates": [lon, lat],
                },
                "properties": site_results.get(site_name, {}),
            }
        )

    geojson = {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {"updated_at": get_utc_now(as_iso=True)},
    }

    out_path = state_dir / "network_state.json"
    write_json(file_path=out_path, data=geojson)
    logger.info("geojson_written", extra={"path": str(out_path)})


def compile_site_summary(
    task_names: list[str] | None = None,
    state_dir: Path = STATE_DIR,
) -> None:
    """Read per-task state files and write a site-pivoted summary.

    Reads each ``<task_name>.json`` from ``state_dir``, pivots from the
    task-first structure ``{task: {site: result}}`` to a site-first view, and
    writes ``site_summary.json`` using the standard envelope::

        {
            "updated_at": "<ISO-8601 UTC>",
            "sites": {
                "<site>": {
                    "<task_name>": <result>,
                    ...
                },
                ...
            }
        }

    Missing or unreadable task files are skipped with a warning so a single
    failed task does not block the summary.

    Args:
        task_names: Ordered list of task names to include; each must correspond
            to a ``<task_name>.json`` file in ``state_dir``.
        state_dir: Directory containing per-task state files. Defaults to the
            configured network state path.
    """
    if task_names is None:
        task_names = [spec["task_name"] for spec in STATE_TASK_SPECS]

    sites: dict[str, dict[str, Any]] = {}

    for task_name in task_names:
        path = state_dir / f"{task_name}.json"
        try:
            payload = read_json(file_path=path)
            for site, result in payload.get("sites", {}).items():
                sites.setdefault(site, {})[task_name] = result
        except Exception as exc:
            logger.warning(
                "site_summary_read_failed",
                extra={"task": task_name, "error": str(exc)},
            )

    write_state(results=sites, task_name="site_summary", state_dir=state_dir)


def run_task(task_name: str) -> dict[str, dict[str, Any]]:
    """Run a single registered task by name and write its state file.

    Looks up the task spec in ``STATE_TASK_SPECS`` by ``task_name`` and
    delegates to ``run_task_for_all_sites``.

    Args:
        task_name: Must match the ``task_name`` key of an entry in
            ``STATE_TASK_SPECS``.

    Returns:
        Dict of the form ``{task_name: {site: result_or_error, ...}}``.

    Raises:
        KeyError: If ``task_name`` is not found in ``STATE_TASK_SPECS``.
    """
    try:
        spec = next(s for s in STATE_TASK_SPECS if s["task_name"] == task_name)
    except StopIteration:
        raise KeyError(f"No task registered under name {task_name!r}") from None

    return run_task_for_all_sites(**spec)


def run_all_tasks() -> None:
    """Run every registered state task in sequence and write its state file.

    Iterates ``STATE_TASK_SPECS`` and calls ``run_task_for_all_sites`` for
    each entry. Tasks fan out concurrently per-site internally; this function
    itself is sequential across tasks so each state file is written before the
    next task begins. Does not run aggregation — call ``aggregate()`` separately
    if needed.
    """
    logger.info("run_all_tasks_start", extra={"n_tasks": len(STATE_TASK_SPECS)})

    for spec in STATE_TASK_SPECS:
        run_task_for_all_sites(**spec)

    logger.info("run_all_tasks_complete")


def aggregate(
    run_tasks: bool = False,
    output: Literal["json", "geojson", "both"] = "both",
) -> None:
    """Aggregate per-task state files into a combined summary.

    Optionally re-runs all tasks first, then compiles the selected output
    format(s) from the state files on disk.

    Args:
        run_tasks: When ``True``, calls ``run_all_tasks()`` before aggregating
            so the output reflects fresh data. Defaults to ``False`` — useful
            when tasks have already been run and only the aggregate needs
            refreshing.
        output: Controls which aggregate files are written:

            - ``'json'``: writes ``site_summary.json`` (site-pivoted, human-readable).
            - ``'geojson'``: writes ``network_state.json`` (GeoJSON FeatureCollection,
              used operationally).
            - ``'both'`` (default): writes both files.
    """
    if run_tasks:
        run_all_tasks()

    if output in ("json", "both"):
        compile_site_summary()

    if output in ("geojson", "both"):
        compile_geojson()


if __name__ == "__main__":
    aggregate(run_tasks=True)
