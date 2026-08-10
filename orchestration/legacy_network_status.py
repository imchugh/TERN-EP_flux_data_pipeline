#!/usr/bin/env python3
"""Construct the legacy-format network status geojson.

Ported from the old TERN-EP_data_pipeline project's
``network_monitoring/network_status.py``. Downstream visualisations (the
flux-status-test.tern.org.au status map) still consume this flat, per-site
``{Fco2, Fh, Fe, Fsd}`` staleness schema written to ``network_status.json``.
``services.network.state_task_orchestrator`` produces a richer replacement
(``network_state.json``) but isn't wired up for that consumer yet — this
module is a temporary bridge until it is, at which point this module,
``construct_legacy_status_geojson`` and ``push_legacy_status_geojson`` should
all be removed.

The old module resolved raw NetCDF columns like ``Fco2_DL`` back to the
canonical ``Fco2`` via a suffix-matching parser (``PFPNameParser``); the new
L1 NetCDF files carry bare canonical names directly, so that resolution step
is dropped here — ``SUBSET`` names are looked up as exact columns.
"""

###############################################################################
### BEGIN IMPORTS ###
###############################################################################

import datetime as dt
import logging
import time

import geojson
import numpy as np
import xarray as xr

from infrastructure import datetime_utils, file_io, paths
from infrastructure.parallel_executor import run_concurrent
from services.metadata.canonical_quantity_registry import (
    build_canonical_quantity_registry,
)
from services.metadata.site_registry import SiteRegistry
from services.network.nc_monitor import get_latest_nc_file

###############################################################################
### END IMPORTS ###
###############################################################################


###############################################################################
### BEGIN INITS ###
###############################################################################

logger = logging.getLogger(__name__)

SITE_REGISTRY = SiteRegistry()

# Core flux quantities the status map reports staleness for.
SUBSET = ["Fco2", "Fh", "Fe", "Fsd"]

# construct_L1_nc writes atomically (temp file + rename), but the L1 output
# directory sits on shared network storage where a reader can still briefly
# race a writer's rename — retry a couple of times before giving up on a
# site rather than letting one bad instant fail the whole run.
_NC_OPEN_RETRIES = 2
_NC_OPEN_RETRY_DELAY_SECS = 2

###############################################################################
### END INITS ###
###############################################################################


###############################################################################
### BEGIN FUNCTIONS ###
###############################################################################


def build(site_list: list[str] | None = None) -> dict:
    """Construct network_status.json (legacy website status map).

    Args:
        site_list: sites to include. Defaults to every registered pipeline
            site (``SITE_REGISTRY.names()``).

    Returns:
        Per-site status dict: ``{site: {"status": "success"}}`` or
        ``{site: {"status": "failure", "error_type": ..., "error": ...}}``.
    """
    if site_list is None:
        # Pre-warm the shared metadata cache before launching threads so all
        # threads see a populated cache rather than racing to load the same
        # YAML file.
        SITE_REGISTRY.get_all_metadata()
        site_list = SITE_REGISTRY.names()

    logger.info(
        "legacy_status_geojson_start",
        extra={"site_count": len(site_list)},
    )

    entries = run_concurrent(task=_build_site_feature, items=site_list)

    # Iterate site_list (not `entries`) so feature order stays deterministic —
    # run_concurrent's dict is in thread-completion order.
    features = [
        entries[site]["feature"]
        for site in site_list
        if entries[site]["status"] == "success"
    ]
    results = {
        site: {k: v for k, v in entries[site].items() if k != "feature"}
        for site in site_list
    }

    collection = geojson.FeatureCollection(features)
    collection["metadata"] = {
        "rundatetime": dt.datetime.now(dt.UTC).isoformat(),
    }

    output_path = (
        paths.get_local_stream_path("network", "status") / "network_status.json"
    )
    file_io.write_json(file_path=output_path, data=collection)

    n_success = sum(r["status"] == "success" for r in results.values())
    logger.info(
        "legacy_status_geojson_complete",
        extra={
            "sites_total": len(site_list),
            "sites_success": n_success,
            "sites_failure": len(site_list) - n_success,
            "output_path": str(output_path),
        },
    )

    return results


# -----------------------------------------------------------------------------


def _build_site_feature(site: str) -> dict:
    """Build one site's geojson Feature. Never raises — a failure is returned as
    a result, not thrown, so one bad site can't take down the concurrent
    run_concurrent dispatch for the rest.
    """
    try:
        status = _get_site_status(site)

        days_since_last_record = min(
            v["days_since_last_record"]
            for v in status.values()
            if isinstance(v["days_since_last_record"], int)
        )

        properties = {
            "days_since_last_record": days_since_last_record,
            **{var: v["days_since_last_valid_record"] for var, v in status.items()},
        }

        metadata = SITE_REGISTRY.get_metadata(site)

        # Coordinate order matches the old producer ([latitude, longitude],
        # not GeoJSON-spec [lon, lat]) to stay compatible with however the
        # downstream status map currently parses this file.
        feature = geojson.Feature(
            id=site,
            geometry=geojson.Point(coordinates=[metadata.latitude, metadata.longitude]),
            properties=properties,
        )

        return {"status": "success", "feature": feature}

    except Exception as e:
        logger.warning(
            "legacy_status_site_failed",
            extra={"site": site, "error": str(e)},
            exc_info=True,
        )
        return {
            "status": "failure",
            "error_type": type(e).__name__,
            "error": str(e),
        }


# -----------------------------------------------------------------------------


def _open_dataset_with_retry(file_path) -> xr.Dataset:
    """Open a NetCDF file, retrying briefly on OSError.

    Guards against the narrow window where a reader's open() races a
    writer's atomic rename on shared network storage (surfaces as netCDF4
    "Unknown file format" or similar low-level OSErrors, not a real
    malformed file).
    """
    for attempt in range(_NC_OPEN_RETRIES + 1):
        try:
            return xr.open_dataset(file_path)
        except OSError:
            if attempt == _NC_OPEN_RETRIES:
                raise
            logger.warning(
                "nc_open_retry",
                extra={"file": str(file_path), "attempt": attempt + 1},
            )
            time.sleep(_NC_OPEN_RETRY_DELAY_SECS)


# -----------------------------------------------------------------------------


def _get_site_status(site: str) -> dict:
    """Read the latest L1 NetCDF file for a site and compute per-SUBSET-variable
    staleness/validity stats.
    """
    file_path = get_latest_nc_file(site=site)
    ds = _open_dataset_with_retry(file_path)

    with ds:
        tz_name = ds.attrs["time_zone"]
        # squeeze drops the singleton latitude/longitude dims build_L1_nc
        # attaches, so to_dataframe() indexes by time alone rather than a
        # (time, latitude, longitude) MultiIndex.
        df = ds[SUBSET].squeeze().to_dataframe()

    # NetCDF time values follow the local-time convention (naive timestamps),
    # matching services.network.nc_monitor / data_monitor.
    site_time = datetime_utils.get_local_datetime_now(
        tz_name=tz_name,
        return_tz_aware=False,
    )

    registry = build_canonical_quantity_registry()

    return {
        variable: _parse_variable(
            series=df[variable],
            valid_range=(
                registry.get_base_metadata(variable).valid_min,
                registry.get_base_metadata(variable).valid_max,
            ),
            site_time=site_time,
        )
        for variable in SUBSET
    }


# -----------------------------------------------------------------------------


def _filter_range(series, max_val, min_val):
    """Mask series values outside [min_val, max_val] to NaN (either bound may be None)."""
    if isinstance(max_val, (int, float)) and isinstance(min_val, (int, float)):
        return series.where((series <= max_val) & (series >= min_val), np.nan)
    if isinstance(max_val, (int, float)):
        return series.where(series <= max_val, np.nan)
    if isinstance(min_val, (int, float)):
        return series.where(series >= min_val, np.nan)
    return series


# -----------------------------------------------------------------------------


def _parse_variable(
    series,
    valid_range: tuple,
    site_time: dt.datetime,
) -> dict:
    """Compute staleness/validity stats for one variable's time series.

    Args:
        series: time-indexed variable data.
        valid_range: (min, max) plausible-value bounds; either may be None.
        site_time: site-local naive "now" to measure elapsed time against.

    Returns:
        Dict with days-since-last-record and last-24h validity stats.
    """
    rec = {
        "days_since_last_record": "N/A",
        "last_valid_value": None,
        "last_valid_record_datetime": None,
        "last_24hr_pct_valid": 0,
        "days_since_last_valid_record": "N/A",
    }

    if series.empty:
        return rec

    rec["days_since_last_record"] = (site_time - series.index[-1]).days

    filtered = _filter_range(
        series.copy(), max_val=valid_range[1], min_val=valid_range[0]
    ).dropna()

    if filtered.empty:
        return rec

    last_valid_time = filtered.index[-1]
    days_since_valid = (site_time - last_valid_time).days
    pct_valid = 0

    if days_since_valid == 0:
        window_start = site_time - dt.timedelta(days=1)
        raw_window = series.loc[window_start:site_time]
        if not raw_window.empty:
            valid_window = filtered.loc[window_start:site_time]
            pct_valid = round(len(valid_window) / len(raw_window) * 100)

    rec.update(
        {
            "last_valid_value": filtered.iloc[-1],
            "last_valid_record_datetime": last_valid_time,
            "last_24hr_pct_valid": pct_valid,
            "days_since_last_valid_record": days_since_valid,
        }
    )

    return rec


# -----------------------------------------------------------------------------

###############################################################################
### END FUNCTIONS ###
###############################################################################
