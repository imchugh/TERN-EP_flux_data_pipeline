#!/usr/bin/env python3
"""Generic concurrent task runner for I/O-bound work.

Uses a thread pool, which is appropriate for tasks dominated by file reads
or network calls. The GIL does not block on I/O, and C-extension libraries
such as pandas release it during computation, so threads give real
concurrency for the workloads in this pipeline.

For heavy pure-Python CPU work, swap ThreadPoolExecutor for
ProcessPoolExecutor from concurrent.futures — the public API is identical.
"""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

logger = logging.getLogger(__name__)


def run_concurrent(
    task: Callable[[str], Any],
    items: list[str],
    max_workers: int = 8,
) -> dict[str, Any]:
    """Run task(item) concurrently for every item in items.

    Individual failures are caught and stored as {'error': <message>} so a
    single failing item does not abort the whole run. All items are always
    represented in the returned dict.

    Args:
        task: A callable that accepts one string argument (e.g. a site name)
            and returns a serialisable result.
        items: The arguments to dispatch, one per worker invocation.
        max_workers: Thread pool size. 8 suits local-disk I/O well; raise to
            16–32 for high-latency network tasks where threads spend most
            time waiting.

    Returns:
        Dict mapping each item to its result, or to {'error': <str>} on
        failure.
    """
    results: dict[str, Any] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_item = {pool.submit(task, item): item for item in items}

        for future in as_completed(future_to_item):
            item = future_to_item[future]
            try:
                results[item] = future.result()
            except Exception as exc:
                logger.error(
                    "parallel_task_failed",
                    extra={"item": item, "error": str(exc)},
                )
                results[item] = {"error": str(exc)}

    return results


def run_concurrent_ordered(
    task: Callable[[str], Any],
    items: list[str],
    max_workers: int = 8,
) -> tuple[list[Any], dict[str, dict]]:
    """Run task(item) concurrently, collecting outputs in input order.

    For per-site builders whose successful outputs are assembled into one
    file: a failing item is logged with its traceback and left out of the
    outputs, so one bad site can't stop the rest.

    Returns:
        (outputs of the successful items, in `items` order;
        per-item status: {"status": "success"} or
        {"status": "failure", "error_type": ..., "error": ...}).
    """

    def guarded(item: str) -> dict:
        try:
            return {"status": "success", "output": task(item)}
        except Exception as exc:
            logger.error("parallel_task_failed", extra={"item": item}, exc_info=True)
            return {
                "status": "failure",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    # run_concurrent's dict is in completion order; iterate `items` instead.
    entries = run_concurrent(task=guarded, items=items, max_workers=max_workers)
    outputs = [entries[i]["output"] for i in items if entries[i]["status"] == "success"]
    status = {i: {k: v for k, v in entries[i].items() if k != "output"} for i in items}
    return outputs, status
