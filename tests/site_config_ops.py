#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue May  5 10:58:21 2026

@author: imchugh
"""

from copy import deepcopy

from services.metadata import instrument_registry

def rebuild_height(height: str):

    if not isinstance(height, str):
        return {'height': None}
    if len(height) == 0:
        return {'height': None}
    height_list = height.split('to')
    height_range = []
    output = {}
    for elem in height_list:
        elem = elem.replace('m', '')
        try:
            height_range.append(float(elem))
        except ValueError:
            breakpoint()
    if len(height_range) == 1:
        output['height'] = height_range[0]
    else:
        output['height'] = sum(height_range) / 2
        output['height_range'] = height_range              
    return output

def fix_height_declarations(var, var_attrs):
    
    new_attrs = {}
    new_height = rebuild_height(height=var_attrs['height'])
    if new_height['height'] is None:
        print (f'    Warning: height not valid for variable {var}!') 
    new_attrs['statistic_type'] = var_attrs['statistic_type']
    new_attrs['height'] = new_height['height']
    if 'height_range' in new_height:
        new_attrs['height_range'] = new_height['height_range']
    new_attrs['input_variables'] = var_attrs['input_variables']
    return new_attrs
            
def fix_all_height_declarations(cfg):
    
    # Rebuild variables
    new_vars = {}
    for variable, attrs in cfg['variables'].items():
        new_vars[variable] = fix_height_declarations(
            var=variable, var_attrs=attrs
            )
    
    # Rebuild complete config
    new_cfg = {}
    for attr_key, attr in cfg.items():
        if attr_key == 'variables':
            new_cfg['variables'] = new_vars
        else:
            new_cfg[attr_key] = attr
            
    return new_cfg

def fix_dimensionless(cfg):
    
    new_cfg = cfg.copy()
    for variable, attrs in new_cfg['variables'].items():
        for input_var, sub_attrs in attrs['input_variables'].items():
            if sub_attrs['units'] == '1':
                sub_attrs.update({'units': 'dimensionless'})
    return new_cfg

def add_flux_system(cfg):
    
    elem_order = ['site', 'file_formats', 'flux_system', 'variables']
    new_cfg = cfg.copy()
    new_cfg.update({'flux_system': 'TERNFlUX'})
    return {elem: new_cfg[elem] for elem in elem_order}
    
def add_flux_file(cfg):
    
    ID_VAR = 'Fh'
    elem_order = ['site', 'file_formats', 'flux_system', 'flux_file', 'variables']
    new_cfg = cfg.copy()
    file_name = list(cfg['variables'][ID_VAR]['input_variables'].values())[-1]['file']
    new_cfg.update({'flux_file': file_name})
    return {elem: new_cfg[elem] for elem in elem_order}

def add_compound_inst_dict(cfg):
    
    keys = ['sonic_anemometer', 'irga']
    # elem_order = ['site', 'file_formats', 'flux_system', 'variables']
    new_cfg = deepcopy(cfg)
    variables = new_cfg['variables']
    for variable, attrs in variables.items():
        if instrument_registry.is_compound_quantity(quantity=variable):
            entries = attrs['input_variables']
            for raw_name, these_attrs in entries.items():
                inst = these_attrs['instrument']
                inst.replace('[', ',')
                inst.replace(']', ',')
                elems = inst.split(',')
                if len(elems) > 2:
                    raise TypeError(f'Cant be more than two instruments! ({elems})')
                if len(elems) > 1:
                    inst = dict(zip(keys, elems))
                these_attrs['instrument'] = inst
    return new_cfg

                    
                    
                    
                    
                    
    
            
        
        
        
    

    