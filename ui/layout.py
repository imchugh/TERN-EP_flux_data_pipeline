#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Apr 23 11:50:26 2026

@author: imchugh
"""

from nicegui import ui
from ui.state import state
# from ui.layout_editor import render_editor
from ui.events import set_render_callback #, trigger_render
from ui.handlers import select_var, update_field


def build_sidebar():
    ui.label("Variables").classes("text-lg")

    for key in state["config_data"]["variables"]:
        ui.button(
            key,
            on_click=lambda k=key: select_var(k)
        )
        
def render_editor():
    
    state["editor_container"].clear()
    state["error_box"].clear()

    key = state["selected_var"]
    if key is None:
        return

    var_data = state["config_data"]["variables"][key]

    with state["editor_container"]:
        ui.label(f"Editing: {key}")

        ui.select(
            ["average", "standard_deviation"],
            value=var_data.get("statistic_type"),
            on_change=lambda e, k=key: update_field(k, "statistic_type", e.value),
        )

        ui.input(
            value=var_data.get("height", ""),
            on_change=lambda e, k=key: update_field(k, "height", e.value),
        )
        
set_render_callback(render_editor)        