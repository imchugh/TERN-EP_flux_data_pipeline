# -*- coding: utf-8 -*-
"""Transfer tasks: rclone and SFTP data movement."""

from importlib import import_module

from tasks.registry import register


# -----------------------------------------------------------------------------
### PULL
# -----------------------------------------------------------------------------

@register
def pull_profile_raw(site: str) -> None:

    rct = import_module('infrastructure.rclone_transfer')
    rct.move_site_data_stream(
        site=site, resource='raw_data', stream='profile', which_way='from_remote'
        )

# -----------------------------------------------------------------------------

@register
def pull_slow_flux(site: str) -> None:

    rct = import_module('infrastructure.rclone_transfer')
    rct.move_site_data_stream(
        site=site, resource='raw_data', stream='flux_slow', which_way='from_remote'
        )

# -----------------------------------------------------------------------------
### PUSH — site-scoped
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

@register
def push_slow_flux(site: str) -> None:

    rct = import_module('infrastructure.rclone_transfer')
    rct.move_site_data_stream(
        site=site, resource='raw_data', stream='flux_slow',
        )

# -----------------------------------------------------------------------------

@register
def push_cosmoz(site: str) -> None:

    sftpt = import_module('infrastructure.sftp_transfer')
    sftpt.push_cosmoz(site=site)

# -----------------------------------------------------------------------------
### PUSH — global
# -----------------------------------------------------------------------------

@register
def push_details_json() -> None:

    rct = import_module('infrastructure.rclone_transfer')
    rct.push_details_json()

# -----------------------------------------------------------------------------

@register
def push_homogenised_TOA5() -> None:

    rct = import_module('infrastructure.rclone_transfer')
    rct.push_homogenised(stream='TOA5')

# -----------------------------------------------------------------------------

@register
def push_L1_nc() -> None:

    rct = import_module('infrastructure.rclone_transfer')
    rct.push_homogenised(stream='nc')

# -----------------------------------------------------------------------------

@register
def push_status_geojson() -> None:

    rct = import_module('infrastructure.rclone_transfer')
    rct.push_status_file(which='geojson')
