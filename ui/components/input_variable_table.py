#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Apr 30 12:27:47 2026

@author: imchugh
"""

from nicegui import ui
from typing import Callable

# def create_input_variable_table(
#     variables,
#     selected_var,
#     get_file_variables: Callable,
#     FILE_FORMATS,
#     validate_ranges,
#     ):
    
#     input_var_table = ui.table(
#         columns=[
#             {"name": "file", "label": "File name", "field": "file"},
#             {"name": "name", "label": "Raw variable name", "field": "name"},
#             {"name": "instrument", "label": "Instrument", "field": "instrument"},
#             {"name": "units", "label": "Units", "field": "units"},
#             {"name": "begin", "label": "Start date", "field": "begin"},
#             {"name": "end", "label": "End date", "field": "end"},
#         ],
#         rows=[],
#         row_key="_key",
#     ).classes("w-full")

#     # -------------------------
#     # ROW BUILDER (local to component)
#     # -------------------------
#     def build_rows(data):
#         rows = []
#         for key, attrs in data.items():

#             file = attrs.get("file")

#             options = []
#             if file:
#                 file_format = FILE_FORMATS.get(file)
#                 if file_format:
#                     options = get_file_variables(file, file_format)

#             rows.append({
#                 "_key": key,
#                 "name": attrs.get("name", key),
#                 "_var_options": options,
#                 "instrument": attrs.get("instrument", ""),
#                 "units": attrs.get("units", ""),
#                 "file": file,
#                 "begin": str(attrs.get("begin", "")),
#                 "end": str(attrs.get("end", "")),
#             })
#         return rows

#     # -------------------------
#     # EDIT HANDLER
#     # -------------------------
#     def handle_table_edit(e):
#         row = e.args

#         var = selected_var.value
#         data = variables[var]["input_variables"]

#         key = row["_key"]
#         if key not in data:
#             return

#         def normalise_date(value):
#             return None if value in ("", None) else value

#         old_file = data[key].get("file")
#         new_file = row.get("file")

#         if new_file != old_file:
        
#             # update backend
#             data[key]["file"] = new_file
        
#             # Reset ALL dependent fields
#             data[key]["name"] = None
#             data[key]["instrument"] = None
#             data[key]["units"] = None
        
#             # Rebuild table and EXIT EARLY
#             def do_refresh():
#                 input_var_table.rows = build_rows(data)
#                 input_var_table.update()
        
#             ui.timer(0, do_refresh, once=True)
#             return
            
#         # normal updates
#         data[key]["instrument"] = row.get("instrument")
#         data[key]["units"] = row.get("units")
        
#         # 🔥 THIS IS THE MISSING PIECE
#         selected_name = row.get("name")
#         if selected_name is not None:
#             file = data[key].get("file")
#             if file:
#                 valid = get_file_variables(file, FILE_FORMATS[file])
#                 if selected_name in valid:
#                     data[key]["name"] = selected_name
#             else:
#                 data[key]["name"] = selected_name
        
#         data[key]["begin"] = normalise_date(row.get("begin"))
#         data[key]["end"] = normalise_date(row.get("end"))

#         try:
#             validate_ranges(data)
#         except ValueError as e:
#             ui.notify(str(e), color="red")

#         def do_refresh():
#             input_var_table.rows = build_rows(data)
#             input_var_table.update()
        
#         ui.timer(0, do_refresh, once=True)

#     input_var_table.on("edit", handle_table_edit)

def create_input_variable_table(get_rows, on_edit, file_list):

    input_var_table = ui.table(
        columns=[
            {"name": "file", "label": "File name", "field": "file"},
            {"name": "name", "label": "Raw variable name", "field": "name"},
            {"name": "instrument", "label": "Instrument", "field": "instrument"},
            {"name": "units", "label": "Units", "field": "units"},
            {"name": "begin", "label": "Start date", "field": "begin"},
            {"name": "end", "label": "End date", "field": "end"},
        ],
        rows=[],
        row_key="_key",
    ).classes("w-full")

    # 🔥 event bridge (component → main logic)
    def _handle(e):
        on_edit(e.args)

    input_var_table.on("edit", _handle)

    # -------------------------
    # SLOTS
    # -------------------------

    # input_var_table.add_slot(
    #     "body-cell-name", r'''
    #     <q-td :props="props">
    #       <q-select
    #         v-model="props.row.name"
    #         :options="props.row._var_options || []"
    #         dense
    #         borderless
    #         emit-value
    #         map-options
    #         placeholder="Select variable"
    #         :disable="!props.row.file"
    #         @update:model-value="$parent.$emit('edit', props.row)"
    #         class="w-full"
    #       />
    #     </q-td>
    #     '''
    #     )

    input_var_table.add_slot(
        "body-cell-name", r'''
        <q-td :props="props">
          <q-select
            v-model="props.row.name"
            :options="props.row._var_options || []"
            dense borderless emit-value map-options
            :disable="!props.row.file"
            @update:model-value="$parent.$emit('edit', props.row)"
          />
        </q-td>
        '''
    )
    
    # # FILE_LIST = list(FILE_FORMATS.keys())
    # input_var_table.add_slot(
    #     "body-cell-file", r'''
    #     <q-td :props="props">
    #       <q-select
    #         v-model="props.row.file"
    #         :options="''' + str(file_list) + r'''"
    #         dense
    #         borderless
    #         emit-value
    #         map-options
    #         @update:model-value="$parent.$emit('edit', props.row)"
    #       />
    #     </q-td>
    #     '''
    # )
    input_var_table.add_slot(
        "body-cell-file", r'''
        <q-td :props="props">
          <q-select
            v-model="props.row.file"
            :options="''' + str(file_list) + r'''"
            dense borderless emit-value map-options
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
                      v-model="props.row.end"
                      mask="YYYY-MM-DD HH:mm"
                    />
                    <q-time
                      v-model="props.row.end"
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

    # (keep your date slots as-is)

    # -------------------------
    # PUBLIC REFRESH
    # -------------------------
    def refresh():
        input_var_table.rows = get_rows()
        input_var_table.update()

    return input_var_table, refresh