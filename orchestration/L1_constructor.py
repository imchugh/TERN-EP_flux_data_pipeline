#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build L1 DataFrames and xarray Datasets from a site context.

Public API
----------
build_dataset_from_site_name(site_name, pad_humidity)   -> xr.Dataset
build_dataset_from_context(ctx, pad_humidity)           -> xr.Dataset
build_dataframe_from_site_name(site_name, pad_humidity) -> pd.DataFrame
build_dataframe_from_context(ctx, pad_humidity)         -> pd.DataFrame
"""

###############################################################################
### BEGIN IMPORTS ###
###############################################################################

import pandas as pd
import xarray as xr

# -----------------------------------------------------------------------------

from services.metadata.site_registry import SiteRegistry, SiteContext
from orchestration.dataframe_builder import build as _build_dataframe
from orchestration.humidity_pad import pad_humidity as _pad_humidity

###############################################################################
### END IMPORTS ###
###############################################################################


###############################################################################
### BEGIN INITS ###
###############################################################################

ATTRS_SUBSET = [
    'site_name', 'fluxnet_id', 'latitude', 'longitude', 'elevation', 
    'time_step', 'time_zone', 'canopy_height', 'tower_height', 'soil', 
    'vegetation', 'system_type'
    ]

SITE_REGISTRY = SiteRegistry()

###############################################################################
### END INITS ###
###############################################################################


###############################################################################
### BEGIN FUNCTIONS ###
###############################################################################

# -----------------------------------------------------------------------------
# Entry points
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def build_dataset_from_site_name(
        site_name: str,
        pad_humidity: bool = True,
        ) -> xr.Dataset:
    """Convenience wrapper — resolves site name to context via registry."""

    ctx = SITE_REGISTRY.get_context(site=site_name)
    return build_dataset_from_context(ctx=ctx, pad_humidity=pad_humidity)

# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def build_dataset_from_context(
        ctx: SiteContext,
        pad_humidity: bool = True,
        ) -> xr.Dataset:
    """Build an L1 xarray dataset from a fully-assembled site context."""

    result = _build_dataframe(ctx)
    if pad_humidity:
        result = _pad_humidity(result)

    ds = result.df.to_xarray()
    ds = _apply_variable_metadata(ds, result.var_attrs)
    ds = _apply_global_metadata(ds, ctx)

    return ds

# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def build_dataframe_from_site_name(
        site_name: str,
        pad_humidity: bool = True,
        ) -> pd.DataFrame:
    """Convenience wrapper — resolves site name to context via registry."""

    ctx = SITE_REGISTRY.get_context(site=site_name)
    return build_dataframe_from_context(ctx=ctx, pad_humidity=pad_humidity)

# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def build_dataframe_from_context(
        ctx: SiteContext,
        pad_humidity: bool = True,
        ) -> pd.DataFrame:
    """Build an L1 DataFrame from a fully-assembled site context."""

    result = _build_dataframe(ctx)
    if pad_humidity:
        result = _pad_humidity(result)
    return result.df

# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Metadata application
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def _apply_variable_metadata(
        ds: xr.Dataset,
        var_attrs: dict[str, dict],
        ) -> xr.Dataset:
    """Attach per-variable attribute dicts to dataset variables."""

    for variable in [v for v in ds.variables if v not in ds.dims]:
        ds[variable].attrs = {k: v for k, v in var_attrs[variable].items() if v is not None}

    return ds

# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def _apply_global_metadata(
        ds: xr.Dataset,
        ctx: SiteContext,
        ) -> xr.Dataset:
    """Add global attributes from site context."""

    for attr in ATTRS_SUBSET:
        value = ctx.metadata.get(attr)
        if value is not None:
            ds.attrs[attr] = value

    for key, value in [
            ('irga_type',   ctx.runtime_config.irga_instrument),
            ('sonic_type',  ctx.runtime_config.sonic_instrument),
            ('flux_system', ctx.runtime_config.flux_system),
            ]:
        if value is not None:
            ds.attrs[key] = value

    return ds

# -----------------------------------------------------------------------------

###############################################################################
### END FUNCTIONS ###
###############################################################################
