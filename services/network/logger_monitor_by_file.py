#!/usr/bin/env python3
"""Logger status check via locally mirrored status files.

Sites are configured to periodically write a status file (same fields as
the logger's own HTTP status API) into their raw-data landing directory.
This is the active path for `logger_status` in `state_task_orchestrator.py`
— it works uniformly across all sites, including the ones where firewall
rules block the direct HTTP API that `logger_monitor.py` uses. That module
is kept for reference/fallback rather than removed, in case file delivery
breaks for a site and a direct API check is needed to diagnose it.
"""

import csv
import logging
import pathlib
from typing import Any

import pandas as pd

from infrastructure import datetime_utils, file_io, paths
from services.metadata.site_registry import SiteContext, SiteRegistry
from services.network.logger_monitor import STATUS_SUBSET, SUMMARY_SUBSET

logger = logging.getLogger(__name__)

FILE_SUFFIX = "Status.dat"

# Status files carry sub-second precision that raw_data_loader's TOA5 date
# formatter does not parse (it uses domain.constants.DATA_TIME_FORMAT, which
# has no %f) — timestamps are parsed locally with this format instead.
TS_FORMAT = "%Y-%m-%d %H:%M:%S.%f"

# Mirrors the header layout of raw_data_loader._FILE_FORMATS["TOA5"] — a
# fixed property of the TOA5 format, not something specific to status files,
# so it's safe to restate here rather than reach into that module's private
# constant.
_STATUS_FILE_FORMAT = {
    "header_lines": {"info": 0, "variable": 1, "units": 2, "sampling": 3},
    "separator": ",",
    "non_numeric_cols": ["TIMESTAMP"],
    "na_values": "NAN",
    "quoting": csv.QUOTE_NONNUMERIC,
}

_EXTRA_FIELDS = ["last_status_time", "minutes_since_last_status"]
NULL_RESULT: dict[str, Any] = {
    key: None for key in SUMMARY_SUBSET + STATUS_SUBSET + _EXTRA_FIELDS
} | {"error": None}

SITE_REGISTRY = SiteRegistry()


def get_status_file_path(site: str) -> pathlib.Path:
    """Return the expected local path of a site's logger status file."""
    return (
        paths.get_local_stream_path(resource="raw_data", stream="flux_slow", site=site)
        / f"{site}_EC_{FILE_SUFFIX}"
    )


def get_logger_status(context: SiteContext) -> dict[str, Any]:
    """Parse the latest row of a site's locally mirrored logger status file.

    Args:
        context: Combined site runtime config and metadata.

    Returns:
        Flat dict containing ``model``, each field in ``STATUS_SUBSET``,
        ``last_status_time`` (ISO-8601, site-local time), and
        ``minutes_since_last_status``. Does not include an ``error`` key;
        see ``check_logger_status`` for the full uniform-shape result.

    Raises:
        FileNotFoundError: If no status file exists yet for the site.
        ValueError: If the status file has no data rows.
    """
    site = context.runtime_config.site_name
    file_path = get_status_file_path(site=site)

    if not file_path.exists():
        raise FileNotFoundError(
            f"No status file found for site {site!r} at {file_path}"
        )

    df = file_io.read_csv_data(
        file_path=file_path,
        file_format=_STATUS_FILE_FORMAT,
        usecols=["TIMESTAMP", *STATUS_SUBSET],
        on_bad_lines="skip",
    )
    if df.empty:
        raise ValueError(f"Status file for site {site!r} contains no data rows")

    # Ring-buffer status tables can hold more than one historical row —
    # always take the most recent rather than assuming a single row.
    last = df.iloc[-1]

    tz_name = context.metadata.time_zone
    last_status_naive = pd.to_datetime(
        last["TIMESTAMP"], format=TS_FORMAT
    ).to_pydatetime()
    last_status_tzaware = datetime_utils.get_tz_aware_datetime(
        naive_dt=last_status_naive, tz_name=tz_name, as_iso=True
    )
    local_now_naive = datetime_utils.get_local_datetime_now(
        tz_name=tz_name, return_tz_aware=False
    )

    return (
        {"model": last["OSVersion"].split(".")[0]}
        | {key: None if pd.isna(last[key]) else last[key] for key in STATUS_SUBSET}
        | {
            "last_status_time": last_status_tzaware,
            "minutes_since_last_status": round(
                (local_now_naive - last_status_naive).total_seconds() / 60
            ),
        }
    )


def check_logger_status(site: str) -> dict[str, Any]:
    """Fetch datalogger status for a named pipeline site, via its status file.

    Resolves the site's runtime context and delegates to
    ``get_logger_status``. File and parse errors are caught and returned as
    a ``NULL_RESULT`` with the ``error`` key populated, so the output shape
    is always identical regardless of whether a status file has arrived —
    matching the contract of ``logger_monitor.check_logger_status`` so this
    is a drop-in replacement in the state-task registry.

    Staleness is not itself treated as an error: ``minutes_since_last_status``
    is returned as data so a consumer can apply its own threshold, the same
    way ``nc_monitor.check_nc_last_record`` reports elapsed days rather than
    judging freshness itself.

    Args:
        site: Site name as registered in the pipeline site registry.

    Returns:
        Dict containing ``model``, each field in ``STATUS_SUBSET``,
        ``last_status_time``, ``minutes_since_last_status``, and ``error``
        (``None`` on success, error string on failure).
    """
    context = SITE_REGISTRY.get_context(site=site)

    try:
        return get_logger_status(context=context) | {"error": None}
    except Exception as exc:
        logger.warning(
            "logger_status_by_file_failed",
            extra={"site": site, "error": str(exc)},
        )
        return NULL_RESULT | {"error": str(exc)}
