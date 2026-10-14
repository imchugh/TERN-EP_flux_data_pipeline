#!/usr/bin/env python3
"""TERN-adapter loading of a site's L2 QC config.

Resolves where a TERN site's own QC config file lives (the
site_config_files_L2 stream, site_configs/operational/L2/{site_name}.yml)
via infrastructure.paths, then delegates to the generic-core
qc_config_schema.load_qc_config.
"""

from fluxcore.services.metadata.core import qc_config_schema
from fluxcore.services.metadata.core.qc_config_schema import SiteQCConfig

from infrastructure import paths


def load_site_qc_config(site_name: str) -> SiteQCConfig:
    """Load a TERN site's QC config (empty pass-through config if none exists)."""
    config_dir = paths.get_local_stream_path("configs", "site_config_files_L2")
    return qc_config_schema.load_qc_config(site_name, config_dir=config_dir)
