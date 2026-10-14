"""Transfer tasks: rclone and SFTP data movement."""

from infrastructure import paths, rclone_transfer
from tasks.registry import register

# Sites where the flux_slow logger data is collected by the site operator and
# pushed to the remote store, rather than pulled from the logger by us — so
# for these (and only these) we pull rather than push. pull_slow_flux and
# push_slow_flux each guard against running for the wrong direction, since a
# stray CLI `--site` bypasses the tasks.csv site-selection matrix entirely.
REMOTE_COLLECTED_SITES = {"CumberlandPlain"}


# PULL - site-scoped


@register
def pull_profile_raw(site: str) -> None:
    """Pull raw profile data from the remote store for a remote-collected site."""
    if site not in REMOTE_COLLECTED_SITES:
        raise ValueError(
            f"'{site}' is not remote-collected — pull_profile_raw would "
            "overwrite local data with a foreign copy. Remote-collected "
            f"sites: {sorted(REMOTE_COLLECTED_SITES)}"
        )

    rclone_transfer.transfer(
        src=paths.get_remote_stream_path("raw_data", "profile", site=site),
        dst=paths.get_local_stream_path("raw_data", "profile", site=site),
    )


@register
def pull_slow_flux(site: str) -> None:
    """Pull raw slow-flux data from the remote store for a remote-collected site."""
    if site not in REMOTE_COLLECTED_SITES:
        raise ValueError(
            f"'{site}' is not remote-collected — pull_slow_flux would "
            "overwrite local data with a foreign copy. Remote-collected "
            f"sites: {sorted(REMOTE_COLLECTED_SITES)}"
        )

    rclone_transfer.transfer(
        src=paths.get_remote_stream_path("raw_data", "flux_slow", site=site),
        dst=paths.get_local_stream_path("raw_data", "flux_slow", site=site),
    )


# PULL — global


@register
def pull_rtmc_images() -> None:
    """Pull RTMC snapshot images from the source remote to local staging."""
    rclone_transfer.transfer(
        src=paths.get_remote_stream_path("network", "rtmc_pull"),
        dst=paths.get_local_stream_path("network", "rtmc_pull"),
    )


# PUSH — site-scoped


@register
def push_aux_fast_flux(site: str) -> None:
    """Push raw auxiliary fast-flux (TOB3) data to the remote store."""
    rclone_transfer.transfer(
        src=paths.get_local_stream_path("raw_data", "flux_fast_aux", site=site),
        dst=paths.get_remote_stream_path("raw_data", "flux_fast_aux", site=site),
        exclude_dirs=["TMP"],
        timeout=1200,
    )


@register
def push_main_fast_flux(site: str) -> None:
    """Push raw main fast-flux (TOB3) data to the remote store."""
    rclone_transfer.transfer(
        src=paths.get_local_stream_path("raw_data", "flux_fast", site=site),
        dst=paths.get_remote_stream_path("raw_data", "flux_fast", site=site),
        exclude_dirs=["TMP"],
        timeout=1200,
    )


@register
def push_profile_processed(site: str) -> None:
    """Push processed profile data (CO2 storage term) to the remote store."""
    rclone_transfer.transfer(
        src=paths.get_local_stream_path("processed_data", "profile", site=site),
        dst=paths.get_remote_stream_path("processed_data", "profile", site=site),
    )


@register
def push_profile_raw(site: str) -> None:
    """Push raw profile data to the remote store for a non-remote-collected site."""
    if site in REMOTE_COLLECTED_SITES:
        raise ValueError(
            f"'{site}' is remote-collected — push_profile_raw would overwrite "
            "the canonical remote copy with a downstream copy."
        )

    rclone_transfer.transfer(
        src=paths.get_local_stream_path("raw_data", "profile", site=site),
        dst=paths.get_remote_stream_path("raw_data", "profile", site=site),
    )


@register
def push_slow_flux(site: str) -> None:
    """Push raw slow-flux data to the remote store for a non-remote-collected site."""
    if site in REMOTE_COLLECTED_SITES:
        raise ValueError(
            f"'{site}' is remote-collected — push_slow_flux would overwrite "
            "the canonical remote copy with a downstream copy."
        )

    rclone_transfer.transfer(
        src=paths.get_local_stream_path("raw_data", "flux_slow", site=site),
        dst=paths.get_remote_stream_path("raw_data", "flux_slow", site=site),
    )


# CSIRO's own site-naming convention for the incoming/ subdirectory — not
# the same as paths.yml's remote_aliases (see note there).
COSMOZ_ALIASES = {"AliceSpringsMulga": "AliceMulga", "GreatWesternWoodlands": "GWW"}


@register
def push_cosmoz(site: str) -> None:
    """Push raw COSMOZ soil-moisture data to its remote incoming/ directory."""
    remote_dir = COSMOZ_ALIASES.get(site, site)
    rclone_transfer.transfer(
        src=paths.get_local_stream_path("raw_data", "cosmoz", site=site),
        dst=f"{paths.get_remote_stream_path('raw_data', 'cosmoz')}/{remote_dir}",
    )


# PUSH — global


@register
def push_site_details_json() -> None:
    """Push the site_info.json details file to the remote store."""
    src = paths.get_local_stream_path("network", "info") / "site_info.json"
    rclone_transfer.transfer(
        src=src,
        dst=paths.get_remote_stream_path("network", "info"),
        set_modtime=False,
    )


@register
def push_rtmc_toa5(dry_run: bool = False) -> None:
    """Push the homogenised TOA5 RTMC data source files to the remote store."""
    rclone_transfer.transfer(
        src=paths.get_local_stream_path("homogenised_data", "toa5"),
        dst=paths.get_remote_stream_path("homogenised_data", "toa5"),
        timeout=180,
        dry_run=dry_run,
    )


@register
def push_L1_nc(dry_run: bool = False) -> None:
    """Push L1 NetCDF output files to the remote store."""
    rclone_transfer.transfer(
        src=paths.get_local_stream_path("homogenised_data", "nc"),
        dst=paths.get_remote_stream_path("homogenised_data", "nc"),
        timeout=180,
        dry_run=dry_run,
    )


@register
def push_status_geojson() -> None:
    """Push the current-format network status geojson to the remote store."""
    from services.network.state_task_orchestrator import GEOJSON_PATH

    rclone_transfer.transfer(
        src=GEOJSON_PATH,
        dst=paths.get_remote_stream_path("network", "status"),
    )


@register
def push_legacy_status_geojson() -> None:
    """Push the legacy-format network_status.json.

    See orchestration/legacy_network_status.py for removal notes.
    """
    src = paths.get_local_stream_path("network", "status") / "network_status.json"
    rclone_transfer.transfer(
        src=src,
        dst=paths.get_remote_stream_path("network", "status"),
        set_modtime=False,
    )


@register
def push_rtmc_images() -> None:
    """Push RTMC snapshot images from local staging to the destination remote."""
    rclone_transfer.transfer(
        src=paths.get_local_stream_path("network", "rtmc_push"),
        dst=paths.get_remote_stream_path("network", "rtmc_push"),
    )
