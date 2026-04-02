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
from dataclasses import dataclass


from services.domain.metadata.variable_metadata_service import (
    SiteRuntimeConfig, load_runtime_config_by_site
    )
from services.domain.metadata import file_mapping_service, global_metadata_service
from services.domain.data import raw_data_loader, conversion_service
from infrastructure.data_conditioning import condition_dataframe

###############################################################################
### END IMPORTS ###
###############################################################################

###############################################################################
### BEGIN CLASSES ###
###############################################################################

# -----------------------------------------------------------------------------

@dataclass
class VariableMapping:
    raw_name: str
    canonical_name: str
    site_units: str
    canonical_units: str
    alias: str
    file_group: str
    file_group_id: str
    quantity: str
# -----------------------------------------------------------------------------

###############################################################################
### END CLASSES ###
###############################################################################


###############################################################################
### BEGIN FUNCTIONS ###
###############################################################################

# -----------------------------------------------------------------------------
# Begin top level xarray functions
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def build_dataset_from_site_name(site_name):
    
    cfg = load_runtime_config_by_site(site=site_name)
    return build_dataset_from_cfg(runtime_cfg=cfg)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def build_dataset_from_cfg(runtime_cfg):
    """Wrap dataframe function and convert to xarray dataset"""

    df = build_dataframe_from_cfg(runtime_cfg)

    ds = df.to_xarray()
    
    attrs_registry = build_attrs_registry(runtime_cfg=runtime_cfg)

    ds = apply_variable_metadata(ds, attrs_registry)

    ds = apply_global_metadata(ds, runtime_cfg)

    return ds
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def apply_variable_metadata(ds, attrs_registry):
    
    var_list = [var for var in ds.variables if not var in ds.dims]
    for variable in var_list:
        ds[variable].attrs = attrs_registry[variable]
    return ds
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
# End top level xarray functions
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
# Begin top level dataframe functions
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def build_dataframe_from_site_name(site_name):
    
    cfg = load_runtime_config_by_site(site=site_name)
    return build_dataframe_from_cfg(runtime_cfg=cfg)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def build_dataframe_from_cfg(runtime_cfg):
    """
    Orchestration function - resulting frame contains raw data with:
        1) canonical names
        2) canonical units
        3) merged time series
        """
      
    return build_dataframe(
        res_pkg=build_resource_package(runtime_cfg=runtime_cfg)
        ) 
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Begin required resource builds
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def build_resource_package(runtime_cfg):
    """
    

    Args:
        runtime_cfg (TYPE): DESCRIPTION.

    Returns:
        dict: DESCRIPTION.

    """

    # Build file groups containing:
        # 1 - resolved master and backup files
        # 2 - expected raw variables across file group, as mapped in config file
    file_groups = file_mapping_service.build_file_groups(runtime_cfg)

    # Do group validation -> ensures that expected variables are all found 
    # across file group
    for group in file_groups.values():
        group.validate()
    
    # Build raw variable registry containing raw variable name as key and 
    # simple dataclass as value containing:
        # 1 - fundamental quantity (e.g. Ta) -> required for fetching 
        #     conversion functions
        # 2 - raw and canonical units -> required for determining unit conversions
        # 3 - canonical name -> required for renaming
        # 4 - alias and file group -> required to prevent variable name 
        #     collisions across file groups
    registry = build_raw_variable_registry(
        runtime_cfg=runtime_cfg,
        file_groups=file_groups
        )
    
    # Build merge blocks containing canonical variable name as key and dict
    # as value containing raw variable name and validity dates 
    merge_blocks = build_merge_blocks(
        runtime_cfg=runtime_cfg,
        registry=registry
        )
    

        
    # Return the resources
    return {
        "registry": registry,
        "merge_blocks": merge_blocks,
        "file_groups": file_groups,
        'system_type': runtime_cfg.system_type
        }
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def build_merge_blocks(runtime_cfg: SiteRuntimeConfig, registry):
    """
    

    Args:
        runtime_cfg (SiteRuntimeConfig): DESCRIPTION.

    Returns:
        rslt (TYPE): DESCRIPTION.

    """
    
    # rslt = {}
    
    # for canonical_name, var_cfg in runtime_cfg.variables.items():
       
    #     if len(var_cfg.raw_inputs) > 1:

    #         block = {}                          
    #         for var_attrs in var_cfg.raw_inputs:

    #             block[var_attrs.raw_name] = {
    #                 'begin': var_attrs.begin, 
    #                 'end': var_attrs.end
    #                 }
                
    #         rslt[canonical_name] = block

    # return rslt

    rslt = {}

    for canonical_name, var_cfg in runtime_cfg.variables.items():

        mappings = [
            m for m in registry.values()
            if m.canonical_name == canonical_name
            ]

        if len(mappings) > 1:

            block = {}

            for m, var_attrs in zip(mappings, var_cfg.raw_inputs):

                block[m.alias] = {
                    "begin": var_attrs.begin,
                    "end": var_attrs.end
                }

            rslt[canonical_name] = block

    return rslt
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def build_raw_variable_registry(
        runtime_cfg: SiteRuntimeConfig, file_groups
        ) -> dict[str, dict[str, str]]:
    """
    Build dict-based variable registry.

    Args:
        runtime_cfg: config class.

    Returns:
        registry.

    """

    registry = {}

    # for canonical_name, var_cfg in runtime_cfg.variables.items():

    #     for variable in var_cfg.raw_inputs:
            
    #         registry[variable.raw_name] = VariableMapping(
    #             canonical_name = canonical_name,
    #             canonical_units = var_cfg.canonical.standard_units,
    #             site_units = getattr(
    #                 variable.raw_units, 
    #                 "raw_units", var_cfg.canonical.standard_units
    #                 ),
    #             quantity = var_cfg.quantity
    #             )

    # return registry



    for i, (group_name, mapper) in enumerate(file_groups.items()):
        
        group_id = f'gp{i}'

        # Get the raw variable names associated with this file group
        group_variables = mapper.expected_variables

        # Iterate over the file names
        for canonical_name, var_cfg in runtime_cfg.variables.items():

            for var_attrs in var_cfg.raw_inputs:

                raw_name = var_attrs.raw_name

                # only include if this variable belongs to this group
                if raw_name not in group_variables:
                    continue

                alias = f"{raw_name}_{group_id}"

                registry[alias] = VariableMapping(
                    raw_name=raw_name,
                    canonical_name=canonical_name,
                    canonical_units=var_cfg.canonical.standard_units,
                    site_units=getattr(
                        var_attrs.raw_units,
                        "raw_units",
                        var_cfg.canonical.standard_units
                        ),
                    quantity=var_cfg.quantity,
                    file_group=group_name,
                    file_group_id=group_id,
                    alias=alias
                    )

    return registry
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def build_attrs_registry(runtime_cfg: SiteRuntimeConfig) -> dict:
    """
    

    Args:
        runtime_cfg (SiteRuntimeConfig): DESCRIPTION.

    Returns:
        dict: DESCRIPTION.

    """
    
    registry = {}
    
    for canonical_name, var_cfg in runtime_cfg.variables.items():

        rslt = {
            "height": var_cfg.height,
            "instrument": var_cfg.instrument,
            "long_name": var_cfg.canonical.long_name,
            "standard_name": var_cfg.canonical.standard_name,
            "statistic_type": var_cfg.statistic_type,
            "units": var_cfg.canonical.standard_units,
            }
        
        if len(var_cfg.raw_inputs) > 1:
            
            history = []
            for var_attrs in var_cfg.raw_inputs:
                history.append(build_history_string(
                    instrument=var_attrs.instrument, 
                    begin=var_attrs.begin, 
                    end=var_attrs.end)
                    )
            rslt['instrument_history'] = ' | '.join(history)
        
        registry[canonical_name] = rslt
    return registry
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def build_history_string(instrument, begin, end):
    
    use_begin, use_end = '', ''
    if begin is not None:
        use_begin = begin.strftime('%Y-%m-%d %H:%M')
    if end is not None:
        use_end = end.strftime('%Y-%m-%d %H:%M')
    return f'{instrument}: {use_begin} -> {use_end}'
    
        
    
    return
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# End required resource builds
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def build_dataframe(res_pkg: dict):
    """
    

    Args:
        res_pkg (dict): DESCRIPTION.

    Returns:
        df (TYPE): DESCRIPTION.

    """
    
    # Get the loader for the system type (Campbell or Licor)
    loader = raw_data_loader.get_data_adapter(
        system_type=res_pkg['system_type']
        )

    # Iterate over different source file groups to stack (master + backups) 
    # via vertical (row-major) concatenation 
    # -> no time overlap within file groups (backups by definition don't overlap)
    dfs = [
        process_file_group(mapper, loader, res_pkg["registry"])
        for mapper in res_pkg["file_groups"].values()
        ]

    # Step 2: horizontal merge (different tables/loggers)
    df = concat_columns(dfs)
    
    # Step 3: merge overlapping variables
    df = merge_overlapping_variables(df, res_pkg["merge_blocks"])

    # Step 4: rename to canonical variables
    df = rename_to_canonical(df, res_pkg["registry"])

    return df
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Begin individual file group processing
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def process_file_group(mapper, loader, registry):
    """
    

    Args:
        mapper (TYPE): DESCRIPTION.
        loader (TYPE): DESCRIPTION.
        registry (TYPE): DESCRIPTION.

    Returns:
        TYPE: DESCRIPTION.

    """
    
    dfs = []

    # Iterate over all files in group
    for file, _ in mapper.variables_by_file.items():
        
        # Load the data
        df = loader.load(file)

        # Filter the data to requested variables
        df = filter_variables(df, registry)
        
        # Convert the data units to canonical
        df = convert_units(df, registry)

        # Accumulate
        dfs.append(df)
        
    # Concatenate vertically
    df = concat_rows(dfs)

    # Condition and return
    return condition_dataframe(df, interval_out=30)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def filter_variables(df, registry):
    """Dump all variables not in the registry listing"""
    
    cols = [c for c in df.columns if c in registry]
    return df[cols].copy()
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def convert_units(df, registry):
    """Do the conversion of the units from site-level to canonical"""
    
    for raw_name, mapping in registry.items():

        if mapping.site_units != mapping.canonical_units:
            converter = conversion_service.get_converter(mapping.quantity)
            df[raw_name] = converter(
                df[raw_name], 
                from_units=mapping.site_units
                )
    
    return df
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def concat_rows(dfs):
    """Concatenate vertically (rows)"""
    
    return pd.concat(dfs).sort_index()
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# End individual file group processing functions
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
# Begin combined dataframe processing functions
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def concat_columns(dfs):
    """Concatenate horizontally (columns)"""
    
    return pd.concat(dfs, axis=1)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def merge_overlapping_variables(df, merge_blocks):
    """
    

    Args:
        df (TYPE): DESCRIPTION.
        merge_blocks (TYPE): DESCRIPTION.

    Returns:
        TYPE: DESCRIPTION.

    """

    merged = {}
    drop_cols = []

    for canonical_name, block in merge_blocks.items():
        merged[canonical_name] = merge_block(df, block)
        drop_cols.extend(block.keys())

    df = df.drop(columns=drop_cols, errors="ignore")

    return df.join(pd.DataFrame(merged))
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def merge_block(df, block):
    """
    

    Args:
        df (TYPE): DESCRIPTION.
        block (TYPE): DESCRIPTION.

    Returns:
        result (TYPE): DESCRIPTION.

    """
    
    result = pd.Series(index=df.index, dtype=float)

    for raw_name, dates in block.items():
        segment = df.loc[dates['begin']:dates['end'], raw_name]
        result.loc[segment.index] = segment

    return result
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def rename_to_canonical(df, registry):
    """
    

    Args:
        df (TYPE): DESCRIPTION.
        registry (TYPE): DESCRIPTION.

    Returns:
        TYPE: DESCRIPTION.

    """
    
    rename_map = {
        raw: mapping.canonical_name
        for raw, mapping in registry.items()
        if raw in df.columns
    }

    return df.rename(columns=rename_map)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# End combined dataframe processing functions
# -----------------------------------------------------------------------------

###############################################################################
### END FUNCTIONS ###
###############################################################################
