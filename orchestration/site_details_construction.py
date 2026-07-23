#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collate the per-site "site details" required for RTMC (sunrise/sunset, flux
logger metadata, missing-data percentage, latest 10Hz file) alongside the
site's fixed metadata (location, commissioning, vegetation, etc.).

`collate_site_info` is the single source of truth for this data — it returns
a flat dict for one site. `build_site_details_json` is the JSON writer built
on top of it (successor to the legacy `details_constructor.site_info_2_json`,
consumed by `tasks/build_tasks.py::construct_site_details_json`).
`build_site_details_toa5` is the second, thin consumer of the same
`collate_site_info` output — RTMC's single-line-per-site TOA5 data source
(successor to `details_constructor.write_site_info`, consumed by
`construct_site_details`).
"""

###############################################################################
### BEGIN IMPORTS ###
###############################################################################

import datetime as dt
import logging

import pandas as pd

from infrastructure import data_diagnostics, datetime_utils, file_io, paths
from infrastructure.parallel_executor import run_concurrent
from infrastructure.safe_ops import safe_component
from services.data import raw_data_loader, toa5_writer
from services.metadata.site_registry import SiteContext, SiteRegistry

###############################################################################
### END IMPORTS ###
###############################################################################


###############################################################################
### BEGIN INITS ###
###############################################################################

logger = logging.getLogger(__name__)

LOGGER_SUBSET = [
    'format', 'station_name', 'logger_type', 'serial_num', 'OS_version',
    'program_name',
    ]

# Standard TOA5 info-line field order (fixed 8-element header row).
TOA5_INFO_FIELDS = [
    'format', 'station_name', 'logger_type', 'serial_num', 'OS_version',
    'program_name', 'program_sig', 'table_name',
    ]

SUN_TIMES_FALLBACK = {'sunrise': '', 'sunset': ''}
LOGGER_INFO_FALLBACK = {key: '' for key in LOGGER_SUBSET}
MISSING_DATA_FALLBACK = {'pct_missing': ''}

# LICOR/EddyPro flux files have no TOA5-style info line, so there is no real
# logger-metadata equivalent to read — unlike CSI, which always has one.
# format/logger_type are the only fields with a meaningful fixed value; the
# rest stay blank. Lets an RTMC viewer tell at a glance whether a site is
# running a Campbell or LICOR system.
LICOR_LOGGER_INFO = {
    'format': 'LICOR',
    'station_name': '',
    'logger_type': 'SmartFlux',
    'serial_num': '',
    'OS_version': '',
    'program_name': '',
    }

# Fields present in collate_site_info's output that the legacy TOA5 details
# file never carried — 'site' is redundant there (the file already identifies
# its site via filename + station_name), 'dsa_label' is just an incidental
# extra field from the newer metadata source. Both are fine to keep in the
# JSON output; dropped here to match the historical TOA5 column set exactly.
TOA5_EXCLUDED_FIELDS = {'site', 'dsa_label'}

SITE_REGISTRY = SiteRegistry()

###############################################################################
### END INITS ###
###############################################################################


###############################################################################
### BEGIN FUNCTIONS ###
###############################################################################

# -----------------------------------------------------------------------------

def collate_site_info(
        context: SiteContext, midnight: dt.datetime | None = None
        ) -> dict:
    """
    Collate site information required for RTMC display.

    Args:
        context: combined site runtime config and metadata.
        midnight: reference date for the sunrise/sunset lookup. Defaults to
            today's midnight (server-local, naive).

    Returns:
        Flat dict of site metadata plus derived fields (start_year, sunrise,
        sunset, 10Hz_file, flux logger info, pct_missing). Individual
        components fail soft — a component that raises falls back to an
        empty/placeholder value rather than aborting the whole site.
    """

    if midnight is None:
        midnight = dt.datetime.combine(dt.datetime.now().date(), dt.time())

    metadata = context.metadata
    runtime_cfg = context.runtime_config
    site_name = runtime_cfg.site_name

    # --- Base site metadata ---------------------------------------------------

    site_info = dict(metadata)
    site_info.pop('site_name', None)
    site_info['site'] = site_name

    commissioned = metadata.get('date_commissioned')
    site_info['start_year'] = commissioned.year if commissioned is not None else ''

    # --- Sunrise / sunset ------------------------------------------------------

    sun_info = safe_component(
        fn=_get_solar_info,
        logger=logger,
        component='sun_times',
        fallback=SUN_TIMES_FALLBACK.copy(),
        metadata=metadata,
        date=midnight,
        )

    # --- Latest 10Hz (fast) file ------------------------------------------------

    fast_file_info = {
        '10Hz_file': safe_component(
            fn=_get_last_fast_file,
            logger=logger,
            component='fast_file_lookup',
            fallback='No files',
            site=site_name,
            )
        }

    # --- Flux logger metadata + missing-data % ---------------------------------

    file_format = runtime_cfg.get_file_format(runtime_cfg.flux_file)
    flux_file_path = (
        paths.get_local_stream_path(
            resource='raw_data', stream='flux_slow', site=site_name,
            )
        / runtime_cfg.flux_filename
        )

    if file_format == 'LICOR':
        # No TOA5-style info line exists to read — nothing to attempt.
        logger_info = LICOR_LOGGER_INFO.copy()
    else:
        logger_info = safe_component(
            fn=_get_flux_logger_info,
            logger=logger,
            component='logger_metadata_retrieval',
            fallback=LOGGER_INFO_FALLBACK.copy(),
            file_path=flux_file_path,
            file_format=file_format,
            )

    missing_info = safe_component(
        fn=_get_flux_data_gaps,
        logger=logger,
        component='gap_analysis',
        fallback=MISSING_DATA_FALLBACK.copy(),
        file_path=flux_file_path,
        file_format=file_format,
        interval_minutes=metadata.time_step,
        )

    # --- Combine ----------------------------------------------------------------

    combined_info = (
        site_info | sun_info | fast_file_info | logger_info | missing_info
        )
    combined_info = {
        k: (v.date().isoformat() if isinstance(v, dt.datetime) else v)
        for k, v in combined_info.items()
        }
    combined_info = {
        k: ('' if v is None else v) for k, v in combined_info.items()
        }

    return combined_info
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def build_site_details_toa5(
        site: str, midnight: dt.datetime | None = None
        ) -> None:
    """
    Write the single-line-per-site TOA5 'details' file consumed by RTMC.

    Successor to `details_constructor.write_site_info`. Shares
    `collate_site_info` with `build_site_details_json` — same collation, a
    different writer — so the JSON and TOA5 outputs never drift out of sync
    with each other, only ever with the underlying data sources both of them
    read from. Calls `collate_site_info` directly rather than reading back
    `site_info.json`, so the two outputs stay decoupled (no run-order
    dependency, no lossy round-trip through JSON's already-stringified
    values).

    Written into the shared `homogenised_data.toa5` directory alongside
    `<site>_merged_std.dat`, so it rides along with the existing
    `push_rtmc_toa5` task without needing a push task of its own.

    Args:
        site: registered pipeline site name.
        midnight: reference date/timestamp for the row and the
            sunrise/sunset lookup. Defaults to today's midnight
            (server-local, naive).

    Returns:
        None.
    """

    if midnight is None:
        midnight = dt.datetime.combine(dt.datetime.now().date(), dt.time())

    context = SITE_REGISTRY.get_context(site=site)
    site_info = collate_site_info(context=context, midnight=midnight)
    site_info = {
        k: v for k, v in site_info.items() if k not in TOA5_EXCLUDED_FIELDS
        }

    columns = list(site_info)
    data = pd.DataFrame([site_info], index=pd.DatetimeIndex([midnight]))
    headers = [columns, ['unitless'] * len(columns), ['Smp'] * len(columns)]

    info = list(toa5_writer.DEFAULT_TOA5_INFO)
    info[1] = site
    info[-1] = 'site_details'

    output_path = (
        paths.get_local_stream_path(resource='homogenised_data', stream='toa5')
        / f'{site}_details.dat'
        )

    toa5_writer.write_toa5(
        data=data, headers=headers, file_path=output_path, info=info,
        )
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def _get_solar_info(metadata, date: dt.datetime) -> dict:
    """Get next sunrise/sunset (HH:MM) for a site, relative to `date`."""

    sun = datetime_utils.SunTime(
        lat=metadata.latitude, lon=metadata.longitude, elev=metadata.elevation,
        )

    return {
        'sunrise': sun.get_next_sunrise(date=date).strftime('%H:%M'),
        'sunset': sun.get_next_sunset(date=date).strftime('%H:%M'),
        }
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def _get_last_fast_file(site: str) -> str:
    """Return the filename of the most recent TOB3 fast-data file for a site."""

    fast_dir = (
        paths.get_local_stream_path(resource='raw_data', stream='flux_fast', site=site)
        / 'TOB3'
        )

    latest = file_io.get_most_recent_file(
        root=fast_dir, pattern='TOB3*.dat', recursive=True,
        )
    if latest is None:
        return 'No files'
    return latest.name
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def _get_flux_logger_info(file_path, file_format: str) -> dict:
    """Read the fixed subset of TOA5 info-line fields from the flux file header."""

    header_adapter = raw_data_loader.get_header_adapter(system_type=file_format)
    header = header_adapter(file_path)
    info = dict(zip(TOA5_INFO_FIELDS, header['info']))
    return {key: info.get(key) for key in LOGGER_SUBSET}
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def _get_flux_data_gaps(file_path, file_format: str, interval_minutes: int) -> dict:
    """Compute the percentage of missing records in the flux file."""

    data_adapter = raw_data_loader.get_data_adapter(system_type=file_format)
    df = data_adapter(file_path)
    gaps = data_diagnostics.analyse_data_gaps(df=df, interval_minutes=interval_minutes)
    return {'pct_missing': gaps['pct_missing']}
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def _build_site_entry(site: str) -> dict:
    """
    Collate one site's info for `build_site_details_json`. Never raises — a
    failure is returned as a result, not thrown, so one bad site can't take
    down the concurrent run_concurrent dispatch for the rest.
    """

    try:
        context = SITE_REGISTRY.get_context(site=site)
        site_info = collate_site_info(context=context)
        return {'status': 'success', 'data': {'site': site} | site_info}

    except Exception as e:
        logger.error(
            'site_info_site_failed', extra={'site': site}, exc_info=True,
            )
        return {
            'status': 'failure',
            'error_type': type(e).__name__,
            'error': str(e),
            }
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def build_site_details_json(site_list: list[str] | None = None) -> dict:
    """
    Generate site_info.json for all (or the given) pipeline sites.

    Per-site work (file reads dominate: flux data load for gap analysis,
    header read, fast-file lookup) is I/O-bound, so sites are collated
    concurrently via a thread pool — same pattern as
    `state_task_orchestrator.run_task_for_all_sites`.

    Args:
        site_list: sites to include. Defaults to every registered pipeline
            site (`SITE_REGISTRY.names()`).

    Returns:
        Per-site status dict: `{site: {"status": "success"}}` or
        `{site: {"status": "failure", "error_type": ..., "error": ...}}`.
    """

    if site_list is None:
        # Pre-warm the shared metadata cache before launching threads so all
        # threads see a populated cache rather than racing to load the same
        # YAML file.
        SITE_REGISTRY.get_all_metadata()
        site_list = SITE_REGISTRY.names()

    logger.info('site_info_generation_start', extra={'site_count': len(site_list)})

    entries = run_concurrent(task=_build_site_entry, items=site_list, max_workers=8)

    # Iterate site_list (not `entries`) so JSON output order stays
    # deterministic — run_concurrent's dict is in thread-completion order.
    data_list = [
        entries[site]['data'] for site in site_list
        if entries[site].get('status') == 'success'
        ]
    results = {
        site: (
            {'status': 'success'} if entries[site].get('status') == 'success'
            else {k: v for k, v in entries[site].items() if k != 'data'}
            )
        for site in site_list
        }

    output_path = (
        paths.get_local_stream_path(resource='network', stream='info')
        / 'site_info.json'
        )
    file_io.write_json(file_path=output_path, data=data_list)

    n_success = sum(r['status'] == 'success' for r in results.values())
    n_failure = sum(r['status'] == 'failure' for r in results.values())

    logger.info(
        'site_info_generation_complete',
        extra={
            'sites_total': len(site_list),
            'sites_success': n_success,
            'sites_failure': n_failure,
            'output_path': str(output_path),
            },
        )

    return results
# -----------------------------------------------------------------------------

###############################################################################
### END FUNCTIONS ###
###############################################################################
