"""Task runner and orchestrator for the flux data pipeline.

Imports the three task modules to trigger @register decorators, then
instantiates SiteTaskManager (validation requires SITE_TASKS / GLOBAL_TASKS
to be fully populated first).
"""

###############################################################################
### BEGIN IMPORTS ###
###############################################################################

import inspect
import logging
from collections.abc import Callable

import pandas as pd

# Trigger @register decorators
import tasks.build_tasks  # noqa: F401
import tasks.monitor_tasks  # noqa: F401
import tasks.transfer_tasks  # noqa: F401
from infrastructure import paths
from infrastructure.paths import CONFIG_PATH
from services import config_loader
from services.metadata.site_registry import SiteRegistry
from tasks.logger_config import configure_logger_json
from tasks.registry import GLOBAL_TASKS, SITE_TASKS

###############################################################################
### END IMPORTS ###
###############################################################################


###############################################################################
### BEGIN INITS ###
###############################################################################

logger = logging.getLogger(__name__)
SITE_REGISTRY = SiteRegistry()

# -----------------------------------------------------------------------------


def _parse_bool_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Strictly parse a str/bool/object DataFrame of TRUE/FALSE cells.

    Unlike `.astype(bool)`, this treats any cell that isn't literally
    TRUE/FALSE (case-insensitive, whitespace-trimmed) as an error rather
    than silently coercing it — a blank cell, a stray trailing space, or a
    'Yes'/'1' typed by hand in a spreadsheet would otherwise all become
    True (any non-empty string, and NaN, are truthy in Python).
    """
    valid = {"TRUE": True, "FALSE": False}
    normalised = df.astype(str).apply(lambda col: col.str.strip().str.upper())
    invalid = {
        (site, task): raw
        for task in normalised.columns
        for site, raw in normalised[task].items()
        if raw not in valid
    }
    if invalid:
        raise ValueError(f"tasks.csv contains non-boolean cells: {invalid}")
    return normalised.map(valid.get).astype(bool)


# -----------------------------------------------------------------------------


class SiteTaskManager:
    """CSV site/task boolean matrix — exposes per-task site lists."""

    def __init__(self) -> None:

        self.tasks_df = (
            config_loader.load_config_file_from_name("tasks")
            .set_index(keys="Site")
            .pipe(_parse_bool_matrix)
        )
        self._validate()

    def get_site_list(self) -> list:
        return self.tasks_df.index.tolist()

    def get_site_list_for_task(self, task: str, disabled: bool = False) -> list:
        return self.tasks_df[~self.tasks_df[task] == disabled].index.tolist()

    def get_site_task_status(self, site: str, task: str) -> bool:
        return self.tasks_df.loc[site, task]

    def get_task_list(self) -> list:
        return self.tasks_df.columns.tolist()

    def get_task_list_for_site(self, site: str, disabled: bool = False) -> list:
        return self.tasks_df.columns[~self.tasks_df.loc[site] == disabled].tolist()

    def set_site_task_status(self, site: str, task: str, status: bool) -> None:
        if not isinstance(status, bool):
            raise TypeError("`status` kwarg must be a boolean")
        self.tasks_df.loc[site, task] = status

    def write_tasks_config(self) -> None:
        self.tasks_df.to_csv(CONFIG_PATH / "tasks.csv", index_label="Site")

    def _validate(self) -> None:
        registered = set(SITE_TASKS) | set(GLOBAL_TASKS)
        unknown_tasks = set(self.tasks_df.columns) - registered
        if unknown_tasks:
            raise ValueError(
                f"tasks.csv references unregistered tasks: {unknown_tasks}"
            )
        known_sites = set(SITE_REGISTRY.names())
        unknown_sites = set(self.tasks_df.index) - known_sites
        if unknown_sites:
            raise ValueError(
                f"tasks.csv references sites not in SITE_REGISTRY: {unknown_sites}"
            )


# Instantiated after task imports so SITE_TASKS / GLOBAL_TASKS are fully
# populated before validation runs.
mngr = SiteTaskManager()

###############################################################################
### END INITS ###
###############################################################################


###############################################################################
### BEGIN RUNNER ###
###############################################################################


def run_task(task: str, site: str | None = None, dry_run: bool = False) -> None:
    """Unified entry point to run any registered task.

    Args:
        task: registered task name.
        site: optional site name — valid only for site-scoped tasks.  When
            omitted for a site-scoped task the CSV matrix is used to build the
            site list.
        dry_run: forwarded to the task function if it accepts a `dry_run`
            parameter; raises if the task doesn't support it.
    """
    func, scope = _resolve_task(task=task, site=site)
    if dry_run and "dry_run" not in inspect.signature(func).parameters:
        raise ValueError(f"Task '{task}' does not support --dry-run.")
    _setup_logger(task=task)

    try:
        if scope == "site":
            _run_site_task(task=task, function=func, site=site)
        else:
            _run_global_task(task=task, func=func, dry_run=dry_run)
    except Exception:
        logger.error(
            "task_end",
            extra={
                "task": task,
                "scope": scope,
                "status": "failure",
                "reason": "unhandled_exception",
            },
            exc_info=True,
        )
        raise


# -----------------------------------------------------------------------------


def _resolve_task(task: str, site: str | None) -> tuple[Callable, str]:

    if task in SITE_TASKS:
        func, scope = SITE_TASKS[task], "site"
    elif task in GLOBAL_TASKS:
        func, scope = GLOBAL_TASKS[task], "global"
    else:
        raise NotImplementedError(f"Task '{task}' is not registered.")

    if scope == "global" and site is not None:
        raise ValueError(f"Task '{task}' is global — cannot be run per-site.")

    return func, scope


# -----------------------------------------------------------------------------


def _setup_logger(task: str) -> None:

    log_path = (
        paths.get_local_stream_path(resource="logs", stream="network_logs")
        / f"{task}.jsonl"
    )
    configure_logger_json(log_path=log_path)


# -----------------------------------------------------------------------------


def _run_site_task(task: str, function: Callable, site: str | None) -> None:

    site_list = [site] if site is not None else _get_sites_for_task(task)

    logger.info(
        "task_start",
        extra={
            "task": task,
            "scope": "site",
            "site_count": len(site_list),
            "single_site": site is not None,
        },
    )

    failed_sites: list[str] = []
    for s in site_list:
        result = _run_single_site_task(task=task, func=function, site=s)
        if result.get("status") == "failure":
            failed_sites.append(s)
        logger.info("task_site_result", extra={"task": task, "site": s, **result})

    overall = "failure" if failed_sites else "success"
    logger.info(
        "task_end",
        extra={
            "task": task,
            "scope": "site",
            "status": overall,
            "failed_sites": failed_sites,
        },
    )


# -----------------------------------------------------------------------------


def _get_sites_for_task(task: str) -> list[str]:

    try:
        return mngr.get_site_list_for_task(task=task)
    except KeyError:
        # Fail closed: a task missing from tasks.csv must not silently run
        # against every site (a stale process holding an outdated tasks.csv
        # snapshot, or a genuinely un-added column, would otherwise fan a
        # site-scoped task out to sites it was never meant to touch).
        raise ValueError(
            f"Task '{task}' has no column in tasks.csv, so its site list is "
            "undefined. Add a column for it (defaulting sites it doesn't "
            "apply to as FALSE) before running it without an explicit --site."
        ) from None


# -----------------------------------------------------------------------------


def _run_single_site_task(task: str, func: Callable, site: str) -> dict:

    try:
        result = func(site)
        if not isinstance(result, dict) or "status" not in result:
            return {"status": "success"}
        return result
    except Exception:
        logger.exception("task_site_exception", extra={"task": task, "site": site})
        return {"status": "failure", "reason": "exception"}


# -----------------------------------------------------------------------------


def _run_global_task(task: str, func: Callable, dry_run: bool = False) -> None:

    logger.info(
        "task_start",
        extra={"task": task, "scope": "global", "dry_run": dry_run},
    )
    try:
        kwargs = (
            {"dry_run": dry_run}
            if "dry_run" in inspect.signature(func).parameters
            else {}
        )
        result = func(**kwargs)
        if isinstance(result, dict) and "status" in result:
            extra = {"task": task, "scope": "global", **result}
        else:
            extra = {"task": task, "scope": "global", "status": "success"}
        logger.info("task_end", extra=extra)
    except Exception as e:
        logger.error(
            "task_end",
            extra={
                "task": task,
                "scope": "global",
                "status": "failure",
                "reason": str(e),
            },
            exc_info=True,
        )
        raise


###############################################################################
### END RUNNER ###
###############################################################################
