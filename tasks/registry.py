#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Sep 11 15:49:52 2025

@author: imchugh
"""

import inspect

###############################################################################
### BEGIN TASK DECORATOR DEFINITION ###
###############################################################################

SITE_TASKS = {}
GLOBAL_TASKS = {}

def register(func):

    params = list(inspect.signature(func).parameters.keys())
    if params == ['site']:
        SITE_TASKS[func.__name__] = func
    else:
        GLOBAL_TASKS[func.__name__] = func
    return func

###############################################################################
### END TASK DECORATOR DEFINITION ###
###############################################################################