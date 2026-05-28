#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Mar 11 11:40:22 2026

@author: imchugh
"""

###############################################################################
### BEGIN IMPORTS ###
###############################################################################

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from domain.constants import CO2_MOL_MASS, H2O_MOL_MASS, K, R

###############################################################################
### END IMPORTS ###
###############################################################################


###############################################################################
### BEGIN INITS ###
###############################################################################

VARIANCE_TO_SD_UNITS = {
    'g^2/m^6': 'g/m^3',
    'umol/mol': 'umol/mol',
    'mg^2/m^6': 'mg/m^3',
    'degC^2': 'degC',
    'm^2/s^2': 'm/s',
    'mmol^2/m^6': 'mmol/m^3',
    'mmol/mol': 'mmol/mol',
    'K^2': 'K'
    }

CONVERSION_REGISTRY = {}
TRANSFORMATION_REGISTRY = {}
CALCULATION_REGISTRY = {}

# -----------------------------------------------------------------------------

def register_conversion(*quantities):
    def decorator(func):
        for q in quantities:
            CONVERSION_REGISTRY[q] = func
        return func
    return decorator
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def register_transformation(*names):
    def decorator(obj):
        for name in names:
            TRANSFORMATION_REGISTRY[name] = obj
        return obj
    return decorator
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def register_calculation(*quantities):
    def decorator(func):
        for q in quantities:
            CALCULATION_REGISTRY[q] = func
        return func
    return decorator
# -----------------------------------------------------------------------------

###############################################################################
### END INITS ###
###############################################################################


###############################################################################
### BEGIN CLASSES ###
###############################################################################

# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class Transformation:
    apply_data: Callable
    apply_units: Callable
# -----------------------------------------------------------------------------

###############################################################################
### END CLASSES ###
###############################################################################


###############################################################################
### BEGIN FUNCTIONS ###
###############################################################################

# -----------------------------------------------------------------------------

@register_conversion("Fco2")
def convert_CO2_flux(data, from_units='mg/m^2/s'):

    if from_units == 'mg/m^2/s':
        return data * 1000 / CO2_MOL_MASS
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

@register_conversion("CO2c")
def convert_CO2_density(data, from_units='mmol/m^3'):

    if from_units == 'mmol/m^3':
        return data * CO2_MOL_MASS
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

@register_conversion('Sig', 'SigCO2', 'SigH2O', 'CO2Sig', 'H2OSig')
def convert_signal_strength(data, from_units='frac'):

    if from_units == 'frac':
        return data * 100
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

@register_conversion('Diag')
def convert_diagnostic(data, n_samples, from_units='invalid_count'):
    """Convert diagnostic counts to valid_count form.

    Diag variables can be stored as either valid_count or invalid_count.
    The pipeline standardises to valid_count; invalid_count is converted
    by subtracting from the total number of samples in the period.

    Note: n_samples must be supplied by the caller; _apply_conversions
    does not yet pass this — wiring it up is a TODO.
    """

    if from_units == 'invalid_count':
        return n_samples - data
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

@register_conversion('AH')
def convert_H2O_density(data, from_units='mmol/m^3'):

    if from_units == 'mmol/m^3':
        return data * H2O_MOL_MASS / 10**3
    if from_units == 'kg/m^3':
        return data * 10**3
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

@register_conversion('Precip')
def convert_precipitation(data, from_units='pulse_0.2mm'):

    if from_units == 'pulse_0.2mm':
        return data * 0.2
    if from_units == 'pulse_0.5mm':
        return data * 0.5
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

@register_conversion('ps')
def convert_pressure(data, from_units='Pa'):

    if from_units == 'Pa':
        return data / 10**3
    if from_units == 'hPa':
        return data / 10
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

@register_conversion('RH')
def convert_RH(data, from_units='frac'):

    if from_units == 'frac':
        return data * 100
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

@register_conversion('Sws')
def convert_Sws(data, from_units='percent'):

    if from_units == 'percent':
        return data / 100
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

@register_conversion('Ta', 'Tv', 'Tbody')
def convert_temperature(data, from_units='K'):

    if from_units == 'K':
        return data - K
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def get_unit_conversion(quantity):
    return CONVERSION_REGISTRY.get(quantity)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def get_calculation(quantity):
    return CALCULATION_REGISTRY.get(quantity)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

@register_calculation('AH')
def calculate_AH_from_RH(Ta: pd.Series, RH: pd.Series, ps: pd.Series) -> pd.Series:
    """Derive absolute humidity (g/m³) from air temperature, RH, and pressure."""

    es = _calculate_es(Ta)
    e = es * RH / 100
    molar_density = ps * 1000 / ((Ta + K) * R)
    return e / ps * molar_density * H2O_MOL_MASS
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

@register_calculation('RH')
def calculate_RH_from_AH(AH: pd.Series, Ta: pd.Series, ps: pd.Series) -> pd.Series:
    """Derive relative humidity (%) from absolute humidity, air temperature, and pressure."""

    molar_density = ps * 1000 / ((Ta + K) * R)
    e = (AH / H2O_MOL_MASS) / molar_density * ps
    es = _calculate_es(Ta)
    return e / es * 100
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def _calculate_es(Ta: pd.Series) -> pd.Series:
    """Saturation vapour pressure (kPa) from Buck (1996)."""

    return 0.61121 * np.exp((18.678 - Ta / 234.5) * (Ta / (257.14 + Ta)))
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

@register_transformation('variance_to_stdev')
def variance_to_stdev():
    return Transformation(
        apply_data=lambda data: (data ** 0.5),
        apply_units=lambda units: VARIANCE_TO_SD_UNITS[units],
        )
# -----------------------------------------------------------------------------

# # -----------------------------------------------------------------------------
# @register_transformation('variance_data_to_stdev')
# def transform_variance_data_to_stdev(data):
    
#     return data**(1/2)
# # -----------------------------------------------------------------------------

# # -----------------------------------------------------------------------------
# @register_transformation('variance_units_to_stdev')
# def transform_variance_units_to_stdev(from_units):
    
#     return VARIANCE_TO_SD_UNITS[from_units]
# # -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def get_statistical_transformation(quantity):
    return TRANSFORMATION_REGISTRY.get(quantity)
# -----------------------------------------------------------------------------

###############################################################################
### END FUNCTIONS ###
###############################################################################
