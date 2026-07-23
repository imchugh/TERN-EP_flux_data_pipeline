# -*- coding: utf-8 -*-
"""Build tasks: data product construction and local file processing."""

import datetime as dt

from infrastructure import paths
from tasks.registry import register


@register
def construct_L1_nc(site: str) -> dict:
    """Build the current-year L1 NetCDF file."""

    import orchestration.build_L1_nc as build_nc
    this_year = dt.datetime.now().year
    written = build_nc.build(site_name=site, year=this_year)
    return {'status': 'success', 'files_written': [str(p) for p in written]}

# -----------------------------------------------------------------------------

@register
def construct_toa5_from_nc(site: str) -> dict:
    """Rebuild the legacy-format merged TOA5 file from L1 NetCDF output."""

    import orchestration.legacy_rtmc_export as toa5con

    nc_dir = paths.get_local_stream_path(resource='homogenised_data', stream='nc') / site
    nc_files = sorted(nc_dir.glob('*.nc'))[-2:]

    output_path = (
        paths.get_local_stream_path(resource='homogenised_data', stream='toa5')
        / f'{site}_merged_std.dat'
        )
    legacy_reference = (
        paths.get_local_stream_path(resource='homogenised_data', stream='toa5_legacy')
        / f'{site}_merged_std.dat'
        )
    if not legacy_reference.exists():
        legacy_reference = None

    toa5con.build_legacy_toa5(
        site_name=site,
        nc_files=nc_files,
        output_path=output_path,
        legacy_reference=legacy_reference,
        )
    return {'status': 'success', 'output_path': str(output_path)}

# -----------------------------------------------------------------------------

@register
def construct_site_details(site: str) -> None:
    """Construct the site details TOA5 file for RTMC plotting."""

    from orchestration.site_details_construction import build_site_details_toa5
    build_site_details_toa5(site=site)

# -----------------------------------------------------------------------------

@register
def construct_site_details_json() -> None:
    """Generate site_info.json for all sites (RTMC data source)."""

    from orchestration.site_details_construction import build_site_details_json
    from tasks.tasks import mngr
    build_site_details_json(site_list=mngr.get_site_list())

# -----------------------------------------------------------------------------

@register
def update_EddyPro_master(site: str) -> None:

    import file_handling.eddypro_concatenator as epc
    epc.update_eddypro_master(site=site)

# -----------------------------------------------------------------------------

@register
def process_profile_data(site: str) -> None:

    import profile_processing.profile_data_processor as pdp
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

@register
def parse_main_fast_data(site: str) -> None:

    _parse_fast_data(site=site, is_aux=False)

# -----------------------------------------------------------------------------

@register
def parse_aux_fast_data(site: str) -> None:

    _parse_fast_data(site=site, is_aux=True)

# -----------------------------------------------------------------------------

def _parse_fast_data(site: str, is_aux: bool) -> None:

    import services.data.tob_file_processor as tfp
    tfp.process_daily_tob_files(site=site, is_aux=is_aux)
