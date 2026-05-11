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
###############################################################################
### BEGIN IMPORTS ###
###############################################################################

from nicegui import ui

# -----------------------------------------------------------------------------

from domain.enums import StatisticType, FileType
from infrastructure import paths, file_io
from services.metadata.file_mapping_service import get_variables_from_file
from services.metadata.variable_syntax_parser import NameParser
from services import config_loader
from ui.components.component_config import (
    create_input_variable_table, create_file_formats_editor
    )

###############################################################################
### END IMPORTS ###
###############################################################################


###############################################################################
### BEGIN INITS ###
###############################################################################

EXCLUDE_VARS = ['TIMESTAMP', 'date', 'time']
IMMUTABLE_FIELDS = ['site']
CANONICAL_VARS = config_loader.load_config_file_from_name(
    'canonical_quantities'
    )
name_parser = NameParser()

file = '/opt/TERN_EP/site_configs/operational/CowBay.yml'

cfg = config_loader.load_config_file(file=file)

variables = cfg["variables"]

file_type_options = [e.name for e in FileType]

BASE_PATH = paths.get_local_stream_path(
    resource='raw_data', stream='flux_slow', site=cfg['site']
    )

###############################################################################
### END INITS ###
###############################################################################


# -----------------------------------------------------------------------------
# def get_input_units():
    
#     metadata = config_loader.load_config_file_from_name('canonical_variables')
#     return {key: cfg.get('valid_input_units') for key, cfg in metadata.items()}

# INPUT_UNITS = get_input_units()
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def get_file_formats(cfg: dict) -> dict[str, str]:
    """
    Get a dict with available files (key) and their formats (value).

    Args:
        cfg: the loaded config file dict.

    Raises:
        ValueError: raised if defaults missing or file format not supported.

    Returns:
        files: files with formats.

    """
    
    # Get format-related dicts
    file_formats = cfg.get('file_formats', {})
    default = file_formats.get('default')
    overrides = file_formats.get('overrides', {}) or {}

    # Check for default
    if default is None:
        raise ValueError("file_formats.default is required")

    # Validate default
    if default not in file_type_options:
        raise ValueError(f"Invalid default file type: {default}")

    # Get files from disk
    files_on_disk = file_io.list_available_files(
        dir_path=BASE_PATH, pattern=['*.dat', 'Cumberland*.txt']
        )
    files = {f.stem: default for f in files_on_disk}

    # Apply overrides safely
    for fname, ftype in overrides.items():

        if ftype not in file_type_options:
            raise ValueError(f"Invalid override type for {fname}: {ftype}")

        # Warn if override not in discovered files -> raise?
        if fname not in files:
            print(f"Warning: override '{fname}' not found in file list")

        files[fname] = ftype

    return files

# Assign formats and file lists
FILE_FORMATS = get_file_formats(cfg=cfg)
FILE_LIST = list(FILE_FORMATS.keys())
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

# Lazy load and cache variables available in header of passed file.
variable_cache = {}
def get_file_variables(file_group: str, file_format: str) -> list[str]:
    """
    Get the list of variables in the headers of the passed file group 
    (master file and any backups).

    Args:
        file_group: file name without extension.
        file_format: the format of the file group to load.

    Returns:
        variable list from file header.

    """
    
    # Only load if not in the cache; otherwise return
    if file_group in variable_cache:
        return variable_cache[file_group]
    
    # Get format
    ftype = FileType[file_format]
    
    # Get the variable list and filter out (time-based) variables for exclusion.
    vars_list = [
        variable for variable in get_variables_from_file(
            file_path=BASE_PATH / f'{file_group}.{ftype.extension}', 
            system_type=ftype.name
            )
        if variable not in EXCLUDE_VARS
        ]
    
    # Assign variables to cache
    variable_cache[file_group] = vars_list
    return vars_list
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def validate_ranges(data):
    """Parse date fields"""
    
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
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def build_rows(data):
    
    def normalize_units(value):
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            return [value]   # single string case
        return []
    
    rows = []
    for key, attrs in data.items():

        file = attrs.get("file")

        options = []
        if file:
            file_format = FILE_FORMATS.get(file)
            if file_format:
                options = get_file_variables(file, file_format)

        quantity = extract_quantity_safe(selected_var.value)

        valid_units = []
        if quantity and quantity in CANONICAL_VARS:
            valid_units = [
                {"label": u, "value": u}
                for u in normalize_units(
                    value=CANONICAL_VARS[quantity]["valid_input_units"]
                    )
                ]

        rows.append({
            "_key": key,
            "name": attrs.get("name", key),
            "_var_options": options,
            "instrument": attrs.get("instrument", ""),
            "units": attrs.get("units", ""),
            "file": file,
            "begin": str(attrs.get("begin", "")),
            "end": str(attrs.get("end", "")),
            "_valid_units": valid_units,
        })
        
    return rows
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def get_rows():
    var = selected_var.value
    if not var:
        return []
    return build_rows(variables[var]["input_variables"])
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def handle_table_edit(row):

    var = selected_var.value
    data = variables[var]["input_variables"]

    key = row["_key"]
    if key not in data:
        return

    # Force python NoneType
    def normalise_date(value):
        return None if value in ("", None) else value

    old_file = data[key].get("file")
    new_file = row.get("file")

    # If file changes, early exit
    if new_file != old_file:

        data[key]["file"] = new_file
        data[key]["name"] = None
        data[key]["instrument"] = None
        data[key]["units"] = None

        refresh_table()
        return

    # normal updates
    data[key]["instrument"] = row.get("instrument")
    data[key]["units"] = row.get("units")

    selected_name = row.get("name")
        
    if selected_name is not None:
    
        file = data[key].get("file")
    
        if file:
            valid = get_file_variables(file, FILE_FORMATS[file])
            if selected_name not in valid:
                refresh_table()
                return
       
        data[key]["name"] = selected_name
    
           
        # no unit-option logic here anymore
        # only validate selected unit exists if you want
        
        selected_units = row.get("units")
        if selected_units is not None:
            data[key]["units"] = selected_units

    # Handle dates
    # Ensure they are are not empty strings
    data[key]["begin"] = normalise_date(row.get("begin"))
    data[key]["end"] = normalise_date(row.get("end"))

    # Do validity checks on dates
    try:
        validate_ranges(data)
    except ValueError as e:
        ui.notify(str(e), color="red")

    refresh_table()
    
def extract_quantity_safe(name: str | None) -> str | None:
    if not name:
        return None
    try:
        return name_parser.parse_variable_name(name).quantity
    except Exception:
        # fallback for partial / invalid names
        return name.split("_")[0] if "_" in name else name
    
# -----------------------------------------------------------------------------

def get_file_formats_state():
    ff = cfg.get("file_formats", {})

    return {
        "default": ff.get("default"),
        "overrides": ff.get("overrides", {}) or {}
    }
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def handle_file_formats_change(event):
    ff = cfg.setdefault("file_formats", {})

    if event["type"] == "default":
        ff["default"] = event["value"]

    elif event["type"] == "override_type":
        overrides = ff.setdefault("overrides", {})
        overrides[event["file"]] = event["value"]

    elif event["type"] == "override_file":
        overrides = ff.setdefault("overrides", {})

        old = event["old_file"]
        new = event["new_file"]

        if old in overrides:
            overrides[new] = overrides.pop(old)

    elif event["type"] == "delete_override":
        overrides = ff.setdefault("overrides", {})
        overrides.pop(event["file"], None)
# -----------------------------------------------------------------------------

# -------------------------
# TOP LEVEL RENDER (unchanged)
# -------------------------
def render_yaml(key, value, level=0):

    base_indent = level * 20
    child_indent = (level + 1) * 20

    if key in IMMUTABLE_FIELDS:
        with ui.column().style(f"margin-left: {child_indent}px"):
            ui.input(
                label=key,
                value=str(value),
            ).classes("w-full").props("readonly")
        return

    # --- TOP LEVEL HEADER ---
    if level == 0:
        ui.label(key).classes("text-h6")

    # --- VARIABLES (special case) ---
    if key == "variables" and isinstance(value, dict):
        with ui.column().style(f"margin-left: {child_indent}px"):

            # global selected_var
            selected_var = ui.select(
                options=sorted(value.keys()),
                label="Selected variable",
                value=sorted(value.keys())[0] if value else None,
            ).classes("w-64")

            # global var_container
            var_container = ui.column().classes("w-full")

        return selected_var, var_container
    
    if key == "file_formats" and isinstance(value, dict):
        
        with ui.column().style("margin-left: 20px"):

            ff_component, ff_refresh = create_file_formats_editor(
                get_file_formats_state=get_file_formats_state,
                on_change=handle_file_formats_change,
                file_list=FILE_LIST,
                file_type_options=file_type_options,
                )
        
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



# selected_var = None
# var_container = None

for k, v in cfg.items():
    result = render_yaml(k, v, level=0)

    if isinstance(result, tuple):
        selected_var, var_container = result

# Build the input_variables table
input_var_table, refresh_table = create_input_variable_table(
    get_rows=get_rows,
    on_edit=handle_table_edit,
    file_list=FILE_LIST,
    )

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

        with ui.column().style("margin-left: 40px"):
            refresh_table()


# events
selected_var.on('update:model-value', lambda e: render_variable())

# init
render_variable()


def main():
    ui.run()

if __name__ in {"__main__", "__mp_main__"}:
    main()
    