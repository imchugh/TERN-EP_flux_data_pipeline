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

from domain.constants import CO2_MOL_MASS, H2O_MOL_MASS, K

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

@register_conversion("CO2c", "CO2c_IRGA")
def convert_CO2_density(data, from_units='mmol/m^3'):

    if from_units == 'mmol/m^3':
        return data * CO2_MOL_MASS
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

@register_conversion('Sig_IRGA', 'SigCO2_IRGA', 'SigH2O_IRGA')
def convert_signal_strength(data, from_units='frac'):

    if from_units == 'frac':
        return data * 100
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

@register_conversion('Diag_IRGA', 'Diag_SONIC')
def convert_diagnostic(data, n_samples, from_units='valid_count'):

    if from_units == 'valid_count':
        return n_samples - data
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

@register_conversion('AH', 'AH_IRGA')
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

@register_conversion('Ta', 'Tv_SONIC', 'Tbody_RAD')
def convert_temperature(data, from_units='K'):

    if from_units == 'K':
        return data - K
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def get_unit_conversion(quantity):
    return CONVERSION_REGISTRY.get(quantity)
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
