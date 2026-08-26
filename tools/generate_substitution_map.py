#!/usr/bin/env python3
"""Generate a YAML substitution map for instrument name cleanup.

Runs the instrument audit and writes configs/instrument_substitutions.yml
with the best fuzzy suggestion for each missing instrument name.

Review and edit that file (remove or correct entries), then run:
    python -m tools.apply_substitution_map [output_dir]

Usage (from project root, with ep_cntl activated):
    python -m tools.generate_substitution_map
"""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.metadata.tern.instrument_registry import (
    is_valid_instrument,
    suggest_instruments,
)
from services.metadata.tern.site_registry import SITE_CONFIG_DIR
from tools.audit_instrument_names import _collect_all_instruments

OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent / "configs" / "instrument_substitutions.yml"
)
CUTOFF = 60.0


def generate_map(
    config_dir: Path = SITE_CONFIG_DIR,
    output: Path = OUTPUT_PATH,
) -> None:
    """Write a YAML map of fuzzy-matched suggestions for missing instrument names."""
    print(f"Scanning: {config_dir}\n")

    instrument_sites = _collect_all_instruments(config_dir)

    # Collect (old, new, score) triples for missing instruments
    suggestions: list[tuple[str, str, float]] = []
    no_match: list[str] = []

    for name in sorted(instrument_sites):
        if is_valid_instrument(name):
            continue
        hits = suggest_instruments(name, n=1, score_cutoff=CUTOFF)
        if hits:
            match, score = hits[0]
            suggestions.append((name, match, score))
        else:
            no_match.append(name)

    # Sort by descending score so highest-confidence entries are at the top
    suggestions.sort(key=lambda t: -t[2])

    # Print to terminal so scores are visible during review
    print(f"{'score':>6}  {'from':<42}  to")
    print("─" * 80)
    for old, new, score in suggestions:
        print(f"{score:6.1f}  {old!r:<42}  {new!r}")
    if no_match:
        print(f"\nNo match (threshold {CUTOFF:.0f}):")
        for name in no_match:
            print(f"  {name!r}")

    # Write the map YAML
    data = {
        "substitutions": {old: new for old, new, _ in suggestions},
        "no_match": no_match if no_match else None,
    }

    with output.open("w", encoding="utf-8") as f:
        f.write("# Instrument name substitution map\n")
        f.write("# Review: remove any entry you do NOT want applied\n")
        f.write("# Entries are ordered by match confidence (highest first)\n")
        f.write("#\n")
        f.write("# Apply with: python -m tools.apply_substitution_map [output_dir]\n\n")
        yaml.safe_dump(
            data,
            f,
            sort_keys=False,
            default_flow_style=False,
            allow_unicode=True,
        )

    print(
        f"\nWrote {len(suggestions)} substitutions + "
        f"{len(no_match)} no-match entries to:"
    )
    print(f"  {output}")


if __name__ == "__main__":
    generate_map()
