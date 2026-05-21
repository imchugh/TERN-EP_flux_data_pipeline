#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Mar  5 12:12:51 2026

@author: imchugh
"""

###############################################################################
### BEGIN IMPORTS ###
###############################################################################

# from dataclasses import dataclass
from typing import Any

# -----------------------------------------------------------------------------

from domain.data_models import metadata_classes
from domain.enums import VariableType

###############################################################################
### END IMPORTS ###
###############################################################################


###############################################################################
### BEGIN FUNCTIONS ###
###############################################################################

# -----------------------------------------------------------------------------
def build_canonical_quantity_definition(
        canonical_metadata, 
        variable_type: VariableType=VariableType.CONTINUOUS
        ):
    
    qc_dummy = {
        'plausible_max': None,
        'plausible_min': None,
        'standard_units': 'dimensionless',
        'valid_input_units': ['dimensionless']
        }
    
    canonical_out = canonical_metadata.copy()
    
    if variable_type == 'quality_flag':
        
        long_name = canonical_out.get('long_name')
        if long_name is not None:
            canonical_out['long_name'] = f'{long_name} quality flag'
        standard_name = canonical_out.get('standard_name')
        if standard_name is not None:
            canonical_out['standard_name'] = f'{standard_name}_quality_flag'
            
        canonical_out.update(qc_dummy)
        
    return metadata_classes.CanonicalVariableMetadata(**canonical_out)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def build_variable_definition(
    var_name: str,
    raw_cfg: Any,
    parsed_name_elems: metadata_classes.ParsedVariableName,
    canonical_metadata: metadata_classes.CanonicalQuantityMetadata,
    ) -> metadata_classes.VariableDefinition:
        
    # 1. Merge YAML + parsed name into RawVariableMetadata
    raw_inputs = []
    for raw_name, cfg in raw_cfg.input_variables.items():
        raw_inputs.append(
            metadata_classes.RawVariableMetadata(
                raw_name = raw_name,
                raw_units = cfg.units,
                instrument = cfg.instrument,
                file = cfg.file,
                begin = cfg.begin,
                end = cfg.end,                
                )
            )
    
    # 3 Return immutable VariableDefinition
    return metadata_classes.VariableDefinition(
        
        # Base properties
        variable_name = var_name,
        instrument = cfg.instrument,
        height = raw_cfg.height,
        statistic_type = raw_cfg.statistic_type,
        variable_type = raw_cfg.variable_type,
        quantity = parsed_name_elems.quantity,

        # Required subclasses
        raw_inputs = tuple(raw_inputs),
        canonical = canonical_metadata,
        parsed_name_elems = parsed_name_elems,
        
        # Diagnostic type (worth moving to site-level?)
        diag_type = cfg.diag_type,
        
        )
# -----------------------------------------------------------------------------

###############################################################################
### END FUNCTIONS ###
###############################################################################
