#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Apr 20 14:20:38 2026

@author: imchugh
"""

import pathlib

from infrastructure import file_io

INPUT_PATH = '/opt/TERN_EP/site_configs/new_exp'
OUTPUT_PATH = '/opt/TERN_EP/site_configs/experimental'
SUFFIXES = ['_DL', '_EP', '_EF']


files = sorted(pathlib.Path(INPUT_PATH).glob('*.yml'))

for file in files:
    
    rslt = file_io.read_yml(file_path=file)
    
    print(rslt['site'])
    
    if rslt['site'] == 'CumberlandPlain':
        
        continue
       
    new_rslt = {}
    
    new_rslt['site'] = rslt['site']

    # Handle format changes    
    fmts = rslt.get('file_formats', None)
    if fmts is None:
        new_rslt['file_formats'] = {'default': 'CSI'}
    else:
        new_rslt['file_formats'] = rslt['file_formats']
        
    # Handle variable name changes
    var_map = {}
    for variable in rslt['variables'].keys():
        var_map[variable] = variable
        for suffix in SUFFIXES:
            if variable.endswith(suffix):
                var_map[variable] = variable.replace(suffix, '')
                break
    new_variables = {value: rslt['variables'][key] for key, value in var_map.items()}
    new_rslt['variables'] = new_variables
   
    file_io.write_yml_file(
        file_path=pathlib.Path(OUTPUT_PATH) / file.name,
        data = new_rslt
        )
    
    # Output
    
    
    
        
        