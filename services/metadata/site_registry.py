#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Authoritative entry point for pipeline site metadata.

A site is considered part of the pipeline if and only if a site-level
runtime configuration YML file exists. The repository
(site_metadata_repository) is broader — it covers all TERN sites
including decommissioned and non-pipeline sites. The registry filters
that down to the pipeline population.

@author: imchugh
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from domain.data_models.metadata_classes import SiteMetadata
from infrastructure import paths
from services import config_loader
from services.metadata.variable_metadata_service import SiteRuntimeConfig

# -----------------------------------------------------------------------------

class InvalidSiteError(KeyError):
    pass

# -----------------------------------------------------------------------------

SITE_CONFIG_DIR = paths.get_local_stream_path(
    resource='configs',
    stream='site_config_files'
    )

# Temporary alias map: config-file/directory name → metadata key.
# WombatStateForest keeps its legacy directory name until the directory is
# renamed; remove this entry once that migration is done.
SITE_ALIASES = {'WombatStateForest': 'WombatForest'}

# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class SiteContext:
    """Combined runtime objects for a configured pipeline site."""

    runtime_config: SiteRuntimeConfig
    metadata: SiteMetadata

# -----------------------------------------------------------------------------


class SiteRegistry:
    """
    Authoritative registry of configured/processable pipeline sites.

    A site exists in the pipeline if and only if a site-level runtime
    configuration YML file exists in SITE_CONFIG_DIR.

    Metadata is loaded lazily on first access and cached for the lifetime
    of the registry instance.
    """

    def __init__(
            self,
            metadata_loader: Callable[[], dict[str, SiteMetadata]],
            runtime_config_loader: Callable[[str], SiteRuntimeConfig],
            ):

        self._metadata_loader = metadata_loader
        self._runtime_config_loader = runtime_config_loader
        self._metadata_cache: dict[str, SiteMetadata] | None = None

    #--------------------------------------------------------------------------

    def names(self) -> list[str]:
        """Return all configured pipeline site names."""

        return sorted(
            path.stem
            for path in SITE_CONFIG_DIR.glob('*.yml')
            )

    #--------------------------------------------------------------------------

    def exists(self, site: str) -> bool:
        """Return True if site is configured in the pipeline."""

        return (SITE_CONFIG_DIR / f'{site}.yml').exists()

    #--------------------------------------------------------------------------

    def require(self, site: str) -> None:
        """Raise InvalidSiteError if site is not in the pipeline."""

        if not self.exists(site):
            raise InvalidSiteError(
                f"Site is not configured in the pipeline: {site}"
            )

    #--------------------------------------------------------------------------

    def get_config_path(self, site: str) -> Path:
        """Return the runtime config path for a pipeline site."""

        self.require(site)
        return SITE_CONFIG_DIR / f'{site}.yml'

    #--------------------------------------------------------------------------

    def get_all_metadata(self) -> dict[str, SiteMetadata]:
        """
        Return metadata for all pipeline sites.

        Results are loaded once from the metadata loader and cached for
        the lifetime of this registry instance.
        """

        if self._metadata_cache is None:
            all_tern = self._metadata_loader()
            self._metadata_cache = {
                site: all_tern[SITE_ALIASES.get(site, site)]
                for site in self.names()
                if SITE_ALIASES.get(site, site) in all_tern
                }

        return self._metadata_cache

    #--------------------------------------------------------------------------

    def get_metadata(self, site: str) -> SiteMetadata:
        """Load metadata for a single pipeline site."""

        self.require(site)
        site_alias = SITE_ALIASES.get(site, site)
        metadata = self.get_all_metadata().get(site_alias)
        if metadata is None:
            raise InvalidSiteError(f'No metadata found for site {site}!')
        return metadata

    #--------------------------------------------------------------------------

    def get_runtime_config(self, site: str) -> SiteRuntimeConfig:
        """Load runtime configuration for a pipeline site."""

        config_path = self.get_config_path(site=site)
        return self._runtime_config_loader(config_path)

    #--------------------------------------------------------------------------

    def get_context(self, site: str) -> SiteContext:
        """Assemble the combined site context object."""

        return SiteContext(
            runtime_config=self.get_runtime_config(site),
            metadata=self.get_metadata(site)
        )

# -----------------------------------------------------------------------------


def yml_loader() -> dict[str, SiteMetadata]:
    """
    Load pipeline site metadata from the local YML file.

    This is the standard loader for production use. Pass it as
    ``metadata_loader`` when constructing a SiteRegistry.
    """

    loaded = config_loader.load_config_file_from_name('site_metadata')
    return {key: SiteMetadata(data=value) for key, value in loaded.items()}


def rdf_loader() -> dict[str, SiteMetadata]:
    """
    Load site metadata from the TERN RDF/SPARQL endpoint.

    Covers all TERN sites (broader than the pipeline). Pass it as
    ``metadata_loader`` when constructing a SiteRegistry if live RDF
    data is preferred over the local YML snapshot.
    """

    from services.metadata.site_metadata_repository import (
        get_flux_tower_fields_from_rdf,
    )
    loaded = get_flux_tower_fields_from_rdf()
    return {key: SiteMetadata(data=value) for key, value in loaded.items()}
