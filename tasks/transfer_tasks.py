# -*- coding: utf-8 -*-
"""Transfer tasks: rclone and SFTP data movement."""

from infrastructure import paths, rclone_transfer
from tasks.registry import register


# -----------------------------------------------------------------------------
### PULL
# -----------------------------------------------------------------------------

@register
def pull_profile_raw(site: str) -> None:

    rclone_transfer.transfer(
        src=paths.get_remote_stream_path('raw_data', 'profile', site=site),
        dst=paths.get_local_stream_path('raw_data', 'profile', site=site),
        )

# -----------------------------------------------------------------------------

@register
def pull_slow_flux(site: str) -> None:

    rclone_transfer.transfer(
        src=paths.get_remote_stream_path('raw_data', 'flux_slow', site=site),
        dst=paths.get_local_stream_path('raw_data', 'flux_slow', site=site),
        )

# -----------------------------------------------------------------------------
### PUSH — site-scoped
# -----------------------------------------------------------------------------

@register
def push_aux_fast_flux(site: str) -> None:

    rclone_transfer.transfer(
        src=paths.get_local_stream_path('raw_data', 'flux_fast_aux', site=site),
        dst=paths.get_remote_stream_path('raw_data', 'flux_fast_aux', site=site),
        exclude_dirs=['TMP'],
        timeout=1200,
        )

# -----------------------------------------------------------------------------

@register
def push_main_fast_flux(site: str) -> None:

    rclone_transfer.transfer(
        src=paths.get_local_stream_path('raw_data', 'flux_fast', site=site),
        dst=paths.get_remote_stream_path('raw_data', 'flux_fast', site=site),
        exclude_dirs=['TMP'],
        timeout=1200,
        )

# -----------------------------------------------------------------------------

@register
def push_profile_processed(site: str) -> None:

    rclone_transfer.transfer(
        src=paths.get_local_stream_path('processed_data', 'profile', site=site),
        dst=paths.get_remote_stream_path('processed_data', 'profile', site=site),
        )

# -----------------------------------------------------------------------------

@register
def push_profile_raw(site: str) -> None:

    rclone_transfer.transfer(
        src=paths.get_local_stream_path('raw_data', 'profile', site=site),
        dst=paths.get_remote_stream_path('raw_data', 'profile', site=site),
        )

# -----------------------------------------------------------------------------

@register
def push_slow_flux(site: str) -> None:

    rclone_transfer.transfer(
        src=paths.get_local_stream_path('raw_data', 'flux_slow', site=site),
        dst=paths.get_remote_stream_path('raw_data', 'flux_slow', site=site),
        )

# -----------------------------------------------------------------------------

@register
def push_cosmoz(site: str) -> None:

    import infrastructure.sftp_transfer as sftpt
    sftpt.push_cosmoz(site=site)

# -----------------------------------------------------------------------------
### PUSH — global
# -----------------------------------------------------------------------------

@register
def push_details_json() -> None:

    rclone_transfer.transfer(
        src=paths.get_local_stream_path('network', 'status') / 'site_info.json',
        dst=paths.get_remote_stream_path('network', 'status'),
        )

# -----------------------------------------------------------------------------

@register
def push_homogenised_TOA5() -> None:

    rclone_transfer.transfer(
        src=paths.get_local_stream_path('homogenised_data', 'toa5'),
        dst=paths.get_remote_stream_path('homogenised_data', 'toa5'),
        timeout=180,
        )

# -----------------------------------------------------------------------------

@register
def push_L1_nc() -> None:

    rclone_transfer.transfer(
        src=paths.get_local_stream_path('homogenised_data', 'nc'),
        dst=paths.get_remote_stream_path('homogenised_data', 'nc'),
        timeout=180,
        )

# -----------------------------------------------------------------------------

@register
def push_status_geojson() -> None:

    rclone_transfer.transfer(
        src=paths.get_local_stream_path('network', 'status') / 'network_status.json',
        dst=paths.get_remote_stream_path('network', 'status'),
        )
