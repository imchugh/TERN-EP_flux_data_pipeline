"""Content-hash-addressed persistent cache of clean instrument-validation passes.

Shared across processes/hosts via a single JSON file in the site_configs
repo, keyed by SHA-256 of the exact validated file bytes — never by path,
site name, or commit. A git rollback to a byte-identical prior config
version transparently hits the cache with no special-casing.

A cache MISS means "unknown", never "invalid": callers must run real
validation and only call record() after a clean pass, so a failing config
never poisons the cache.
"""

import fcntl
import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

from infrastructure import file_io, paths

logger = logging.getLogger(__name__)

CACHE_PATH = paths.get_local_stream_path(
    resource="configs", stream="instrument_validation_cache"
)
LOCK_PATH = CACHE_PATH.with_name(CACHE_PATH.name + ".lock")


class CacheEntry(TypedDict):
    """A single content-hash-keyed cached validation record."""

    label: str | None
    validated_at: str
    instrument_uris: dict[str, str | None]


def hash_bytes(content: bytes) -> str:
    """Return the SHA-256 hex digest identifying exact config content."""
    return hashlib.sha256(content).hexdigest()


def hash_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file's current on-disk bytes."""
    return hash_bytes(Path(path).read_bytes())


def _load() -> dict[str, CacheEntry]:
    if not CACHE_PATH.exists():
        return {}
    try:
        return file_io.read_json(CACHE_PATH)
    except (ValueError, OSError):
        logger.warning(
            "Instrument validation cache at %s is unreadable; treating as empty",
            CACHE_PATH,
        )
        return {}


def lookup(content_hash: str) -> CacheEntry | None:
    """Return the cached entry for content_hash, or None on a miss."""
    return _load().get(content_hash)


def record(
    content_hash: str,
    *,
    instrument_uris: dict[str, str | None],
    label: str | None = None,
) -> None:
    """Record a clean validation pass for content_hash.

    Safe for concurrent callers (threads within one process, or two
    overlapping cron processes): the read-modify-write cycle is
    serialized with an flock on a sidecar lock file; the write itself is
    temp-file + fsync + atomic rename (file_io.write_json).
    """
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.touch(exist_ok=True)

    with open(LOCK_PATH, "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            cache = _load()
            cache[content_hash] = {
                "label": label,
                "validated_at": datetime.now(UTC).isoformat(),
                "instrument_uris": instrument_uris,
            }
            file_io.write_json(file_path=CACHE_PATH, data=cache, sort_keys=True)
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)
