# -*- coding: utf-8 -*-
"""
Path resolver for local and remote data streams.

Driven by configs/paths.yml.  Local paths resolve to pathlib.Path objects;
remote paths resolve to rclone designator strings (e.g. 'uqrdm:...').
"""

import pathlib

from pydantic import BaseModel

from infrastructure import file_io

###############################################################################
### BEGIN INITS ###
###############################################################################

CONFIG_PATH = pathlib.Path(__file__).parents[1] / 'configs'
CONFIG_FILE = 'paths.yml'

_PLACEHOLDER = '<site>'

# -----------------------------------------------------------------------------

class _ResourceConfig(BaseModel):
    base_path: str
    stream: dict[str, str]


class _PathsConfig(BaseModel):
    local: dict[str, _ResourceConfig]
    remote: dict[str, _ResourceConfig]
    remote_aliases: dict[str, str] = {}


_PATHS = _PathsConfig.model_validate(
    file_io.read_yml(file_path=CONFIG_PATH / CONFIG_FILE)
    )

###############################################################################
### END INITS ###
###############################################################################


###############################################################################
### BEGIN FUNCTIONS ###
###############################################################################

def list_local_resources() -> list[str]:
    return list(_PATHS.local.keys())

# -----------------------------------------------------------------------------

def list_local_streams(resource: str) -> list[str]:
    return list(_PATHS.local[resource].stream.keys())

# -----------------------------------------------------------------------------

def list_remote_resources() -> list[str]:
    return list(_PATHS.remote.keys())

# -----------------------------------------------------------------------------

def list_remote_streams(resource: str) -> list[str]:
    return list(_PATHS.remote[resource].stream.keys())

# -----------------------------------------------------------------------------

def get_local_resource_path(resource: str) -> pathlib.Path:
    return pathlib.Path(_PATHS.local[resource].base_path)

# -----------------------------------------------------------------------------

def get_local_stream_path(
        resource: str, stream: str, site: str | None = None
        ) -> pathlib.Path:
    """
    Resolve a local stream to a filesystem path.

    Args:
        resource: top-level resource key (e.g. 'raw_data').
        stream: stream key within that resource (e.g. 'flux_slow').
        site: site name — substituted for the '<site>' placeholder where
            present.

    Returns:
        Resolved pathlib.Path.
    """

    cfg = _PATHS.local[resource]
    path = pathlib.Path(cfg.base_path) / cfg.stream[stream]
    if site is not None:
        path = pathlib.Path(str(path).replace(_PLACEHOLDER, site))
    return path

# -----------------------------------------------------------------------------

def get_remote_stream_path(
        resource: str, stream: str, site: str | None = None
        ) -> str:
    """
    Resolve a remote stream to an rclone designator string.

    Args:
        resource: top-level resource key (e.g. 'raw_data').
        stream: stream key within that resource (e.g. 'flux_slow').
        site: site name — substituted for the '<site>' placeholder where
            present.  Remote aliases are applied automatically.

    Returns:
        Rclone path string (e.g. 'uqrdm:TERNEP-Q5937/Sites/...').
    """

    cfg = _PATHS.remote[resource]
    stream_val = cfg.stream[stream]
    path = f'{cfg.base_path}/{stream_val}' if cfg.base_path else stream_val
    if site is not None:
        alias = _PATHS.remote_aliases.get(site, site)
        path = path.replace(_PLACEHOLDER, alias)
    return path

###############################################################################
### END FUNCTIONS ###
###############################################################################
