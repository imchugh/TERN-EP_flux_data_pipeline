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
    begin: Optional[str] = None
    end: Optional[str] = None
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
    
    # Mandatory attributes
    variable_name: str
    instrument: str
    height: str
    statistic_type: str
    quantity: str

    # Mandatory subclasses    
    raw_inputs: RawVariableMetadata
    canonical: CanonicalVariableMetadata
    
    # Optional attributes
    instrument_type: Optional[str] = None
    vertical_location: Optional[str] = None
    horizontal_location: Optional[str] = None
    replicate: Optional[str] = None
    diag_type: Optional[str] = None
# -----------------------------------------------------------------------------

###############################################################################
### END CLASSES ###
###############################################################################


###############################################################################
### BEGIN FUNCTIONS ###
###############################################################################

# -----------------------------------------------------------------------------

def build_variable_definition(
    var_name: str,
    raw_cfg: any,
    parsed_name_elems: dict,
    canonical_metadata: dict
    ) -> VariableDefinition:
    
    # breakpoint()
    
    # 1. Merge YAML + parsed name into RawVariableMetadata
    raw_inputs = []
    for raw_name, cfg in raw_cfg.input_variables.items():
        raw_inputs.append(
            RawVariableMetadata(
                raw_name = raw_name,
                raw_units = cfg.units,
                instrument = cfg.instrument,
                file = cfg.file,
                begin = cfg.begin,
                end = cfg.end,                
                )
            )
    
    # 2 Build canonical metadata object
    canonical_meta = CanonicalVariableMetadata(**canonical_metadata)

    # 3 Return immutable VariableDefinition
    return VariableDefinition(
        
        # Base properties
        variable_name = var_name,
        instrument = cfg.instrument,
        height = raw_cfg.height,
        statistic_type = raw_cfg.statistic_type,
        quantity = parsed_name_elems.quantity,

        # Required subclasses
        raw_inputs = tuple(raw_inputs),
        canonical = canonical_meta,
        
        # Optionals
        instrument_type = parsed_name_elems.instrument_type,
        diag_type = cfg.diag_type,
        vertical_location = parsed_name_elems.vertical_location,
        horizontal_location = parsed_name_elems.horizontal_location,
        replicate = parsed_name_elems.replicate,
        
        )
# -----------------------------------------------------------------------------

###############################################################################
### END FUNCTIONS ###
###############################################################################
