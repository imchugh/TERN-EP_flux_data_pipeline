#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Derive and pad missing humidity variables in a DataframeBuildResult.

Where a (instrument, height) group contains Ta and RH but not AH, AH is
derived from Ta + RH + ps.  Where it contains Ta and AH but not RH, RH is
derived from Ta + AH + ps.  Groups missing Ta, or that already have both RH
and AH, are left unchanged.  If no pressure variable is present in the
dataframe the result is returned unchanged.

Public API
----------
pad_humidity(result) -> DataframeBuildResult
"""

###############################################################################
### BEGIN IMPORTS ###
###############################################################################

import pandas as pd

from orchestration.dataframe_builder import DataframeBuildResult
from infrastructure.convert_calc_filter import (
    calculate_AH_from_RH,
    calculate_RH_from_AH,
)

###############################################################################
### END IMPORTS ###
###############################################################################


###############################################################################
### BEGIN INITS ###
###############################################################################

_HUMIDITY_QUANTITIES = frozenset({'Ta', 'RH', 'AH'})

_CANONICAL_ATTRS = {
    'AH': {
        'long_name':     'Absolute humidity',
        'standard_name': 'mass_concentration_of_water_vapor_in_air',
        'units':         'g/m^3',
    },
    'RH': {
        'long_name':     'Relative humidity',
        'standard_name': 'relative_humidity',
        'units':         'percent',
    },
}

###############################################################################
### END INITS ###
###############################################################################


###############################################################################
### BEGIN PUBLIC FUNCTIONS ###
###############################################################################

# -----------------------------------------------------------------------------

def pad_humidity(result: DataframeBuildResult) -> DataframeBuildResult:
    """
    Derive and add the missing humidity variable (RH or AH) for each
    instrument+height group that has Ta and exactly one of {RH, AH}.

    Returns the result unchanged if no pressure variable is found or there is
    nothing to derive.
    """

    df = result.df.copy()
    var_attrs = dict(result.var_attrs)

    ps_col = _find_pressure(df, var_attrs)
    if ps_col is None:
        return result

    groups = _group_by_instrument_height(var_attrs)

    for group in groups.values():

        ta_col = group.get('Ta')
        rh_col = group.get('RH')
        ah_col = group.get('AH')

        if ta_col is None:
            continue
        if (rh_col is None) == (ah_col is None):   # both present or both absent
            continue

        if rh_col is not None:
            new_col = _derived_name(rh_col, 'RH', 'AH')
            df[new_col] = calculate_AH_from_RH(
                Ta=df[ta_col], RH=df[rh_col], ps=df[ps_col]
                )
            var_attrs[new_col] = _build_attrs(
                source_attrs=var_attrs[rh_col], quantity='AH'
                )
        else:
            new_col = _derived_name(ah_col, 'AH', 'RH')
            df[new_col] = calculate_RH_from_AH(
                AH=df[ah_col], Ta=df[ta_col], ps=df[ps_col]
                )
            var_attrs[new_col] = _build_attrs(
                source_attrs=var_attrs[ah_col], quantity='RH'
                )

    return DataframeBuildResult(df=df, var_attrs=var_attrs)

# -----------------------------------------------------------------------------

###############################################################################
### END PUBLIC FUNCTIONS ###
###############################################################################


###############################################################################
### BEGIN PRIVATE FUNCTIONS ###
###############################################################################

# -----------------------------------------------------------------------------

def _find_pressure(
        df: pd.DataFrame,
        var_attrs: dict[str, dict],
        ) -> str | None:
    """Return the first ps column present in both var_attrs and df, or None."""

    for var_name, attrs in var_attrs.items():
        if attrs.get('quantity') == 'ps' and var_name in df.columns:
            return var_name
    return None

# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def _group_by_instrument_height(
        var_attrs: dict[str, dict],
        ) -> dict[tuple, dict[str, str]]:
    """
    Group humidity-relevant canonical names by (instrument, height).

    Returns:
        dict keyed by (instrument, height); values are quantity → canonical name
        for quantities in {Ta, RH, AH}.
    """

    groups: dict[tuple, dict[str, str]] = {}
    for var_name, attrs in var_attrs.items():
        qty = attrs.get('quantity')
        if qty not in _HUMIDITY_QUANTITIES:
            continue
        key = (attrs['instrument'], attrs['height'])
        groups.setdefault(key, {})[qty] = var_name
    return groups

# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def _derived_name(source_name: str, source_qty: str, new_qty: str) -> str:
    """Replace the quantity prefix of source_name with new_qty."""

    suffix = source_name[len(source_qty):]      # preserves leading '_'
    return f"{new_qty}{suffix}"

# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def _build_attrs(source_attrs: dict, quantity: str) -> dict:
    """Build attrs for a derived variable, inheriting spatial/instrument context."""

    canonical = _CANONICAL_ATTRS[quantity]
    return {
        'height':             source_attrs['height'],
        'height_range':       source_attrs['height_range'],
        'instrument':         source_attrs['instrument'],
        'instrument_history': source_attrs['instrument_history'],
        'long_name':          canonical['long_name'],
        'quantity':           quantity,
        'standard_name':      canonical['standard_name'],
        'statistic_type':     source_attrs['statistic_type'],
        'units':              canonical['units'],
    }

# -----------------------------------------------------------------------------

###############################################################################
### END PRIVATE FUNCTIONS ###
###############################################################################
