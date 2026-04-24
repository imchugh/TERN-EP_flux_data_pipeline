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

# attr_container = ui.column()

input_var_table = (
    ui.table(
        columns=[
            {"name": "name", "label": "Input Variable", "field": "name"},
            {"name": "instrument", "label": "Instrument", "field": "instrument"},
            {"name": "begin", "label": "Begin", "field": "begin"},
            {"name": "end", "label": "End", "field": "end"},
            ],
        rows=[],
        row_key="name",
        )
    .classes("w-full")
    )

input_var_table.add_slot(
    "body-cell", r'''
    <q-td :props="props">
      <q-input
        v-model="props.row[props.col.name]"
        dense
        borderless
        @blur="$parent.$emit('edit', props.row)"
      />
    </q-td>
    '''
    )

# -------------------------
# LEVEL 1: variable → fields
# -------------------------
def update_fields():
    var = selected_var.value

    selected_input_var.options = []
    selected_input_var.value = None
    selected_input_var.update()

    # attr_container.clear()

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

    if not var or not field:
        value_input.value = ""
        value_input.update()
        input_var_table.rows = []
        input_var_table.update()
        return

    value = variables[var][field]

    # NEW table handling
    if field == "input_variables" and isinstance(value, dict):
        value_input.value = ""
        value_input.update()

        update_input_var()
        return

    # scalar field
    if not isinstance(value, dict):
        value_input.value = str(value)
        value_input.update()

        input_var_table.rows = []
        input_var_table.update()

# -------------------------
# LEVEL 3: input_variable → attributes
# -------------------------
def update_input_var():
    
    var = selected_var.value
    field = selected_field.value

    if not var or field != "input_variables":
        input_var_table.rows = []
        input_var_table.update()
        return

    data = variables[var][field]

    rows = []
    for name, attrs in data.items():
        rows.append({
            "name": name,
            "instrument": attrs.get("instrument", ""),
            "begin": str(attrs.get("begin", "")),
            "end": str(attrs.get("end", "")),
        })

    input_var_table.rows = rows
    input_var_table.update()

# -------------------------
# WRITE BACK HANDLERS (scalar fields)
# -------------------------
def write_back(e):
    
    var = selected_var.value
    field = selected_field.value

    if not var or not field:
        return

    variables[var][field] = value_input.value

def handle_table_edit(e):
    
    row = e.args

    var = selected_var.value
    data = variables[var]["input_variables"]

    name = row["name"]

    if name not in data:
        return

    data[name]["instrument"] = row.get("instrument")
    data[name]["begin"] = row.get("begin")
    data[name]["end"] = row.get("end")

# -------------------------
# EVENTS
# -------------------------
selected_var.on('update:model-value', lambda e: update_fields())
selected_field.on('update:model-value', lambda e: update_field())
selected_input_var.on('update:model-value', lambda e: update_input_var())
value_input.on('blur', write_back)
input_var_table.on("edit", handle_table_edit)

# --- INITIALISE UI STATE ---
update_fields()

def main():
    ui.run()

if __name__ in {"__main__", "__mp_main__"}:
    main()