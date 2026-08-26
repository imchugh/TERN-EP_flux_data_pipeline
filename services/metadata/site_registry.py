#!/usr/bin/env python3
"""Authoritative entry point for pipeline site metadata.

A site is considered part of the pipeline if and only if a site-level
runtime configuration YML file exists. The repository
(site_metadata_repository) is broader — it covers all TERN sites
including decommissioned and non-pipeline sites. The registry filters
that down to the pipeline population.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from domain.data_models.metadata_classes import SiteMetadata
from infrastructure import paths
from services import config_loader
from services.metadata.runtime_config_builder import SiteRuntimeConfig
from services.metadata.runtime_config_loader import load_runtime_config


class InvalidSiteError(KeyError):
    """Raised when a site is not configured in the pipeline."""


SITE_CONFIG_DIR = paths.get_local_stream_path(
    resource="configs", stream="site_config_files"
)

# One-off/legacy config snapshots — used to rebuild L1 output with an
# earlier generation of instruments/variables/files for a site. Not part
# of the operational pipeline population; a site may exist here without
# being pipeline-configured, or vice versa.
LEGACY_SITE_CONFIG_DIR = paths.get_local_stream_path(
    resource="configs", stream="site_config_files_legacy"
)

# Temporary alias map: config-file/directory name → metadata key.
# WombatStateForest keeps its legacy directory name until the directory is
# renamed; remove this entry once that migration is done.
SITE_ALIASES = {"WombatStateForest": "WombatForest"}


@dataclass(frozen=True)
class SiteContext:
    """Combined runtime objects for a configured pipeline site."""

    runtime_config: SiteRuntimeConfig
    metadata: SiteMetadata


class SiteRegistry:
    """Authoritative registry of configured/processable pipeline sites.

    A site exists in the pipeline if and only if a site-level runtime
    configuration YML file exists in SITE_CONFIG_DIR.

    Metadata is loaded lazily on first access and cached for the lifetime
    of the registry instance.
    """

    def __init__(
        self,
        metadata_loader: Callable[[], dict[str, SiteMetadata]] = None,
    ):
        """Create a registry instance with an empty metadata/runtime-config cache.

        Args:
            metadata_loader: callable returning site-name-keyed SiteMetadata.
                Defaults to `yml_loader`; pass `rdf_loader` for live RDF data.
        """
        self._metadata_loader = (
            metadata_loader if metadata_loader is not None else yml_loader
        )
        self._metadata_cache: dict[str, SiteMetadata] | None = None
        self._runtime_config_cache: dict[tuple[str, bool], SiteRuntimeConfig] = {}

    def names(self) -> list[str]:
        """Return all configured pipeline site names."""
        return sorted(path.stem for path in SITE_CONFIG_DIR.glob("*.yml"))

    def exists(self, site: str) -> bool:
        """Return True if site is configured in the pipeline."""
        return (SITE_CONFIG_DIR / f"{site}.yml").exists()

    def require(self, site: str) -> None:
        """Raise InvalidSiteError if site is not in the pipeline."""
        if not self.exists(site):
            raise InvalidSiteError(f"Site is not configured in the pipeline: {site}")

    def get_config_path(self, site: str, legacy: bool = False) -> Path:
        """Return the runtime config path for a pipeline site.

        Args:
            site: registered site name.
            legacy: if True, return the path to the site's legacy config
                snapshot (site_configs/legacy) instead of its operational
                config. Raises InvalidSiteError if no legacy config exists
                for the site.
        """
        self.require(site)
        if not legacy:
            return SITE_CONFIG_DIR / f"{site}.yml"

        legacy_path = LEGACY_SITE_CONFIG_DIR / f"{site}.yml"
        if not legacy_path.exists():
            raise InvalidSiteError(f"No legacy config found for site: {site}")
        return legacy_path

    def get_all_metadata(self) -> dict[str, SiteMetadata]:
        """Return metadata for all pipeline sites.

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

    def get_metadata(self, site: str) -> SiteMetadata:
        """Load metadata for a single pipeline site."""
        self.require(site)
        metadata = self.get_all_metadata().get(site)
        if metadata is None:
            raise InvalidSiteError(f"No metadata found for site {site}!")
        return metadata

    def get_runtime_config(self, site: str, legacy: bool = False) -> SiteRuntimeConfig:
        """Load runtime configuration for a pipeline site.

        Args:
            site: registered site name.
            legacy: if True, load the site's legacy config snapshot
                (site_configs/legacy) instead of its operational config.
                Use for one-off rebuilds of L1 output under an earlier
                generation of instruments/variables/files.

        Results are cached by (site, legacy) for the lifetime of this
        registry instance — subsequent calls return the same object without
        re-parsing the config file.
        """
        cache_key = (site, legacy)
        if cache_key not in self._runtime_config_cache:
            config_path = self.get_config_path(site=site, legacy=legacy)
            self._runtime_config_cache[cache_key] = load_runtime_config(config_path)
        return self._runtime_config_cache[cache_key]

    def get_context(self, site: str, legacy: bool = False) -> SiteContext:
        """Assemble the combined site context object.

        Args:
            site: registered site name.
            legacy: if True, assemble the context from the site's legacy
                config snapshot instead of its operational config. Site
                metadata (location, tower height, etc.) is unaffected and
                always comes from the standard metadata source.
        """
        return SiteContext(
            runtime_config=self.get_runtime_config(site, legacy=legacy),
            metadata=self.get_metadata(site),
        )


def yml_loader() -> dict[str, SiteMetadata]:
    """Load pipeline site metadata from the local YML file.

    This is the standard loader for production use. Pass it as
    ``metadata_loader`` when constructing a SiteRegistry.
    """
    loaded = config_loader.load_config_file_from_name("site_metadata")
    return {key: SiteMetadata(data=value) for key, value in loaded.items()}


def rdf_loader() -> dict[str, SiteMetadata]:
    """Load site metadata from the TERN RDF/SPARQL endpoint.

    Covers all TERN sites (broader than the pipeline). Pass it as
    ``metadata_loader`` when constructing a SiteRegistry if live RDF
    data is preferred over the local YML snapshot.
    """
    from services.metadata.site_metadata_repository import (
        get_flux_tower_fields_from_rdf,
    )

    loaded = get_flux_tower_fields_from_rdf()
    return {key: SiteMetadata(data=value) for key, value in loaded.items()}
