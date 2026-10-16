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

import datetime as dt
import logging

import geojson

from fluxtools.datetime_utils import get_local_datetime_now
from fluxtools.file_io import write_json
from infrastructure import paths
from infrastructure.parallel_executor import run_concurrent_ordered
from services.metadata.site_registry import SiteRegistry
from services.network.data_monitor import MONITOR_VARS, mask_to_default_range
from services.network.nc_monitor import (
    NETCDF_LOCK,
    get_latest_nc_file,
    open_dataset_with_retry,
)

logger = logging.getLogger(__name__)

SITE_REGISTRY = SiteRegistry()

# Core flux quantities the status map reports staleness for — the same set
# the state-task monitor tracks.
SUBSET = MONITOR_VARS


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
        site_list = SITE_REGISTRY.names()

    logger.info(
        "legacy_status_geojson_start",
        extra={"site_count": len(site_list)},
    )

    features, results = run_concurrent_ordered(
        task=_build_site_feature, items=site_list
    )

    collection = geojson.FeatureCollection(features)
    collection["metadata"] = {
        "rundatetime": dt.datetime.now(dt.UTC).isoformat(),
    }

    output_path = (
        paths.get_local_stream_path("network", "status") / "network_status.json"
    )
    write_json(file_path=output_path, data=collection)

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


def _build_site_feature(site: str) -> geojson.Feature:
    """Build one site's geojson Feature."""
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
    return geojson.Feature(
        id=site,
        geometry=geojson.Point(coordinates=[metadata.latitude, metadata.longitude]),
        properties=properties,
    )


def _get_site_status(site: str) -> dict:
    """Read the latest L1 NetCDF file for a site and compute per-variable stats.

    Staleness/validity stats for the fixed subset of monitored variables.
    """
    file_path = get_latest_nc_file(site=site)

    # NETCDF_LOCK: see services.network.nc_monitor — libnetcdf's open-file
    # registry is process-global and not thread-safe in this build, so all
    # netCDF4 file access across the process must serialise on one lock.
    with NETCDF_LOCK:
        ds = open_dataset_with_retry(file_path)
        with ds:
            tz_name = ds.attrs["time_zone"]
            # squeeze drops the singleton latitude/longitude dims build_L1_nc
            # attaches, so to_dataframe() indexes by time alone rather than a
            # (time, latitude, longitude) MultiIndex.
            df = ds[SUBSET].squeeze().to_dataframe()

    # NetCDF time values follow the local-time convention (naive timestamps),
    # matching services.network.nc_monitor / services.network.data_monitor.
    site_time = get_local_datetime_now(
        tz_name=tz_name,
        return_tz_aware=False,
    )

    return {
        variable: _parse_variable(
            series=df[variable],
            valid=mask_to_default_range(df[variable], variable).dropna(),
            site_time=site_time,
        )
        for variable in SUBSET
    }


def _parse_variable(
    series,
    valid,
    site_time: dt.datetime,
) -> dict:
    """Compute staleness/validity stats for one variable's time series.

    Args:
        series: time-indexed variable data.
        valid: the plausible, non-missing subset of `series`.
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

    if valid.empty:
        return rec

    last_valid_time = valid.index[-1]
    days_since_valid = (site_time - last_valid_time).days
    pct_valid = 0

    if days_since_valid == 0:
        window_start = site_time - dt.timedelta(days=1)
        raw_window = series.loc[window_start:site_time]
        if not raw_window.empty:
            valid_window = valid.loc[window_start:site_time]
            pct_valid = round(len(valid_window) / len(raw_window) * 100)

    rec.update(
        {
            "last_valid_value": valid.iloc[-1],
            "last_valid_record_datetime": last_valid_time,
            "last_24hr_pct_valid": pct_valid,
            "days_since_last_valid_record": days_since_valid,
        }
    )

    return rec
