#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Apr 23 12:07:29 2026

@author: imchugh
"""

from nicegui import ui
from pathlib import Path
import yaml

file = '/opt/TERN_EP/site_configs/new_exp/CowBay.yml'

# --- load config ---
with open(Path(file), "r") as f:
    cfg = yaml.safe_load(f)

variables = cfg["variables"]

# -------------------------
# INDENTATION HELPER
# -------------------------
def ind(level: int):
    return ui.column().style(f'margin-left: {level * 24}px')

# -------------------------
# TOP LEVEL RENDER
# -------------------------
def render_top_level(cfg):

    def render_node(key, value):

        if isinstance(value, dict):
            with ui.expansion(key, value=True).classes('w-full q-pl-none'):
                for k, v in value.items():
                    render_node(k, v)

        else:
            ui.input(label=key, value=str(value)).classes('w-full')

    for k, v in cfg.items():
        if k == "variables":
            continue

        render_node(k, v)
        
        
# -------------------------
# UI STATE
# -------------------------
ui.label(Path(file).name).classes("text-h5")

render_top_level(cfg)

with ind(0):
    
    sorted_vars = sorted(variables.keys())
    selected_var = ui.select(
        options=sorted_vars,
        label="Variable",
        value=sorted_vars[0] if sorted_vars else None,
        )
    
    # selected_var = ui.select(
    #     options=list(variables.keys()),
    #     label="Variable",
    # )

with ind(1):
    selected_field = ui.select(
        options=[],
        label="Field",
    )

with ind(2):
    selected_input_var = ui.select(
        options=[],
        label="Input Variable",
    )

with ind(1):
    value_input = ui.input(label="Value")

attr_container = ui.column()

# -------------------------
# LEVEL 1: variable → fields
# -------------------------
def update_fields():
    var = selected_var.value

    selected_input_var.options = []
    selected_input_var.value = None
    selected_input_var.update()

    attr_container.clear()

    if not var:
        selected_field.options = []
        selected_field.value = None
        selected_field.update()
        value_input.value = ""
        value_input.update()
        return

    fields = list(variables[var].keys())

    selected_field.options = fields

    default_field = "statistic_type" if "statistic_type" in fields else (fields[0] if fields else None)

    selected_field.value = default_field
    selected_field.update()

    if default_field:
        update_field()


# -------------------------
# LEVEL 2: field → value OR input_variables
# -------------------------
def update_field():
    var = selected_var.value
    field = selected_field.value

    selected_input_var.options = []
    selected_input_var.value = None
    selected_input_var.update()

    attr_container.clear()

    if not var or not field:
        value_input.value = ""
        value_input.update()
        return

    value = variables[var][field]

    # input_variables branch
    if field == "input_variables" and isinstance(value, dict):
        selected_input_var.options = list(value.keys())
        selected_input_var.update()

        value_input.value = ""
        value_input.update()
        return

    # scalar field
    if not isinstance(value, dict):
        value_input.value = str(value)
        value_input.update()


# -------------------------
# LEVEL 3: input_variable → attributes
# -------------------------
def update_input_var():
    var = selected_var.value
    field = selected_field.value
    input_var = selected_input_var.value

    attr_container.clear()

    if not var or field != "input_variables" or not input_var:
        return

    attrs = variables[var][field][input_var]

    with attr_container:
        with ind(3):
            for k, v in attrs.items():

                def commit(e, key=k):
                    variables[var][field][input_var][key] = widget.value

                widget = ui.input(
                    label=k,
                    value=str(v)
                )
                widget.on('blur', commit)


# -------------------------
# WRITE BACK (scalar fields)
# -------------------------
def write_back(e):
    var = selected_var.value
    field = selected_field.value

    if not var or not field:
        return

    variables[var][field] = value_input.value



# -------------------------
# EVENTS
# -------------------------
selected_var.on('update:model-value', lambda e: update_fields())
selected_field.on('update:model-value', lambda e: update_field())
selected_input_var.on('update:model-value', lambda e: update_input_var())
value_input.on('blur', write_back)

# --- INITIALISE UI STATE ---
update_fields()

def main():
    ui.run()

if __name__ in {"__main__", "__mp_main__"}:
    main()