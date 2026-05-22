#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Orchestrates network-status tasks across all configured pipeline sites.

Each task is a callable with the signature:

    task(context: SiteContext) -> dict

The orchestrator resolves the SiteContext for each site, fans out the task
concurrently using a thread pool, and returns a payload keyed by task name,
ready to be written to a per-task JSON state file.

Usage example
-------------
results = run_task_for_all_sites(
    task=missing_data_task,
    task_name='missing_data_analysis',
)
"""

import logging
from typing import Any, Callable

from infrastructure.parallel_executor import run_concurrent
from services.metadata.site_registry import SiteContext, SiteRegistry, yml_loader
from services.metadata.variable_metadata_service import load_runtime_config
from services.network.data_monitor import analyse_missing_data

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared registry — built once at import time, metadata cache pre-warmed
# before each concurrent run.
# ---------------------------------------------------------------------------

SITE_REGISTRY = SiteRegistry(
    metadata_loader=yml_loader,
    runtime_config_loader=load_runtime_config,
)

# ---------------------------------------------------------------------------
# Task adapters
#
# Each adapter wraps an existing task function so that it conforms to the
# task(context: SiteContext) -> dict contract expected by the orchestrator.
# Add one adapter here for each new task; keep adapters thin.
# ---------------------------------------------------------------------------

def missing_data_task(context: SiteContext) -> dict:
    """Adapter: analyse_missing_data -> SiteContext interface."""
    return analyse_missing_data(
        data_cfg=context.runtime_config,
        site_cfg=context.metadata,
        )

# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_task_for_all_sites(
    task: Callable[[SiteContext], Any],
    task_name: str,
    max_workers: int = 8,
    ) -> dict[str, dict]:
    """
    Run task concurrently for every configured pipeline site.

    Args:
        task: A task adapter conforming to the SiteContext interface.
        task_name: Label used as the top-level key in the returned payload,
            and as the filename stem when writing results to JSON.
        max_workers: Thread pool size passed to the executor (default 8).

    Returns:
        Dict of the form {task_name: {site: result_or_error, ...}}.
    """

    # Pre-warm the shared metadata cache before launching threads so that
    # all threads see a populated cache rather than racing to load the same
    # YAML file.
    SITE_REGISTRY.get_all_metadata()

    sites = SITE_REGISTRY.names()

    logger.info(
        "task_run_start",
        extra={"task": task_name, "site_count": len(sites)},
        )

    def _run_for_site(site: str) -> Any:
        context = SITE_REGISTRY.get_context(site=site)
        return task(context)

    results = run_concurrent(
        task=_run_for_site,
        items=sites,
        max_workers=max_workers,
        )

    logger.info(
        "task_run_complete",
        extra={"task": task_name, "site_count": len(results)},
        )

    return {task_name: results}
