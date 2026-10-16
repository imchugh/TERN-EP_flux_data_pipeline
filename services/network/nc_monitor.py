#!/usr/bin/env python3
"""NetCDF file last-record freshness check."""

import logging
import pathlib
import threading
import time
from typing import Any

import pandas as pd
import xarray as xr

from fluxtools.datetime_utils import get_local_datetime_now, get_tz_aware_datetime
from infrastructure import paths
from infrastructure.safe_ops import safe_component

logger = logging.getLogger(__name__)

# netCDF4-python wraps the C libnetcdf/HDF5 libraries, which are not
# thread-safe in the default (non-thread-safe-HDF5) Anaconda build used here.
# state_task_orchestrator runs check_nc_last_record concurrently across sites
# via a thread pool; without this lock, concurrent nc_open calls race on
# libnetcdf's global open-file registry and have crashed the process with a
# C-level assertion failure in nc4_nc4f_list_add (a hard abort, not a Python
# exception). Serialising all netCDF4 file access to one thread at a time
# avoids the race. Public (not module-private) because the C library's
# open-file registry is process-global, not module-scoped: any other module
# that opens netCDF4 files from a thread pool in the same process (e.g.
# orchestration/legacy_network_status.py) must serialise against this same
# lock, not just its own, or the two can still race against each other.
NETCDF_LOCK = threading.Lock()

NC_SUFFIX = "_L1.nc"
# Files modified more recently than this are considered mid-write and skipped.
# Half-hourly updates mean a 60-second window is conservative enough to avoid
# false positives once the monitor is scheduled away from the ingest window.
_WRITE_QUIET_SECS: int = 60
# The netCDF4/HDF5 backend can fail to parse a perfectly valid file with a
# generic "Unknown file format" OSError: under host memory pressure, or when
# a reader's open races construct_L1_nc's atomic rename on shared network
# storage. A short retry rides out either; genuine corruption fails again.
_OPEN_RETRY_ATTEMPTS: int = 2
_OPEN_RETRY_DELAY_SECS: float = 2.0
NULL_RESULT: dict[str, Any] = {
    "last_record": None,
    "days_since_last_record": None,
    "error": None,
}


def get_nc_site_dir(site: str) -> pathlib.Path:
    """Return the directory containing L1 NetCDF files for a site.

    Args:
        site: Site name.

    Returns:
        Path to the site's NetCDF directory.
    """
    return paths.get_local_stream_path(resource="homogenised_data", stream="nc") / site


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
        raise TimeoutError(
            f'All L1 NetCDF files for site "{site}" were modified within the last '
            f"{_WRITE_QUIET_SECS}s and were skipped as likely mid-write; retry later"
        )

    return stable[-1]


def open_dataset_with_retry(file_path: pathlib.Path) -> xr.Dataset:
    """Open file_path as an xarray Dataset, retrying once on a transient OSError.

    Args:
        file_path: NetCDF file to open.

    Returns:
        The opened dataset.

    Raises:
        OSError: if every attempt fails.
    """
    last_exc: OSError | None = None

    for attempt in range(1, _OPEN_RETRY_ATTEMPTS + 1):
        try:
            return xr.open_dataset(file_path)
        except OSError as exc:
            last_exc = exc
            if attempt < _OPEN_RETRY_ATTEMPTS:
                logger.warning(
                    "nc_open_retry",
                    extra={
                        "file": str(file_path),
                        "attempt": attempt,
                        "error": str(exc),
                    },
                )
                time.sleep(_OPEN_RETRY_DELAY_SECS)

    raise last_exc


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
    return safe_component(
        _read_last_record,
        logger=logger,
        component="nc_last_record_failed",
        fallback=NULL_RESULT,
        include_error=True,
        log_extra={"site": site},
        site=site,
    )


def _read_last_record(site: str) -> dict[str, Any]:
    """Unguarded body of check_nc_last_record."""
    file_path = get_latest_nc_file(site=site)
    logger.debug(
        "nc_last_record_check",
        extra={"site": site, "file": str(file_path)},
    )

    with NETCDF_LOCK, open_dataset_with_retry(file_path) as ds:
        tz_name: str = ds.attrs["time_zone"]
        # Timestamps are stored as naive local time; convert via pandas
        # Timestamp to match the convention used by data_monitor.py.
        last_record_naive = (
            pd.Timestamp(ds.time.values[-1]).to_pydatetime().replace(tzinfo=None)
        )

    local_now_naive = get_local_datetime_now(tz_name=tz_name, return_tz_aware=False)

    last_record_tzaware = get_tz_aware_datetime(
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
