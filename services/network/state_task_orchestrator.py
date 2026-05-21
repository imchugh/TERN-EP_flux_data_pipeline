#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed May 20 20:04:10 2026

@author: imchugh
"""

# Orchestration helpers
from services.metadata.site_registry import SiteRegistry, yml_loader
from services.metadata.variable_metadata_service import load_runtime_config

# Tasks
from services.network.data_monitor import analyse_missing_data

SITE_REGISTRY = SiteRegistry(
    metadata_loader=yml_loader, 
    runtime_config_loader=load_runtime_config
    )

def run_site_task(site):
    
    context = SITE_REGISTRY.get_context(site=site)
    return analyse_missing_data(
        data_cfg=context.runtime_config, 
        site_cfg=context.metadata
        )

def run_task_for_all_sites(task):
    
    result = {}
    for site in SITE_REGISTRY.names():

        result[site] = run_site_task(site=site)
        
    return {'missing_data_analysis': result}
    
    
