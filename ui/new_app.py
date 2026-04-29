#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Apr 23 12:07:29 2026

@author: imchugh
"""

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Apr 23 12:07:29 2026

@author: imchugh
"""

from nicegui import ui
from pathlib import Path
import yaml

from domain.enums import StatisticType, FileType
from infrastructure import paths, file_io

file = '/opt/TERN_EP/site_configs/new_exp/CowBay.yml'


# FILE_LIST = [
#     file.stem for file in 
#         file_io.list_available_files(
#         dir_path=paths.get_local_resource_path(
#             resource='raw_data', stream='flux_slow', site=Path(file).stem
#             ), 
#         pattern='*.dat'
#         )
#     ]

file_type_options = [e.name for e in FileType]

def get_file_list():
    
    return [
        file.stem for file in 
            file_io.list_available_files(
            dir_path=paths.get_local_resource_path(
                resource='raw_data', stream='flux_slow', site=Path(file).stem
                ), 
            pattern=['*.dat', 'Cumberland*.txt']
            )
        ]

FILE_LIST = get_file_list()



def get_variable_list(file_group, file_format):
    
    base_path = paths.get_local_stream_path(
        resource='raw_data', stream='flux_slow'
        )
    for file in FILE_LIST:
        ext = FileType[file_format].extension
        master = f'{file_group}.{ext}'
        file_io.get_backup_files()

# --- load config ---
with open(Path(file), "r") as f:
    cfg = yaml.safe_load(f)

variables = cfg["variables"]

# -------------------------
# TOP LEVEL RENDER (unchanged)
# -------------------------
def render_yaml(key, value, level=0):

    base_indent = level * 20
    child_indent = (level + 1) * 20

    # --- TOP LEVEL HEADER ---
    if level == 0:
        ui.label(key).classes("text-h6")

    # --- VARIABLES (special case) ---
    if key == "variables" and isinstance(value, dict):
        with ui.column().style(f"margin-left: {child_indent}px"):

            global selected_var
            selected_var = ui.select(
                options=sorted(value.keys()),
                label="Selected variable",
                value=sorted(value.keys())[0] if value else None,
            ).classes("w-64")

            global var_container
            var_container = ui.column().classes("w-full")

        return
    
    # if key == "file_formats" and isinstance(value, dict):

    #     with ui.column().style(f"margin-left: {20}px"):

    #         # --- DEFAULT DROPDOWN ---
    #         with ui.row().classes("items-center"):
    #             ui.label("default").classes("w-40")
    
    #             current = value.get("default")
    
    #             default_select = ui.select(
    #                 options=file_type_options,
    #                 value=current if current in file_type_options else None,
    #             ).classes("w-64")
    
    #             def update_default(e):
    #                 value["default"] = default_select.value
    
    #             default_select.on("update:model-value", update_default)
    
    #         # --- render any OTHER keys normally ---
    #         for k, v in value.items():
    #             if k == "default":
    #                 continue
    #             render_yaml(k, v, level + 1)

    if key == "file_formats" and isinstance(value, dict):
    
        with ui.column().style(f"margin-left: {20}px"):
    
            # -------------------------
            # DEFAULT
            # -------------------------
            with ui.row().classes("items-center"):
                ui.label("default").classes("w-40")
    
                current = value.get("default")
    
                default_select = ui.select(
                    options=file_type_options,
                    value=current if current in file_type_options else None,
                ).classes("w-64")
    
                def update_default(e):
                    value["default"] = default_select.value
    
                default_select.on("update:model-value", update_default)
    
            # -------------------------
            # OVERRIDES HEADER
            # -------------------------
    
            # ensure structure exists
            if "overrides" not in value or value["overrides"] is None:
                value["overrides"] = {}
    
            # -------------------------
            # OVERRIDES TABLE
            # -------------------------
            with ui.row().classes("items-start"):
                
                # LEFT: label (anchor point)
                ui.label("overrides").classes("w-40")
                
                override_rows = [
                    {"file": k, "type": v, "_original_file": k}
                    for k, v in value.get("overrides", {}).items()
                    ]
                
                # RIGHT: table (always aligned)
                with ui.column().classes("flex-grow"):
                    
                    overrides_table = ui.table(
                        columns=[
                            {"name": "file", "label": "File", "field": "file"},
                            {"name": "type", "label": "Type", "field": "type"},
                        ],
                        rows=override_rows,
                        row_key="file",
                    ).classes("w-full")
    
                # editable file name
                overrides_table.add_slot(
                    "body-cell-file", r'''
                    <q-td :props="props">
                      <q-select
                        v-model="props.row.file"
                        :options="''' + str(FILE_LIST) + r'''"
                        dense
                        borderless
                        emit-value
                        map-options
                        @update:model-value="$parent.$emit('edit', props.row, 'file')"
                      />
                    </q-td>
                    '''
                    )
    
                # dropdown for type
                overrides_table.add_slot(
                    "body-cell-type", r'''
                    <q-td :props="props">
                      <q-select
                        v-model="props.row.type"
                        :options="''' + str(file_type_options) + r'''"
                        dense
                        borderless
                        emit-value
                        map-options
                        @update:model-value="$parent.$emit('edit', props.row, 'type')"
                      />
                    </q-td>
                    '''
                )
    
                def handle_override_edit(e):
                    row, field = e.args
                    overrides = value["overrides"]
                
                    original = row["_original_file"]
                    new_file = row["file"]
                    new_type = row["type"]
                
                    # rename key if needed
                    if original != new_file:
                        overrides[new_file] = overrides.pop(original)
                        row["_original_file"] = new_file
                
                    # always update type
                    overrides[new_file] = new_type
    
                overrides_table.on("edit", handle_override_edit)
    
        return


    # --- DICT ---
    if isinstance(value, dict):
    
        for k, v in value.items():
    
            if level == 0:
                # top-level children: just recurse
                render_yaml(k, v, level + 1)
    
            else:
                # render label at THIS level
                with ui.column().style(f"margin-left: {level * 20}px"):
                    ui.label(k).classes("text-subtitle2")
    
                # recurse WITHOUT adding extra visual indent
                render_yaml(k, v, level + 1)

    # --- SCALAR ---
    else:
        with ui.column().style(f"margin-left: {child_indent}px"):
            ui.input(
                label=None if level == 0 else key,   # ← fixes duplicate "site"
                value="" if value is None else str(value)
            ).classes("w-full")

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

    def normalise_date(value):
        return None if value in ("", None) else value

    # --- write edits ---
    data[name]["instrument"] = row.get("instrument")
    data[name]["units"] = row.get("units")
    data[name]["file"] = row.get("file")
    data[name]["begin"] = normalise_date(row.get("begin"))
    data[name]["end"] = normalise_date(row.get("end"))

    # --- validate AFTER update ---
    try:
        validate_ranges(data)
    except ValueError as e:
        ui.notify(str(e), color="red")

def validate_ranges(data):
    # extract and sort by begin (None = earliest)
    def sort_key(item):
        begin = item[1].get("begin")
        return begin or "0000-00-00"

    items = sorted(data.items(), key=sort_key)

    prev_end = None

    for i, (name, attrs) in enumerate(items):
        begin = attrs.get("begin")
        end = attrs.get("end")

        # first can have begin = None
        if i == 0:
            pass
        else:
            if begin is None:
                raise ValueError(f"{name}: begin cannot be None unless first segment")

        # last can have end = None
        if i == len(items) - 1:
            pass
        else:
            if end is None:
                raise ValueError(f"{name}: end cannot be None unless last segment")

        # check overlap
        if prev_end and begin and begin < prev_end:
            raise ValueError(f"{name}: overlaps previous segment")

        if end:
            prev_end = end

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
       
        # statistic_type
        with ui.row().classes("items-center").style("margin-left: 20px"):
            ui.label("statistic_type").classes("w-40")
        
            options = [e.value for e in StatisticType]
            current = data.get("statistic_type")
        
            stat_select = ui.select(
                options=options,
                value=current if current in options else None,
                ).classes("w-64")
        
            stat_select.on(
                "update:model-value",
                lambda e: data.update({"statistic_type": stat_select.value})
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

for k, v in cfg.items():
    render_yaml(k, v, level=0)

# table (single instance)

# -------------------------
# Input variable table
# -------------------------
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

input_var_table.add_slot(
    "body-cell-file", r'''
    <q-td :props="props">
      <q-select
        v-model="props.row.file"
        :options="''' + str(FILE_LIST) + r'''"
        dense
        borderless
        emit-value
        map-options
        @update:model-value="$parent.$emit('edit', props.row)"
      />
    </q-td>
    '''
)

input_var_table.add_slot(
    "body-cell-begin", r'''
    <q-td :props="props">
      <q-input
        v-model="props.row.begin"
        dense
        borderless
        placeholder="YYYY-MM-DD HH:mm"
        class="w-full"
      >
        <template v-slot:append>
          <q-icon name="event" class="cursor-pointer">
            <q-popup-proxy cover transition-show="scale" transition-hide="scale">
              <div>
                <q-date
                  v-model="props.row.begin"
                  mask="YYYY-MM-DD HH:mm"
                />
                <q-time
                  v-model="props.row.begin"
                  mask="YYYY-MM-DD HH:mm"
                  format24h
                  @update:model-value="$parent.$emit('edit', props.row)"
                />
              </div>
            </q-popup-proxy>
          </q-icon>
        </template>
      </q-input>
    </q-td>
    '''
)

input_var_table.add_slot(
    "body-cell-end", r'''
    <q-td :props="props">
      <q-input
        v-model="props.row.end"
        dense
        borderless
        placeholder="YYYY-MM-DD HH:mm"
        class="w-full"
      >
        <template v-slot:append>
          <q-icon name="event" class="cursor-pointer">
            <q-popup-proxy cover transition-show="scale" transition-hide="scale">
              <div>
                <q-date
                  v-model="props.row.begin"
                  mask="YYYY-MM-DD HH:mm"
                />
                <q-time
                  v-model="props.row.begin"
                  mask="YYYY-MM-DD HH:mm"
                  format24h
                  @update:model-value="$parent.$emit('edit', props.row)"
                />
              </div>
            </q-popup-proxy>
          </q-icon>
        </template>
      </q-input>
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
    