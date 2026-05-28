#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Orchestrates network-status tasks across all configured pipeline sites.

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
    # Runs missing-data analysis for all pipeline sites and writes
    # <state_dir>/missing_data_analysis.json
    run_task_for_all_sites(
        task=missing_data_task,
        task_name='missing_data_analysis',
    )

    # Runs a gateway connectivity scan, updating the persistent state file
    from services.network.connectivity import connectivity_sites, persist_connectivity_state

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
from typing import Any

from infrastructure import paths
from infrastructure.datetime_utils import get_utc_now
from infrastructure.file_io import write_json
from infrastructure.parallel_executor import run_concurrent
from services.metadata.site_registry import SiteRegistry
from services.network.connectivity import (
    run_site_connectivity,
    connectivity_sites,
    persist_connectivity_state,
    )
from services.network.data_monitor import analyse_missing_data, NULL_RESULT as MISSING_DATA_NULL_RESULT
from services.network.logger_monitor import check_logger_status
from services.network.nc_monitor import check_nc_last_record

logger = logging.getLogger(__name__)

STATE_DIR = paths.get_local_stream_path(resource='network', stream='state')

# Shared type alias for the two-argument persist-callback contract.
type PersistFn = Callable[[dict[str, Any], str], None]

# ---------------------------------------------------------------------------
# Shared registry — built once at import time, metadata cache pre-warmed
# before each concurrent run.
# ---------------------------------------------------------------------------

SITE_REGISTRY = SiteRegistry()

# ---------------------------------------------------------------------------
# Task adapters
#
# Each adapter wraps an existing task function so that it conforms to the
# task(site: str) -> dict contract expected by the orchestrator.
# Add one adapter here for each new task; keep adapters thin.
# ---------------------------------------------------------------------------

def missing_data_task(site: str) -> dict[str, Any]:
    """
    Adapter: analyse_missing_data -> site-name interface.

    Args:
        site: Site name as registered in the pipeline site registry.

    Returns:
        Missing-data analysis result dict for the site, with ``error: null``
        on success or all data fields set to ``null`` and ``error`` populated
        on failure.
    """
    context = SITE_REGISTRY.get_context(site=site)
    try:
        return analyse_missing_data(
            data_cfg=context.runtime_config,
            site_cfg=context.metadata,
        ) | {'error': None}
    except Exception as exc:
        logger.warning(
            'missing_data_failed',
            extra={'site': site, 'error': str(exc)},
        )
        return MISSING_DATA_NULL_RESULT | {'error': str(exc)}


def logger_status_task(site: str) -> dict[str, Any]:
    """
    Adapter: check_logger_status -> site-name interface.

    Args:
        site: Site name as registered in the VPN IP config.

    Returns:
        Logger status result dict for the site.
    """

    return check_logger_status(site=site)


def nc_last_record_task(site: str) -> dict[str, Any]:
    """
    Adapter: check_nc_last_record -> site-name interface.

    Args:
        site: Site name as registered in the pipeline site registry.

    Returns:
        NetCDF last-record result dict for the site.
    """

    return check_nc_last_record(site=site)


def make_connectivity_task(
    hardware: str = "gateway",
    ) -> Callable[[str], dict[str, Any]]:
    """
    Factory: return a per-site connectivity task for the given hardware type.

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


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def write_state(
    results: dict[str, Any],
    task_name: str,
    state_dir: Path = STATE_DIR,
    ) -> None:
    """
    Write a snapshot state file for a completed task.

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


# ---------------------------------------------------------------------------
# State task registry
#
# Each entry maps directly to the kwargs of run_task_for_all_sites.
# Add one dict here to register a new state task — nothing else changes.
# sites=None means run_task_for_all_sites uses the full pipeline registry.
# connectivity_sites() is evaluated at import time; it reads a static config
# so this is safe for a daily cron job.
# ---------------------------------------------------------------------------

_CONNECTIVITY_SITES = connectivity_sites()

STATE_TASK_SPECS: list[dict[str, Any]] = [
    dict(
        task=missing_data_task,
        task_name='missing_data',
    ),
    dict(
        task=nc_last_record_task,
        task_name='nc_last_record',
    ),
    dict(
        task=logger_status_task,
        task_name='logger_status',
        sites=_CONNECTIVITY_SITES,
    ),
    dict(
        task=make_connectivity_task('gateway'),
        task_name='gateway',
        sites=_CONNECTIVITY_SITES,
        persist=persist_connectivity_state,
    ),
    dict(
        task=make_connectivity_task('ec'),
        task_name='ec',
        sites=_CONNECTIVITY_SITES,
        persist=persist_connectivity_state,
    ),
]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_task_for_all_sites(
    task: Callable[[str], dict[str, Any]],
    task_name: str,
    sites: list[str] | None = None,
    max_workers: int = 8,
    persist: PersistFn | None = write_state,
    ) -> dict[str, dict[str, Any]]:
    """
    Run task concurrently for every configured pipeline site.

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


# ---------------------------------------------------------------------------
# Convenience runner — temporary, for manual testing before wiring into the
# main task registry. Run with: python -m services.network.state_task_orchestrator
# ---------------------------------------------------------------------------

def run_all_state_tasks() -> None:
    """
    Run every registered state task in sequence and write its state file.

    Iterates ``STATE_TASK_SPECS`` and calls ``run_task_for_all_sites`` for
    each entry. Tasks fan out concurrently per-site internally; this function
    itself is sequential across tasks so each state file is written before the
    next task begins.
    """

    logger.info("run_all_state_tasks_start", extra={"n_tasks": len(STATE_TASK_SPECS)})

    for spec in STATE_TASK_SPECS:
        run_task_for_all_sites(**spec)

    logger.info("run_all_state_tasks_complete")


if __name__ == '__main__':
    run_all_state_tasks()
