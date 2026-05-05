#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Feb 26 13:39:03 2026

@author: imchugh
"""

###############################################################################
### BEGIN IMPORTS ###
###############################################################################

import datetime as dt
import logging
import pathlib
import time

from infrastructure import paths, gap_analysis
from infrastructure.safe_ops import safe_component
from infrastructure.file_io import get_most_recent_file, write_json_file
from infrastructure.geospatial import TimeFunctions
from services.domain import (
    global_metadata_service, metadata_config_service,
    raw_data_loader
    )
from services.domain.file_mapping_service import get_flux_file_path

###############################################################################
### END IMPORTS ###
###############################################################################


###############################################################################
### BEGIN INITS ###
###############################################################################

DETAILS_SUBSET = []
LOGGER_SUBSET = [
    'format', 'station_name', 'logger_type', 'serial_num', 'OS_version',
    'program_name'
    ]
SUN_TIMES_FALLBACK = {
    "sunrise": '', 'sunset': '', 'time_zone': '', 'UTC_offset': ''
    }
logger = logging.getLogger(__name__)

###############################################################################
### END INITS ###
###############################################################################


###############################################################################
### BEGIN FUNCTIONS ###
###############################################################################

# -----------------------------------------------------------------------------

def build_site_info(site: str, midnight: dt.datetime | None=None) -> dict:
    """
    Collate and write site information required for RTMC files.

    Args:
        site: name of site.

    Returns:
        None.

    """

    # Use today's midnight if not provided
    if midnight is None:
        midnight = dt.datetime.combine(dt.datetime.now().date(), dt.time())

    # --- Critical components (must succeed) ----------------------------------

    # Get global metadata configs
    try:
        global_metadata = global_metadata_service.get_site_metadata(site=site)
    except KeyError as e:
        raise KeyError(f"No global metadata found for site '{site}'") from e
    
    # Get variable metadata configs
    try:
        runtime_cfg = metadata_config_service.load_runtime_config_by_site(
            site=site
            )
    except KeyError as e:
        raise KeyError(f"No variable metadata found for site '{site}'") from e

    # Get the path to the flux file
    flux_file_path = get_flux_file_path(runtime_cfg=runtime_cfg)    

    # --- Base site info ------------------------------------------------------

    # Add derived fields
    site_info = dict(global_metadata)
    site_info['site'] = site_info.pop('site_name')
    try:
        site_info['start_year'] = site_info.pop('date_commissioned').year
        # site_info.pop('date_commissioned')
    except Exception as e:
        logger.debug(
            "site_info_component_failed",
            extra={
                "event": "component_failed",
                "component": "start_year_derivation",
                "status": "failure",
                "error_type": type(e).__name__,
                }
            )
        site_info["start_year"] = ""
  
    # Get sunrise / sunset info
    sun_info = safe_component(
        fn=_get_solar_info,
        logger=logger,
        component='sun_times',
        fallback=SUN_TIMES_FALLBACK.copy(),
        site=site, 
        global_metadata=global_metadata, 
        date=midnight
        )
       
    # Fast file info
    fast_file = safe_component(
       fn=_get_last_fast_file,
       logger=logger,
       component='fast_file_lookup',
       fallback='No files',
       site=site,
       )
    if isinstance(fast_file, pathlib.Path):
        fast_file = fast_file.name
    fast_file_info = {"10Hz_file": fast_file}

    # Logger metadata
    logger_info = safe_component(
        fn=_get_flux_logger_info,
        logger=logger,
        component='logger_metadata_retrieval',
        fallback={k: "" for k in LOGGER_SUBSET},
        file_path=flux_file_path,
        system_type=runtime_cfg.system_type,
        )

    # Gap analysis
    missing_info = safe_component(
        fn=_get_flux_data_gaps,
        logger=logger,
        component='gap_analysis',
        fallback={'pct_missing': ''},
        file_path=flux_file_path,
        system_type=runtime_cfg.system_type,
        time_step=global_metadata.time_step,
        )

    # Combine all
    combined_info = (
        site_info | sun_info | fast_file_info | logger_info | missing_info
        )
    combined_info = {
        k: ('' if v is None else v) for k, v in combined_info.items()
        }
    
    return combined_info    
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def _get_solar_info(site: str, global_metadata: dict, date: dt.datetime) -> dict:
    """
    

    Args:
        site (str): DESCRIPTION.
        global_metadata (dict): DESCRIPTION.
        date (dt.datetime): DESCRIPTION.

    Returns:
        dict: DESCRIPTION.

    """
    
    time_getter = TimeFunctions(
        lat=global_metadata.latitude,
        lon=global_metadata.longitude,
        elev=global_metadata.elevation,
        date=date,
        )

    return {
        "sunrise": time_getter.get_next_sunrise().strftime("%H:%M"),
        "sunset": time_getter.get_next_sunset().strftime("%H:%M"),
        "time_zone": getattr(time_getter, "time_zone", ""),
        "UTC_offset": getattr(
            time_getter,
            "utc_offset",
            dt.timedelta(),
            ).total_seconds() / 3600,
        }
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def _get_last_fast_file(site: str) -> str:
    """
    

    Args:
        site (str): DESCRIPTION.

    Returns:
        str: DESCRIPTION.

    """
    
    fast_data_path = paths.get_local_stream_path(
        resource='raw_data', 
        stream='flux_fast',
        site=site,
        subdirs=['TOB3'],
        )    
    latest = get_most_recent_file(
        root=fast_data_path,
        pattern='TOB3*.dat',
        recursive=True
        )
    if latest is not None:
        return latest
    return 'No files'
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def _get_flux_logger_info(file_path, system_type):
    """
    

    Args:
        file_path (TYPE): DESCRIPTION.
        system_type (TYPE): DESCRIPTION.

    Returns:
        dict: DESCRIPTION.

    """
    
    header_adapter = raw_data_loader.get_header_adapter(
        system_type=system_type
        )
    header = header_adapter.load(file_path=file_path)
    logger_info = dict(zip(
        raw_data_loader.FILE_FORMATS['TOA5']['info_fields'],
        header['info']
        ))
    return {key: logger_info.get(key) for key in LOGGER_SUBSET}
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def _get_flux_data_gaps(file_path, system_type, time_step):
    """
    

    Args:
        file_path (TYPE): DESCRIPTION.
        system_type (TYPE): DESCRIPTION.
        time_step (TYPE): DESCRIPTION.

    Returns:
        dict: DESCRIPTION.

    """
    
    data_adapter = raw_data_loader.get_data_adapter(
        system_type=system_type
        )
    data = data_adapter.load(file_path=file_path)
    missing = gap_analysis.analyse_data_gaps(
        df=data, interval_minutes=time_step
        )
    return {'pct_missing': missing['pct_missing']}
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def generate_site_info(
    *,
    run_id: str,
    site_list: list[str],
    ) -> dict:
    """
    Generate site_info.json for all sites.

    Returns:
        dict: per-site status results
    """

    start = time.perf_counter()

    logger.info(
        "",
        extra={
            "event": "task_started",
            "status": "start",
            "site": None,
            "n_sites": len(site_list),
            },
        )

    data_list: list[dict] = []
    results: dict[str, dict] = {}

    for site in site_list:

        site_start = time.perf_counter()        

        logger.info(
            "",
            extra={
                "event": "site_started",
                "site": site,
                "status": "start",
                },
            )        

        
        try:
            
            site_info = build_site_info(site=site)

            data_list.append({"site": site} | site_info)

            duration = round(time.perf_counter() - site_start, 3)

            results[site] = {
                "status": "success",
                "duration_sec": duration,
                }

            logger.info(
                "",
                extra={
                    "event": "site_completed",
                    "site": site,
                    "status": "success",
                    "duration_sec": duration,
                    },
                )

        except KeyError as e:

            duration = round(time.perf_counter() - site_start, 3)

            results[site] = {
                "status": "failure",
                "error_type": "metadata_missing",
                "error": str(e),
                "duration_sec": duration,
                }

            logger.warning(
                "",
                extra={
                    "event": "site_completed",
                    "site": site,
                    "status": "failure",
                    "error_type": "metadata_missing",
                    "error": str(e),
                    "duration_sec": duration,
                    },
                )

        except Exception as e:

            duration = round(time.perf_counter() - site_start, 3)

            results[site] = {
                "status": "failure",
                "error_type": type(e).__name__,
                "error": str(e),
                "duration_sec": duration,
                }

            logger.error(
                "",
                extra={
                    "event": "site_completed",
                    "site": site,
                    "status": "failure",
                    "error_type": type(e).__name__,
                    "duration_sec": duration,
                    },
                exc_info=True,
                )

    # Infrastructure call (separated cleanly)
    output_path = paths.get_local_stream_path(
        resource="network",
        stream="status",
        file_name="site_info.json",
    )

    write_json_file(
        file_path=output_path,
        data=data_list,
        run_id=run_id,
        )

    # Summary
    n_success = sum(r["status"] == "success" for r in results.values())
    n_failure = sum(r["status"] == "failure" for r in results.values())
    duration = round(time.perf_counter() - start, 3)

    overall_status = "success" if n_failure == 0 else "partial"

    logger.info(
        "",
        extra={
            "event": "task_completed",
            "status": overall_status,
            "site": None,
            "n_sites": len(site_list),
            "n_success": n_success,
            "n_failure": n_failure,
            "duration_sec": duration,
            "output_path": str(output_path),
            },
        )

    return {
        "status": overall_status,
        "n_sites": len(site_list),
        "n_success": n_success,
        "n_failure": n_failure,
        "duration_sec": duration,
        }
# -----------------------------------------------------------------------------

###############################################################################
### END FUNCTIONS ###
###############################################################################
