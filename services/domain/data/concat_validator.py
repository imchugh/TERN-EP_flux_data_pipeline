#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Mar 26 11:39:04 2026

@author: imchugh
"""

from typing import Dict, List

UNIT_ALIASES = {
    'degC': ['C'],
    'n': ['arb', 'samples'],
    'arb': ['n', 'samples'],
    'samples': ['arb', 'n'],
    'm^3/m^3': ['fraction']
    }

def concat_reporter(
    master_header: Dict[str, List[str]], 
    slave_header: Dict[str, List[str]]
    ) -> Dict:
    """
    Compare master and slave headers for safe column-wise concatenation.

    Assumes 'variables' and 'units' are always present.
    Checks 'sampling' only if present in both headers.
    
    Returns a detailed report with pass/fail/skipped info.
    """
    
    report = {}

    # --- 1) Variables ---
    master_vars = master_header["variable"]
    slave_vars = slave_header["variable"]
    common_vars = set(master_vars) & set(slave_vars)
    report["common_variables"] = {
        "passed": bool(common_vars),
        "common": sorted(common_vars),
        "master_only": set(master_vars) - set(slave_vars),
        "slave_only": set(slave_vars) - set(master_vars)
        }

    # --- 2) Units ---
    unit_failures = {}
    for var in common_vars:
        m_units = master_header["units"][master_vars.index(var)]
        s_units = slave_header["units"][slave_vars.index(var)]
        if m_units != s_units:
            try:
                aliases = UNIT_ALIASES[m_units]
            except KeyError:
                aliases = []
            if s_units in aliases:
                continue
            unit_failures[var] = {
                'master': m_units,
                'slave': s_units
                }
    report["unit_consistency"] = {
        "passed": len(unit_failures) == 0,
        "failures": unit_failures
    }

    # --- 3) Sampling/statistical type (optional) ---
    stat_failures = {}
    if "sampling" in master_header and "sampling" in slave_header:
        for var in common_vars:
            m_stat = master_header["sampling"][master_vars.index(var)]
            s_stat = slave_header["sampling"][slave_vars.index(var)]
            if m_stat != s_stat:
                stat_failures[var] = {
                    'master': m_stat,
                    'slave': s_stat
                    }
        report["stat_consistency"] = {
            "passed": len(stat_failures) == 0,
            "failures": stat_failures,
            "skipped": False
            }
    else:
        report["stat_consistency"] = {
            "passed": True,
            "failures": [],
            "skipped": True
            }

    # --- Overall ---
    report["overall"] = all([
        report["common_variables"]["passed"],
        report["unit_consistency"]["passed"],
        report["stat_consistency"]["passed"]
        ])

    return report