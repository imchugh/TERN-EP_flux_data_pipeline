#!/usr/bin/env python3
"""TERN-adapter convenience wrappers for resolving a site name to a context.

Resolves a site name to a SiteContext via SiteRegistry, then delegates to
the generic-core `*_from_context` builders.

Public API
----------
build_dataframe_from_site_name(site_name, quantities, start_date) -> pd.DataFrame
build_dataset_from_site_name(site_name, pad_humidity, pad_co2, start_date, legacy)
    -> xr.Dataset
"""

import pandas as pd
import xarray as xr

from orchestration.dataframe_builder import build_dataframe_from_context
from orchestration.dataset_builder import build_dataset_from_context
from services.metadata.tern.site_registry import SiteRegistry

SITE_REGISTRY = SiteRegistry()


def build_dataframe_from_site_name(
    site_name: str,
    quantities: set[str] | None = None,
    start_date: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Convenience wrapper — resolves site name to context via registry."""
    ctx = SITE_REGISTRY.get_context(site=site_name)
    return build_dataframe_from_context(
        ctx=ctx,
        quantities=quantities,
        start_date=start_date,
    )


def build_dataset_from_site_name(
    site_name: str,
    pad_humidity: bool = True,
    pad_co2: bool = True,
    start_date: pd.Timestamp | None = None,
    legacy: bool = False,
) -> xr.Dataset:
    """Convenience wrapper — resolves site name to context via registry.

    legacy: if True, build from the site's legacy config snapshot
        (site_configs/legacy) instead of its operational config. Use for
        one-off rebuilds of L1 output under an earlier generation of
        instruments/variables/files.
    """
    ctx = SITE_REGISTRY.get_context(site=site_name, legacy=legacy)
    return build_dataset_from_context(
        ctx=ctx, pad_humidity=pad_humidity, pad_co2=pad_co2, start_date=start_date
    )
