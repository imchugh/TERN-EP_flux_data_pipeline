#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build L1 xarray datasets from site context objects.

Public API
----------
build_dataset_from_site_name(site_name)   -> xr.Dataset
build_dataset_from_context(ctx)           -> xr.Dataset
build_dataset_from_cfg(runtime_cfg)       -> xr.Dataset  [shim]
build_dataframe_from_site_name(site_name) -> pd.DataFrame
build_dataframe_from_cfg(runtime_cfg)     -> pd.DataFrame
"""

###############################################################################
### BEGIN IMPORTS ###
###############################################################################

import pandas as pd
import xarray as xr

# -----------------------------------------------------------------------------

from services.metadata.variable_metadata_service import SiteRuntimeConfig
from services.metadata.site_registry import SiteRegistry, SiteContext
from orchestration.dataframe_builder import build as _build_dataframe

###############################################################################
### END IMPORTS ###
###############################################################################


###############################################################################
### BEGIN INITS ###
###############################################################################

ATTRS_SUBSET = [
    'site_name', 'fluxnet_id', 'latitude', 'longitude', 'time_step',
    'time_zone', 'canopy_height', 'tower_height', 'soil', 'vegetation',
    'system_type', 'elevation'
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

def build_dataset_from_site_name(site_name: str) -> xr.Dataset:
    """Convenience wrapper — resolves site name to context via registry."""

    ctx = SITE_REGISTRY.get_context(site=site_name)
    return build_dataset_from_context(ctx=ctx)

# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def build_dataset_from_context(ctx: SiteContext) -> xr.Dataset:
    """Build an xarray dataset from a fully-assembled site context."""

    result = _build_dataframe(ctx)

    ds = result.df.to_xarray()
    ds = _apply_variable_metadata(ds, result.var_attrs)
    ds = _apply_global_metadata(ds, ctx)

    return ds

# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def build_dataset_from_cfg(runtime_cfg: SiteRuntimeConfig) -> xr.Dataset:
    """
    Shim for callers that only have a SiteRuntimeConfig.

    Prefer build_dataset_from_context() for new call sites.
    """

    ctx = SITE_REGISTRY.get_context(site=runtime_cfg.site_name)
    return build_dataset_from_context(ctx=ctx)

# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def build_dataframe_from_site_name(site_name: str) -> pd.DataFrame:
    """Convenience wrapper — resolves site name to context via registry."""

    ctx = SITE_REGISTRY.get_context(site=site_name)
    return _build_dataframe(ctx).df

# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def build_dataframe_from_cfg(runtime_cfg: SiteRuntimeConfig) -> pd.DataFrame:
    """
    Shim for callers that only have a SiteRuntimeConfig.

    Prefer build_dataframe_from_site_name() for new call sites.
    """

    ctx = SITE_REGISTRY.get_context(site=runtime_cfg.site_name)
    return _build_dataframe(ctx).df

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

    # Skip dimension coordinates (e.g. time)
    for variable in [v for v in ds.variables if v not in ds.dims]:
        ds[variable].attrs = var_attrs[variable]

    return ds

# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def _apply_global_metadata(
        ds: xr.Dataset,
        ctx: SiteContext,
        ) -> xr.Dataset:
    """Add global attributes from site context."""

    for attr in ATTRS_SUBSET:
        ds.attrs[attr] = ctx.metadata.get(attr)

    ds.attrs['irga_type']  = ctx.runtime_config.irga_instrument
    ds.attrs['sonic_type'] = ctx.runtime_config.sonic_instrument
    ds.attrs['flux_system'] = ctx.runtime_config.flux_system

    return ds

# -----------------------------------------------------------------------------

###############################################################################
### END FUNCTIONS ###
###############################################################################
