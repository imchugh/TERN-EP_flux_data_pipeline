#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Mar 26 13:10:37 2026

@author: imchugh
"""

from services.domain.data import raw_data_loader, concat_validator
from services.domain.metadata import metadata_config_service, file_mapping_service


def check_concat(site):
    
    # Get the metadata configurator
    cfg = metadata_config_service.load_runtime_config_by_site(site=site)
    
    # Get the list of files
    file_groups = file_mapping_service.build_file_groups(runtime_cfg=cfg)
    
    # Get CSI header adapter
    adapter = raw_data_loader.get_header_adapter('CSI')
    
    # Iterate over the file groups
    reports = {}
    for file, elements in file_groups.items():
               
        master = elements['master']

        print(f'Checking backups for master file {master.name}:')
        
        slaves = elements['slaves']
        
        if len(slaves) == 0:
            
            print ('No backups!')
            continue
               
        reports[master.name] = {}
        
        for slave in slaves:
            
            rslt = (
                {'backup': slave.name} |
                concat_validator.concat_reporter(
                    master_header=adapter(master),
                    slave_header=adapter(slave)
                    )
                )
            reports[master.name][slave.name] = rslt
                       
            if not rslt['overall']:
                
                print(f'    Backup file {slave.name} failed! Reason:')
                for var in [
                    'common_variables', 'unit_consistency', 'stat_consistency'
                    ]:
                    if not rslt[var]["passed"]:
                        
                        print(f'        Failed {var} check: {rslt[var]["failures"]}')
                
    return reports
