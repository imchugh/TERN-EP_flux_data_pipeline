#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rebuild a legacy-format TOA5 file from L1 NetCDF output.

This is a temporary bridge for the Campbell Scientific RTMC visualisation,
which reads a merged TOA5 file (``<site>_merged_std.dat``) and cannot consume
NetCDF. RTMC is being retired, so column names here are chosen to match the
historical TOA5 output as closely as possible rather than the current
canonical convention — changing a column name means updating the RTMC config,
which this module tries to avoid.
"""

###############################################################################
### BEGIN IMPORTS ###
###############################################################################

import csv
import logging
import pathlib

import xarray as xr

from services import config_loader
from services.data import toa5_writer
from services.data.transform_service import get_calculation

###############################################################################
### END IMPORTS ###
###############################################################################


###############################################################################
### BEGIN INITS ###
###############################################################################

logger = logging.getLogger(__name__)

# Quantities searched for a temperature/humidity sensor at (or nearest) flux
# measurement height; IRGA/SONIC-qualified variants are excluded since they
# are kept under their own qualified name.
MET_QUANTITIES = ['Ta', 'RH', 'AH']

# Flux quantities whose 'height' attr is used as the target height for the
# met sensor search (first one found in the dataset wins).
FLUX_HEIGHT_INDICATORS = ['Fco2', 'Fh', 'Fe']

# Canonical soil quantities and the soil_variables.yml key each maps to.
SOIL_QUANTITIES = {
    'Fg': 'soil_heat_flux',
    'Ts': 'soil_temperature',
    'Sws': 'soil_moisture',
    }

# Variables computed if not already present in the dataset.
ADD_VARIABLES = ['Td', 'VPD']

# Suffixes the legacy TOA5 output used to carry on non-turbulent-flux
# quantities (e.g. 'ustar_DL') that the current pipeline no longer attaches.
# Used only to line a legacy reference file's column order up against the
# current bare name, never to rename output columns.
LEGACY_FLUX_SUFFIXES = ('_DL', '_EF', '_EP')

# statistic_type value -> legacy TOA5 sampling-row label.
STATISTIC_LABELS = {
    'average': 'Avg',
    'sum': 'Tot',
    'standard_deviation': 'Sd',
    'variance': 'Vr',
    'minimum': 'Min',
    'maximum': 'Max',
    'covariance': 'Cov',
    'instantaneous': 'Smp',
    }

###############################################################################
### END INITS ###
###############################################################################


###############################################################################
### BEGIN PUBLIC FUNCTIONS ###
###############################################################################

def build_legacy_toa5(
        site_name: str,
        nc_files: list[pathlib.Path],
        output_path: pathlib.Path | str,
        legacy_reference: pathlib.Path | str | None = None,
        ) -> None:
    """
    Build a legacy-format TOA5 file from a set of L1 NetCDF files.

    Args:
        site_name: registered site name (used to look up soil_variables.yml).
        nc_files: L1 NetCDF files to merge (e.g. current + previous year).
        output_path: destination TOA5 file path.
        legacy_reference: path to an existing legacy TOA5 file for this site
            (e.g. the current production ``<site>_merged_std.dat``). If
            given, output columns are ordered to match its header — purely
            cosmetic (TOA5 readers bind by column name, not position), but
            makes byte-level diffing against the old file trivial. Columns
            not present in the reference are appended in their natural order.

    Returns:
        None.
    """

    logger.info('Reading .nc files for %s...', site_name)
    ds = xr.open_mfdataset(paths=sorted(nc_files), chunks={'time': 1000})

    logger.info('Dropping extraneous variables...')
    ds = _drop_extraneous_variables(ds, site_name=site_name)

    logger.info('Renaming variables to legacy convention...')
    ds = _rename_variables(ds)

    logger.info('Applying valid_range limits...')
    ds = _apply_valid_range(ds)

    logger.info('Adding derived variables...')
    ds = _add_missing_variables(ds)

    ds = ds.load()

    logger.info('Formatting data and headers...')
    df = ds.to_dataframe().droplevel(['latitude', 'longitude'])

    columns = list(df.columns)
    if legacy_reference is not None:
        columns = _order_like_legacy(columns, legacy_reference)
        df = df[columns]

    headers = _build_headers(ds=ds, columns=columns)
    ds.close()

    info = list(toa5_writer.DEFAULT_TOA5_INFO)
    info[-1] = 'merged'

    logger.info('Writing TOA5 file to %s...', output_path)
    toa5_writer.write_toa5(
        data=df,
        headers=headers,
        file_path=output_path,
        info=info,
        )
    logger.info('Done!')

###############################################################################
### END PUBLIC FUNCTIONS ###
###############################################################################


###############################################################################
### BEGIN PRIVATE FUNCTIONS ###
###############################################################################

def _drop_extraneous_variables(ds: xr.Dataset, site_name: str) -> xr.Dataset:
    """Drop QC flags, stdev variables, crs, and extraneous soil/met replicates."""

    drop = {'crs'}
    drop.update(var for var in ds.variables if var.endswith('QCFlag'))
    drop.update(var for var in ds.variables if var.endswith('_Sd'))
    drop.update(_get_extraneous_soil(ds=ds, site_name=site_name))
    drop.update(_get_extraneous_met(ds=ds))

    return ds.drop_vars([var for var in drop if var in ds.variables])


def _get_extraneous_soil(ds: xr.Dataset, site_name: str) -> list[str]:
    """Return soil variables not in the site's configured keep-list."""

    try:
        vars_to_keep = config_loader.load_config_file_from_name(
            name='soil_variables'
            )[site_name]
    except KeyError:
        vars_to_keep = {}

    drop = []
    for quantity, config_key in SOIL_QUANTITIES.items():
        raw_keep = vars_to_keep.get(config_key)
        if raw_keep is None:
            continue
        keep = [name.strip() for name in raw_keep.split(',')]
        available = [var for var in ds.variables if var.startswith(quantity + '_')]
        drop += [var for var in available if var not in keep]

    return drop


def _get_extraneous_met(ds: xr.Dataset) -> list[str]:
    """
    Choose one Ta/RH/AH variable to keep for each quantity: the one at (or
    nearest) the flux measurement height, preferring the same instrument as
    the chosen temperature sensor. Return the rest as a drop list.

    Raises:
        KeyError: if the flux measurement height cannot be determined.
    """

    target_height = None
    for var in FLUX_HEIGHT_INDICATORS:
        if var in ds.variables and 'height' in ds[var].attrs:
            target_height = float(ds[var].attrs['height'])
            break
    if target_height is None:
        raise KeyError(
            'Could not determine flux measurement height from any of: '
            f'{", ".join(FLUX_HEIGHT_INDICATORS)}'
            )

    candidates = []
    for quantity in MET_QUANTITIES:
        for var in ds.variables:
            if not var.startswith(quantity):
                continue
            if 'IRGA' in var or 'SONIC' in var:
                continue
            if var.endswith('QCFlag') or var.endswith('_Sd'):
                continue
            attrs = ds[var].attrs
            if 'height' not in attrs:
                continue
            candidates.append({
                'variable': var,
                'quantity': quantity,
                'height_diff': abs(float(attrs['height']) - target_height),
                'instrument': attrs.get('instrument'),
                })

    if not candidates:
        return []

    ta_candidates = sorted(
        (c for c in candidates if c['quantity'] == 'Ta'),
        key=lambda c: c['height_diff'],
        )

    rslt = {'Ta': None, 'RH': None, 'AH': None}
    fallback_rslt = {'Ta': None, 'RH': None, 'AH': None}
    use_main = False
    for ta in ta_candidates:
        rslt['Ta'] = ta['variable']
        fallback_rslt['Ta'] = ta['variable']
        for quantity in ['RH', 'AH']:

            # Same instrument at same height as the chosen Ta sensor.
            same_instrument = [
                c for c in candidates
                if c['quantity'] == quantity
                and c['height_diff'] == ta['height_diff']
                and c['instrument'] == ta['instrument']
                ]
            if same_instrument:
                rslt[quantity] = same_instrument[0]['variable']
                continue

            # Fallback: any instrument at the same height.
            same_height = [
                c for c in candidates
                if c['quantity'] == quantity
                and c['height_diff'] == ta['height_diff']
                ]
            if same_height:
                fallback_rslt[quantity] = same_height[0]['variable']

        if rslt['RH'] is not None or rslt['AH'] is not None:
            use_main = True
            break

    if not use_main:
        if fallback_rslt['RH'] is not None or fallback_rslt['AH'] is not None:
            rslt = fallback_rslt
        else:
            raise RuntimeError(
                'Could not find a humidity sensor at the same height as any '
                'temperature sensor!'
                )

    keep = {var for var in rslt.values() if var is not None}
    return [c['variable'] for c in candidates if c['variable'] not in keep]


def _rename_variables(ds: xr.Dataset) -> xr.Dataset:
    """Map canonical variable names to the legacy TOA5 naming convention."""

    # Drop the average-statistic suffix from all variables.
    ds = ds.rename({
        var: var[:-len('_Av')] for var in ds.variables if var.endswith('_Av')
        })

    # Collapse the single surviving Ta/RH/AH replicate to the bare quantity name.
    rename = {}
    for quantity in MET_QUANTITIES:
        rename.update({
            var: quantity for var in ds.variables
            if var.startswith(quantity)
            and 'IRGA' not in var and 'SONIC' not in var
            })
    ds = ds.rename(rename)

    # Sonic-derived wind direction/speed lose the instrument qualifier.
    wind_rename = {}
    for var in ['Wd', 'Ws']:
        if var in ds:
            ds = ds.drop(var)
        sonic_var = f'{var}_SONIC'
        if sonic_var in ds.variables:
            wind_rename[sonic_var] = var
    ds = ds.rename(wind_rename)

    # First precipitation replicate wins.
    precip_vars = [var for var in ds.variables if 'Precip' in var]
    if precip_vars and precip_vars[0] != 'Precip':
        ds = ds.rename({precip_vars[0]: 'Precip'})

    # Soil variables: metres -> centimetres (legacy depth-naming convention).
    soil_rename = {}
    for quantity in SOIL_QUANTITIES:
        soil_rename.update({
            var: _convert_soil_var_name(var) for var in ds.variables
            if var.startswith(quantity + '_')
            })
    ds = ds.rename(soil_rename)

    return ds


def _convert_soil_var_name(variable: str) -> str:
    """Convert a soil variable's depth qualifier from metres to centimetres.

    e.g. 'Fg_0.08ma' -> 'Fg_8cma'
    """

    quantity, loc, *other = variable.split('_')
    depth_str, _, replicate = loc.partition('m')
    depth_cm = int(round(float(depth_str) * 100))
    return '_'.join([quantity, f'{depth_cm}cm{replicate}'] + other)


def _apply_valid_range(ds: xr.Dataset) -> xr.Dataset:
    """Mask values outside each variable's valid_range attr (where present)."""

    for var in ds.variables:
        if var in ds.dims or var == 'crs':
            continue
        valid_range = ds[var].attrs.get('valid_range')
        if valid_range is None:
            continue
        vmin, vmax = valid_range
        ds[var] = ds[var].where((ds[var] >= vmin) & (ds[var] <= vmax))

    return ds


def _add_missing_variables(ds: xr.Dataset) -> xr.Dataset:
    """Compute Td/VPD from Ta/RH if not already present in the dataset."""

    units = {'Td': 'degC', 'VPD': 'kPa'}
    for var in ADD_VARIABLES:
        if var in ds.variables:
            continue
        func = get_calculation(var)
        ds[var] = func(Ta=ds['Ta'], RH=ds['RH'])
        ds[var].attrs = {'units': units[var], 'statistic_type': 'average'}

    return ds


def _read_legacy_columns(legacy_reference: pathlib.Path | str) -> list[str]:
    """Read the column-name header row of an existing TOA5 file."""

    with open(legacy_reference, newline='') as f:
        reader = csv.reader(f)
        next(reader)  # info line
        header = next(reader)  # variable names, including TIMESTAMP

    return header[1:]


def _order_like_legacy(
        columns: list[str],
        legacy_reference: pathlib.Path | str,
        ) -> list[str]:
    """
    Reorder columns to match a legacy TOA5 file's column order.

    Legacy columns are matched against `columns` directly, falling back to
    stripping a known legacy flux-system suffix (e.g. 'ustar_DL' -> 'ustar')
    for quantities the current pipeline no longer suffixes. Legacy columns
    with no match, and current columns absent from the legacy file, are
    dropped/appended respectively rather than raising, since the variable set
    can legitimately differ between an old file and a freshly built one.
    """

    available = set(columns)
    ordered = []
    seen = set()
    for legacy_name in _read_legacy_columns(legacy_reference):
        resolved = legacy_name if legacy_name in available else None
        if resolved is None:
            for suffix in LEGACY_FLUX_SUFFIXES:
                if legacy_name.endswith(suffix) and legacy_name[:-len(suffix)] in available:
                    resolved = legacy_name[:-len(suffix)]
                    break
        if resolved is not None and resolved not in seen:
            ordered.append(resolved)
            seen.add(resolved)

    ordered += [c for c in columns if c not in seen]
    return ordered


def _build_headers(ds: xr.Dataset, columns: list[str]) -> list[list[str]]:
    """Build the [variables, units, sampling] header rows for write_toa5."""

    units, sampling = [], []
    for var in columns:
        attrs = ds[var].attrs
        units.append(attrs.get('units', '1'))
        default = 'Tot' if var.startswith('Diag') else 'Avg'
        sampling.append(STATISTIC_LABELS.get(attrs.get('statistic_type'), default))

    return [columns, units, sampling]

###############################################################################
### END PRIVATE FUNCTIONS ###
###############################################################################
