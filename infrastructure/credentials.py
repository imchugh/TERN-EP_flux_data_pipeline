"""Read service logins from the local secrets file.

The file is the ``configs``/``secrets`` stream in ``paths.yml``
(``/opt/TERN_EP/secrets/logins.yml``), kept outside every git repo and
readable only by the pipeline user. It is a YAML mapping of one section per
service. A section is either a single login::

    SITE_DETAILS: {USERNAME: ..., PASSWORD: ...}

or a mapping of named logins, e.g. one per site::

    LOGGERS:
      Calperum: {USERNAME: admin, PASSWORD: <logger UID>}

Never log the values returned here.
"""

import pathlib
from functools import cache

from infrastructure import config_loader, paths

Login = tuple[str, str]


def secrets_path() -> pathlib.Path:
    """Return the path of the secrets file."""
    return paths.get_local_stream_path(resource="configs", stream="secrets")


@cache
def load_secrets() -> dict:
    """Return the whole secrets file (read once per process)."""
    return config_loader.load_config_file(file=secrets_path()) or {}


def get_login(
    section: str, entry: str | None = None, *, required: bool = True
) -> Login | None:
    """Return a ``(USERNAME, PASSWORD)`` login from the secrets file.

    Args:
        section: Top-level section name (e.g. ``'SITE_DETAILS'``).
        entry: Named login within the section (e.g. a site name), for
            sections that hold several. None for a single-login section.
        required: If True, a missing section or entry raises; if False it
            returns None (for services where only some targets need a login).

    Returns:
        ``(username, password)``, or None when not found and not ``required``.

    Raises:
        KeyError: if the login is missing and ``required`` is True.
    """
    login = load_secrets().get(section)
    if login is not None and entry is not None:
        login = login.get(entry)
    if login is None:
        if required:
            where = section if entry is None else f"{section}.{entry}"
            raise KeyError(f"No login {where!r} in {secrets_path()}")
        return None
    return login["USERNAME"], login["PASSWORD"]
