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
    """
    Register a task into SITE_TASKS or GLOBAL_TASKS by inspecting its
    signature: a lone 'site' parameter routes to SITE_TASKS, anything else
    (no params, or params not including 'site') routes to GLOBAL_TASKS.

    Raises TypeError instead of silently routing to GLOBAL_TASKS if 'site'
    is present alongside other parameters, since that combination can't be
    disambiguated by signature alone.
    """

    params = list(inspect.signature(func).parameters.keys())
    if params == ['site']:
        SITE_TASKS[func.__name__] = func
    elif 'site' in params:
        raise TypeError(
            f"{func.__name__!r} takes 'site' plus other parameters "
            f"{params!r} — only a lone 'site' parameter is supported for "
            "site-scoped tasks. Rename the parameter or restructure the "
            "task to disambiguate."
            )
    else:
        GLOBAL_TASKS[func.__name__] = func
    return func

###############################################################################
### END TASK DECORATOR DEFINITION ###
###############################################################################