#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed May  6 14:57:06 2026

@author: imchugh
"""

import datetime

def get_data_year_bounds(year: int, time_step: int) -> tuple[datetime, datetime]:
    """Create boundaries for valid data years"""
    
    start = datetime.datetime(year, 1, 1) + datetime.timedelta(minutes=time_step)
    end = datetime.datetime(year + 1, 1, 1)
    return start, end