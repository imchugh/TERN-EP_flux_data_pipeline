#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Mar 10 09:00:40 2026

@author: imchugh
"""

###############################################################################
### BEGIN IMPORTS ###
###############################################################################

import pandas as pd
import xarray as xr

from services.domain.metadata_config_service import SiteRuntimeConfig
from services.domain import (
    file_mapping_service, raw_data_loader, conversion_service,
    global_metadata_service
    )
from services.domain.raw_data_integrity_validator import validate_raw_data_integrity

###############################################################################
### END IMPORTS ###
###############################################################################


###############################################################################
### BEGIN FUNCTIONS ###
###############################################################################

# -----------------------------------------------------------------------------
def build_variable_registry(
        runtime_cfg: SiteRuntimeConfig
        ) -> dict[str, dict[str, str]]:
    """
    Build dict-based variable registry.

    Args:
        runtime_cfg: config class.

    Returns:
        registry.

    """

    registry = {}

    for canonical_name, var_cfg in runtime_cfg.variables.items():

        registry[var_cfg.raw.raw_name] = {
            "canonical_name": canonical_name,
            "fundamental_quantity": var_cfg.raw.quantity,
            "site_units": getattr(
                var_cfg.raw, "raw_units", var_cfg.canonical.standard_units
                ),
            "attrs": {
                "height": var_cfg.raw.height,
                "instrument": var_cfg.raw.instrument,
                "long_name": var_cfg.canonical.long_name,
                "standard_name": var_cfg.canonical.standard_name,
                "statistic_type": var_cfg.raw.statistic_type,
                "units": var_cfg.canonical.standard_units,
                },
            }

    return registry
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def apply_global_metadata(
        ds: xr.Dataset, runtime_cfg: SiteRuntimeConfig
        ) -> xr.Dataset:        
    """
    Add global attributes.

    Args:
        ds: existing xarray dataset.
        runtime_cfg: config class.

    Returns:
        ds: augmented dataset.

    """
    
    ATTRS_LIST = [
        'site_name', 'fluxnet_id', 'latitude', 'longitude', 'time_step', 
        'time_zone', 'canopy_height', 'tower_height', 'soil', 'vegetation', 
        'system_type', 'altitude'
        ]
    
    # Retrieve global metadata from global_metadata_service
    metadata = global_metadata_service.get_site_metadata(
        site=runtime_cfg.site_name
        )
    
    # Add metadata from 
    for attr in ATTRS_LIST:
        ds.attrs[attr] = metadata.get(attr)
    
    # Add global metadata from runtime_cfg    
    ds.attrs['system_type'] = runtime_cfg.system_type
    ds.attrs['irga_type'] = runtime_cfg.irga_instrument
    ds.attrs['sonic_type'] = runtime_cfg.sonic_instrument
    
    return ds
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def dataframe_to_dataset(df: pd.DataFrame, registry: dict) -> xr.Dataset:
    """
    Convert dataframe data to subsetted dataset (drop unlisted variables).

    Args:
        df: dataframe.
        registry: dict-based variable descriptor.

    Returns:
        ds: dataset.

    """

    # select only columns we know about
    cols = [c for c in df.columns if c in registry]
    df = df[cols].copy()

    # Convert units using domain service
    for raw_name in cols:
        site_unit = registry[raw_name]["site_units"]
        canonical_unit = registry[raw_name]["attrs"]["units"]
        if site_unit != canonical_unit:
            converter = conversion_service.get_converter(
                quantity=registry[raw_name]['fundamental_quantity']
                )
            df[raw_name] = converter(df[raw_name], from_units=site_unit)

    # rename to canonical names
    rename_map = {c: registry[c]["canonical_name"] for c in cols}
    df = df.rename(columns=rename_map)

    # Create xarray object
    ds = df.to_xarray()

    # apply metadata
    for raw_name in cols:

        canonical = registry[raw_name]["canonical_name"]

        ds[canonical].attrs.update(registry[raw_name]["attrs"])

    return ds
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def build_site_dataset(runtime_cfg):
    """
    Build the site xarray dataset from raw sources.

    Args:
        runtime_cfg: config class.

    Returns:
        ds: dataset with names standardised.

    """

    registry = build_variable_registry(runtime_cfg)

    # services
    file_map = file_mapping_service.build_file_map(runtime_cfg)
       
    # validate raw data integrity
    validate_raw_data_integrity(
        file_map=file_map, system_type=runtime_cfg.system_type
        )

    # Get loader adapter for system type
    data_adapter = raw_data_loader.get_data_adapter(
        system_type=runtime_cfg.system_type
        )

    # Iterate over files
    datasets = []
    for file, var_list in file_map.items():

        # Load file
        df = data_adapter.load(file_path=file)

        # Convert from pandas dataframe to xarray dataset
        ds_file = dataframe_to_dataset(df, registry)
        
        # Append
        datasets.append(ds_file)

    # Merge all
    ds = xr.merge(datasets, compat="override")

    # Apply global metadata to merged data
    ds = apply_global_metadata(ds=ds, runtime_cfg=runtime_cfg)

    return ds
# -----------------------------------------------------------------------------

###############################################################################
### END FUNCTIONS ###
###############################################################################
