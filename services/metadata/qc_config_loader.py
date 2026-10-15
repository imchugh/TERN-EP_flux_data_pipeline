#!/usr/bin/env python3
"""TERN-adapter loading of a site's L2 QC config.

Resolves where a TERN site's own QC config file lives (the
site_config_files_L2 stream, site_configs/operational/L2/{site_name}.yml)
via infrastructure.paths, then delegates to the generic-core
load_qc_config.
"""

from fluxcore import SiteQCConfig, load_qc_config

from infrastructure import paths


def load_site_qc_config(site_name: str) -> SiteQCConfig:
    """Load a TERN site's QC config (empty pass-through config if none exists)."""
    config_dir = paths.get_local_stream_path("configs", "site_config_files_L2")
    return load_qc_config(site_name, config_dir=config_dir)
