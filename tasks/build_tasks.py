"""Build tasks: data product construction and local file processing."""

import datetime as dt

from infrastructure import file_io, paths
from tasks.registry import register


@register
def construct_L1_nc(site: str) -> dict:
    """Build the current-year L1 NetCDF file."""
    import orchestration.build_L1_nc as build_nc

    this_year = dt.datetime.now().year
    written = build_nc.build(site_name=site, year=this_year)
    return {"status": "success", "files_written": [str(p) for p in written]}


@register
def construct_L1_zarr(site: str) -> dict:
    """Incrementally update the site's whole-history L1 Zarr store.

    Runs in parallel with construct_L1_nc for now (not yet a dependency of
    it — NetCDF export still reads from raw data directly). Cheap
    regardless of total site history length: checkpoints off the store's
    own last timestamp and appends only newer records, self-healing to a
    full rebuild if the append fails (e.g. a site-config change added or
    removed a variable). See rebuild_L1_zarr for the periodic full-rebuild
    reconciliation pass this depends on to correct for backfills/config
    drift an incremental append can't see.
    """
    import orchestration.build_L1_zarr as build_zarr

    store_path = build_zarr.update(site_name=site)
    return {"status": "success", "store_path": str(store_path)}


@register
def rebuild_L1_zarr(site: str) -> dict:
    """Full rebuild of the site's whole-history L1 Zarr store from raw data.

    Reconciliation pass for construct_L1_zarr's incremental appends —
    corrects for late-arriving/backfilled raw records and site-config
    changes an append can't see. Scheduled nightly, off-peak.
    """
    import orchestration.build_L1_zarr as build_zarr

    store_path = build_zarr.build(site_name=site)
    return {"status": "success", "store_path": str(store_path)}


@register
def construct_toa5_from_nc(site: str) -> dict:
    """Rebuild the legacy-format merged TOA5 file from L1 NetCDF output."""
    import orchestration.legacy_rtmc_export as toa5con

    nc_dir = (
        paths.get_local_stream_path(resource="homogenised_data", stream="nc") / site
    )
    nc_files = sorted(nc_dir.glob("*.nc"))[-2:]

    output_path = (
        paths.get_local_stream_path(resource="homogenised_data", stream="toa5")
        / f"{site}_merged_std.dat"
    )
    legacy_reference = (
        paths.get_local_stream_path(resource="homogenised_data", stream="toa5_legacy")
        / f"{site}_merged_std.dat"
    )
    if not legacy_reference.exists():
        legacy_reference = None

    toa5con.build_legacy_toa5(
        site_name=site,
        nc_files=nc_files,
        output_path=output_path,
        legacy_reference=legacy_reference,
    )
    return {"status": "success", "output_path": str(output_path)}


@register
def construct_site_details_toa5(site: str) -> None:
    """Construct the site details TOA5 file for RTMC plotting."""
    from orchestration.site_details_construction import build_site_details_toa5

    build_site_details_toa5(site=site)


@register
def construct_site_details_json() -> None:
    """Generate site_info.json for all sites (RTMC data source)."""
    from orchestration.site_details_construction import build_site_details_json
    from tasks.tasks import mngr

    build_site_details_json(site_list=mngr.get_site_list())


@register
def update_EddyPro_master(site: str) -> dict:
    """Append new SmartFlux daily EddyPro summary files to the site's master file."""
    from domain.enums import FluxSystemType
    from services.data import eddypro_concatenator as epc
    from services.metadata.site_registry import SiteRegistry

    runtime_cfg = SiteRegistry().get_runtime_config(site)
    if runtime_cfg.flux_system != FluxSystemType.SMARTFLUX:
        # Guards against tasks.csv drift / a stray direct call fanning this
        # out to a non-EddyPro site — derived from the site's own config
        # rather than a separately maintained site list, so there's nothing
        # to keep in sync.
        raise ValueError(
            f"'{site}' does not run SmartFlux (flux_system="
            f"{runtime_cfg.flux_system.value!r}) — update_EddyPro_master "
            "only applies to SmartFlux sites."
        )

    data_path = paths.get_local_stream_path(
        resource="raw_data", stream="flux_slow", site=site
    )
    master = data_path / runtime_cfg.flux_filename
    candidates = file_io.list_available_files(data_path, "*EP-Summary.txt")
    slaves = epc.select_new_slaves(master=master, candidates=candidates)

    report = epc.concatenate_eddypro(master=master, slaves=slaves, output=master)
    return {"status": "success", **report}


@register
def process_profile_data(site: str) -> dict:
    """Compute the CO2 storage term for legacy profile-instrumented sites."""
    from orchestration import profile_processing

    return profile_processing.build_profile_output(site=site)


@register
def parse_main_fast_data(site: str) -> None:
    """Split the main fast-flux (TOB3) daily files into 30-minute TOA5 blocks."""
    _parse_fast_data(site=site, is_aux=False)


@register
def parse_aux_fast_data(site: str) -> None:
    """Split the auxiliary fast-flux (TOB3) daily files into 30-minute TOA5 blocks."""
    _parse_fast_data(site=site, is_aux=True)


def _parse_fast_data(site: str, is_aux: bool) -> None:
    """Shared implementation for parse_main_fast_data/parse_aux_fast_data."""
    import services.data.tob_file_processor as tfp

    tfp.process_daily_tob_files(site=site, is_aux=is_aux)
