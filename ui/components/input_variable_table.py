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

    # -------------------------
    # PUBLIC REFRESH
    # -------------------------
    def refresh():
        input_var_table.rows = get_rows()
        input_var_table.update()

    return input_var_table, refresh