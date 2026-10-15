#!/usr/bin/env python3
"""TERN instrument-vocabulary lookups, alias mapping, and name corrections."""

import functools
import logging

from rapidfuzz import fuzz, process

from infrastructure import config_loader
from services.metadata.site_metadata_repository import get_instrument_vocab

logger = logging.getLogger(__name__)


def _normalize_key(label: str) -> str:
    """Case-fold a vocab category label for case-insensitive lookup."""
    return label.strip().casefold()


@functools.lru_cache(maxsize=1)
def get_raw_vocab() -> list[dict]:
    """Return the raw SPARQL bindings (fetched once per process)."""
    return get_instrument_vocab()


@functools.lru_cache(maxsize=1)
def _get_vocab_registry() -> dict[str, list[str]]:
    """Build the raw TERN vocab registry keyed by vocab category label.

    The SPARQL query uses skos:broader+ (transitive), producing one row per
    (concept x ancestor). We identify the direct-parent row by checking
    broader_chain == broader, then exclude category nodes (any URI that itself
    appears as a broader reference) so only leaf instruments are listed.
    """
    data = get_raw_vocab()

    # Any URI used as a broader reference is a category node, not a leaf instrument
    parent_uris = {entry["broader"] for entry in data if entry.get("broader")}

    registry: dict[str, set[str]] = {}
    for entry in data:
        if entry.get("is_top_concept") == "true":
            continue
        if entry["uri"] in parent_uris:
            continue
        if entry.get("broader_chain") != entry.get("broader"):
            continue
        cat = entry.get("broader_chain_label")
        if cat:
            registry.setdefault(_normalize_key(cat), set()).add(entry["label"])

    return {k: sorted(v) for k, v in sorted(registry.items())}


@functools.lru_cache(maxsize=1)
def _load_quantity_map() -> dict:
    """Load instrument_quantity_map.yml: alias entries plus flux_quantities."""
    return config_loader.load_config_file_from_name("instrument_quantity_map")


def _get_alias_map() -> dict[str, dict]:
    """Alias entries from instrument_quantity_map.yml (excludes flux_quantities)."""
    return {k: v for k, v in _load_quantity_map().items() if k != "flux_quantities"}


def _get_flux_quantities() -> dict[str, list[str]]:
    """Compound flux quantity definitions from instrument_quantity_map.yml."""
    return _load_quantity_map().get("flux_quantities", {})


@functools.lru_cache(maxsize=1)
def _load_name_corrections() -> dict:
    """Load instrument_name_corrections.yml ({} if the file doesn't exist)."""
    try:
        return config_loader.load_config_file_from_name("instrument_name_corrections")
    except FileNotFoundError:
        logger.debug("No instrument_name_corrections config found")
        return {}


def _get_name_corrections() -> dict[str, str]:
    """Preferred name → vocab label, for incorrectly named vocab entries."""
    return _load_name_corrections().get("corrections", {}) or {}


def _get_pending_instruments() -> dict[str, str]:
    """Pending instrument names (no vocab entry yet), mapped to alias category."""
    return _load_name_corrections().get("pending", {}) or {}


@functools.lru_cache(maxsize=1)
def _get_label_uris() -> dict[str, str]:
    """Return the vocab label → URI map."""
    uri_label = {
        e["uri"]: e["label"] for e in get_raw_vocab() if e.get("uri") and e.get("label")
    }
    return {label: uri for uri, label in uri_label.items()}


def _get_vocab_keys(alias: str) -> list[str]:
    alias_map = _get_alias_map()
    if alias not in alias_map:
        raise KeyError(
            f"Unknown instrument alias {alias!r}. Valid aliases: {list(alias_map)}"
        )
    return alias_map[alias]["vocab_keys"]


def list_instruments(instrument_type: str) -> list[str]:
    """Return all instruments for a given alias.

    Args:
        instrument_type: clean alias (e.g. 'sonic_anemometer'), not the raw
            vocab label.

    Returns:
        Sorted list of instrument names from the TERN vocabulary, merged
        across all vocab_keys configured for the alias.
    """
    vocab_keys = _get_vocab_keys(instrument_type)
    vocab_registry = _get_vocab_registry()
    missing = [k for k in vocab_keys if _normalize_key(k) not in vocab_registry]
    if missing:
        raise KeyError(
            f"Alias {instrument_type!r} has vocab_keys not found in the TERN "
            f"vocabulary: {missing}. Available: {list(vocab_registry)}"
        )
    instruments: set[str] = set()
    for k in vocab_keys:
        instruments.update(vocab_registry[_normalize_key(k)])
    return sorted(instruments)


def list_quantities(instrument_type: str) -> list[str]:
    """Return canonical quantity keys measured by a given instrument alias."""
    alias_map = _get_alias_map()
    if instrument_type not in alias_map:
        raise KeyError(
            f"Unknown instrument alias {instrument_type!r}. "
            f"Valid aliases: {list(alias_map)}"
        )
    return alias_map[instrument_type]["quantities"]


def is_compound_quantity(quantity: str) -> bool:
    """Return True if a quantity requires more than one instrument type."""
    flux_quantities = _get_flux_quantities()
    return quantity in flux_quantities and len(flux_quantities[quantity]) > 1


def get_quantity_components(quantity: str) -> list[str]:
    """Return the instrument aliases required for a compound quantity.

    Args:
        quantity: compound canonical quantity key (e.g. 'Fco2').

    Returns:
        List of instrument aliases (e.g. ['irga', 'sonic_anemometer']).

    Raises:
        KeyError: if quantity is not a known compound quantity.
    """
    flux_quantities = _get_flux_quantities()
    if quantity not in flux_quantities:
        raise KeyError(
            f"{quantity!r} is not a compound quantity. "
            f"Known compound quantities: {list(flux_quantities)}"
        )
    return flux_quantities[quantity]


def get_instrument_type(name: str) -> str:
    """Return the alias for a given instrument label.

    Args:
        name: specific instrument label (e.g. 'HMP155A').

    Returns:
        Clean alias (e.g. 'temperature_humidity').
    """
    pending = _get_pending_instruments()
    if name in pending:
        return pending[name]

    alias_map = _get_alias_map()
    vocab_registry = _get_vocab_registry()
    resolved = _get_name_corrections().get(name, name)

    for alias, cfg in alias_map.items():
        if any(
            resolved in vocab_registry.get(_normalize_key(k), [])
            for k in cfg["vocab_keys"]
        ):
            return alias
    raise KeyError(f"Unknown instrument {name!r}")


def is_valid_instrument(name: str) -> bool:
    """Return True if name is a known instrument label under any configured alias.

    Also accepts names listed as keys in instrument_name_corrections.yml.
    For those, validation is against the full TERN vocab (not just aliased
    categories) because the underlying vocab entry may be in an unmapped
    category — the correction itself is the assertion that it exists.
    """
    if name in _get_pending_instruments():
        return True

    corrections = _get_name_corrections()
    vocab_registry = _get_vocab_registry()

    if name in corrections:
        resolved = corrections[name]
        return any(resolved in insts for insts in vocab_registry.values())

    alias_map = _get_alias_map()
    return any(
        name in vocab_registry.get(_normalize_key(k), [])
        for cfg in alias_map.values()
        for k in cfg["vocab_keys"]
    )


def list_instruments_for_quantity(quantity: str) -> list[str]:
    """Return all instruments that measure a given simple (non-compound) quantity.

    Args:
        quantity: canonical quantity key (e.g. 'Ta').

    Returns:
        Sorted list of instrument names, merged across all aliases that
        include the quantity.

    Raises:
        KeyError: if quantity is compound — use
            list_instruments_for_compound_quantity() instead.
    """
    if is_compound_quantity(quantity):
        raise KeyError(
            f"{quantity!r} is a compound quantity requiring multiple instrument "
            f"types. Use list_instruments_for_compound_quantity() instead."
        )
    alias_map = _get_alias_map()
    vocab_registry = _get_vocab_registry()

    instruments: set[str] = set()
    for cfg in alias_map.values():
        if quantity in cfg.get("quantities", []):
            for k in cfg["vocab_keys"]:
                instruments.update(vocab_registry.get(_normalize_key(k), []))

    pending = _get_pending_instruments()
    for name, alias in pending.items():
        if alias in alias_map and quantity in alias_map[alias].get("quantities", []):
            instruments.add(name)

    return sorted(instruments)


def list_instruments_for_compound_quantity(quantity: str) -> dict[str, list[str]]:
    """Return instruments needed for a compound quantity, grouped by alias.

    Args:
        quantity: compound canonical quantity key (e.g. 'Fco2').

    Returns:
        Dict keyed by instrument alias, values are sorted instrument lists.
        e.g. {'irga': [...], 'sonic_anemometer': [...]}

    Raises:
        KeyError: if quantity is not a known compound quantity.
    """
    components = get_quantity_components(quantity)
    pending = _get_pending_instruments()

    result = {}
    for alias in components:
        instruments = set(list_instruments(alias))
        for name, p_alias in pending.items():
            if p_alias == alias:
                instruments.add(name)
        result[alias] = sorted(instruments)
    return result


def get_instrument_uri(name: str) -> str:
    """Return the TERN vocabulary URI for a given instrument label.

    Args:
        name: instrument label (e.g. 'LI-7500RS').

    Returns:
        URI string from the TERN controlled vocabulary.

    Raises:
        KeyError: if name is not a known instrument label.
    """
    resolved = _get_name_corrections().get(name, name)
    label_uris = _get_label_uris()
    if resolved not in label_uris:
        raise KeyError(f"Unknown instrument {name!r}")
    return label_uris[resolved]


def suggest_instruments(
    name: str,
    n: int = 5,
    score_cutoff: float = 60.0,
) -> list[tuple[str, float]]:
    """Return top-n fuzzy matches from the full TERN vocab.

    Uses rapidfuzz.token_set_ratio, which handles word-order and
    brand-prefix variation.

    Args:
        name: instrument label to match (need not be in the vocab).
        n: maximum number of suggestions to return.
        score_cutoff: minimum similarity score 0–100 to include a candidate.

    Returns:
        List of (instrument_label, score) tuples, sorted descending by score.
    """
    vocab_registry = _get_vocab_registry()
    seen: set[str] = set()
    # Preferred/pending names come first so they win score ties over the
    # (wrong or absent) vocab labels they correspond to.
    candidates: list[str] = []
    for preferred in list(_get_name_corrections()) + list(_get_pending_instruments()):
        if preferred not in seen:
            seen.add(preferred)
            candidates.append(preferred)
    for insts in vocab_registry.values():
        for inst in insts:
            if inst not in seen:
                seen.add(inst)
                candidates.append(inst)

    results = process.extract(
        name,
        candidates,
        scorer=fuzz.token_set_ratio,
        score_cutoff=score_cutoff,
        limit=n,
    )
    return [(match, float(score)) for match, score, _ in results]
