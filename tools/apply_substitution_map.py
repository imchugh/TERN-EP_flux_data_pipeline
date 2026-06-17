#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Apply instrument name substitutions, writing corrected files to a new directory.

Reads configs/instrument_substitutions.yml (produced by generate_substitution_map.py),
walks every site YAML in the source directory, applies substitutions, and writes
the result to the output directory. Original files are never touched.

Usage (from project root, with ep_cntl activated):
    python -m tools.apply_substitution_map <output_dir>

Example:
    python -m tools.apply_substitution_map /opt/TERN_EP/site_configs/corrected
"""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from infrastructure import file_io
from services.metadata.site_registry import SITE_CONFIG_DIR

MAP_PATH = Path(__file__).resolve().parent.parent / 'configs' / 'instrument_substitutions.yml'


# ── substitution logic ────────────────────────────────────────────────────────

def _apply_to_obj(obj: object, subs: dict[str, str]) -> bool:
    """Recursively substitute instrument names in-place. Returns True if changed."""
    changed = False
    if isinstance(obj, dict):
        if 'instrument' in obj:
            val = obj['instrument']
            if isinstance(val, str):
                if val in subs:
                    obj['instrument'] = subs[val]
                    changed = True
                elif ',' in val:
                    parts = [p.strip() for p in val.split(',')]
                    new_parts = [subs.get(p, p) for p in parts]
                    if new_parts != parts:
                        obj['instrument'] = ', '.join(new_parts)
                        changed = True
            elif isinstance(val, dict):
                for k, v in val.items():
                    if isinstance(v, str) and v in subs:
                        val[k] = subs[v]
                        changed = True
        for v in obj.values():
            if _apply_to_obj(v, subs):
                changed = True
    elif isinstance(obj, list):
        for item in obj:
            if _apply_to_obj(item, subs):
                changed = True
    return changed


# ── main ──────────────────────────────────────────────────────────────────────

def apply_map(
    output_dir: Path,
    config_dir: Path = SITE_CONFIG_DIR,
    map_path: Path = MAP_PATH,
) -> None:
    if not map_path.exists():
        print(f'ERROR: map file not found: {map_path}')
        print('Run python -m tools.generate_substitution_map first.')
        sys.exit(1)

    with map_path.open(encoding='utf-8') as f:
        map_data = yaml.safe_load(f)

    subs: dict[str, str] = map_data.get('substitutions') or {}
    if not subs:
        print('No substitutions in map — nothing to do.')
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f'Source:      {config_dir}')
    print(f'Output:      {output_dir}')
    print(f'Map:         {map_path}')
    print(f'Substitutions: {len(subs)}\n')

    n_changed = 0
    n_unchanged = 0

    for yml_path in sorted(config_dir.glob('*.yml')):
        data = file_io.read_yml(yml_path)
        if data is None:
            continue

        changed = _apply_to_obj(data, subs)
        out_path = output_dir / yml_path.name
        file_io.write_yml_file(out_path, data)

        if changed:
            n_changed += 1
            print(f'  CHANGED    {yml_path.name}')
        else:
            n_unchanged += 1
            print(f'  unchanged  {yml_path.name}')

    print(f'\n{n_changed} file(s) changed, {n_unchanged} unchanged.')
    print(f'Corrected configs written to: {output_dir}')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f'Usage: python -m tools.apply_substitution_map <output_dir>')
        sys.exit(1)
    apply_map(output_dir=Path(sys.argv[1]))
