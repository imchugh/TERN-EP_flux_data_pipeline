#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Mar 18 15:16:37 2026

@author: imchugh
"""

import pathlib

from infrastructure import file_io

base_in_path = pathlib.Path('/store/Config_files/Sites/Operational')
base_out_path = pathlib.Path('/store/Config_files/Sites/Test')

def convert_file(in_path):
    
    site = pathlib.Path(in_path).stem
    print (site)
    data = {
        'site': site,
        'system_type': 'CSI',
        'variables': file_io.read_yml(file_path=in_path)
        }
    out_path = base_out_path / f'{site}.yml'
    file_io.write_yml_file(out_path, data=data)

def convert_all_files():
    
    for file in base_in_path.glob('*.yml'):
        
        convert_file(in_path=file)
        
def convert_new(in_path, out_path):
    
    in_path = pathlib.Path(in_path)
    out_path = pathlib.Path(out_path)   
    site = pathlib.Path(in_path).stem
    old_variables = file_io.read_yml(file_path=in_path)
    new_variables = {}
    for var, attrs in old_variables.items():
        new_variables[var] = build_new_dict(site=site, attrs=attrs)
    data = {
        'site': site,
        'system_type': 'CSI',
        'variables': new_variables
        }
    file_io.write_yml_file(out_path, data=data)

def build_new_dict(site, attrs):
    
    new_dict = attrs.copy()
    name = new_dict.pop('name')
    sub_attrs = {}
    sub_attrs['instrument'] = new_dict.pop('instrument')
    if 'file' in new_dict:
        sub_attrs['file'] = new_dict.pop('file')
    else:
        sub_attrs['file'] = f'{site}_{new_dict.pop("logger")}_{new_dict.pop("table")}.dat'
    new_dict['input_variables'] = {name: sub_attrs}
    return new_dict

def convert_all_files_new():
    
    base_out_path = pathlib.Path('/opt/TERN_EP/site_configs/new_exp')
    
    for file in base_in_path.glob('*.yml'):
    
        convert_new(in_path=file, out_path=base_out_path / file.name)