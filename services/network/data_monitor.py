#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu May 14 09:30:42 2026

@author: imchugh
"""

import pandas as pd
from datetime import datetime, timedelta

from infrastructure import datetime_utils
from infrastructure import data_functions

from services.data import raw_data_loader

from infrastructure import paths

MONITOR_VARS = []
ANALYSIS_PERIODS_DAYS = [1, 7, 30]




# -----------------------------------------------------------------------------

def get_missing_records(
    df: pd.DataFrame,
    reference_date: datetime,
    data_interval: int = 30,
    days: int | list[int] | None = None,
    ) -> dict[str, dict]:
    """
    Analyse recent data gaps over one or more rolling periods.
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
                    interval_minutes=data_interval,
                    )['pct_missing']
                )
            
        except ValueError:
            
            missing = 100.0
            
        results[f'pct_missing_last_{period}_days'] = missing
            
    return results
# -----------------------------------------------------------------------------        
    
def analyse_missing_data(data_cfg, site_cfg):
        
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
        'days_since_last_record': elapsed 
        }
       
    result.update(
        get_missing_records(
            df=df, 
            reference_date=datetime.now(),
            data_interval=site_cfg.time_step    
            )
        )
    
    return result
    