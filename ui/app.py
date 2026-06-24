#!/usr/bin/env python3
"""
Site configuration editor.  Run from the repo root:
    conda run -n ep_cntl python -m ui.app
"""

from pathlib import Path
import yaml
from nicegui import ui

from domain.enums import StatisticType, FileType, FluxSystemType, VariableType
from infrastructure import paths, file_io
from infrastructure.file_io import read_yml
from services import config_loader
from services.metadata.file_group_builder import get_variables_from_file
from services.metadata.variable_name_parser import NameParser
from services.metadata.canonical_quantity_registry import build_canonical_quantity_registry
from services.metadata.site_config_schema import validate_all
from services.metadata.instrument_registry import (
    is_compound_quantity,
    list_instruments,
    list_instruments_for_quantity,
    get_quantity_components,
)
from ui.components.component_config import (
    create_input_variable_table,
    create_file_formats_editor,
)

# ── Constants ─────────────────────────────────────────────────────────────────

SITES_DIR = Path('/opt/TERN_EP/site_configs/operational')
SAVE_DIR = Path('/tmp/site_config_edits')
EXCLUDE_VARS = ['TIMESTAMP', 'date', 'time']

CANONICAL_VARS = config_loader.load_config_file_from_name('canonical_quantities')
CANONICAL_REGISTRY = build_canonical_quantity_registry()
FILE_TYPE_OPTIONS = [e.name for e in FileType]
FLUX_SYSTEM_OPTIONS = [e.value for e in FluxSystemType]
STATISTIC_TYPE_OPTIONS = [e.value for e in StatisticType]
VARIABLE_TYPE_OPTIONS = [e.value for e in VariableType]

name_parser = NameParser()

# ── App state ─────────────────────────────────────────────────────────────────

state = {
    'cfg': {},          # raw dict from YAML (mutated in place as user edits)
    'site': None,       # currently loaded site name
    'base_path': None,  # path to raw data dir for this site
    'file_formats': {}, # {file_stem: format_name}
    'file_list': [],    # sorted list of file stems available on disk
    'var_cache': {},    # lazy cache: {file_stem: [variable_names]}
    'selected_var': None,
}

# ── Data helpers ──────────────────────────────────────────────────────────────

def _site_names() -> list[str]:
    return sorted(p.stem for p in SITES_DIR.glob('*.yml'))


def _compute_file_formats(cfg: dict, base_path: Path) -> dict[str, str]:
    """Return {file_stem: format_name} for all files found on disk.

    Files present on disk but absent from the YAML file_formats dict default
    to CSI until the user explicitly assigns a format.
    """
    yaml_formats = cfg.get('file_formats', {}) or {}
    try:
        found = file_io.list_available_files(
            dir_path=base_path, pattern=['*.dat', 'Cumberland*.txt']
        )
    except Exception:
        found = []
    formats = {f.stem: yaml_formats.get(f.stem, FILE_TYPE_OPTIONS[0]) for f in found}
    # Include YAML-configured files even if not on disk (e.g. path not mounted)
    for stem, fmt in yaml_formats.items():
        if stem not in formats:
            formats[stem] = fmt
    return formats


def _get_file_vars(file_stem: str, fmt: str) -> list[str]:
    """Return variable names from a file header, with results cached."""
    cache = state['var_cache']
    if file_stem in cache:
        return cache[file_stem]
    ftype = FileType[fmt]
    file_path = state['base_path'] / f'{file_stem}.{ftype.extension}'
    try:
        names = [
            v for v in get_variables_from_file(file_path=file_path, system_type=ftype.name)
            if v not in EXCLUDE_VARS
        ]
    except Exception:
        names = []
    cache[file_stem] = names
    return names


def _extract_quantity(var_name: str | None) -> str | None:
    """Parse the base quantity from a canonical variable name (e.g. 'Fco2' from 'Fco2_Av')."""
    if not var_name:
        return None
    try:
        return name_parser.parse_variable_name(var_name).quantity
    except Exception:
        return var_name.split('_')[0] if '_' in var_name else var_name


def _long_name_for(var_name: str, var_data: dict) -> str:
    """Return the resolved long_name for var_name, accounting for variable_type and statistic_type.

    Falls back to base long_name if resolve_metadata raises (e.g. variance units
    not defined for some quantities — variance doesn't alter the long_name anyway).
    """
    quantity = _extract_quantity(var_name)
    if not quantity or not CANONICAL_REGISTRY.has_quantity(quantity):
        return ''
    vtype = VariableType(var_data.get('variable_type') or 'continuous')
    stat_str = var_data.get('statistic_type')
    stat = StatisticType(stat_str) if stat_str else None
    try:
        return CANONICAL_REGISTRY.resolve_metadata(quantity, vtype, stat).long_name or ''
    except ValueError:
        return CANONICAL_REGISTRY.get_base_metadata(quantity).long_name or ''


def _valid_units_for(var_name: str) -> list[dict]:
    """Return [{label, value}] options for the canonical quantity of var_name."""
    quantity = _extract_quantity(var_name)
    if not quantity or quantity not in CANONICAL_VARS:
        return []
    raw = CANONICAL_VARS[quantity].get('valid_input_units') or []
    units = raw if isinstance(raw, list) else [raw]
    return [{'label': u, 'value': u} for u in units]


def _fmt_instrument(instrument) -> str:
    """Flatten a compound instrument dict to a readable display string."""
    if isinstance(instrument, dict):
        return ' | '.join(f'{k}: {v}' for k, v in instrument.items())
    return str(instrument) if instrument else ''


def _validate_date_ranges(input_variables: dict) -> None:
    """Raise ValueError if date ranges are missing, unordered, or overlapping."""
    items = sorted(
        input_variables.items(),
        key=lambda x: x[1].get('begin') or '0000-00-00',
    )
    prev_end = None
    for i, (name, attrs) in enumerate(items):
        begin = attrs.get('begin')
        end = attrs.get('end')
        if i > 0 and begin is None:
            raise ValueError(f'{name}: begin cannot be None unless first segment')
        if i < len(items) - 1 and end is None:
            raise ValueError(f'{name}: end cannot be None unless last segment')
        if prev_end and begin and begin < prev_end:
            raise ValueError(f'{name}: overlaps previous segment')
        if end:
            prev_end = end

# ── Site loading ──────────────────────────────────────────────────────────────

def load_site(site_name: str) -> None:
    state['cfg'] = read_yml(SITES_DIR / f'{site_name}.yml')
    state['site'] = site_name
    state['var_cache'] = {}
    state['selected_var'] = next(iter(state['cfg'].get('variables', {})), None)
    base_path = paths.get_local_stream_path(
        resource='raw_data', stream='flux_slow', site=site_name,
    )
    state['base_path'] = base_path
    state['file_formats'] = _compute_file_formats(state['cfg'], base_path)
    state['file_list'] = sorted(state['file_formats'].keys())

# ── File-formats section callbacks ────────────────────────────────────────────

def _get_file_formats_state() -> dict:
    return dict(state['cfg'].get('file_formats', {}) or {})


def _on_file_formats_change(event: dict) -> None:
    ff = state['cfg'].setdefault('file_formats', {})
    ff[event['file']] = event['value']
    state['file_formats'][event['file']] = event['value']

# ── Input-variable table helpers ──────────────────────────────────────────────

def _instruments_for_alias(alias: str) -> list[str]:
    try:
        return list_instruments(alias)
    except Exception:
        return []


def _instrument_options_for(var_name: str) -> dict:
    """Return instrument dropdown metadata derived from the canonical quantity."""
    quantity = _extract_quantity(var_name)
    empty = {'qty_is_compound': False, 'options': [], 'components': []}
    if not quantity:
        return empty
    try:
        if is_compound_quantity(quantity):
            return {'qty_is_compound': True, 'options': [], 'components': get_quantity_components(quantity)}
        return {'qty_is_compound': False, 'options': list_instruments_for_quantity(quantity), 'components': []}
    except Exception:
        return empty


def _build_rows(var_name: str) -> list[dict]:
    """Build the list of row dicts for the input-variables table."""
    input_vars = state['cfg']['variables'][var_name].get('input_variables', {})
    valid_units = _valid_units_for(var_name)
    opts = _instrument_options_for(var_name)

    rows = []
    for key, attrs in input_vars.items():
        file_stem = attrs.get('file')
        fmt = state['file_formats'].get(file_stem) if file_stem else None
        var_options = _get_file_vars(file_stem, fmt) if (file_stem and fmt) else []
        raw_instrument = attrs.get('instrument')

        # Data-driven compound detection: the stored value is the authority.
        # Fall back to quantity-registry for new entries (instrument still None).
        is_compound = isinstance(raw_instrument, dict) or (
            raw_instrument is None and opts['qty_is_compound']
        )

        if is_compound:
            if isinstance(raw_instrument, dict):
                compound_parts = [
                    {'alias': a, 'name': n or '', 'options': _instruments_for_alias(a)}
                    for a, n in raw_instrument.items()
                ]
            else:
                compound_parts = [
                    {'alias': a, 'name': '', 'options': _instruments_for_alias(a)}
                    for a in opts['components']
                ]
        else:
            compound_parts = []

        rows.append({
            '_key': key,
            'name': attrs.get('name', key),
            '_var_options': var_options,
            'instrument': '' if is_compound else _fmt_instrument(raw_instrument),
            '_instrument_is_compound': is_compound,
            '_compound_parts': compound_parts,
            '_instrument_options': opts['options'],
            'units': attrs.get('units', ''),
            'file': file_stem,
            'begin': str(attrs.get('begin', '') or ''),
            'end': str(attrs.get('end', '') or ''),
            '_valid_units': valid_units,
        })
    return rows


def _make_table_edit_handler(var_name: str, refresh_fn) -> callable:
    """Return a handler for table cell edits bound to var_name."""
    def handle(row: dict) -> None:
        input_vars = state['cfg']['variables'][var_name]['input_variables']
        key = row['_key']
        if key not in input_vars:
            return

        attrs = input_vars[key]
        norm_date = lambda v: None if v in ('', None) else v

        # File change: reset dependent fields and exit early
        old_file, new_file = attrs.get('file'), row.get('file')
        if new_file != old_file:
            attrs.update({'file': new_file, 'name': None, 'instrument': None, 'units': None})
            refresh_fn()
            return

        # Raw variable name: validate against file header before accepting
        new_name = row.get('name')
        if new_name is not None:
            file_stem = attrs.get('file')
            fmt = state['file_formats'].get(file_stem) if file_stem else None
            if fmt and new_name not in _get_file_vars(file_stem, fmt):
                refresh_fn()
                return
            attrs['name'] = new_name

        # Instrument: reconstruct compound dict or store simple string
        if row.get('_instrument_is_compound'):
            attrs['instrument'] = {
                p['alias']: p['name'] or None
                for p in row.get('_compound_parts', [])
            }
        else:
            attrs['instrument'] = row.get('instrument') or None

        attrs['units'] = row.get('units')
        attrs['begin'] = norm_date(row.get('begin'))
        attrs['end'] = norm_date(row.get('end'))

        try:
            _validate_date_ranges(input_vars)
        except ValueError as exc:
            ui.notify(str(exc), color='red')

        refresh_fn()

    return handle

# ── Variable detail panel ─────────────────────────────────────────────────────

def render_variable(var_name: str, container) -> None:
    """Rebuild the variable detail panel inside container."""
    container.clear()
    if not var_name or var_name not in state['cfg'].get('variables', {}):
        return

    var_data = state['cfg']['variables'][var_name]

    with container:
        with ui.row().classes('items-baseline gap-6 q-pb-xs'):
            ui.label(var_name).classes('text-h6')
            with ui.row().classes('items-baseline gap-1'):
                ui.label('Long name:').classes('text-caption text-grey-6')
                ui.label(_long_name_for(var_name, var_data) or '—')

        with ui.row().classes('items-center gap-4 q-pb-sm'):
            cur_stat = var_data.get('statistic_type')
            cur_vtype = var_data.get('variable_type', 'continuous')
            is_continuous = cur_vtype == 'continuous'

            stat_select = ui.select(
                options=STATISTIC_TYPE_OPTIONS,
                label='Statistic type',
                value=cur_stat if cur_stat in STATISTIC_TYPE_OPTIONS else None,
                on_change=lambda e, d=var_data: d.update({'statistic_type': e.value}),
            ).classes('w-52')
            if not is_continuous:
                stat_select.props('disable')

            def on_vtype_change(e) -> None:
                var_data['variable_type'] = e.value
                if e.value == 'continuous':
                    stat_select.props(remove='disable')
                else:
                    var_data['statistic_type'] = None
                    stat_select.set_value(None)
                    stat_select.props('disable')

            ui.select(
                options=VARIABLE_TYPE_OPTIONS,
                label='Variable type',
                value=cur_vtype if cur_vtype in VARIABLE_TYPE_OPTIONS else None,
                on_change=on_vtype_change,
            ).classes('w-52')

            height_inp = ui.input(
                label='Height (m)', value=str(var_data.get('height', ''))
            ).classes('w-32')
            height_inp.on(
                'blur',
                lambda _ev, d=var_data, inp=height_inp: d.update({'height': inp.value}),
            )

        ui.label('Input variables').classes('text-subtitle2 q-mt-sm')

        # The edit handler needs the table's refresh function, which is only
        # returned after the table is created.  Use a one-element list as a
        # mutable cell to close over it.
        refresh_cell = [None]

        def on_edit(row: dict) -> None:
            _make_table_edit_handler(var_name, refresh_cell[0])(row)

        _table, refresh = create_input_variable_table(
            get_rows=lambda: _build_rows(var_name),
            on_edit=on_edit,
            file_list=state['file_list'],
        )
        refresh_cell[0] = refresh
        refresh()

# ── Full editor ───────────────────────────────────────────────────────────────

def build_editor(content_col) -> None:
    """Build the full config editor inside content_col."""
    cfg = state['cfg']

    with content_col:

        # File formats + site config in one card, all spread horizontally
        with ui.card().classes('w-full q-mb-sm'):
            with ui.row().classes('w-full gap-8 items-start q-pa-sm'):

                with ui.column():
                    ui.label('File formats').classes('text-subtitle1 font-bold q-pb-xs')
                    create_file_formats_editor(
                        get_file_formats_state=_get_file_formats_state,
                        on_change=_on_file_formats_change,
                        file_type_options=FILE_TYPE_OPTIONS,
                    )

                with ui.column():
                    ui.label('Flux system').classes('text-subtitle1 font-bold q-pb-xs')
                    ui.select(
                        options=FLUX_SYSTEM_OPTIONS,
                        value=cfg.get('flux_system'),
                        on_change=lambda e: cfg.update({'flux_system': e.value}),
                    ).classes('w-44')

                with ui.column():
                    ui.label('Flux file').classes('text-subtitle1 font-bold q-pb-xs')
                    ui.select(
                        options=state['file_list'],
                        value=cfg.get('flux_file'),
                        on_change=lambda e: cfg.update({'flux_file': e.value}),
                    ).classes('w-72')

        # Variables section
        with ui.card().classes('w-full'):
            ui.label('Variables').classes('text-subtitle1 q-pa-xs')

            with ui.row().classes('w-full gap-0 items-start'):

                # Left: persistent scrollable variable list
                var_list_col = ui.column().style('min-width:200px; max-width:220px')

                ui.separator().props('vertical').classes('q-mx-sm')

                # Right: variable detail editor
                var_detail = ui.column().classes('flex-grow q-pa-xs')

            def render_var_list() -> None:
                var_list_col.clear()
                with var_list_col:
                    with ui.list().props('dense separator').style(
                        'max-height:520px; overflow-y:auto'
                    ):
                        for vname in sorted(cfg.get('variables', {}).keys()):
                            active = vname == state['selected_var']
                            with ui.item(
                                on_click=lambda v=vname: on_var_select(v),
                            ).props('clickable v-ripple').classes(
                                'bg-blue-100 text-blue-900' if active else ''
                            ):
                                with ui.item_section():
                                    ui.item_label(vname).classes('text-sm font-mono')

            def on_var_select(var_name: str) -> None:
                state['selected_var'] = var_name
                render_var_list()
                render_variable(var_name, var_detail)

            render_var_list()
            if state['selected_var']:
                render_variable(state['selected_var'], var_detail)

# ── Actions ───────────────────────────────────────────────────────────────────

def do_validate(error_col) -> None:
    ok, errors = validate_all(state['cfg'])
    error_col.clear()
    if ok:
        ui.notify('Config is valid', color='green')
        return
    ui.notify(f'{len(errors)} validation error(s) — see below', color='red')
    with error_col:
        ui.separator()
        ui.label('Validation errors:').classes('text-subtitle2 text-red q-mt-sm')
        for err in errors:
            loc = ' → '.join(str(x) for x in err.get('loc', []))
            ui.label(f'  {loc}: {err.get("msg", "")}').classes('text-red text-sm')


def do_save() -> None:
    if not state['site']:
        ui.notify('No site loaded', color='orange')
        return
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    dest = SAVE_DIR / f'{state["site"]}.yml'
    with open(dest, 'w') as fh:
        yaml.dump(state['cfg'], fh, default_flow_style=False, allow_unicode=True, sort_keys=False)
    ui.notify(f'Draft saved to {dest}', color='green')

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    sites = _site_names()

    dark = ui.dark_mode()

    with ui.column().classes('w-full q-pa-md'):
        with ui.row().classes('items-center q-mb-md'):
            ui.label('L1 Configuration Editor').classes('text-h5')
            ui.label('Site').classes('text-caption text-grey-6').style('margin-left: 60px; margin-right: 2px')
            site_select = ui.select(
                options=sites, value=None,
            ).props('borderless hide-selected dense').style('min-width: 28px; max-width: 40px')
            site_name_label = ui.label('').classes('text-h5')
            ui.space()
            ui.button(icon='dark_mode', on_click=dark.toggle).props('flat round dense')

        content_col = ui.column().classes('w-full')
        error_col = ui.column().classes('w-full')

        with ui.row().classes('q-mt-md gap-4'):
            ui.button(
                'Validate', on_click=lambda: do_validate(error_col),
            ).props('color=primary')
            ui.button('Save draft', on_click=do_save).props('color=secondary')

    def on_site_change(_event) -> None:
        site = site_select.value
        if not site:
            return
        try:
            load_site(site)
            site_name_label.set_text(site)
            content_col.clear()
            error_col.clear()
            build_editor(content_col)
        except Exception as exc:
            ui.notify(f'Error loading {site}: {exc}', color='red')
            raise

    site_select.on('update:model-value', on_site_change)

    ui.run(title='L1 Configuration Editor', port=8080)


if __name__ in {'__main__', '__mp_main__'}:
    main()
