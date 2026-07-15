# -*- coding: utf-8 -*-
"""
Path resolver for local and remote data streams.

Driven by configs/paths.yml. Each resource groups related streams under an
optional shared base path; each stream carries a local suffix, a remote
designator, or both. Local paths resolve to pathlib.Path objects; remote
paths resolve to rclone designator strings (e.g. 'uqrdm:...').
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


class _StreamConfig(BaseModel):
    local: str | None = None
    remote: str | None = None


class _ResourceConfig(BaseModel):
    base_path: dict[str, str] = {}
    stream: dict[str, _StreamConfig]


_RAW = file_io.read_yml(file_path=CONFIG_PATH / CONFIG_FILE)

REMOTE_ALIASES: dict[str, str] = _RAW.pop('remote_aliases', {})

RESOURCES: dict[str, _ResourceConfig] = {
    name: _ResourceConfig.model_validate(cfg) for name, cfg in _RAW.items()
    }

###############################################################################
### END INITS ###
###############################################################################


###############################################################################
### BEGIN FUNCTIONS ###
###############################################################################

def _resolve(resource: str, stream: str, kind: str, site: str | None) -> str:

    cfg = RESOURCES[resource]
    suffix = getattr(cfg.stream[stream], kind)
    if suffix is None:
        raise KeyError(f"No {kind} path configured for '{resource}.{stream}'")

    base = cfg.base_path.get(kind)
    path = f'{base}/{suffix}' if base else suffix

    if site is not None:
        if kind == 'remote':
            site = REMOTE_ALIASES.get(site, site)
        path = path.replace(_PLACEHOLDER, site)

    return path

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

    return pathlib.Path(_resolve(resource, stream, 'local', site))

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
            present. Remote aliases are applied automatically.

    Returns:
        Rclone path string (e.g. 'uqrdm:TERNEP-Q5937/Sites/...').
    """

    return _resolve(resource, stream, 'remote', site)

# -----------------------------------------------------------------------------

def show(resource: str | None = None) -> None:
    """
    Print a quick-reference overview of configured resources and streams.

    Args:
        resource: if given, print only this resource's streams, with local
            and remote templates filled in. If omitted, list all resources
            and their stream names.

    Returns:
        None.
    """

    if resource is None:
        for name, cfg in RESOURCES.items():
            print(f'{name}: {", ".join(cfg.stream)}')
        return

    cfg = RESOURCES[resource]
    for stream_name, stream_cfg in cfg.stream.items():
        print(f'{resource}.{stream_name}')
        if stream_cfg.local is not None:
            base = cfg.base_path.get('local')
            local = f'{base}/{stream_cfg.local}' if base else stream_cfg.local
            print(f'    local:  {local}')
        if stream_cfg.remote is not None:
            base = cfg.base_path.get('remote')
            remote = f'{base}/{stream_cfg.remote}' if base else stream_cfg.remote
            print(f'    remote: {remote}')

###############################################################################
### END FUNCTIONS ###
###############################################################################
