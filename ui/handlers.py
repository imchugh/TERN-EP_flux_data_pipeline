#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Apr 23 11:49:39 2026

@author: imchugh
"""

from ui.state import state
from ui.events import trigger_render


def select_var(key):
    state["selected_var"] = key
    render_editor()


def update_field(var_key, field, value):
    state["config_data"]["variables"][var_key][field] = value
    render_editor()


def save_config(write_func):
    write_func(state["config_data"])