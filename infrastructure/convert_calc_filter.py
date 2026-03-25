# -*- coding: utf-8 -*-
"""
Created on Fri Feb 24 14:05:44 2023

Add a way to fill unknown variables with NaN to the function getter

@author: jcutern-imchugh
"""

###############################################################################
### BEGIN IMPORTS ###
###############################################################################

import ephem
import inspect
import numpy as np
import pandas as pd
from pytz import timezone
from timezonefinder import TimezoneFinder

###############################################################################
### END IMPORTS ###
###############################################################################



###############################################################################
### BEGIN INITS ###
###############################################################################

CO2_MOL_MASS = 44
H2O_MOL_MASS = 18
K = 273.15
R = 8.3143

VARIANCE_CONVERSIONS = {
    'g/m^3': 'g^2/m^6',
    'umol/mol': 'umol/mol',
    'mg/m^3': 'mg^2/m^6',
    'degC': 'degC^2',
    'm/s': 'm^2/s^2',
    'mmol/m^3': 'mmol^2/m^6',
    'mmol/mol': 'mmol/mol',
    'K': 'K^2'
    }

###############################################################################
### END INITS ###
###############################################################################



###############################################################################
### BEGIN CLASSES ###
###############################################################################

#------------------------------------------------------------------------------
class TimeFunctions():

    def __init__(self, lat, lon, elev, date):

        self.date = date
        self.time_zone = get_timezone(lat=lat, lon=lon)
        self.utc_offset = get_timezone_utc_offset(tz=self.time_zone, date=date)
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

#------------------------------------------------------------------------------
def get_timezone(lat, lon):
    """Get the timezone (as region/city)"""

    tf = TimezoneFinder()
    return tf.timezone_at(lng=lon, lat=lat)
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def get_timezone_utc_offset(tz, date, dst=False):
    """Get the UTC offset (local standard or daylight)"""

    tz_obj = timezone(tz)
    utc_offset = tz_obj.utcoffset(date)
    if not dst:
        return utc_offset - tz_obj.dst(date)
    return utc_offset
#------------------------------------------------------------------------------

###############################################################################
### END CLASSES ###
###############################################################################



###############################################################################
### BEGIN QUANTITY CONVERSION FUNCTIONS ###
###############################################################################

#------------------------------------------------------------------------------
def apply_limits(data, data_min, data_max, inplace=False):

    filter_bool = (data < data_min) | (data > data_max)
    if inplace:
        data.loc[filter_bool] = np.nan
    else:
        return data.where(~filter_bool, np.nan)
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def convert_CO2_flux(data, from_units='mg/m^2/s'):

    if from_units == 'mg/m^2/s':
        return data * 1000 / CO2_MOL_MASS
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def convert_CO2_density(data, from_units='mmol/m^3'):

    if from_units == 'mmol/m^3':
        return data * CO2_MOL_MASS
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def convert_signal_strength(data, from_units='frac'):

    if from_units == 'frac':
        return data * 100
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def convert_diagnostic(data, n_samples, from_units='valid_count'):

    if from_units == 'valid_count':
        return n_samples - data
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def convert_H2O_density(data, from_units='mmol/m^3'):

    if from_units == 'mmol/m^3':
        return data * H2O_MOL_MASS / 10**3
    if from_units == 'kg/m^3':
        return data * 10**3
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def convert_precipitation(data, from_units='pulse_0.2mm'):

    if from_units == 'pulse_0.2mm':
        return data * 0.2
    if from_units == 'pulse_0.5mm':
        return data * 0.5
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def convert_pressure(data, from_units='Pa'):

    if from_units == 'Pa':
        return data / 10**3
    if from_units == 'hPa':
        return data / 10
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def convert_RH(data, from_units='frac'):

    if from_units == 'frac':
        return data * 100
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def convert_Sws(data, from_units='percent'):

    if from_units == 'percent':
        return data / 100
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def convert_temperature(data, from_units='K'):

    if from_units == 'K':
        return data - K
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def convert_variance_stdev(data, from_variance=True):

    if from_variance:
        return data**(1/2)
    return data**2
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def convert_variable(variable):

    conversions_dict = {
        'Fco2': convert_CO2_flux,
        'Sig_IRGA': convert_signal_strength,
        'SigCO2_IRGA': convert_signal_strength,
        'SigH2O_IRGA': convert_signal_strength,
        'CO2Sig_IRGA': convert_signal_strength,
        'H2OSig_IRGA': convert_signal_strength,
        'RH': convert_RH,
        'CO2c_IRGA': convert_CO2_density,
        'AH_IRGA': convert_H2O_density,
        'AH': convert_H2O_density,
        'Ta': convert_temperature,
        'Tv_SONIC': convert_temperature,
        'ps': convert_pressure,
        'Sws': convert_Sws,
        'VPD': convert_pressure,
        'Precip': convert_precipitation,
        'Tbody_RAD': convert_temperature
        }
    return conversions_dict[variable]
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def convert_variance(variable, data, variance_units):

    reverse_units = {
        value: key for key, value in VARIANCE_CONVERSIONS.items()
        }
    from_units = reverse_units[variance_units]
    func = convert_variable(variable=variable)
    return func(data=data**(1/2), from_units=from_units)**2
#------------------------------------------------------------------------------

###############################################################################
### END QUANTITY CONVERSION FUNCTIONS ###
###############################################################################



###############################################################################
### BEGIN QUANTITY CALCULATION FUNCTIONS ###
###############################################################################

#------------------------------------------------------------------------------
def calculate_AH_from_RH(Ta: pd.Series, RH: pd.Series, ps: pd.Series):

    return (
        calculate_e(Ta=Ta, RH=RH) / ps *
        calculate_molar_density(Ta=Ta, ps=ps) *
        H2O_MOL_MASS
        )
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def calculate_dew_point(Ta: pd.Series, RH: pd.Series) -> pd.Series:

    e = calculate_e(Ta=Ta, RH=RH)
    ln_ratio = np.log(e / 0.61121)
    return (243.5 * ln_ratio) / (17.502 - ln_ratio)
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def calculate_CO2_density(
        CO2: pd.Series, Ta: pd.Series, ps: pd.Series
        ) -> pd.Series:

    return CO2 / 10**3 * calculate_molar_density(Ta=Ta, ps=ps) * CO2_MOL_MASS
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def calculate_CO2_mole_fraction(
        CO2c_IRGA: pd.Series, Ta: pd.Series, ps: pd.Series
        ) -> pd.Series:

    return (
        (CO2c_IRGA / CO2_MOL_MASS) /
        calculate_molar_density(Ta=Ta, ps=ps)
        * 10**3
        )
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def calculate_e(Ta: pd.Series, RH: pd.Series) -> pd.Series:

    return calculate_es(Ta=Ta) * RH / 100
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def calculate_es(Ta: pd.Series) -> pd.Series:
    """Saturation vapor pressure (kPa) from Buck (1996) formula"""
    
    return 0.61121 * np.exp((18.678 - Ta / 234.5) * (Ta / (257.14 + Ta)))
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def calculate_molar_density(ps: pd.Series, Ta: pd.Series) -> pd.Series:

    return ps * 1000 / ((Ta + K) * R)
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def calculate_RH_from_AH(AH, Ta, ps):

    e = (AH / 18) / calculate_molar_density(Ta=Ta, ps=ps) * ps
    es = calculate_es(Ta=Ta)
    return e / es * 100
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def calculate_ustar_from_tau_rho(tau, rho):

    return abs(tau) / rho
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def calculate_VPD(Ta: pd.Series, RH: pd.Series) -> pd.Series:

    return calculate_es(Ta=Ta) - calculate_e(Ta=Ta, RH=RH)
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def get_function(variable, with_params=True):

    CALCS_DICT = {
        'es': calculate_es,
        'e': calculate_e,
        'AH': calculate_AH_from_RH,
        'Td': calculate_dew_point,
        'molar_density': calculate_molar_density,
        'CO2': calculate_CO2_mole_fraction,
        'CO2_IRGA': calculate_CO2_mole_fraction,
        'RH': calculate_RH_from_AH,
        'CO2c': calculate_CO2_density,
        'ustar': calculate_ustar_from_tau_rho,
        'VPD': calculate_VPD
        }

    func = CALCS_DICT[variable]
    if not with_params:
        return func
    return func, inspect.signature(func).parameters
#------------------------------------------------------------------------------

###############################################################################
### END QUANTITY CALCULATION FUNCTIONS ###
###############################################################################



###############################################################################
### BEGIN DATA FILTERING FUNCTIONS ###
###############################################################################

#------------------------------------------------------------------------------
def filter_range(series, max_val, min_val):

    if isinstance(max_val, (int, float)) and isinstance(min_val, (int, float)):
        return series.where((series <= max_val) & (series >= min_val), np.nan)
    if isinstance(max_val, (int, float)):
        return series.where(series <= max_val, np.nan)
    if isinstance(min_val, (int, float)):
        return series.where(series >= min_val, np.nan)
    return series
#------------------------------------------------------------------------------

###############################################################################
### END DATA FILTERING FUNCTIONS ###
###############################################################################

###############################################################################
### BEGIN VARIABLE RENAMING FUNCTIONS ###
###############################################################################

#------------------------------------------------------------------------------
def convert_soil_vars(variable):

    funcs_dict = {'cm': _convert_cm_2_m, 'm': _convert_m_2_cm}
    units_list = ['cm', 'm']

    elems = variable.split('_')
    quant = elems[0]
    loc = elems[1]
    other = elems[2:]

    current_units = None
    for these_units in units_list:
        loc_elems = loc.split(these_units)
        if not loc_elems[0] == loc:
            current_units = these_units
            break
    if current_units is None:
        raise KeyError('Could not detect units for conversion!')

    units_list.remove(current_units)
    new_units = units_list[0]
    func = funcs_dict[current_units]
    new_loc = func(loc_elems.pop(0)) + new_units
    if len(loc_elems) == 1:
        new_loc += loc_elems[0]

    return '_'.join([quant, new_loc] + other)
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def _convert_cm_2_m(num_str):

    try:
        interm = int(num_str)
    except ValueError:
        if '.' in num_str:
            interm = float(num_str)
        if '-' in num_str:
            interm = sum([int(num) for num in num_str.split('-')]) / 2
    interm = round(interm / 100, 3)
    if interm == int(interm):
        interm = int(interm)
    return str(interm).rstrip('0')
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def _convert_m_2_cm(num_str):

    return str(int(float(num_str) * 100))
#------------------------------------------------------------------------------

###############################################################################
### END VARIABLE RENAMING FUNCTIONS ###
###############################################################################