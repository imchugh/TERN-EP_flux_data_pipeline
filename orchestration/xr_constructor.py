#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Mar 10 09:00:40 2026

Orchestration function - resulting frame contains raw data with:
    1) canonical names
    2) canonical units
    3) merged time series

@author: imchugh
"""

###############################################################################
### BEGIN IMPORTS ###
###############################################################################

import datetime as dt
import pandas as pd
import xarray as xr
from dataclasses import dataclass
from typing import Callable

# -----------------------------------------------------------------------------

from services.metadata.variable_metadata_service import (
    SiteRuntimeConfig, load_runtime_config_by_site
    )
from services.metadata import file_mapping_service, global_metadata_service
from services.metadata.file_mapping_service import FileGroup
from services.data import raw_data_loader, conversion_service
from infrastructure.data_conditioning import condition_dataframe

###############################################################################
### END IMPORTS ###
###############################################################################


###############################################################################
### BEGIN INITS ###
###############################################################################

TRANSFORM_SUFFIXES = {'variance_to_stdev': ('Vr', 'Sd')}
TRANSFORM_STATS = {'variance_to_stdev': ('variance', 'standard_deviation')}
ATTRS_SUBSET = [
    'site_name', 'fluxnet_id', 'latitude', 'longitude', 'time_step', 
    'time_zone', 'canopy_height', 'tower_height', 'soil', 'vegetation', 
    'system_type', 'elevation'
    ]

###############################################################################
### END INITS ###
###############################################################################


###############################################################################
### BEGIN CLASSES ###
###############################################################################

# -----------------------------------------------------------------------------

@dataclass
class VariableSpec:
    
    # Fundamentals
    raw_name: str
    canonical_name: str
    site_units: str
    canonical_units: str
    statistic_type: str | None
    quantity: str
    
    # xarray variables attrs
    height: int
    height_range: tuple[float, float]
    instrument: str
    long_name: str
    standard_name: str
    
    # Aliasing / grouping
    alias: str
    file_group: str
    file_group_id: str
    
    # Temporal validity
    begin: pd.Timestamp | None
    end: pd.Timestamp | None
    
    # Transform
    transform: None
# -----------------------------------------------------------------------------

###############################################################################
### END CLASSES ###
###############################################################################


###############################################################################
### BEGIN FUNCTIONS ###
###############################################################################

# -----------------------------------------------------------------------------
# Begin top level xarray (and related) functions
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def build_dataset_from_site_name(site_name: str) -> xr.Dataset:
    """Convenience wrapper - avoids loading runtime configuration object"""
    
    cfg = load_runtime_config_by_site(site=site_name)
    return build_dataset_from_cfg(runtime_cfg=cfg)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def build_dataset_from_cfg(runtime_cfg: SiteRuntimeConfig) -> xr.Dataset:
    """Wrap dataframe function and convert to xarray dataset"""

    res_pkg = collate_resource_package(runtime_cfg=runtime_cfg)
    
    df = build_dataframe(res_pkg=res_pkg)
    
    attrs = build_var_attrs_from_registry(registry=res_pkg['registry'])

    ds = df.to_xarray()
    
    ds = apply_variable_metadata(ds, attrs)

    ds = apply_global_metadata(ds, runtime_cfg)

    return ds
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def build_var_attrs_from_registry(
        registry: dict[str: VariableSpec]
        ) -> dict[str: dict]:
    """
    Build canonical variable attributes from raw variable registry.

    Args:
        registry: raw variable registry.

    Returns:
        dict containing key: value of canonical variable: dict of attrs.

    """

    rslt = {}

    # Reconstitute canonical variables from registry
    canonical_groups = canonical_from_registry(registry=registry)

    # Iterate over canonical variables
    for canonical_name, var_specs in canonical_groups.items():       

        # Assign primary attributes from last entry (since current instrument 
        # should be in instrument field)
        main_spec = var_specs[-1]
        attrs = {
            "height": main_spec.height,
            "height_range": main_spec.height_range,
            "instrument": main_spec.instrument,
            "long_name": main_spec.long_name,
            "standard_name": main_spec.standard_name,
            "statistic_type": convert_output_statistic(var_spec=main_spec),
            "units": main_spec.canonical_units,
            }
        
        # Create output name (edit Vr suffix to Sd)
        output_name = generate_canonical_output_name(var_spec=main_spec)

        # Check for multiple input variable condition
        if len(var_specs) > 1:
                        
            # Iterate over individual variable specifications to build 
            # instrument history
            instrument_history = {}
            for var_spec in var_specs:
                instrument_history[var_spec.instrument] = [
                    var_spec.begin,
                    var_spec.end
                    ]
            attrs['instrument_history'] = instrument_history
            
        # Assign to results
        rslt[output_name] = attrs
    
    return rslt
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def apply_variable_metadata(
        ds: xr.Dataset, attrs_registry: dict[str: dict]
        ) -> xr.Dataset:
    """
    Attach variable metadata fields to variables in xarray dataset.

    Args:
        ds: input dataset.
        attrs_registry: dict of attrs.

    Returns:
        dataset with variable attrs.

    """
    
    # Don't try to add attrs to time variable!
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
          
    # Retrieve global metadata from global_metadata_service
    metadata = global_metadata_service.get_site_metadata(
        site=runtime_cfg.site_name
        )
    
    # Add only metadata fields in subset
    for attr in ATTRS_SUBSET:
        ds.attrs[attr] = metadata.get(attr)
   
    # Add global metadata from runtime_cfg    
    ds.attrs['irga_type'] = runtime_cfg.irga_instrument
    ds.attrs['sonic_type'] = runtime_cfg.sonic_instrument
    ds.attrs['flux_system'] = runtime_cfg.flux_system
    
    return ds
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# End top level xarray functions
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
# Begin top level dataframe functions
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def build_dataframe_from_site_name(site_name: str) -> pd.DataFrame:
    """Convenience wrapper - avoids loading runtime configuration object"""
    
    cfg = load_runtime_config_by_site(site=site_name)
    return build_dataframe_from_cfg(runtime_cfg=cfg)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def build_dataframe_from_cfg(runtime_cfg: SiteRuntimeConfig) -> pd.DataFrame:
    """Build dataframe from runtime config class"""
      
    return build_dataframe(
        res_pkg=collate_resource_package(runtime_cfg=runtime_cfg)
        ) 
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Begin required resource builds
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def collate_resource_package(runtime_cfg: SiteRuntimeConfig) -> dict:
    """
    Collate the resources required for successful data build.

    Args:
        runtime_cfg: config class.

    Returns:
        dict containing registry, file groups and system type.

    """

    # Build file groups containing:
        # 1 - resolved master and backup files
        # 2 - expected raw variables across file group, as mapped in config file
    # Do group validation -> ensures that expected variables are all found 
    # across file group
    file_groups = file_mapping_service.build_file_groups(runtime_cfg)
    for group in file_groups.values():
        group.validate()
    
    # Build raw variable registry containing raw variable name as key and 
    # dataclass as value (see VariableSpec class for specifications)
    registry = build_raw_variable_registry(
        runtime_cfg=runtime_cfg,
        file_groups=file_groups
        )
        
    # Return the resources
    return {
        "registry": registry,
        "file_groups": file_groups,
        }
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def get_merge_blocks(registry: dict[str: VariableSpec]) -> dict:
    """
    Get all canonical variables constructed from multiple raw inputs.

    Args:
        registry: raw variable registry.

    Returns:
        rslt: dict containing blocks keyed by canonical variable.

    """

    rslt = {}

    # Test for groups with more than one input variable
    canonical_groups = canonical_from_registry(registry=registry)
    for canonical_name, var_specs in canonical_groups.items():

        # Pass if only one variable
        if len(var_specs) <= 1:
            continue

        # Otherwise create a block of variable names and dates
        block = {}

        # Add all instrument specifications to block
        for var_spec in var_specs:
            block[var_spec.alias] = {
                'begin': var_spec.begin,
                'end': var_spec.end
                }

        # Assign to canonical name
        rslt[canonical_name] = block

    return rslt
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def canonical_from_registry(
        registry: dict[str: VariableSpec]
        ) -> dict[str, tuple[VariableSpec]]:
    """Rebuild the registry so that the common key is canonical variable"""
    
    # Reconstitute canonical variables from registry
    canonical_groups = {}
    for entry in registry.values():
        canonical_groups.setdefault(entry.canonical_name, []).append(entry)
    return canonical_groups
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def build_raw_variable_registry(
        runtime_cfg: SiteRuntimeConfig, file_groups: dict[str: FileGroup]
        ) -> dict[str, VariableSpec]:
    """
    Build dict-based variable registry.

    Args:
        runtime_cfg: config class.

    Returns:
        registry.

    """

    registry = {}

    # Iterate over all files in the group
    for i, (group_name, mapper) in enumerate(file_groups.items()):

        group_id = f'gp{i}'

        # Iterate over the file names
        for canonical_name, var_cfg in runtime_cfg.variables.items():
                
            for var_attrs in var_cfg.raw_inputs:

                raw_name = var_attrs.raw_name

                # only include if this variable belongs to this group
                if var_attrs.file != group_name:
                    continue

                # Create the alias
                alias = f"{raw_name}_{group_id}"

                # Build the mapping
                registry[alias] = VariableSpec(
                    
                    # --- identity ---
                    raw_name=raw_name,
                    canonical_name=canonical_name,
                    alias=alias,
                    long_name=var_cfg.canonical.long_name,
                    standard_name=var_cfg.canonical.standard_name,
                    
                    # --- units ---
                    canonical_units=var_cfg.canonical.standard_units,
                    site_units=var_attrs.raw_units or var_cfg.canonical.standard_units,
                    
                    # --- semantics ---
                    statistic_type=var_cfg.statistic_type,
                    quantity=var_cfg.quantity,
                    transform=infer_transform(
                        statistic_type=var_cfg.statistic_type
                        ),
                    height=var_cfg.height,
                    height_range=var_cfg.height_range,
                    instrument=var_attrs.instrument,
                    
                    # --- provenance ---
                    file_group=group_name,
                    file_group_id=group_id,
                    begin=var_attrs.begin,
                    end=var_attrs.end,
                    
                    )

    return registry
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def infer_transform(statistic_type: str | None) -> str | None:
    """
    Infer the transform function name from the statistic_type

    Args:
        statistic_type: name of statistic (e.g. mean, standard_deviation, variance).

    Returns:
        TYPE: DESCRIPTION.

    """
    
    return (
        {"variance": "variance_to_stdev",}
        .get(statistic_type)
        )
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# End required resource builds
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def build_dataframe(res_pkg: dict) -> pd.DataFrame:
    """
    Build the dataframe.

    Args:
        res_pkg: resource package required for processing.

    Returns:
        dataframe.

    """
    
    # Step 1: iterate over source file groups to stack master + backups via 
    # vertical (row-major) concatenation 
    dfs = []
    for _, mapper in res_pkg["file_groups"].items():
        
        loader = raw_data_loader.get_data_adapter(
            system_type=mapper.file_format
            )
        
        dfs.append(
            process_file_group(
                mapper=mapper, 
                loader=loader, 
                registry=res_pkg['registry']
                )
            )

    # Step 2: horizontal (column-major) concatenation (different tables/loggers)
    df = concat_columns(dfs)
        
    # Step 3: merge overlapping variables
    merge_blocks = get_merge_blocks(registry=res_pkg['registry'])
    df = merge_overlapping_variables(df=df, merge_blocks=merge_blocks)

    # Step 4: rename to canonical variables
    df = rename_to_canonical(df, res_pkg["registry"])

    return df
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Begin individual file group processing
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def process_file_group(
        mapper: FileGroup, 
        loader: Callable, 
        registry: dict[str, VariableSpec]
        ) -> pd.DataFrame:
    """
    Do the file group (master + backups for CSI systems) vertical (time-based) 
    concatenation (no overlap between groups by definition)

    Args:
        mapper: validate map object that links file groups to individual files 
        and variables.
        loader: DESCRIPTION.
        registry: raw variable registry.

    Returns:
        single concatenated dataframe.

    """
    
    # Build raw to alias renaming map for THIS group only -> iterate over all 
    # registry entries (ignore registry keys) to find entries for which file 
    # group matches the mapper's group
    rename_map = {
        entry.raw_name: entry.alias
        for entry in registry.values()
        if entry.file_group == mapper.group
        }

    # Iterate over all files in group
    dfs = []
    for file, _ in mapper.variables_by_file.items():
        
        # Load the data
        df = loader.load(file)

        # Filter the data to requested variables
        df = filter_variables(df=df, variables=mapper.expected_variables)
               
        # Apply aliasing
        df = df.rename(
            columns={
                col: rename_map[col]
                for col in df.columns if col in rename_map
                }
            )

        # Convert variances to stdev in data, and return unit overrides to apply
        # at conversion step
        df, unit_overrides = transform_variances(df=df, registry=registry)
               
        # Convert the data units to canonical
        df = convert_units(df=df, registry=registry, overrides=unit_overrides)

        # Accumulate
        dfs.append(df)
        
    # Concatenate vertically
    df = concat_rows(dfs)

    # Condition and return
    return condition_dataframe(df, interval_out=30)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def filter_variables(df: pd.DataFrame, variables: list) -> pd.DataFrame:
    """Dump all variables not in the registry listing"""
    
    cols = [c for c in df.columns if c in variables]
    return df[cols].copy()
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def transform_variances(
        df: pd.DataFrame, registry: dict[str, VariableSpec]
        ) -> (pd.DataFrame, dict[str: str]):    
    """
    Transform all variance variables to standard deviations.

    Args:
        df: data with untransformed variance variables.
        registry: raw variable registry.

    Returns:
        data with variance variables transformed to standard deviation.

    """
    
    overrides = {}
    
    # Iterate over data variables
    for variable in df.columns:
        
        # Skip if variable not in registry
        if variable not in registry:
            continue
        
        # Skip if transform not required
        reg_entry = registry[variable]
        if reg_entry.transform is None:
            continue

        # Get transformation function
        transformer = conversion_service.get_statistical_transformation(
            reg_entry.transform
            )()
            
        # Do statistical transformation and accumulate unit overrides
        try:
            df[variable] = transformer.apply_data(data=df[variable])
            overrides[variable] = (
                transformer.apply_units(units=reg_entry.site_units)
                )
            
        except Exception as e:
            raise RuntimeError(
                f"Transformation failed for {variable} "
                f"(transform={reg_entry.transform}, units={reg_entry.site_units})"
                ) from e

    return df, overrides
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def convert_units(
        df: pd.DataFrame, 
        registry: dict[str, VariableSpec], 
        overrides: dict[str, str]
        ) -> pd.DataFrame:
    """
    Convert units from site-level to canonical.

    Args:
        df: data in site-level units.
        registry: raw variable registry.
        overrides: dict containing unit overrides.

    Raises:
        RuntimeError: raised on any exception.

    Returns:
        df: data in canonical units.

    """

    # Iterate over data variables
    for variable in df.columns:

        # Skip if variable not in registry
        if variable not in registry:
            continue
        
        # Get registry entry
        reg_entry = registry[variable]

        # Get site units (use overrides if provided)
        site_units = overrides.get(variable, reg_entry.site_units)

        # Cross-check site and canonical units
        if site_units != reg_entry.canonical_units:

            # Get conversion function
            converter = conversion_service.get_unit_conversion(
                reg_entry.quantity
                )
            
            # Do unit conversion
            try:
                df[variable] = converter(
                    data=df[variable],
                    from_units=site_units
                    )
            except Exception as e:
                breakpoint()
                raise RuntimeError(
                    f"Unit conversion failed for {variable} "
                    f"(from {site_units} → {reg_entry.canonical_units})"
                    ) from e

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

def merge_overlapping_variables(
        df: pd.DataFrame, merge_blocks: dict[str: dict[str: dt.datetime]]
        ) -> pd.DataFrame:
    """
    Merge separate time series into one.

    Args:
        df: the data on which to perform the merge.
        merge_blocks: dict containing raw variable names and validity dates.

    Returns:
        merged data.

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

def merge_block(
        df: pd.DataFrame, block: dict[str: dt.datetime]
        ) -> pd.DataFrame:
    """
    Helper function called by merge_overlapping_variables.

    Args:
        df: the data on which to perform the merge..
        block (TYPE): DESCRIPTION.

    Returns:
        result (TYPE): DESCRIPTION.

    """
    
    result = pd.Series(index=df.index, dtype=float)

    for raw_name, info in block.items():
        segment = df.loc[info['begin']: info['end'], raw_name]
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
        raw: generate_canonical_output_name(var_spec=var_spec)
        for raw, var_spec in registry.items()
        if raw in df.columns
        }

    return df.rename(columns=rename_map)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def generate_canonical_output_name(var_spec: VariableSpec) -> str:
    """
    

    Args:
        var_spec (TYPE): DESCRIPTION.

    Returns:
        TYPE: DESCRIPTION.

    """
    

    # Get the canonical name
    name = var_spec.canonical_name
    
    # Return unchanged if no statistical transform
    if var_spec.transform is None:
        return name
        
    # Get suffixes (return unchanged if None)
    suffixes = TRANSFORM_SUFFIXES.get(var_spec.transform)
    if suffixes is None:
        return name
    
    # Assign suffixes
    old, new = suffixes
    
    # Do the rename
    if name.endswith(f"_{old}"):
        return f"{name[:-len(old)]}{new}"
    
    # Return unchanged if suffix not found
    return name
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def convert_output_statistic(var_spec: VariableSpec) -> str:
    
    # Get the statistic type
    stat_type = var_spec.statistic_type
    
    # Return unchanged if no statistical transform
    if var_spec.transform is None:
        return stat_type
    
    # Get suffixes (return unchanged if None)
    stat_types = TRANSFORM_STATS.get(var_spec.transform)
    if stat_types is None:
        return stat_type

    # Assign stat types
    old, new = stat_types
    
    # Pass back the new stat type
    if var_spec.statistic_type == old:
        return new
    
    # Return unchanged if old stat_type does not match specification
    return stat_type
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# End combined dataframe processing functions
# -----------------------------------------------------------------------------

###############################################################################
### END FUNCTIONS ###
###############################################################################
