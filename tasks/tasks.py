# -*- coding: utf-8 -*-
"""
Created on Fri Aug  2 09:43:07 2024

@author: jcutern-imchugh

Note that some imports are embedded in the task function calls so that all modules
do not need to be loaded every time the task manager is called externally!
"""

###############################################################################
### BEGIN IMPORTS ###
###############################################################################

# import argparse
import datetime as dt
import inspect
import logging.config
import pathlib
from importlib import import_module
from typing import Callable

#------------------------------------------------------------------------------

from tasks.registry import register, SITE_TASKS, GLOBAL_TASKS
from services.domain import config_loader
# from file_transfers import sftp_transfer as sftpt
from infrastructure import paths
from tasks.logger_config import configure_logger_json
from services.domain import global_metadata_service as gms

###############################################################################
### END IMPORTS ###
###############################################################################


###############################################################################
### BEGIN INITS ###
###############################################################################

task_list = list(SITE_TASKS.keys()) + list(GLOBAL_TASKS.keys())
logger = logging.getLogger(__name__)

#------------------------------------------------------------------------------
class SiteTaskManager():
    """
    Ingest csv site / task boolean matrix and expose methods to get task 
    lists
    """
    
    #--------------------------------------------------------------------------
    def __init__(self) -> None:
        """
        Initialise with contents of csv config file.

        Returns:
            None.

        """
        
        self.tasks_df = (
            config_loader.load_config_file_from_name('tasks')
            .set_index(keys='Site')
            .astype(bool)
            )
    #--------------------------------------------------------------------------

    #--------------------------------------------------------------------------    
    def get_site_list(self) -> list:
        """
        Return the list of sites.

        Returns:
            the list.

        """
        
        return self.tasks_df.index.tolist()
    #--------------------------------------------------------------------------

    #--------------------------------------------------------------------------        
    def get_site_list_for_task(self, task: str, disabled=False) -> list:
        """
        Return the list of sites for which task is enabled.

        Args:
            task: name of task.
            disabled: set True to get a list of sites for which task is disabled.

        Returns:
            the list.

        """
        
        return self.tasks_df[~self.tasks_df[task]==disabled].index.tolist()
    #--------------------------------------------------------------------------

    #--------------------------------------------------------------------------
    def get_site_task_status(self, site: str, task: str) -> bool:
        """
        Get the status of a site task.

        Args:
            site: name of site.
            task: name of task.

        Returns:
            Status.

        """
        
        return self.tasks_df.loc[site, task]
    #-------------------------------------------------------------------------- 

    #--------------------------------------------------------------------------    
    def get_task_list(self):
        """
        Return the list of tasks.

        Returns:
            the list.

        """
        
        return self.tasks_df.columns.tolist()        
    #--------------------------------------------------------------------------

    #--------------------------------------------------------------------------    
    def get_task_list_for_site(self, site: str, disabled=False) -> list:
        """
        Return the list of enabled tasks for a site.

        Args:
            site: name of site.

        Returns:
            the list.

        """
        
        return self.tasks_df.columns[~self.tasks_df.loc[site]==disabled]
    #--------------------------------------------------------------------------

    #--------------------------------------------------------------------------
    def set_site_task_status(self, site: str, task: str, status: bool) -> None:
        """
        Edit the status of a site task.

        Args:
            site: name of site.
            task: name of task.
            status: status of task.

        Raises:
            TypeError: raised if `status` kwarg not passed a boolean.

        Returns:
            None.

        """
        
        if not isinstance(status, bool):
            raise TypeError('`status` kwarg must be a boolean')
        self.tasks_df.loc[site, task] = status
    #--------------------------------------------------------------------------
    
    #--------------------------------------------------------------------------
    def write_tasks_config(self) -> None:
        """
        Write config file.

        Returns:
            None.

        """
        
        self.tasks_df.to_csv(
            paths.get_internal_config_path('tasks'), 
            index_label='Site'
            )
    #--------------------------------------------------------------------------

#------------------------------------------------------------------------------

# Instantiate tasks manager at top level, since for site-based tasks, it must be
# repeatedly called.
mngr = SiteTaskManager()

###############################################################################
### END INITS ###
###############################################################################



###############################################################################
### BEGIN TASK DEFINITION FUNCTIONS ###
###############################################################################

#------------------------------------------------------------------------------
### BEGIN DATA CONSTRUCTORS ###
#------------------------------------------------------------------------------

# #------------------------------------------------------------------------------
# @register
# def construct_homogenised_TOA5_from_nc(site: str) -> None:

#     nctoa5 = import_module('data_constructors.nc_toa5_constructor')
#     nctoa5.construct_visualisation_TOA5(site=site, n_files=2)
# #------------------------------------------------------------------------------

#------------------------------------------------------------------------------
@register
def construct_L1_nc(site: str) -> None:
    """Construct the L1 NetCDF file"""

    nccon = import_module('data_constructors.nc_constructors')
    L1con = nccon.L1DataConstructor(
        site=site, constrain_start_to_flux=True, concat_files=True, 
        pad_humidity_vars=True
        )
    this_year = dt.datetime.now().year
    if max(L1con.data_years) == this_year:
        L1con.write_nc_file_by_year(year=this_year, overwrite=True)
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
@register
def update_EddyPro_master(site: str) -> None:

    epc = import_module('file_handling.eddypro_concatenator')
    epc.update_eddypro_master(site=site)
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
@register
def construct_site_details(site: str) -> None:
    """Construct the details file for the RTMC plotting"""

    deetcon = import_module('data_constructors.details_constructor')
    deetcon.write_site_info(site=site)
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
@register
def construct_site_details_json(site_list) -> None:
    
    deetcon = import_module('data_constructors.details_constructor')
    return deetcon.site_info_2_json(site_list=site_list)
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
@register
def construct_status_xlsx() -> None:
    """Construct the status xlsx seeded with site list"""

    ns = import_module('network_monitoring.network_status')
    this_task = inspect.stack()[0][3]
    ns.write_status_xlsx(
        site_list=mngr.get_site_list_for_task(task=this_task)
        )
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
@register
def construct_status_geojson(site_list) -> None:
    """Construct the status geojson seeded with site list"""

    ns = import_module('network_monitoring.network_status')
    return ns.network_status_to_geojson(site_list=site_list)
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
### END DATA CONSTRUCTORS ###
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
### BEGIN NETWORK CHECKS ###
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
@register
def check_site_connections(site_list) -> dict:
    
    ns = import_module('services.orchestration.network_services')
    return ns.scan_network(site_list=site_list)
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
### END NETWORK CHECKS ###
#------------------------------------------------------------------------------



#------------------------------------------------------------------------------
### BEGIN DATA PROCESSING ###
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
@register
def process_profile_data(site: str) -> None:

    pdp = import_module('profile_processing.profile_data_processor')
    output_path = paths.get_local_stream_path(
        resource='processed_data',
        stream='profile',
        site=site,
        )
    processor = pdp.load_site_profile_processor(site=site)
    processor.write_to_csv(file_name=output_path / 'storage_data.csv')
    processor.plot_diel_storage_mean(
        output_to_file=output_path / 'diel_storage_mean.png', open_window=False
        )
    processor.plot_time_series(
        output_to_file=output_path / 'diel_storage_mean.png', open_window=False
        )
    processor.plot_vertical_evolution_mean(
        output_to_file=output_path / 'vertical_evolution_mean.png',
        open_window=False
        )
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
### END DATA PROCESSING ###
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
### BEGIN LOCAL DATA MOVING ###
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
@register
def parse_main_fast_data(site: str) -> None:

    _parse_fast_data(site=site, is_aux=False)
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
@register
def parse_aux_fast_data(site: str) -> None:

    _parse_fast_data(site=site, is_aux=True)
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def _parse_fast_data(site: str, is_aux: bool) -> None:

    ffc = import_module('data_constructors.fast_file_converters')
    ffc.parse_TOB3_daily(site=site, is_aux=is_aux)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

@register
def process_fast_data(site: str) -> dict:
    
    fd_task = import_module('services.orchestration.fast_data')
    
    root_dir = paths.get_local_stream_path(
        resource='raw_data', 
        stream='flux_fast', 
        site=site
        )
    input_dir = root_dir / 'TMP'
    
    details = (
        gms.get_metadata_manager(source='yml')
        .get_single_site_details(site=site)
        )
    
    return fd_task.process_all_fast_daily(
        site=site,
        input_dir=input_dir,
        root_dir=root_dir,
        time_step=details.time_step,
        freq_hz=details.freq_hz
        )

#------------------------------------------------------------------------------
### END LOCAL DATA MOVING ###
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
### BEGIN RCLONE DATA TRANSFERS ###
#------------------------------------------------------------------------------

# PULL TASKS

#------------------------------------------------------------------------------
@register
def pull_profile_raw(site: str):

    return transfer_stream(
        resource='raw_data', 
        stream_local='profile', 
        to_remote=False,
        path_kwargs={'site': site},
        )
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
@register
def pull_RTMC_images():

    return transfer_stream(
        resource='network', 
        stream_local='RTMC_images', 
        stream_remote='RTMC_image_source', 
        to_remote=False,
        set_modtime=False
        )
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
@register
def pull_slow_flux(site: str):

    return transfer_stream(
        resource='raw_data', 
        stream_local='flux_slow', 
        to_remote=False,
        path_kwargs={'site': site},
        )
#------------------------------------------------------------------------------

# PUSH TASKS

#------------------------------------------------------------------------------
@register
def push_aux_fast_flux(site: str):

    return transfer_stream(
        resource='raw_data', 
        stream_local='flux_fast_aux',
        exclude_dirs=['TMP'], 
        timeout=1200,
        path_kwargs={'site': site},
        )
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
@register
def push_details_json():

    return transfer_stream(
        resource='network', 
        stream_local='status',
        path_kwargs={'file_name': 'site_info.json'}
        )
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
@register
def push_homogenised_TOA5():

    return transfer_stream(
        resource='homogenised_data', 
        stream_local='TOA5',
        timeout=180,
        )
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
@register
def push_L1_nc():

    return transfer_stream(
        resource='homogenised_data', 
        stream_local='nc', 
        timeout=180,
        )    
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
@register
def push_main_fast_flux(site):

    return transfer_stream(
        resource='raw_data', 
        stream_local='flux_fast',
        exclude_dirs=['TMP'], 
        timeout=1200,
        path_kwargs={'site': site},
        )
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
@register
def push_profile_processed(site):

    return transfer_stream(
        resource='processed_data', 
        stream_local='profile',
        path_kwargs={'site': site},
        )    
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
@register
def push_profile_raw(site: str) -> None:

    return transfer_stream(
        resource='raw_data', 
        stream_local='profile',
        path_kwargs={'site': site},
        )        
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
@register
def push_RTMC_images():

    return transfer_stream(
        resource='network', 
        stream_local='RTMC_images', 
        stream_remote='RTMC_image_dest', 
        set_modtime=False,
        )
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
@register
def push_slow_flux(site):

    return transfer_stream(
        resource='raw_data',
        stream_local='flux_slow', 
        path_kwargs={'site': site},
        )    
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
@register
def push_status_geojson() -> None:
    """Use Rclone to push data to rdm"""

    return transfer_stream(
        resource='network', 
        stream_local='status',
        path_kwargs={'file_name': 'network_status.json'}
        )
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
@register
def push_status_xlsx() -> None:
    """Use Rclone to push data to rdm"""

    return transfer_stream(
        resource='network', 
        stream_local='status',
        path_kwargs={'file_name': 'network_status.xlsx'}
        )
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def transfer_stream(
        resource: str,
        stream_local: str,
        stream_remote: str | None = None,
        to_remote: bool = True,
        path_kwargs: dict | None = None,
        **rclone_kwargs
        ) -> dict:
    """
    Generic stream transfer: local <-> remote.

    Args:
        resource: resource type (e.g., 'raw_data', 'network')
        stream_local: local stream name
        stream_remote: remote stream name (defaults to same as stream_local)
        site: optional site identifier
        to_remote: True=local->remote (push), False=remote->local (pull)
        rclone_kwargs: passed to run_rclone_task
    """

    # Save passing the stream name twice
    if stream_remote is None:
        stream_remote = stream_local
        
    # Ensure path_kwargs is a dict and extract file_name if present
    path_kwargs = path_kwargs or {}
    file_name = path_kwargs.pop('file_name', None)

    # Get paths
    local_path = paths.get_local_stream_path(
        resource=resource,
        stream=stream_local,
        **path_kwargs
        )
    remote_path = paths.get_remote_stream_path(
        resource=resource,
        stream=stream_remote,
        **path_kwargs            
        )
    
    if file_name:
       local_path = local_path / file_name
       
    src, dst = (local_path, remote_path) if to_remote else (remote_path, local_path)

    try:
        result = run_rclone_task(src=src, dst=dst, **rclone_kwargs)

        return {
            "status": "success",
            "src": str(src),
            "dst": str(dst),
            "exit_code": result.returncode,
        }

    except Exception:
        return {
            "status": "failure",
            "src": str(src),
            "dst": str(dst),
        }
# -----------------------------------------------------------------------------

#------------------------------------------------------------------------------
def run_rclone_task(
        src, 
        dst,
        *,
        exclude_dirs=None, 
        set_modtime=True, 
        validate=True, 
        timeout=600
        ):
    """
    Generic wrapper for any rclone transfer.

    Handles:
      - calling rclone_transfer.transfer()
      - logging
      - error handling
    """
    
    rt = import_module('infrastructure.rclone_transfer')
    try:
        logger.info(
            "rclone_transfer_start",
            extra={
                "src": str(src),
                "dst": str(dst),
                },
            )
        result = rt.transfer(
            src=src,
            dst=dst,
            exclude_dirs=exclude_dirs,
            set_modtime=set_modtime,
            validate=validate
        )
        
        returncode = getattr(result, "returncode", None)
        
        if returncode not in (0, None):
            logger.error(
                "rclone_transfer_nonzero_exit",
                extra={
                    "src": str(src),
                    "dst": str(dst),
                    "returncode": returncode,
                },
            )
            raise RuntimeError(
                f"rclone returned non-zero exit code: {returncode}"
            )

        logger.info(
            "rclone_transfer_success",
            extra={
                "src": str(src),
                "dst": str(dst),
                "returncode": returncode,
                },
            )

        return result

    except Exception:
        logger.exception(
            "rclone_transfer_failed",
            extra={
                "src": str(src),
                "dst": str(dst),
                },
            )
        raise

#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
### END RCLONE DATA TRANSFERS ###
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
### BEGIN SFTP DATA TRANSFERS ###
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
# @register
# def push_cosmoz(site) -> None:

#     sftpt.push_cosmoz(site=site)
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
### END SFTP DATA TRANSFERS ###
#------------------------------------------------------------------------------

###############################################################################
### END TASK DEFINITION FUNCTIONS ###
###############################################################################


###############################################################################
### BEGIN TASK MANAGEMENT FUNCTIONS ###
###############################################################################

# --------------------------------------------------------------------------

def run_task(task: str, site: str | None = None) -> None:
    """
    Unified entry point to run any task.

    Args:
        task: task name
        site: optional site (only valid for site-scoped tasks)
    """

    # Get task function and scope
    function, scope = _resolve_task(task=task, site=site)

    # Set up logger
    _setup_logger(task)

    # Dispatch to helper based on scope
    try:
        if scope == "site":
            _run_site_task(task, function, site)
        else:
            _run_global_task(task, function)
    except Exception:
        logger.error(
            "task_end",
            extra={"task": task, "scope": scope, "status": "failure", "reason": "unhandled_exception"},
            exc_info=True,
            )
        raise
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def _resolve_task(task: str, site: str | None) -> tuple:
    """
    Resolve the task function and its scope.
    """
    
    # Locate task function and scope
    if task in SITE_TASKS:
        func = SITE_TASKS[task]
        scope = "site"
    elif task in GLOBAL_TASKS:
        func = GLOBAL_TASKS[task]
        scope = "global"
    else:
        raise NotImplementedError(
            f"Task '{task}' has unknown scope or is not implemented"
            )

    # Prevent illegal combinations
    if scope == "global" and site is not None:
        raise ValueError(
            f"Task '{task}' is global and cannot be run per-site"
            )

    return func, scope
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def _setup_logger(task: str) -> pathlib.Path:
    """
    Configure JSON logger for this task.
    """
    
    log_path = (
        paths.get_local_stream_path(resource="logs", stream="network_logs")
        / f"{task}.jsonl"
        )
    configure_logger_json(log_path=log_path)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def _run_site_task(task: str, function: Callable, site: str | None) -> None:
    """
    Execute a site-scoped task (may iterate over multiple sites)
    """
    
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

    for site in site_list:
        result = _run_single_site_task(task, function, site)
        if result.get("status") == "failure":
            failed_sites.append(site)

        logger.info(
            "task_site_result", 
            extra={
                "task": task, 
                "site": site, 
                **result
                }
            )

    overall_status = "failure" if failed_sites else "success"
    logger.info("task_end", extra={"task": task, "scope": "site", "status": overall_status, "failed_sites": failed_sites})
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def _get_sites_for_task(task: str) -> list[str]:
    """
    Fetch site list for a task from metadata manager.
    """

    try:
        return mngr.get_site_list_for_task(task=task)
    except KeyError:
        return mngr.get_site_list()
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def _run_single_site_task(task: str, func, site: str) -> dict:
    """
    Execute a single site task with error handling and validation.
    """
    try:
        result = func(site)

        if not isinstance(result, dict) or "status" not in result:
            logger.error(
                "task_site_invalid_result",
                extra={
                    "task": task, 
                    "site": site, 
                    "returned_type": type(result).__name__
                    },
                )
            return {"status": "failure", "reason": "invalid_result_format"}

        return result

    except Exception:
        
        logger.exception(
            "task_site_exception", 
            extra={
                "task": task, 
                "site": site
                }
            )
        return {
            "status": "failure", 
            "reason": "exception"
            }
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def _run_global_task(task: str, func: Callable, site_list: list[str] | None = None) -> None:
    """
    Execute a global task. If the task function accepts 'site_list', pass it;
    otherwise call with no arguments.
    """

    logger.info("task_start", extra={"task": task, "scope": "global"})

    try:
        # Check if the function accepts a 'site_list' argument
        sig = inspect.signature(func)
        if 'site_list' in sig.parameters:
            result = func(site_list)
        else:
            result = func()

        # Standardize logging
        if isinstance(result, dict) and "status" in result:
            extra = {"task": task, "scope": "global", **result}
        else:
            extra = {"task": task, "scope": "global", "status": "success"}

        logger.info("task_end", extra=extra)

    except Exception as e:
        logger.error(
            "task_end",
            extra={"task": task, "scope": "global", "status": "failure", "reason": str(e)},
            exc_info=True,
        )
        raise
# -----------------------------------------------------------------------------

###############################################################################
### END TASK MANAGEMENT FUNCTIONS ###
###############################################################################
