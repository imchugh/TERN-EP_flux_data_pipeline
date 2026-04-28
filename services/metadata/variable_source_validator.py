#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Mar  2 14:34:02 2026

@author: imchugh
Simple validation function to ensure that (in order):
    1) the file names specified in the site variable map exist in the directory 
    structure, and; 
    2) the variable names are found in the header of the specified file.
"""

###############################################################################
### BEGIN IMPORTS ###
###############################################################################

from dataclasses import dataclass
from pathlib import Path
from typing import Set

from services.domain.metadata.file_mapping_service import FileGroup
from services.domain.data.raw_data_loader import get_header_adapter

###############################################################################
### END IMPORTS ###
###############################################################################


###############################################################################
### BEGIN CLASSES ###
###############################################################################

@dataclass
class ValidationResult:
    group: str
    found: Set[str]
    missing: Set[str]

###############################################################################
### END CLASSES ###
###############################################################################


###############################################################################
### BEGIN FUNCTIONS ###
###############################################################################

def validate_file_group(group: FileGroup) -> ValidationResult:

    available: Set[str] = set()
    header_adapter = get_header_adapter(system_type=group.system_type)

    for file in group.all_files:
        header_vars = header_adapter.load(file)['variable']  # your existing logic
        available.update(header_vars)

    expected = group.variables
    missing = expected - available

    return ValidationResult(
        group=group.group,
        found=available & expected,
        missing=missing,
    )

# -----------------------------------------------------------------------------

def validate_raw_data_source(
    file_path: Path, variables: list, system_type: str, 
    raise_if_missing: bool=False
    ) -> None:
    """
    Validate raw data files exist and contain expected variables.
    """

    if not file_path.exists():
        raise FileNotFoundError(f"Expected file missing: {file_path}")

    header_adapter = get_header_adapter(system_type=system_type)
    header_line = set(header_adapter.load(file_path=file_path)['variable'])

    missing = [v for v in variables if v not in header_line]
    
    if len(missing) == 0:
        return missing

    if len(missing) != 0:
        if raise_if_missing:
            raise ValueError(f"{file_path} missing variables: {missing}")
    
    return missing
# -----------------------------------------------------------------------------
                
###############################################################################
### END FUNCTIONS ###
###############################################################################                