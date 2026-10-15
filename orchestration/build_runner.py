#!/usr/bin/env python3
"""TERN-adapter wrappers for the L1/L2 Zarr and NetCDF builders.

The generic-core builders (orchestration/build_L1_zarr.py, build_L1_nc.py,
build_L2_zarr.py, build_L2_nc.py) take a SiteContext / SiteQCConfig and
explicit directories. These wrappers resolve a bare TERN site name to those:
the context via SiteRegistry, the QC config via qc_config_loader, the
directories via the homogenised_data streams in configs/paths.yml, and the
network global attributes from configs/nc_metadata.yml.

Usage (from project root, with ep_cntl activated):
    python -m orchestration.build_runner L1-zarr SITE [--update] \
        [--year YEAR] [--output-dir DIR] [--legacy]
    python -m orchestration.build_runner L1-nc SITE [--year YEAR] \
        [--zarr-dir DIR] [--output-dir DIR]
    python -m orchestration.build_runner L2-zarr SITE [--update] \
        [--output-dir DIR]
    python -m orchestration.build_runner L2-nc SITE [--year YEAR] \
        [--zarr-dir DIR] [--output-dir DIR]

NetCDF is always exported from a Zarr store. For a legacy-config build, write
the store somewhere separate first, then export from it:
    python -m orchestration.build_runner L1-zarr SITE --legacy --output-dir Z
    python -m orchestration.build_runner L1-nc SITE --zarr-dir Z --output-dir N
"""

import argparse
import pathlib

from fluxcore import build_L1_nc, build_L1_zarr, build_L2_nc, build_L2_zarr

from infrastructure import config_loader, paths
from orchestration.site_runner import SITE_REGISTRY
from services.metadata.qc_config_loader import load_site_qc_config

NC_GLOBAL_ATTRS = config_loader.load_config_file_from_name(
    name="nc_metadata", config_dir=paths.CONFIG_PATH
)


def _zarr_dir(level: str) -> pathlib.Path:
    return paths.get_local_stream_path("homogenised_data", "zarr") / level


def _nc_dir(site: str) -> pathlib.Path:
    return paths.get_local_stream_path("homogenised_data", "nc") / site


def build_L1_zarr_for_site(
    site: str,
    output_dir: pathlib.Path | str | None = None,
    year: int | None = None,
    legacy: bool = False,
) -> pathlib.Path:
    """Full rebuild of a site's L1 Zarr store (see build_L1_zarr.build)."""
    return build_L1_zarr.build(
        SITE_REGISTRY.get_context(site=site, legacy=legacy),
        output_dir=output_dir or _zarr_dir("L1"),
        year=year,
        global_attrs=NC_GLOBAL_ATTRS,
    )


def update_L1_zarr_for_site(
    site: str,
    output_dir: pathlib.Path | str | None = None,
    legacy: bool = False,
) -> pathlib.Path:
    """Incremental update of a site's L1 Zarr store (see build_L1_zarr.update)."""
    return build_L1_zarr.update(
        SITE_REGISTRY.get_context(site=site, legacy=legacy),
        output_dir=output_dir or _zarr_dir("L1"),
        global_attrs=NC_GLOBAL_ATTRS,
    )


def build_L1_nc_from_zarr_for_site(
    site: str,
    zarr_dir: pathlib.Path | str | None = None,
    output_dir: pathlib.Path | str | None = None,
    year: int | None = None,
) -> list[pathlib.Path]:
    """Build a site's L1 NetCDF files from its Zarr store."""
    return build_L1_nc.build_from_zarr(
        site,
        zarr_dir=zarr_dir or _zarr_dir("L1"),
        output_dir=output_dir or _nc_dir(site),
        year=year,
        global_attrs=NC_GLOBAL_ATTRS,
    )


def build_L2_zarr_for_site(
    site: str,
    output_dir: pathlib.Path | str | None = None,
    l1_dir: pathlib.Path | str | None = None,
) -> pathlib.Path:
    """Full rebuild of a site's L2 Zarr store (see build_L2_zarr.build)."""
    return build_L2_zarr.build(
        load_site_qc_config(site),
        output_dir=output_dir or _zarr_dir("L2"),
        l1_dir=l1_dir or _zarr_dir("L1"),
    )


def update_L2_zarr_for_site(
    site: str,
    output_dir: pathlib.Path | str | None = None,
    l1_dir: pathlib.Path | str | None = None,
) -> pathlib.Path:
    """Incremental update of a site's L2 Zarr store (see build_L2_zarr.update)."""
    return build_L2_zarr.update(
        load_site_qc_config(site),
        output_dir=output_dir or _zarr_dir("L2"),
        l1_dir=l1_dir or _zarr_dir("L1"),
    )


def build_L2_nc_from_zarr_for_site(
    site: str,
    zarr_dir: pathlib.Path | str | None = None,
    output_dir: pathlib.Path | str | None = None,
    year: int | None = None,
) -> list[pathlib.Path]:
    """Build a site's L2 NetCDF files from its L2 Zarr store."""
    return build_L2_nc.build_from_zarr(
        site,
        zarr_dir=zarr_dir or _zarr_dir("L2"),
        output_dir=output_dir or _nc_dir(site),
        year=year,
        global_attrs=NC_GLOBAL_ATTRS,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a TERN site's L1/L2 Zarr store or NetCDF files."
    )
    sub = parser.add_subparsers(dest="target", required=True)

    def add_common(p, year=True):
        p.add_argument("site", help="Registered site name, e.g. Dookie2.")
        p.add_argument(
            "--output-dir",
            type=pathlib.Path,
            default=None,
            help="Override output directory (default: homogenised_data stream).",
        )
        if year:
            p.add_argument(
                "--year",
                type=int,
                default=None,
                help="Only build from/for this calendar year.",
            )

    def add_zarr_dir(p):
        p.add_argument(
            "--zarr-dir",
            type=pathlib.Path,
            default=None,
            help="Override the Zarr store directory to export from.",
        )

    p = sub.add_parser("L1-zarr", help="Build or update the L1 Zarr store.")
    add_common(p)
    p.add_argument("--update", action="store_true", help="Append new records only.")
    p.add_argument("--legacy", action="store_true", help="Use legacy config snapshot.")

    p = sub.add_parser("L1-nc", help="Build L1 NetCDF files from the L1 Zarr store.")
    add_common(p)
    add_zarr_dir(p)

    p = sub.add_parser("L2-zarr", help="Build or update the L2 Zarr store.")
    add_common(p, year=False)
    p.add_argument("--update", action="store_true", help="Append new records only.")

    p = sub.add_parser("L2-nc", help="Build L2 NetCDF files from the L2 Zarr store.")
    add_common(p)
    add_zarr_dir(p)

    return parser.parse_args()


def main() -> None:
    """CLI entry point."""
    args = _parse_args()
    if args.target == "L1-zarr":
        if args.update:
            result = update_L1_zarr_for_site(
                args.site, output_dir=args.output_dir, legacy=args.legacy
            )
        else:
            result = build_L1_zarr_for_site(
                args.site,
                output_dir=args.output_dir,
                year=args.year,
                legacy=args.legacy,
            )
    elif args.target == "L1-nc":
        result = build_L1_nc_from_zarr_for_site(
            args.site,
            zarr_dir=args.zarr_dir,
            output_dir=args.output_dir,
            year=args.year,
        )
    elif args.target == "L2-zarr":
        fn = update_L2_zarr_for_site if args.update else build_L2_zarr_for_site
        result = fn(args.site, output_dir=args.output_dir)
    else:
        result = build_L2_nc_from_zarr_for_site(
            args.site,
            zarr_dir=args.zarr_dir,
            output_dir=args.output_dir,
            year=args.year,
        )
    for path in result if isinstance(result, list) else [result]:
        print(f"Wrote: {path}")


if __name__ == "__main__":
    main()
