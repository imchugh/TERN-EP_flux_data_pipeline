# -*- coding: utf-8 -*-
"""
Task definitions and runner for the flux data pipeline.

Note: imports are embedded inside task function bodies so that all modules do
not need to be loaded every time the runner is called.
"""

###############################################################################
### BEGIN IMPORTS ###
###############################################################################

import datetime as dt
import logging
import pathlib
from importlib import import_module
from typing import Callable

# -----------------------------------------------------------------------------

from infrastructure import paths
from infrastructure.paths import CONFIG_PATH
from services import config_loader
from services.metadata.site_registry import SiteRegistry
from tasks.logger_config import configure_logger_json
from tasks.registry import register, SITE_TASKS, GLOBAL_TASKS

###############################################################################
### END IMPORTS ###
###############################################################################


###############################################################################
### BEGIN INITS ###
###############################################################################

logger = logging.getLogger(__name__)
SITE_REGISTRY = SiteRegistry()

# -----------------------------------------------------------------------------

class SiteTaskManager:
    """CSV site/task boolean matrix — exposes per-task site lists."""

    def __init__(self) -> None:

        self.tasks_df = (
            config_loader.load_config_file_from_name('tasks')
            .set_index(keys='Site')
            .astype(bool)
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
            raise TypeError('`status` kwarg must be a boolean')
        self.tasks_df.loc[site, task] = status

    def write_tasks_config(self) -> None:
        self.tasks_df.to_csv(CONFIG_PATH / 'tasks.csv', index_label='Site')

    def _validate(self) -> None:
        registered = set(SITE_TASKS) | set(GLOBAL_TASKS)
        unknown_tasks = set(self.tasks_df.columns) - registered
        if unknown_tasks:
            raise ValueError(
                f'tasks.csv references unregistered tasks: {unknown_tasks}'
                )
        known_sites = set(SITE_REGISTRY.names())
        unknown_sites = set(self.tasks_df.index) - known_sites
        if unknown_sites:
            raise ValueError(
                f'tasks.csv references sites not in SITE_REGISTRY: {unknown_sites}'
                )

###############################################################################
### END INITS ###
###############################################################################


###############################################################################
### BEGIN TASK DEFINITIONS ###
###############################################################################

# -----------------------------------------------------------------------------
### DATA CONSTRUCTORS
# -----------------------------------------------------------------------------

@register
def construct_L1_nc(site: str) -> dict:
    """Build the current-year L1 NetCDF file."""

    build_nc = import_module('orchestration.build_L1_nc')
    this_year = dt.datetime.now().year
    written = build_nc.build(site_name=site, year=this_year)
    return {'status': 'success', 'files_written': [str(p) for p in written]}

# -----------------------------------------------------------------------------

@register
def update_EddyPro_master(site: str) -> None:

    epc = import_module('file_handling.eddypro_concatenator')
    epc.update_eddypro_master(site=site)

# -----------------------------------------------------------------------------

@register
def construct_site_details(site: str) -> None:
    """Construct the details file for RTMC plotting."""

    deetcon = import_module('data_constructors.details_constructor')
    deetcon.write_site_info(site=site)

# -----------------------------------------------------------------------------

@register
def construct_site_details_json() -> None:

    deetcon = import_module('data_constructors.details_constructor')
    deetcon.site_info_2_json(site_list=mngr.get_site_list())

# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

@register
def construct_status_geojson() -> None:
    """Construct the network status geojson."""

    ns = import_module('network_monitoring.network_status')
    ns.network_status_to_geojson(
        site_list=mngr.get_site_list_for_task(task='construct_status_geojson')
        )

# -----------------------------------------------------------------------------
### DATA PROCESSING
# -----------------------------------------------------------------------------

@register
def process_profile_data(site: str) -> None:

    pdp = import_module('profile_processing.profile_data_processor')
    output_path = paths.get_local_stream_path(
        resource='processed_data', stream='profile', site=site,
        )
    processor = pdp.load_site_profile_processor(site=site)
    processor.write_to_csv(file_name=output_path / 'storage_data.csv')
    processor.plot_diel_storage_mean(
        output_to_file=output_path / 'diel_storage_mean.png', open_window=False
        )
    processor.plot_time_series(
        output_to_file=output_path / 'time_series.png', open_window=False
        )
    processor.plot_vertical_evolution_mean(
        output_to_file=output_path / 'vertical_evolution_mean.png',
        open_window=False
        )

# -----------------------------------------------------------------------------
### LOCAL FILE HANDLING
# -----------------------------------------------------------------------------

@register
def parse_main_fast_data(site: str) -> None:

    _parse_fast_data(site=site, is_aux=False)

# -----------------------------------------------------------------------------

@register
def parse_aux_fast_data(site: str) -> None:

    _parse_fast_data(site=site, is_aux=True)

# -----------------------------------------------------------------------------

def _parse_fast_data(site: str, is_aux: bool) -> None:

    ffc = import_module('data_constructors.fast_file_converters')
    ffc.parse_TOB3_daily(site=site, is_aux=is_aux)

# -----------------------------------------------------------------------------
### RCLONE DATA TRANSFERS — PULL
# -----------------------------------------------------------------------------

@register
def pull_profile_raw(site: str) -> None:

    rct = import_module('infrastructure.rclone_transfer')
    rct.move_site_data_stream(
        site=site, resource='raw_data', stream='profile', which_way='from_remote'
        )

# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

@register
def pull_slow_flux(site: str) -> None:

    rct = import_module('infrastructure.rclone_transfer')
    rct.move_site_data_stream(
        site=site, resource='raw_data', stream='flux_slow', which_way='from_remote'
        )

# -----------------------------------------------------------------------------
### RCLONE DATA TRANSFERS — PUSH
# -----------------------------------------------------------------------------

@register
def push_aux_fast_flux(site: str) -> None:

    rct = import_module('infrastructure.rclone_transfer')
    rct.move_site_data_stream(
        site=site, resource='raw_data', stream='flux_fast_aux',
        exclude_dirs=['TMP'], timeout=1200,
        )

# -----------------------------------------------------------------------------

@register
def push_details_json() -> None:

    rct = import_module('infrastructure.rclone_transfer')
    rct.push_details_json()

# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

@register
def push_L1_nc() -> None:

    rct = import_module('infrastructure.rclone_transfer')
    rct.push_homogenised(stream='nc')

# -----------------------------------------------------------------------------

@register
def push_main_fast_flux(site: str) -> None:

    rct = import_module('infrastructure.rclone_transfer')
    rct.move_site_data_stream(
        site=site, resource='raw_data', stream='flux_fast',
        exclude_dirs=['TMP'], timeout=1200,
        )

# -----------------------------------------------------------------------------

@register
def push_profile_processed(site: str) -> None:

    rct = import_module('infrastructure.rclone_transfer')
    rct.move_site_data_stream(
        site=site, resource='processed_data', stream='profile',
        )

# -----------------------------------------------------------------------------

@register
def push_profile_raw(site: str) -> None:

    rct = import_module('infrastructure.rclone_transfer')
    rct.move_site_data_stream(
        site=site, resource='raw_data', stream='profile', which_way='to_remote'
        )

# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

@register
def push_slow_flux(site: str) -> None:

    rct = import_module('infrastructure.rclone_transfer')
    rct.move_site_data_stream(
        site=site, resource='raw_data', stream='flux_slow',
        )

# -----------------------------------------------------------------------------

@register
def push_status_geojson() -> None:

    rct = import_module('infrastructure.rclone_transfer')
    rct.push_status_file(which='geojson')

# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
### SFTP DATA TRANSFERS
# -----------------------------------------------------------------------------

@register
def push_cosmoz(site: str) -> None:

    sftpt = import_module('infrastructure.sftp_transfer')
    sftpt.push_cosmoz(site=site)

###############################################################################
### END TASK DEFINITIONS ###
###############################################################################

# Instantiated here so SITE_TASKS / GLOBAL_TASKS are fully populated before
# validation runs.
mngr = SiteTaskManager()

###############################################################################
### BEGIN RUNNER ###
###############################################################################

def run_task(task: str, site: str | None = None) -> None:
    """
    Unified entry point to run any registered task.

    Args:
        task: registered task name.
        site: optional site name — valid only for site-scoped tasks.  When
            omitted for a site-scoped task the CSV matrix is used to build the
            site list.
    """

    func, scope = _resolve_task(task=task, site=site)
    _setup_logger(task=task)

    try:
        if scope == 'site':
            _run_site_task(task=task, function=func, site=site)
        else:
            _run_global_task(task=task, func=func)
    except Exception:
        logger.error(
            'task_end',
            extra={'task': task, 'scope': scope, 'status': 'failure',
                   'reason': 'unhandled_exception'},
            exc_info=True,
            )
        raise

# -----------------------------------------------------------------------------

def _resolve_task(task: str, site: str | None) -> tuple[Callable, str]:

    if task in SITE_TASKS:
        func, scope = SITE_TASKS[task], 'site'
    elif task in GLOBAL_TASKS:
        func, scope = GLOBAL_TASKS[task], 'global'
    else:
        raise NotImplementedError(f"Task '{task}' is not registered.")

    if scope == 'global' and site is not None:
        raise ValueError(f"Task '{task}' is global — cannot be run per-site.")

    return func, scope

# -----------------------------------------------------------------------------

def _setup_logger(task: str) -> None:

    log_path = (
        paths.get_local_stream_path(resource='logs', stream='network_logs')
        / f'{task}.jsonl'
        )
    configure_logger_json(log_path=log_path)

# -----------------------------------------------------------------------------

def _run_site_task(task: str, function: Callable, site: str | None) -> None:

    site_list = [site] if site is not None else _get_sites_for_task(task)

    logger.info(
        'task_start',
        extra={'task': task, 'scope': 'site', 'site_count': len(site_list),
               'single_site': site is not None},
        )

    failed_sites: list[str] = []
    for s in site_list:
        result = _run_single_site_task(task=task, func=function, site=s)
        if result.get('status') == 'failure':
            failed_sites.append(s)
        logger.info('task_site_result', extra={'task': task, 'site': s, **result})

    overall = 'failure' if failed_sites else 'success'
    logger.info(
        'task_end',
        extra={'task': task, 'scope': 'site', 'status': overall,
               'failed_sites': failed_sites},
        )

# -----------------------------------------------------------------------------

def _get_sites_for_task(task: str) -> list[str]:

    try:
        return mngr.get_site_list_for_task(task=task)
    except KeyError:
        logger.warning('task_not_in_csv', extra={'task': task, 'fallback': 'all_sites'})
        return mngr.get_site_list()

# -----------------------------------------------------------------------------

def _run_single_site_task(task: str, func: Callable, site: str) -> dict:

    try:
        result = func(site)
        if not isinstance(result, dict) or 'status' not in result:
            return {'status': 'success'}
        return result
    except Exception:
        logger.exception('task_site_exception', extra={'task': task, 'site': site})
        return {'status': 'failure', 'reason': 'exception'}

# -----------------------------------------------------------------------------

def _run_global_task(task: str, func: Callable) -> None:

    logger.info('task_start', extra={'task': task, 'scope': 'global'})
    try:
        result = func()
        if isinstance(result, dict) and 'status' in result:
            extra = {'task': task, 'scope': 'global', **result}
        else:
            extra = {'task': task, 'scope': 'global', 'status': 'success'}
        logger.info('task_end', extra=extra)
    except Exception as e:
        logger.error(
            'task_end',
            extra={'task': task, 'scope': 'global', 'status': 'failure',
                   'reason': str(e)},
            exc_info=True,
            )
        raise

###############################################################################
### END RUNNER ###
###############################################################################
