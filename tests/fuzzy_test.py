#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Jun 17 06:21:46 2026

@author: imchugh
"""



from services.metadata.variable_registry import build_variable_registry
from services.metadata.site_registry import SiteRegistry
from services.metadata.file_group_builder import build_file_groups
from services.metadata import instrument_registry

site_reg = SiteRegistry()

site = 'Calperum'

def get_variable_registry(site):
    
    cfg = site_reg.get_runtime_config(site=site)
    grps = build_file_groups(runtime_cfg=cfg)
    return build_variable_registry(runtime_cfg=cfg, file_groups=grps)

def get_variable_names(var_reg):
    
    return {var: attrs.instrument for var, attrs in var_reg.items()}

var_reg = get_variable_registry(site=site)
instruments = get_variable_names(var_reg=var_reg)
        