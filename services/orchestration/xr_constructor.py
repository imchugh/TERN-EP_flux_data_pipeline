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

from services.domain.metadata.variable_metadata_service import SiteRuntimeConfig
from services.domain.metadata import file_mapping_service, global_metadata_service
from services.domain.data import raw_data_loader, conversion_service
from infrastructure.data_conditioning import condition_dataframe

###############################################################################
### END IMPORTS ###
###############################################################################


###############################################################################
### BEGIN FUNCTIONS ###
###############################################################################

# -----------------------------------------------------------------------------
def build_merge_blocks(runtime_cfg: SiteRuntimeConfig):
    
    rslt = {}
    
    for canonical_name, var_cfg in runtime_cfg.variables.items():
       
        if len(var_cfg.raw_inputs) > 1:

            block = {}                          
            for var_attrs in var_cfg.raw_inputs:

                block[var_attrs.raw_name] = {
                    'begin': var_attrs.begin, 
                    'end': var_attrs.end
                    }
                
            rslt[canonical_name] = block

    return rslt
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def build_input_variable_registry(
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

        for variable in var_cfg.raw_inputs:

            registry[variable.raw_name] = {
                "canonical_name": canonical_name,
                "canonical_units": var_cfg.canonical.standard_units,
                "fundamental_quantity": var_cfg.quantity,
                "site_units": getattr(
                    variable.raw_units, 
                    "raw_units", var_cfg.canonical.standard_units
                    )
                }

    return registry
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def build_attrs_registry(runtime_cfg: SiteRuntimeConfig) -> dict:
    
    registry = {}
    
    for canonical_name, var_cfg in runtime_cfg.variables.items():

        rslt = {
            'var_attrs': {
                "height": var_cfg.height,
                "instrument": var_cfg.instrument,
                "long_name": var_cfg.canonical.long_name,
                "standard_name": var_cfg.canonical.standard_name,
                "statistic_type": var_cfg.statistic_type,
                "units": var_cfg.canonical.standard_units,
                }
            }
        
        if len(var_cfg.raw_inputs) > 1:
            
            history = {}            
            for var_attrs in var_cfg.raw_inputs:
                history[var_attrs.instrument] = {
                    'begin': var_attrs.begin,
                    'end': var_attrs.end
                    }
            rslt['instrument_history'] = history
        
        registry[canonical_name] = rslt
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

# # -----------------------------------------------------------------------------

# def dataframe_to_dataset(df: pd.DataFrame, registry: dict) -> xr.Dataset:
#     """
#     Convert dataframe data to subsetted dataset (drop unlisted variables).

#     Args:
#         df: dataframe.
#         registry: dict-based variable descriptor.

#     Returns:
#         ds: dataset.

#     """

#     # select only columns we know about
#     cols = [c for c in df.columns if c in registry]
#     df = df[cols].copy()

#     # Convert units using domain service
#     for raw_name in cols:
#         site_unit = registry[raw_name]["site_units"]
#         canonical_unit = registry[raw_name]["canonical_units"]
#         if site_unit != canonical_unit:
#             converter = conversion_service.get_converter(
#                 quantity=registry[raw_name]['fundamental_quantity']
#                 )
#             df[raw_name] = converter(df[raw_name], from_units=site_unit)

#     # rename to canonical names
#     rename_map = {c: registry[c]["canonical_name"] for c in cols}
#     df = df.rename(columns=rename_map)

#     # Create xarray object
#     ds = df.to_xarray()

#     # apply metadata
#     for raw_name in cols:

#         canonical = registry[raw_name]["canonical_name"]

#         ds[canonical].attrs.update(registry[raw_name]["attrs"])

#     return ds
# # -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def concat_by_row(
        mapper, 
        loader_adapter, 
        registry: dict[str, dict[str, str]]
        ) -> pd.DataFrame():
    """
    

    Returns:
        None.

    """
    
    # Get content for each file in group
    df_list = []
    for file, var_list in mapper.variables_by_file.items():
        
        # Load file
        df = loader_adapter.load(file_path=file)
    
        # Subset columns we want
        cols = [c for c in df.columns if c in registry]
        df = df[cols].copy()

        # Convert units using conversion service
        for raw_name in cols:
            site_unit = registry[raw_name]["site_units"]
            canonical_unit = registry[raw_name]["canonical_units"]
            if site_unit != canonical_unit:
                converter = conversion_service.get_converter(
                    quantity=registry[raw_name]['fundamental_quantity']
                    )
                df[raw_name] = converter(df[raw_name], from_units=site_unit)
                
        # Append
        df_list.append(df)
        
    # Condition
    return condition_dataframe(
        df=pd.concat(df_list), 
        interval_out=30
        )
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def merge_columns(df: pd.DataFrame, merge_block):
    
    series_list = []
    for var_name, dates in merge_block.items():
        series_list.append(df.loc[dates['begin']: dates['end'], var_name])
    return pd.concat(series_list)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def build_site_dataframe(runtime_cfg):
    """
    Build the site xarray dataset from raw sources.

    Args:
        runtime_cfg: config class.

    Returns:
        ds: dataset with names standardised.

    """

    # Create a clean single-layer variable registry from the config
    input_registry = build_input_variable_registry(runtime_cfg)

    # Get the file map and use the onboard validator to check variables are available
    file_map = file_mapping_service.build_file_groups(runtime_cfg)
    for file, var_map in file_map.items():
        rslt = var_map.validate()
        if len(rslt['missing']) > 0:
            raise RuntimeError(
                'The following variables were not found in the raw data file group:'
                f'{rslt["missing"]}'
                )                  
            
    # Get loader adapter for system type
    loader_adapter = raw_data_loader.get_data_adapter(
        system_type=runtime_cfg.system_type
        )

    # Iterate over different source file groups to merge (master + backups) 
    # via vertical (row-major) concatenation 
    # -> no time overlap within file groups (backups by definition don't overlap)
    datasets = []
    for file_group, mapper in file_map.items():
               
        # Merge file groups 
        datasets.append(
            concat_by_row(
                mapper=mapper, 
                loader_adapter=loader_adapter, 
                registry=input_registry
                )
            )
    
    # Merge separate data files (e.g. from separate tables / logger) via 
    # horizontal (column-major) concatenation to create complete, pre-merge dataframe
    df = pd.concat(datasets, axis=1)
    
    # Handle vertical merge of separate time series that MAY have time overlap   
    merge_blocks = build_merge_blocks(runtime_cfg=runtime_cfg)
    new_df = pd.DataFrame(index=df.index)
    for canonical_name, block in merge_blocks.items():
        merge_df = df[block.keys()]
        df = df.drop(block.keys(), axis=1)
        new_df[canonical_name] = merge_columns(df=merge_df, merge_block=block)
        
    # Rename the variables in the main df
    rename_dict = {x: input_registry[x]['canonical_name'] for x in df.columns}
    df = df.rename(rename_dict, axis=1)
    df = pd.concat([df, new_df], axis=1)
    
    # # Merge all
    # ds = xr.merge(df, compat="override")




    # # Apply global metadata to merged data
    # ds = apply_global_metadata(ds=ds, runtime_cfg=runtime_cfg)

    return df
# -----------------------------------------------------------------------------

###############################################################################
### END FUNCTIONS ###
###############################################################################
