#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Mar  5 12:12:51 2026

@author: imchugh
"""

###############################################################################
### BEGIN IMPORTS ###
###############################################################################

from dataclasses import dataclass
from typing import Optional

###############################################################################
### BEGIN IMPORTS ###
###############################################################################


###############################################################################
### BEGIN CLASSES ###
###############################################################################

# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class RawVariableMetadata:
    
    raw_name: str
    raw_units: str
    file: str
    instrument: str
    height: str
    statistic_type: str
    quantity: str

    diag_type: Optional[str] = None
    begin: Optional[str] = None
    end: Optional[str] = None
    instrument_type: Optional[str] = None
    vertical_location: Optional[str] = None
    horizontal_location: Optional[str] = None
    replicate: Optional[str] = None
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class CanonicalVariableMetadata:
    long_name: str
    standard_name: str
    standard_units: str
    plausible_min: Optional[float] = None
    plausible_max: Optional[float] = None
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class VariableDefinition:
    site_variable_name: str
    raw: RawVariableMetadata
    canonical: CanonicalVariableMetadata
# -----------------------------------------------------------------------------

###############################################################################
### END CLASSES ###
###############################################################################


###############################################################################
### BEGIN FUNCTIONS ###
###############################################################################

# -----------------------------------------------------------------------------

def build_variable_definition(
    site_var_name: str,
    raw_cfg: any,
    parsed_name_elems: dict,
    canonical_metadata: dict
    ) -> VariableDefinition:
    
    # 1. Merge YAML + parsed name into RawVariableMetadata
    raw_inputs = []
    for raw_name, cfg in raw_cfg.input_variables.items():
        raw_inputs.append(
            RawVariableMetadata(
                raw_name = raw_name,
                raw_units = cfg.units,
                instrument = cfg.instrument,
                height = raw_cfg.height,
                statistic_type = raw_cfg.statistic_type,
                file = cfg.file,
                diag_type = cfg.diag_type,
                begin = cfg.begin,
                end = cfg.end,
                quantity = parsed_name_elems.get("quantity"),
                instrument_type = parsed_name_elems.get("instrument_type"),
                vertical_location = parsed_name_elems.get("vertical_location"),
                horizontal_location = parsed_name_elems.get("horizontal_location"),
                replicate = parsed_name_elems.get("replicate"),
                )
            )
    
    # 2 Build canonical metadata object
    canonical_meta = CanonicalVariableMetadata(**canonical_metadata)

    # 3 Return immutable VariableDefinition
    return VariableDefinition(
        site_variable_name = site_var_name,
        raw = tuple(raw_inputs),
        canonical = canonical_meta
        )
# -----------------------------------------------------------------------------

###############################################################################
### END FUNCTIONS ###
###############################################################################
