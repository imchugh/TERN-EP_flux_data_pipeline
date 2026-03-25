#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Mar 13 09:02:09 2026

@author: imchugh
"""

import ephem
import datetime as dt

from timezonefinder import TimezoneFinder
from pytz import timezone

#------------------------------------------------------------------------------
class TimeFunctions():

    def __init__(self, lat, lon, elev, date):

        self.date = date
        self.time_zone = get_timezone(lat=lat, lon=lon)
        self.utc_offset = get_UTC_offset(
            tz_name=self.time_zone, date=date, offset_as_delta=True
            )
        obs = ephem.Observer()
        obs.lat = str(lat)
        obs.long = str(lon)
        obs.elev = elev
        obs.date = date
        self.obs = obs

    def get_next_sunrise(self, as_local=True):

        return self._get_rise_set(
            rise_or_set='rise', next_or_last='next', as_utc=not(as_local)
            )

    def get_last_sunrise(self, as_local=True):

        return self._get_rise_set(
            rise_or_set='rise', next_or_last='last', as_utc=not(as_local)
            )

    def get_next_sunset(self, as_local=True):

        return self._get_rise_set(
            rise_or_set='set', next_or_last='next', as_utc=not(as_local)
            )

    def get_last_sunset(self, as_local=True):

        return self._get_rise_set(
            rise_or_set='set', next_or_last='last', as_utc=not(as_local)
            )

    def _get_rise_set(self, rise_or_set, next_or_last, as_utc=True):

        sun = ephem.Sun()
        funcs_dict = {
            'rise':
                {
                    'next': self.obs.next_rising(sun).datetime(),
                    'last': self.obs.previous_rising(sun).datetime()
                    },
            'set':
                {
                    'next': self.obs.next_setting(sun).datetime(),
                    'last': self.obs.previous_setting(sun).datetime()
                    }
                }

        if as_utc:
            return funcs_dict[rise_or_set][next_or_last]
        return funcs_dict[rise_or_set][next_or_last] + self.utc_offset
#------------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def get_timezone(lat: float, lon: float) -> str:
    
    tf = TimezoneFinder()

    try:
        return tf.timezone_at(lat=lat, lng=lon)
    except Exception:
        return None
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def get_UTC_offset(
    tz_name: str, 
    date: dt.datetime=None, 
    offset_as_delta: bool=False, 
    dst: bool=False
    ) -> float | None:
    
    if date is None:
        date = dt.datetime.now()
    tz = timezone(tz_name)
    offset = tz.utcoffset(date)
    if not dst:
        offset -= tz.dst(date)
    if offset_as_delta:
        return offset
    return offset.total_seconds() / 3600 if offset else None
# -----------------------------------------------------------------------------