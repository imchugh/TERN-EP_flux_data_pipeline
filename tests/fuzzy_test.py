#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Jun 17 06:21:46 2026

@author: imchugh
"""



# from services.metadata.variable_registry import build_variable_registry
from services.metadata.site_registry import SiteRegistry
from services.metadata.file_group_builder import build_file_groups
from services.metadata import instrument_registry

def get_variable_registry(site):

    from services.metadata.variable_registry import build_variable_registry
    cfg = SiteRegistry().get_runtime_config(site=site)
    grps = build_file_groups(runtime_cfg=cfg)
    return build_variable_registry(runtime_cfg=cfg, file_groups=grps)

# def get_variable_names(var_reg):
    
#     return {var: attrs.instrument for var, attrs in var_reg.items()}

def validate_instrument_names(site):
    
    print(f'Running site {site}...')
    instrument_registry.clear_cache()
    var_reg = get_variable_registry(site=site)
    for var, attrs in var_reg.items():
        inst_rep = attrs.instrument
        if isinstance(inst_rep, dict):
            instrument = list(inst_rep.values())
        elif isinstance(inst_rep, str):
            instrument = [inst_rep]
            
        for this_inst in instrument:
            if not instrument_registry.is_valid_instrument(name=this_inst):
                print(
                    f'Error at site {site}: instrument "{instrument}" is invalid for variable {var}'
                    )
    
def get_all_instrument_names():

    instruments = set()
    site_reg = SiteRegistry()
    for site in site_reg.names():
        print (site)
        var_reg = get_variable_registry(site=site)
        for var, attrs in var_reg.items():
            inst_rep = attrs.instrument
            if isinstance(inst_rep, dict):
                instrument = list(inst_rep.values())
            elif isinstance(inst_rep, str):
                instrument = [inst_rep]
            for this_inst in instrument:
                instruments.add(this_inst)
    
    return sorted(instruments)

def get_instrument_categories(instruments: list):
    
    rslt = {}
    voc = instrument_registry.get_instrument_vocab()
    for instrument in instruments:
        for rec in voc:
            if rec.get('label') == instrument:            
                rslt[instrument] = rec.get('broader_chain_label')
                break
    return rslt
    
                    
                    
        
        
        