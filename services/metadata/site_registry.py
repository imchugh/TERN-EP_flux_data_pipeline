#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This module uses the presence of configuration files as the source of truth for 
site existence. 

@author: imchugh
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from services.metadata.variable_metadata_service import SiteRuntimeConfig
from domain.data_models.metadata_classes import SiteMetadata
from infrastructure import paths

# -----------------------------------------------------------------------------

class InvalidSiteError(KeyError):
    pass
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

SITE_CONFIG_DIR = paths.get_local_stream_path(
    resource='configs',
    stream='site_config_files'
    )
SITE_ALIASES = {'WombatStateForest': 'WombatForest'}

#------------------------------------------------------------------------------


@dataclass(frozen=True)
class SiteContext:
    """
    Combined runtime objects for a configured site.
    """

    runtime_config: SiteRuntimeConfig
    metadata: SiteMetadata

#------------------------------------------------------------------------------


class SiteRegistry:
    """
    Authoritative registry of configured/processable sites.

    A site exists if and only if a site-level runtime configuration
    YML file exists.
    """

    def __init__(
            self,
            metadata_loader: Callable[[], dict[str, SiteMetadata]],
            runtime_config_loader: Callable[[str], SiteRuntimeConfig],
            ):

        self._metadata_loader = metadata_loader
        self._runtime_config_loader = runtime_config_loader

    #--------------------------------------------------------------------------

    def names(self) -> list[str]:
        """
        Return all configured site names.
        """

        return sorted(
            path.stem
            for path in SITE_CONFIG_DIR.glob('*.yml')
            )

    #--------------------------------------------------------------------------

    def exists(self, site: str) -> bool:
        """
        Return True if site is configured.
        """

        return (SITE_CONFIG_DIR / f'{site}.yml').exists()

    #--------------------------------------------------------------------------

    def require(self, site: str) -> None:
        """
        Validate configured site existence.
        """

        if not self.exists(site):
            raise InvalidSiteError(
                f"Configured site does not exist: {site}"
            )

    #--------------------------------------------------------------------------

    def get_config_path(self, site: str) -> Path:
        """
        Return runtime config path for site.
        """

        self.require(site)

        return SITE_CONFIG_DIR / f'{site}.yml'

    #--------------------------------------------------------------------------

    def get_runtime_config(
            self,
            site: str,
            ) -> SiteRuntimeConfig:
        """
        Load runtime configuration for site.
        """

        self.require(site)
        
        config_path = self.get_config_path(site=site)
        
        return self._runtime_config_loader(config_path)

    #--------------------------------------------------------------------------

    def get_metadata(
            self,
            site: str,
            ) -> SiteMetadata:
        """
        Load site metadata.
        """

        self.require(site)
        site_alias = SITE_ALIASES.get(site, site)
        metadata = self._metadata_loader().get(site_alias)
        if metadata is None:
            raise InvalidSiteError(f'No metadata for site {site}!')
        return metadata

    #--------------------------------------------------------------------------

    def get_context(
            self,
            site: str,
            ) -> SiteContext:
        """
        Assemble combined site context object.
        """

        return SiteContext(
            runtime_config=self.get_runtime_config(site),
            metadata=self.get_metadata(site)
        )

#------------------------------------------------------------------------------

