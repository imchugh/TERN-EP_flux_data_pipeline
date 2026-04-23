#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Apr 23 11:51:37 2026

@author: imchugh
"""

from nicegui import ui

from ui.state import state
from services.domain.variable_metadata_validator import validate_L1_config_structure
from ui.layout import build_sidebar
from ui.layout import render_editor


FILE = "/opt/TERN_EP/site_configs/new_exp/AliceSpringsMulga.yml"


def main():

    state["config_data"] = validate_L1_config_structure(FILE)

    with ui.row().classes("w-full"):

        with ui.column().classes("w-1/4"):
            build_sidebar()

        with ui.column().classes("w-3/4"):
            ui.label("Editor")

            state["editor_container"] = ui.column()
            state["error_box"] = ui.column().classes("text-red")

    with ui.row():
        ui.button("Validate All")
        ui.button("Save")

    ui.run()


if __name__ in {"__main__", "__mp_main__"}:
    main()