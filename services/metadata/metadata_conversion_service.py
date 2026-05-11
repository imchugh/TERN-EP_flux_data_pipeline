#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon May 11 15:42:00 2026

@author: imchugh
"""

from domain.enums import StatisticType

STATISTIC_UNIT_TRANSFORMS = {
    StatisticType.VAR: {
        'g^2/m^6': 'g/m^3',
        'umol/mol': 'umol/mol',
        'mg^2/m^6': 'mg/m^3',
        'degC^2': 'degC',
        'm^2/s^2': 'm/s',
        'mmol^2/m^6': 'mmol/m^3',
        'mmol/mol': 'mmol/mol',
        'K^2': 'K'
        }
    }

def resolve_variance_units(
        units: str, from_variance: bool=True
        ) -> str:
    
    mapping = STATISTIC_UNIT_TRANSFORMS[StatisticType.VAR]
    if not from_variance:
        mapping = {value: key for key, value in mapping.items()}
    try:
        return mapping[units]
    except KeyError:
        raise ValueError(f"No unit transform defined for unit '{units}'")

# @dataclass(frozen=True)
# class VarianceTransformer:
#     variance_to_sd: Callable
#     sd_to_variance: Callable
    
# def get_variance_transformer():
#     return VarianceTransformer(
#         variance_to_sd=lambda units: (data ** 0.5),
#         apply_units=lambda units: VARIANCE_TO_SD_UNITS[units],
#         )