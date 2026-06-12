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
