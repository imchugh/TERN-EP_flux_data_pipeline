#!/usr/bin/env python3
"""Audit instrument names in site YAML configs against the TERN controlled vocab.

For each unique instrument string found in the configs:
  - VALID: it exists in the TERN vocab (exact match)
  - MISSING: it doesn't — fuzzy suggestions are printed

Usage (from project root, with ep_cntl activated):
    python -m tools.audit_instrument_names
"""

import sys
from collections import defaultdict
from pathlib import Path

import yaml

# Ensure project root is on path when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.metadata.instrument_registry import (
    get_instrument_type,
    is_valid_instrument,
    suggest_instruments,
)
from services.metadata.site_registry import SITE_CONFIG_DIR

# Constants
_SEP = "─" * 64
_SUGGESTION_CUTOFF = 60.0
_N_SUGGESTIONS = 5


# Helpers
def _extract_instrument_names(obj: object) -> list[str]:
    """Recursively collect all instrument strings from a parsed YAML dict."""
    names: list[str] = []
    if isinstance(obj, dict):
        if "instrument" in obj:
            val = obj["instrument"]
            if isinstance(val, str):
                # Handle legacy comma-separated compound format
                names.extend(p.strip() for p in val.split(",") if p.strip())
            elif isinstance(val, dict):
                names.extend(v.strip() for v in val.values() if isinstance(v, str))
        for v in obj.values():
            names.extend(_extract_instrument_names(v))
    elif isinstance(obj, list):
        for item in obj:
            names.extend(_extract_instrument_names(item))
    return names


def _collect_all_instruments(
    config_dir: Path,
) -> dict[str, list[str]]:
    """Return {instrument_name: [site_name, ...]} across all site YAMLs."""
    instrument_sites: dict[str, list[str]] = defaultdict(list)

    for yml_path in sorted(config_dir.glob("*.yml")):
        site_name = yml_path.stem
        try:
            with yml_path.open() as fh:
                data = yaml.safe_load(fh)
        except Exception as exc:
            print(f"  WARNING: could not parse {yml_path.name}: {exc}", file=sys.stderr)
            continue

        for name in _extract_instrument_names(data):
            instrument_sites[name].append(site_name)

    # deduplicate site lists while preserving order
    return {k: list(dict.fromkeys(v)) for k, v in instrument_sites.items()}


# Report


def _format_sites(sites: list[str], max_inline: int = 4) -> str:
    if len(sites) <= max_inline:
        return ", ".join(sites)
    return ", ".join(sites[:max_inline]) + f", … (+{len(sites) - max_inline} more)"


def run_audit(config_dir: Path = SITE_CONFIG_DIR) -> None:
    """Print a report of every instrument name not recognised by the TERN vocabulary."""
    print(f"\nScanning: {config_dir}\n")

    instrument_sites = _collect_all_instruments(config_dir)
    if not instrument_sites:
        print("No instrument entries found.")
        return

    valid: dict[str, tuple[str, list[str]]] = {}  # name → (alias, sites)
    missing: dict[str, list[str]] = {}  # name → sites

    for name, sites in sorted(instrument_sites.items()):
        if is_valid_instrument(name):
            try:
                alias = get_instrument_type(name)
            except KeyError:
                alias = "?"
            valid[name] = (alias, sites)
        else:
            missing[name] = sites

    # Valid
    print(_SEP)
    print(f"VALID  ({len(valid)} instruments found in TERN vocab)")
    print(_SEP)
    if valid:
        name_w = max(len(n) for n in valid) + 2
        for name, (alias, sites) in sorted(valid.items()):
            n_sites = f"{len(sites)} site{'s' if len(sites) != 1 else ''}"
            print(f"  {name:<{name_w}}  [{alias}]  —  {n_sites}")
    else:
        print("  (none)")

    # Missing
    print()
    print(_SEP)
    print(f"MISSING  ({len(missing)} instruments not in TERN vocab)")
    print(_SEP)
    if missing:
        for name, sites in sorted(missing.items()):
            site_str = _format_sites(sites)
            print(f"\n  '{name}'  —  {site_str}")
            suggestions = suggest_instruments(
                name, n=_N_SUGGESTIONS, score_cutoff=_SUGGESTION_CUTOFF
            )
            if suggestions:
                for match, score in suggestions:
                    try:
                        alias = get_instrument_type(match)
                    except KeyError:
                        alias = "?"
                    print(f"      {score:>5.1f}  {match}  [{alias}]")
            else:
                print("      (no suggestions above threshold — manual review needed)")
    else:
        print("  (none — all instrument names are valid)")

    print()


# Entry point
if __name__ == "__main__":
    run_audit()
