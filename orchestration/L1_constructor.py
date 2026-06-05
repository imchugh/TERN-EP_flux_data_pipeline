#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build L1 DataFrames and xarray Datasets from a site context.

Public API
----------
build_dataset_from_site_name(site_name, pad_humidity, pad_co2, start_date)   -> xr.Dataset
build_dataset_from_context(ctx, pad_humidity, pad_co2, start_date)           -> xr.Dataset
build_dataframe_from_site_name(site_name, pad_humidity, pad_co2, start_date) -> pd.DataFrame
build_dataframe_from_context(ctx, pad_humidity, pad_co2, start_date)         -> pd.DataFrame
"""

import datetime
import pandas as pd
import xarray as xr

from services.metadata.site_registry import SiteRegistry, SiteContext
from orchestration.dataframe_builder import build as _build_dataframe
from orchestration.derived_quantities import pad_humidity as _pad_humidity
from orchestration.derived_quantities import pad_co2 as _pad_co2


ATTRS_SUBSET = [
    'site_name', 'fluxnet_id', 'latitude', 'longitude', 'elevation',
    'time_step', 'time_zone', 'canopy_height', 'tower_height', 'soil',
    'vegetation', 'system_type', 'date_commissioned'
    ]

SITE_REGISTRY = SiteRegistry()


def build_dataset_from_site_name(
        site_name: str,
        pad_humidity: bool = True,
        pad_co2: bool = True,
        start_date: pd.Timestamp | None = None,
        ) -> xr.Dataset:
    """Convenience wrapper — resolves site name to context via registry."""

    ctx = SITE_REGISTRY.get_context(site=site_name)
    return build_dataset_from_context(
        ctx=ctx, pad_humidity=pad_humidity, pad_co2=pad_co2, start_date=start_date
        )


def build_dataset_from_context(
        ctx: SiteContext,
        pad_humidity: bool = True,
        pad_co2: bool = True,
        start_date: pd.Timestamp | None = None,
        ) -> xr.Dataset:
    """Build an L1 xarray dataset from a fully-assembled site context."""

    result = _build_dataframe(ctx, start_date=start_date)
    if pad_humidity:
        result = _pad_humidity(result)
    if pad_co2:
        result = _pad_co2(result)

    ds = result.df.to_xarray()
    ds = _apply_variable_metadata(ds, result.var_attrs)
    ds = _apply_global_metadata(ds, ctx)

    return ds


def build_dataframe_from_site_name(
        site_name: str,
        pad_humidity: bool = True,
        pad_co2: bool = True,
        start_date: pd.Timestamp | None = None,
        ) -> pd.DataFrame:
    """Convenience wrapper — resolves site name to context via registry."""

    ctx = SITE_REGISTRY.get_context(site=site_name)
    return build_dataframe_from_context(
        ctx=ctx, pad_humidity=pad_humidity, pad_co2=pad_co2, start_date=start_date
        )


def build_dataframe_from_context(
        ctx: SiteContext,
        pad_humidity: bool = True,
        pad_co2: bool = True,
        start_date: pd.Timestamp | None = None,
        ) -> pd.DataFrame:
    """Build an L1 DataFrame from a fully-assembled site context."""

    result = _build_dataframe(ctx, start_date=start_date)
    if pad_humidity:
        result = _pad_humidity(result)
    if pad_co2:
        result = _pad_co2(result)
    return result.df


def _apply_variable_metadata(
        ds: xr.Dataset,
        var_attrs: dict[str, dict],
        ) -> xr.Dataset:
    """Attach per-variable attribute dicts to dataset variables."""

    for variable in [v for v in ds.variables if v not in ds.dims]:
        ds[variable].attrs = {k: v for k, v in var_attrs[variable].items() if v is not None}

    return ds


def _apply_global_metadata(
        ds: xr.Dataset,
        ctx: SiteContext,
        ) -> xr.Dataset:
    """Add global attributes from site context."""

    for attr in ATTRS_SUBSET:
        value = ctx.metadata.get(attr)
        if value is None:
            continue
        if isinstance(value, (datetime.date, datetime.datetime)):
            value = value.isoformat()
        ds.attrs[attr] = value

    for key, value in [
            ('irga_type',   ctx.runtime_config.irga_instrument),
            ('sonic_type',  ctx.runtime_config.sonic_instrument),
            ('flux_system', ctx.runtime_config.flux_system),
            ]:
        if value is not None:
            ds.attrs[key] = value

    return ds
