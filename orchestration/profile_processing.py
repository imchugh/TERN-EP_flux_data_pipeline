#!/usr/bin/env python3
"""CO2 storage-term (Sco2) output for legacy profile-instrumented sites.

Standalone side-output — writes CSV + NetCDF under the `processed_data/
profile` stream. Not part of the main L1 canonical dataset/NetCDF pipeline.
"""

import pandas as pd
import xarray as xr

from infrastructure import file_io, paths
from services.data import profile_loader, profile_storage
from services.metadata.core.canonical_quantity_registry import (
    build_canonical_quantity_registry,
)


def build_profile_output(site: str) -> dict:
    """Load raw profile data, compute the storage term, and write CSV/NetCDF output."""
    ds = profile_loader.load_profile_dataset(site)

    csv_df = _build_csv_dataframe(ds)
    nc_ds = _build_netcdf_dataset(ds, site=site)

    output_dir = paths.get_local_stream_path(
        resource="processed_data",
        stream="profile",
        site=site,
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / "storage_data.csv"
    nc_path = output_dir / "storage_data.nc"

    csv_df.to_csv(csv_path, index_label=profile_storage.TIME_DIM)
    file_io.write_netcdf(
        ds=file_io.serialize_dataset_attrs(nc_ds),
        file_path=nc_path,
    )

    return {"status": "success", "files_written": [str(csv_path), str(nc_path)]}


def _build_csv_dataframe(ds: xr.Dataset) -> pd.DataFrame:

    layer_da = profile_storage.calculate_delta_CO2_storage(ds)
    df = layer_da.to_dataframe()["Sco2"].unstack(profile_storage.LAYER_DIM)
    df.columns = [f"Sco2_{c}" for c in df.columns]
    df["Sco2_total"] = profile_storage.calculate_summed_CO2_storage(ds).to_series()
    return df


def _build_netcdf_dataset(ds: xr.Dataset, site: str) -> xr.Dataset:

    meta = build_canonical_quantity_registry().get_base_metadata("Sco2")
    layer_da = profile_storage.calculate_delta_CO2_storage(ds)
    total_da = profile_storage.calculate_summed_CO2_storage(ds)

    out = xr.Dataset({"Sco2_layers": layer_da, "Sco2": total_da})
    out.attrs = {
        "Site": site,
        "Heights (m)": ", ".join(str(h) for h in profile_storage.get_heights(ds)),
        "Layer depths (m)": ", ".join(
            str(d) for d in profile_storage.get_layer_depths(ds)
        ),
        "long_name": meta.long_name,
        "units": meta.standard_units,
    }
    return out
