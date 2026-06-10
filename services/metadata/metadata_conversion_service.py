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
        units: str, to_stdev: bool=True
        ) -> str:

    mapping = STATISTIC_UNIT_TRANSFORMS[StatisticType.VAR]
    if not to_stdev:
        mapping = {value: key for key, value in mapping.items()}
    try:
        return mapping[units]
    except KeyError:
        raise ValueError(f"No unit transform defined for unit '{units}'")

