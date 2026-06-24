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
            {"name": "file", "label": "File name", "field": "file", "align": "left"},
            {"name": "name", "label": "Raw variable name", "field": "name", "align": "left"},
            {"name": "instrument", "label": "Instrument", "field": "instrument", "align": "left"},
            {"name": "units", "label": "Units", "field": "units", "align": "left"},
            {"name": "begin", "label": "Start date", "field": "begin", "align": "left"},
            {"name": "end", "label": "End date", "field": "end", "align": "left"},
        ],
        rows=[],
        row_key="_key",
    ).classes("w-full").props("separator=cell")

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
              <div v-for="(part, i) in props.row._compound_parts" :key="i"
                   class="row items-center" style="gap:6px">
                <span class="text-caption text-grey-6" style="width:130px">{{ part.alias }}:</span>
                <q-select
                  v-model="part.name"
                  :options="part.options || []"
                  dense borderless clearable emit-value map-options
                  style="min-width:200px"
                  @update:model-value="$parent.$emit('edit', props.row)"
                />
              </div>
            </div>
          </template>
          <template v-else>
            <q-select
              v-model="props.row.instrument"
              :options="props.row._instrument_options || []"
              dense borderless clearable emit-value map-options
              style="min-width:200px"
              @update:model-value="$parent.$emit('edit', props.row)"
            />
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
    file_type_options,
):
    container = ui.column()

    def refresh():
        container.clear()
        formats = get_file_formats_state()

        rows = [{"file": k, "type": v} for k, v in sorted(formats.items())]

        with container:
            table = ui.table(
                columns=[
                    {"name": "file", "label": "File", "field": "file", "align": "left"},
                    {"name": "type", "label": "Format", "field": "type", "align": "left"},
                ],
                rows=rows,
                row_key="file",
            ).classes("w-full")

            table.add_slot(
                "body-cell-type", r'''
                <q-td :props="props">
                  <q-select
                    v-model="props.row.type"
                    :options="''' + str(file_type_options) + r'''"
                    dense borderless emit-value map-options
                    @update:model-value="$parent.$emit('edit', props.row)"
                  />
                </q-td>
                '''
            )

            def handle_edit(e):
                row = e.args
                on_change({"file": row["file"], "value": row["type"]})

            table.on("edit", handle_edit)

    refresh()
    return container, refresh
