#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
List instrument name inconsistencies grouped by site YAML file.

For each site config, reports instrument names that are not found in the
TERN controlled vocabulary. Run this on the corrected output directory to
see what is still outstanding after applying a substitution map.

Usage (from project root, with ep_cntl activated):
    python -m tools.list_inconsistencies_by_site [config_dir]

Default config_dir: /opt/TERN_EP/site_configs/operational

Example — check the corrected output:
    python -m tools.list_inconsistencies_by_site /opt/TERN_EP/site_configs/corrected
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from infrastructure import file_io
from services.metadata.instrument_registry import is_valid_instrument
from services.metadata.site_registry import SITE_CONFIG_DIR
from tools.audit_instrument_names import _extract_instrument_names

_SEP = '─' * 64


def list_by_site(config_dir: Path = SITE_CONFIG_DIR) -> None:
    yml_files = sorted(config_dir.glob('*.yml'))
    if not yml_files:
        print(f'No YAML files found in: {config_dir}')
        return

    print(f'Scanning: {config_dir}\n')

    affected: list[tuple[str, list[str]]] = []

    for yml_path in yml_files:
        data = file_io.read_yml(yml_path)
        if data is None:
            continue

        all_names = _extract_instrument_names(data)
        invalid = sorted(set(n for n in all_names if not is_valid_instrument(n)))

        if invalid:
            affected.append((yml_path.name, invalid))

    if not affected:
        print('No inconsistencies found — all instrument names are valid.')
        return

    total = sum(len(names) for _, names in affected)
    print(_SEP)
    print(f'{len(affected)} site(s) with outstanding inconsistencies  ({total} total)')
    print(_SEP)

    for site_file, names in affected:
        print(f'\n{site_file}  ({len(names)})')
        for name in names:
            print(f'  {name}')

    print()


if __name__ == '__main__':
    config_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else SITE_CONFIG_DIR
    list_by_site(config_dir)
