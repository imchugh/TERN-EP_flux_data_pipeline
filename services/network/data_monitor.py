#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu May 14 09:30:42 2026

@author: imchugh
"""

import logging
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from domain.enums import StatisticType, VariableType
from infrastructure import data_diagnostics, datetime_utils, paths
from services.data import raw_data_loader
from services.metadata.site_registry import SiteContext

logger = logging.getLogger(__name__)

MONITOR_VARS = ['Fco2', 'Fh', 'Fe', 'Fsd']
ANALYSIS_PERIODS_DAYS = [1, 7, 30]
NULL_RESULT: dict[str, Any] = {
    'last_record': None,
    'days_since_last_record': None,
    **{f'pct_missing_last_{p}_days': None for p in ANALYSIS_PERIODS_DAYS},
    'error': None,
    }

VARIABLE_QUALITY_NULL_RESULT: dict[str, Any] = {
    **{var: None for var in MONITOR_VARS},
    'error': None,
    }

_MONITOR_STATISTIC_TYPES = {StatisticType.AVG, None}
_MONITOR_VARIABLE_TYPES  = {VariableType.CONTINUOUS}


# -----------------------------------------------------------------------------

def get_missing_records(
    df: pd.DataFrame | pd.Series,
    reference_date: datetime,
    interval_minutes: int = 30,
    days: int | list[int] | None = None,
    ) -> dict[str, float]:
    """
    Analyse recent data gaps over one or more rolling periods.

    Args:
        df: Time-indexed DataFrame or Series to analyse.
        reference_date: Upper bound of the analysis window. Should be the
            site-local naive datetime so window boundaries align with the
            data timestamps.
        interval_minutes: Expected data interval in minutes. Defaults to 30.
        days: Analysis period(s) in days. Accepts a single int or a list of
            ints. When None, defaults to ANALYSIS_PERIODS_DAYS.

    Returns:
        Dict mapping period labels to percentage-missing floats, e.g.
        ``{'pct_missing_last_1_days': 0.0, 'pct_missing_last_7_days': 4.2}``.

    Raises:
        ValueError: If df fails validation, days list is empty, or any period is <= 0.
        TypeError: If df fails validation, or days is not int/list.
    """

    data_diagnostics.validate_dataframe(df)

    if not df.index.is_monotonic_increasing:
        df = df.sort_index()

    analysis_periods = ANALYSIS_PERIODS_DAYS

    if days is not None:

        if isinstance(days, int) and not isinstance(days, bool):
            analysis_periods = [days]

        elif isinstance(days, list):

            if not days:
                raise ValueError('days list cannot be empty')

            if not all(isinstance(elem, int) for elem in days):
                raise TypeError(
                    'days argument must be either an int or a list of ints'
                    )

            analysis_periods = days

        else:
            raise TypeError(
                'days argument must be either an int or a list of ints'
                )

    if any(period <= 0 for period in analysis_periods):
        raise ValueError('All analysis periods must be positive integers')

    last = reference_date
    results = {}

    for period in analysis_periods:

        first = last - timedelta(days=period)
        analysis_df = df.loc[first:last]

        missing = (
            data_diagnostics.analyse_data_gaps(
                df=analysis_df,
                interval_minutes=interval_minutes,
                start=first,
                end=last,
                )['pct_missing']
            )

        results[f'pct_missing_last_{period}_days'] = missing

    return results
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------

def _build_monitor_series(
        df: pd.DataFrame,
        quantity: str,
        context: SiteContext,
        ) -> pd.Series | None:
    """
    Extract a plausibility-filtered sparse Series for a single quantity.

    Walks the site variable registry to find raw column name(s) for the
    quantity in the flux file, restricts to continuous average-statistic
    variables, applies the canonical plausible range (masking out-of-range
    values as NaN), then drops NaN so the resulting index contains only
    plausible records. Multiple raw columns (instrument changeover periods)
    are merged with combine_first. Returns None if no matching column exists
    in df.

    Args:
        df: Raw flux DataFrame with DatetimeIndex.
        quantity: Canonical quantity name, e.g. 'Fco2'.
        context: Site runtime config and metadata.

    Returns:
        Sparse Series of plausible values, or None if not available.
    """

    runtime_cfg = context.runtime_config
    flux_file = runtime_cfg.flux_file

    series: list[pd.Series] = []

    for var_def in runtime_cfg.variables.values():

        if var_def.quantity != quantity:
            continue
        if var_def.variable_type not in _MONITOR_VARIABLE_TYPES:
            continue
        if var_def.statistic_type not in _MONITOR_STATISTIC_TYPES:
            continue

        pmin = var_def.canonical.plausible_min
        pmax = var_def.canonical.plausible_max

        for raw_input in var_def.raw_inputs:

            if raw_input.file != flux_file:
                continue
            if raw_input.raw_name not in df.columns:
                continue

            s = df[raw_input.raw_name].copy()

            if pmin is not None:
                s = s.where(s >= pmin)
            if pmax is not None:
                s = s.where(s <= pmax)

            series.append(s)

    if not series:
        return None

    combined = series[0]
    for s in series[1:]:
        combined = combined.combine_first(s)

    return combined.dropna()
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------

def get_variable_quality(
        df: pd.DataFrame,
        context: SiteContext,
        reference_date: datetime,
        interval_minutes: int = 30,
        days: int | list[int] | None = None,
        ) -> dict[str, dict[str, float] | None]:
    """
    Analyse plausible-value coverage for each monitored flux variable.

    For each variable in MONITOR_VARS, extracts raw values from the flux
    file, discards readings outside canonical plausible bounds, then
    computes percentage-missing over rolling windows. The resulting
    percentage reflects both absent records AND implausible values, so it
    will always be >= the overall record-coverage figure from
    get_missing_records. Variables not present in the site config or raw
    file return None.

    Args:
        df: Raw flux DataFrame with DatetimeIndex.
        context: Site runtime config and metadata.
        reference_date: Upper bound of the analysis window (site-local naive
            datetime).
        interval_minutes: Expected data interval in minutes. Defaults to 30.
        days: Analysis period(s) in days. Accepts a single int or a list of
            ints. When None, defaults to ANALYSIS_PERIODS_DAYS.

    Returns:
        Dict keyed by variable name. Each value is a period-keyed dict of
        percentage-missing floats (absent + implausible), or None if the
        variable is unavailable for this site.
    """

    results = {}

    for var in MONITOR_VARS:

        series = _build_monitor_series(df=df, quantity=var, context=context)

        if series is None or series.empty:
            results[var] = None
            continue

        results[var] = get_missing_records(
            df=series,
            reference_date=reference_date,
            interval_minutes=interval_minutes,
            days=days,
            )

    return results
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
def analyse_missing_data(context: SiteContext) -> dict[str, Any]:
    """
    Analyse data recency and record coverage for a site.

    Loads the site's flux slow data file, computes the time elapsed since the
    last record (relative to site-local time), and calculates the percentage
    of expected timestamps absent from the raw file over each standard
    analysis period.

    Args:
        context: Combined site runtime config and metadata.

    Returns:
        Dict with keys:
            - ``last_record``: ISO-8601 timezone-aware datetime of the final
              record in the file.
            - ``days_since_last_record``: Whole days elapsed since that record,
              measured against site-local now.
            - ``pct_missing_last_<N>_days``: Percentage of expected records
              absent over each standard analysis period.
    """

    data_cfg = context.runtime_config
    site_cfg = context.metadata

    file_path = paths.get_local_stream_path(
        resource='raw_data',
        stream='flux_slow',
        site=data_cfg.site_name,
        file_name=data_cfg.flux_filename
        )

    adapter = raw_data_loader.get_data_adapter(
        system_type=data_cfg.get_file_format(file_group=data_cfg.flux_file)
        )

    df = adapter(file_path)

    local_now = datetime_utils.get_local_datetime_now(tz_name=site_cfg.time_zone)
    local_now_naive = local_now.replace(tzinfo=None)
    last_data_record_naive = df.index[-1].to_pydatetime()
    last_data_record_tzaware = datetime_utils.get_tz_aware_datetime(
        naive_dt=last_data_record_naive,
        tz_name=site_cfg.time_zone,
        as_iso=True
        )

    result = {
        'last_record': last_data_record_tzaware,
        'days_since_last_record': (local_now_naive - last_data_record_naive).days,
        }

    result.update(
        get_missing_records(
            df=df,
            reference_date=local_now_naive,
            interval_minutes=site_cfg.time_step,
            )
        )

    return result
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
def analyse_variable_quality(context: SiteContext) -> dict[str, Any]:
    """
    Analyse plausible-value coverage for each monitored flux variable.

    Loads the site's flux slow data file and computes per-variable
    percentage-missing over each standard analysis period. The metric
    combines absent records and implausible values, so it will always be
    >= the record-coverage figure from analyse_missing_data.

    Args:
        context: Combined site runtime config and metadata.

    Returns:
        Dict keyed by variable name (entries from MONITOR_VARS). Each value
        is a period-keyed dict of percentage-missing floats, or None if the
        variable is not configured or present for this site.
    """

    data_cfg = context.runtime_config
    site_cfg = context.metadata

    file_path = paths.get_local_stream_path(
        resource='raw_data',
        stream='flux_slow',
        site=data_cfg.site_name,
        file_name=data_cfg.flux_filename
        )

    adapter = raw_data_loader.get_data_adapter(
        system_type=data_cfg.get_file_format(file_group=data_cfg.flux_file)
        )

    df = adapter(file_path)

    local_now = datetime_utils.get_local_datetime_now(tz_name=site_cfg.time_zone)
    local_now_naive = local_now.replace(tzinfo=None)

    return get_variable_quality(
        df=df,
        context=context,
        reference_date=local_now_naive,
        interval_minutes=site_cfg.time_step,
        )
# -----------------------------------------------------------------------------
