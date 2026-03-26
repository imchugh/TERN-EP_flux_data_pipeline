#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Mar 11 11:40:22 2026

@author: imchugh
"""

###############################################################################
### BEGIN INITS ###
###############################################################################

CO2_MOL_MASS = 44
H2O_MOL_MASS = 18
K = 273.15
R = 8.3143

CONVERSION_REGISTRY = {}

# -----------------------------------------------------------------------------

def register_conversion(*quantities):
    def decorator(func):
        for q in quantities:
            CONVERSION_REGISTRY[q] = func
        return func
    return decorator
# -----------------------------------------------------------------------------

###############################################################################
### END INITS ###
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

def get_converter(quantity):
    return CONVERSION_REGISTRY.get(quantity)
# -----------------------------------------------------------------------------

###############################################################################
### END FUNCTIONS ###
###############################################################################
