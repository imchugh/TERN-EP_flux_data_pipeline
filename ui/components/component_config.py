#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Apr 30 12:27:47 2026

@author: imchugh
"""

from nicegui import ui
from typing import Callable

def create_input_variable_table(
    get_rows: Callable, on_edit: Callable, file_list: list[str]
    ):

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

    # Event bridge (component -> main logic)
    def _handle(e):
        on_edit(e.args)

    input_var_table.on("edit", _handle)

    # -------------------------
    # SLOTS
    # -------------------------

    # Configure variable name slot
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
    
    # Configure file name slot
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
    
    # Configure instrument slot
    input_var_table.add_slot(
        "body-cell-instrument", r'''
        <q-td :props="props">
          <template v-if="props.row._instrument_is_compound">
            <div class="column" style="gap:2px">
              <div class="row items-center" style="gap:6px">
                <span class="text-caption text-grey-6" style="width:36px">sonic:</span>
                <span class="text-body2">{{ props.row._sonic_name }}</span>
              </div>
              <div class="row items-center" style="gap:6px">
                <span class="text-caption text-grey-6" style="width:36px">irga:</span>
                <span class="text-body2">{{ props.row._irga_name }}</span>
              </div>
            </div>
          </template>
          <template v-else>
            <span class="text-body2">{{ props.row.instrument }}</span>
          </template>
        </q-td>
        '''
    )

    # Configure unit slot
    input_var_table.add_slot(
        "body-cell-units", r'''
        <q-td :props="props">
          <q-select
            v-model="props.row.units"
            :options="props.row._valid_units"
            option-label="label"
            option-value="value"
            dense
            borderless
            emit-value
            map-options
            @update:model-value="$parent.$emit('edit', props.row)"
          />
        </q-td>
        '''
        )
    
    # Configure start date slot
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

    # Configure end date slot    
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

    # -------------------------
    # PUBLIC REFRESH
    # -------------------------
    def refresh():
        input_var_table.rows = get_rows()
        input_var_table.update()

    return input_var_table, refresh



def create_file_formats_editor(
    get_file_formats_state,
    on_change,
    file_list,
    file_type_options,
    ):

    container = ui.column()

    def build_rows(overrides: dict):
        return [
            {
                "file": k,
                "type": v,
                "_original_file": k,
            }
            for k, v in overrides.items()
        ]

    def refresh():
        container.clear()

        state = get_file_formats_state()
        default = state["default"]
        overrides = state["overrides"]

        with container:

            # -------------------------
            # DEFAULT
            # -------------------------
            with ui.row().classes("items-center"):
                ui.label("default").classes("w-40")

                default_select = ui.select(
                    options=file_type_options,
                    value=default,
                ).classes("w-64")

                default_select.on(
                    "update:model-value",
                    lambda e: on_change({
                        "type": "default",
                        "value": default_select.value
                    })
                )

            # -------------------------
            # OVERRIDES
            # -------------------------
            with ui.row().classes("items-start"):

                ui.label("overrides").classes("w-40")

                rows = build_rows(overrides)

                with ui.column().classes("flex-grow"):

                    table = ui.table(
                        columns=[
                            {"name": "file", "label": "File", "field": "file"},
                            {"name": "type", "label": "Type", "field": "type"},
                        ],
                        rows=rows,
                        row_key="_original_file",
                    ).classes("w-full")

                    # file selector
                    table.add_slot(
                        "body-cell-file", r'''
                        <q-td :props="props">
                          <q-select
                            v-model="props.row.file"
                            :options="''' + str(file_list) + r'''"
                            dense borderless emit-value map-options
                            @update:model-value="$parent.$emit('edit', {row: props.row, field: 'file'})"
                          />
                        </q-td>
                        '''
                    )

                    # type selector
                    table.add_slot(
                        "body-cell-type", r'''
                        <q-td :props="props">
                          <q-select
                            v-model="props.row.type"
                            :options="''' + str(file_type_options) + r'''"
                            dense borderless emit-value map-options
                            @update:model-value="$parent.$emit('edit', {row: props.row, field: 'type'})"
                          />
                        </q-td>
                        '''
                    )

                    def handle_edit(e):
                        payload = e.args
                        row = payload["row"]
                        field = payload["field"]

                        if field == "file":
                            on_change({
                                "type": "override_file",
                                "old_file": row["_original_file"],
                                "new_file": row["file"],
                            })

                        elif field == "type":
                            on_change({
                                "type": "override_type",
                                "file": row["file"],
                                "value": row["type"],
                            })

                        refresh()

                    table.on("edit", handle_edit)

    refresh()
    return container, refresh
