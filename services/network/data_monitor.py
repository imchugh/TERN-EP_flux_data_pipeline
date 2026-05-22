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

from infrastructure import data_functions, datetime_utils, paths
from services.data import raw_data_loader
from services.metadata.variable_metadata_service import SiteRuntimeConfig
from domain.data_models.metadata_classes import SiteMetadata

logger = logging.getLogger(__name__)

MONITOR_VARS = ['Fco2', 'Fh', 'Fe', 'Fsd']
ANALYSIS_PERIODS_DAYS = [1, 7, 30]
NULL_RESULT: dict[str, Any] = {
    'last_record': None,
    'days_since_last_record': None,
    **{f'pct_missing_last_{p}_days': None for p in ANALYSIS_PERIODS_DAYS},
    'error': None,
    }


# -----------------------------------------------------------------------------

def get_missing_records(
    df: pd.DataFrame,
    reference_date: datetime,
    interval_minutes: int = 30,
    days: int | list[int] | None = None,
    ) -> dict[str, float]:
    """
    Analyse recent data gaps over one or more rolling periods.

    Args:
        df: Time-indexed DataFrame to analyse.
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
        ValueError: If df is empty, days list is empty, or any period is <= 0.
        TypeError: If df index is not a DatetimeIndex, or days is not int/list.
    """

    if df.empty:
        raise ValueError('Input dataframe is empty')

    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError('DataFrame index must be a DatetimeIndex')

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

        try:
            missing = (
                data_functions.analyse_data_gaps(
                    df=analysis_df,
                    interval_minutes=interval_minutes,
                    )['pct_missing']
                )

        except ValueError as exc:
            logger.warning(
                "gap_analysis_failed",
                extra={"period_days": period, "error": str(exc)},
            )
            missing = 100.0

        results[f'pct_missing_last_{period}_days'] = missing

    return results
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
def analyse_missing_data(
    data_cfg: SiteRuntimeConfig,
    site_cfg: SiteMetadata,
    ) -> dict[str, Any]:
    """
    Analyse data recency and gap statistics for a single site.

    Loads the site's flux slow data file, computes the time elapsed since the
    last record (relative to site-local time), and calculates percentage-missing
    statistics over the standard analysis periods.

    Args:
        data_cfg: Site runtime configuration supplying file paths and format.
        site_cfg: Site metadata supplying timezone and sampling interval.

    Returns:
        Dict with keys:
            - ``last_record``: ISO-8601 timezone-aware datetime of the final
              record in the file.
            - ``days_since_last_record``: Whole days elapsed since that record,
              measured against site-local now.
            - ``pct_missing_last_<N>_days``: Percentage of expected records
              absent over each standard analysis period.
    """

    # Get the raw data path based on site
    file_path = paths.get_local_stream_path(
        resource='raw_data',
        stream='flux_slow',
        site=data_cfg.site_name,
        file_name=data_cfg.flux_filename
        )

    # Get the file type adapter
    adapter = raw_data_loader.get_data_adapter(
        system_type=data_cfg.get_file_format(
            file_group=data_cfg.flux_file
            )
        )

    # Load the data
    df = adapter.load(file_path=file_path)

    # Get the datetimes
    local_now = datetime_utils.get_local_datetime_now(
        tz_name=site_cfg.time_zone,
        )
    local_now_naive = local_now.replace(tzinfo=None)
    last_data_record_naive = df.index[-1].to_pydatetime()
    last_data_record_tzaware = datetime_utils.get_tz_aware_datetime(
        naive_dt=last_data_record_naive,
        tz_name=site_cfg.time_zone,
        as_iso=True
        )

    # Calculate delta in days
    elapsed = (local_now_naive - last_data_record_naive).days

    result = {
        'last_record': last_data_record_tzaware,
        'days_since_last_record': elapsed,
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
