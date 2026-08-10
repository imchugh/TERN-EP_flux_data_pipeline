#!/usr/bin/env python3
"""Created on Fri May 22 2026

@author: imchugh
"""

import logging
import pathlib
import time
from typing import Any

import pandas as pd
import xarray as xr

from infrastructure import datetime_utils, paths

logger = logging.getLogger(__name__)

NC_SUFFIX = "_L1.nc"
# Files modified more recently than this are considered mid-write and skipped.
# Half-hourly updates mean a 60-second window is conservative enough to avoid
# false positives once the monitor is scheduled away from the ingest window.
_WRITE_QUIET_SECS: int = 60
NULL_RESULT: dict[str, Any] = {
    "last_record": None,
    "days_since_last_record": None,
    "error": None,
}


# -----------------------------------------------------------------------------
def get_nc_site_dir(site: str) -> pathlib.Path:
    """Return the directory containing L1 NetCDF files for a site.

    Args:
        site: Site name.

    Returns:
        Path to the site's NetCDF directory.
    """
    return paths.get_local_stream_path(resource="homogenised_data", stream="nc") / site


# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
def get_latest_nc_file(site: str) -> pathlib.Path:
    """Return the path to the most recent L1 NetCDF file for a site.

    Files are matched by the pattern ``<site>*_L1.nc`` inside the site
    directory and sorted lexicographically; the year component in the filename
    makes this equivalent to a chronological sort.

    Args:
        site: Site name.

    Returns:
        Path to the latest L1 NetCDF file.

    Raises:
        FileNotFoundError: if no matching files exist under the site directory.
    """
    site_dir = get_nc_site_dir(site=site)
    files = sorted(site_dir.glob(f"{site}*{NC_SUFFIX}"))

    if not files:
        raise FileNotFoundError(
            f'No L1 NetCDF files found for site "{site}" in {site_dir}'
        )

    now = time.time()
    stable = [f for f in files if (now - f.stat().st_mtime) >= _WRITE_QUIET_SECS]

    if not stable:
        logger.warning(
            "nc_all_files_recently_modified",
            extra={"site": site, "quiet_secs": _WRITE_QUIET_SECS},
        )
        stable = files

    return stable[-1]


# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
def check_nc_last_record(site: str) -> dict[str, Any]:
    """Report the last data record in the most recent L1 NetCDF file for a site.

    Opens the site's latest L1 NetCDF file, reads the final timestamp from the
    ``time`` coordinate, and computes elapsed whole days relative to site-local
    now.  The timezone is read from the file's global ``time_zone`` attribute,
    so no external metadata is required.

    NetCDF time values follow the local-time convention (naive timestamps),
    consistent with the raw-data monitor in ``data_monitor.py``.

    Args:
        site: Site name (must match a directory under the NetCDF base path).

    Returns:
        Dict with keys:
            - ``last_record``: ISO-8601 timezone-aware datetime string of the
              final record in the file, or ``None`` on failure.
            - ``days_since_last_record``: Whole days elapsed since that record,
              measured against site-local now, or ``None`` on failure.
            - ``error``: ``None`` on success, or an error string describing
              why the check failed.
    """
    try:
        file_path = get_latest_nc_file(site=site)
        logger.debug(
            "nc_last_record_check",
            extra={"site": site, "file": str(file_path)},
        )

        with xr.open_dataset(file_path) as ds:
            tz_name: str = ds.attrs["time_zone"]
            # Timestamps are stored as naive local time; convert via pandas
            # Timestamp to match the convention used by data_monitor.py.
            last_record_naive = (
                pd.Timestamp(ds.time.values[-1]).to_pydatetime().replace(tzinfo=None)
            )

        local_now = datetime_utils.get_local_datetime_now(tz_name=tz_name)
        local_now_naive = local_now.replace(tzinfo=None)

        last_record_tzaware = datetime_utils.get_tz_aware_datetime(
            naive_dt=last_record_naive,
            tz_name=tz_name,
            as_iso=True,
        )
        elapsed = (local_now_naive - last_record_naive).days

        return {
            "last_record": last_record_tzaware,
            "days_since_last_record": elapsed,
            "error": None,
        }

    except Exception as exc:
        logger.warning(
            "nc_last_record_failed",
            extra={"site": site, "error": str(exc)},
        )
        return NULL_RESULT | {"error": str(exc)}


# -----------------------------------------------------------------------------
