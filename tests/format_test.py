#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Jun 11 09:39:27 2026

@author: imchugh
"""

from services.data import raw_data_loader, toa5_writer

file_format = 'TOA5'
input_file = '/home/imchugh/Documents/Whroo_EC_TERNflux.dat'
output_file = '/home/imchugh/Documents/Whroo_EC_TERNflux_test.dat'

data = raw_data_loader.load_raw_data(
    file_path=input_file, file_format=file_format
    )

headers = raw_data_loader.load_raw_header(
    file_path=input_file, file_format=file_format
    )

info = headers.pop('info')
headers = list(headers.values())

toa5_writer.write_toa5(
    data=data, 
    headers=headers, 
    file_path=output_file,
    info=info
    )