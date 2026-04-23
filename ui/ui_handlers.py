#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Apr 23 10:06:32 2026

@author: imchugh
"""

from nicegui import ui
import yaml
from pydantic import ValidationError

from infrastructure.file_io import read_yml, write_yml_file
from services.domain.metadata import variable_metadata_validator as vmv
from services.domain.metadata.variable_metadata_validator import VariableConfig, SiteConfig

file = '/opt/TERN_EP/site_configs/new_exp/AliceSpringsMulga.yml'

# -----------------------------
# Load + validate initial config
# -----------------------------
# with open('config.yml') as f:
#     raw_config = yaml.safe_load(f)

try:
    model = vmv.validate_L1_config_structure(file=file)
    config_data = model.model_dump()
except ValidationError as e:
    raise RuntimeError(f'Invalid starting config:\n{e}')

state = {
    "config_data": config_data,
    "selected_var": None,
    "editor_container": None,
    "error_box": None,
    "validation_errors": []
    }
    

# -----------------------------
# App state
# -----------------------------
selected_var = {'key': None}
validation_errors = []


# -----------------------------
# Helpers
# -----------------------------
def validate_variable(var_key):
    try:
        VariableConfig(**config_data['variables'][var_key])
        return True, None
    except ValidationError as e:
        return False, e.errors()


def validate_all():
    try:
        SiteConfig(**state["config_data"])

        state["validation_errors"] = []
        ui.notify("Config is valid", color="green")

        # clear UI error box safely
        if state["error_box"] is not None:
            state["error_box"].clear()

        return True

    except ValidationError as e:
        state["validation_errors"] = e.errors()

        ui.notify("Validation failed", color="red")

        if state["error_box"] is not None:
            state["error_box"].clear()

            with state["error_box"]:
                for err in state["validation_errors"]:
                    ui.label(str(err))

        return False


def save_config():
    if not validate_all():
        return
    with open('config.yml', 'w') as f:
        yaml.safe_dump(config_data, f)
    ui.notify('Saved successfully', color='green')


# # -----------------------------
# # UI Layout
# # -----------------------------
# with ui.row().classes('w-full'):

#     # -------- Sidebar --------
#     with ui.column().classes('w-1/4'):
#         ui.label('Variables').classes('text-lg')

#         def select_var(key):
#             print(f"Clicked: {key}")
#             selected_var['key'] = key
#             render_editor()

#         for key in config_data['variables']:
#             ui.button(key, on_click=lambda k=key: select_var(k))

#     # -------- Editor Panel --------
#     with ui.column().classes('w-3/4'):
#         ui.label('Editor').classes('text-lg')
#         editor_container = ui.column()
#         error_box = ui.column().classes('text-red')


def render_editor():
    container = state["editor_container"]
    error_box = state["error_box"]

    container.clear()
    error_box.clear()

    key = state["selected_var"]
    if key is None:
        return

    var_data = state["config_data"]["variables"][key]

    with container:
        ui.label(f"Editing: {key}").classes("text-xl")

        ui.select(
            ["average", "standard_deviation"],
            value=var_data.get("statistic_type"),
            label="Statistic Type",
            on_change=lambda e, k=key: update_field(k, "statistic_type", e.value),
        )

        ui.input(
            label="Height",
            value=var_data.get("height", ""),
            on_change=lambda e, k=key: update_field(k, "height", e.value),
        )

        render_input_variables(key)

        valid, errors = validate_variable(key)
        if not valid:
            with error_box:
                for err in errors:
                    ui.label(str(err))

# -----------------------------
# Editor renderer
# -----------------------------


def render_input_variables(var_key):
    var_data = state["config_data"]["variables"][var_key]
    inputs = var_data.setdefault("input_variables", {})

    def add_input():
        name = f"new_input_{len(inputs)}"
        inputs[name] = {
            "instrument": "",
            "units": "",
            "file": "",
        }
        render_editor()

    def update_input(input_name, field, value):
        inputs[input_name][field] = value

    def remove_input(input_name):
        inputs.pop(input_name, None)
        render_editor()

    def rename_input(old, new):
        if not new or new == old:
            return
        if new in inputs:
            ui.notify("Name already exists", color="red")
            return
        inputs[new] = inputs.pop(old)
        render_editor()

    ui.row().classes("items-center justify-between w-full")
    ui.label("Input Variables").classes("text-lg")
    ui.button("Add", on_click=add_input)

    for input_name, data in list(inputs.items()):

        with ui.expansion(input_name).classes("w-full"):

            ui.input(
                label="Input Name",
                value=input_name,
                on_change=lambda e, o=input_name: rename_input(o, e.value),
            )

            ui.input(
                label="Instrument",
                value=data.get("instrument", ""),
                on_change=lambda e, n=input_name: update_input(n, "instrument", e.value),
            )

            ui.input(
                label="Units",
                value=data.get("units", ""),
                on_change=lambda e, n=input_name: update_input(n, "units", e.value),
            )

            ui.input(
                label="File",
                value=data.get("file", ""),
                on_change=lambda e, n=input_name: update_input(n, "file", e.value),
            )

            ui.button(
                "Remove",
                color="red",
                on_click=lambda _, n=input_name: remove_input(n),
            )

def update_field(var_key, field, value):
    state["config_data"]["variables"][var_key][field] = value
    render_editor()


def build_sidebar():
    ui.label("Variables").classes("text-lg")

    for key in state["config_data"]["variables"]:
        ui.button(
            key,
            on_click=lambda k=key: select_var(k),
        )

def select_var(key):
    state["selected_var"] = key
    render_editor()

# -----------------------------
# Bottom controls
# -----------------------------
def main():

    with ui.row().classes("w-full"):

        # Sidebar
        with ui.column().classes("w-1/4"):
            build_sidebar()

        # Editor
        with ui.column().classes("w-3/4"):
            ui.label("Editor").classes("text-lg")

            state["editor_container"] = ui.column()
            state["error_box"] = ui.column().classes("text-red")

    with ui.row():
        ui.button("Validate All", on_click=validate_all)
        ui.button("Save", on_click=save_config)

    ui.run()


if __name__ in {"__main__", "__mp_main__"}:
    main()

if __name__ in {"__main__", "__mp_main__"}:
    main()