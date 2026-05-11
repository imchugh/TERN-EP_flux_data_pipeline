#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon May 11 14:47:14 2026

@author: imchugh
"""

from domain.data_models.metadata_classes import CanonicalQuantityMetadata
from services import config_loader
from services.metadata.canonical_quantity_registry import CanonicalQuantityRegistry

def build_canonical_quantity_registry():
    
    validated_quantities = config_loader.load_config_file_from_name(
        name='canonical_quantities'
        )
    
    transition_dict = {
        quantity: CanonicalQuantityMetadata(**quantity_dict) 
        for quantity, quantity_dict in validated_quantities.items()
        }
    
    return CanonicalQuantityRegistry(quantity_definitions=transition_dict)