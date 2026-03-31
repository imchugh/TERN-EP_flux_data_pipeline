#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Mar 30 13:19:34 2026

@author: imchugh
"""

from infrastructure import paths

def get_local_site_list():
    
    return sorted(
        [
            x.name for x in (
                paths.get_local_resource_path(resource='raw_data')
                .parent
                .glob('*')
                )
            ]
        )

def check_site_exists(site_name: str) -> bool:
    
    return site_name in get_local_site_list()