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

variables = cfg["variables"]

# -------------------------
# TOP LEVEL RENDER (unchanged)
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
# BUILD TABLE ROWS
# -------------------------
def build_rows(data):
    rows = []
    for name, attrs in data.items():
        rows.append({
            "name": name,
            "instrument": attrs.get("instrument", ""),
            "units": attrs.get("units", ""),
            "file": attrs.get("file", ""),
            "begin": str(attrs.get("begin", "")),
            "end": str(attrs.get("end", "")),
        })
    return rows


# -------------------------
# WRITE BACK TABLE EDITS
# -------------------------
def handle_table_edit(e):
    row = e.args

    var = selected_var.value
    data = variables[var]["input_variables"]

    name = row["name"]
    if name not in data:
        return

    data[name]["instrument"] = row.get("instrument")
    data[name]["units"] = row.get("units")
    data[name]["file"] = row.get("file")
    data[name]["begin"] = row.get("begin")
    data[name]["end"] = row.get("end")


# -------------------------
# RENDER VARIABLE (core)
# -------------------------
def render_variable():
    var_container.clear()

    var = selected_var.value
    if not var:
        return

    data = variables[var]

    with var_container:

        # Variable name
        ui.label(var).classes("text-h6")

        # statistic_type
        with ui.row().classes("items-center").style("margin-left: 20px"):
            ui.label("statistic_type").classes("w-40")
            stat_input = ui.input(
                value=str(data.get("statistic_type", ""))
            ).classes("w-64")

            stat_input.on(
                "blur",
                lambda e: data.update({"statistic_type": stat_input.value})
            )

        # height
        with ui.row().classes("items-center").style("margin-left: 20px"):
            ui.label("height").classes("w-40")
            height_input = ui.input(
                value=str(data.get("height", ""))
            ).classes("w-64")

            height_input.on(
                "blur",
                lambda e: data.update({"height": height_input.value})
            )

        # input_variables label
        with ui.row().style("margin-left: 20px"):
            ui.label("input_variables").classes("text-subtitle2")

        # table (indented further)
        with ui.column().style("margin-left: 40px"):

            input_var_table.rows = build_rows(
                data.get("input_variables", {})
            )
            input_var_table.update()


# -------------------------
# UI
# -------------------------
ui.label(Path(file).name).classes("text-h5")

render_top_level(cfg)

with ui.row().classes("w-full gap-4"):

    selected_var = ui.select(
        options=sorted(variables.keys()),
        label="Variable",
        value=sorted(variables.keys())[0] if variables else None,
    ).classes("w-64")

# container for YAML-like rendering
var_container = ui.column().classes("w-full")

# table (single instance)
input_var_table = (
    ui.table(
        columns=[
            {"name": "name", "label": "Input Variable", "field": "name", "align": "left"},
            {"name": "instrument", "label": "Instrument", "field": "instrument", "align": "left"},
            {"name": "units", "label": "Units", "field": "units", "align": "left"},
            {"name": "file", "label": "File", "field": "file", "align": "left"},
            {"name": "begin", "label": "Begin", "field": "begin", "align": "left"},
            {"name": "end", "label": "End", "field": "end", "align": "left"},
            ],
        rows=[],
        row_key="name",
    )
    .classes("w-full")
)

# editable cells
input_var_table.add_slot(
    "body-cell", r'''
    <q-td :props="props">
      <q-input
        v-model="props.row[props.col.name]"
        dense
        borderless
        class="w-full"
        input-class="text-left"
        @blur="$parent.$emit('edit', props.row)"
      />
    </q-td>
    '''
    )

input_var_table.on("edit", handle_table_edit)

# events
selected_var.on('update:model-value', lambda e: render_variable())

# init
render_variable()


def main():
    ui.run()


if __name__ in {"__main__", "__mp_main__"}:
    main()
    