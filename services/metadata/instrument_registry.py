#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@author: imchugh
"""

import functools

from services import config_loader
from services.metadata.site_metadata_repository import get_instrument_vocab


@functools.lru_cache(maxsize=1)
def get_raw_vocab() -> list[dict]:
    """Return the raw SPARQL bindings for inspection."""
    return get_instrument_vocab()


@functools.lru_cache(maxsize=1)
def _get_vocab_registry() -> dict[str, list[str]]:
    """Build the raw TERN vocab registry keyed by vocab category label.

    The SPARQL query uses skos:broader+ (transitive), producing one row per
    (concept x ancestor). We identify the direct-parent row by checking
    broader_chain == broader, then exclude category nodes (any URI that itself
    appears as a broader reference) so only leaf instruments are listed.
    """

    data = get_instrument_vocab()

    # Any URI used as a broader reference is a category node, not a leaf instrument
    parent_uris = {entry['broader'] for entry in data if entry.get('broader')}

    registry: dict[str, set[str]] = {}
    for entry in data:
        if entry.get('is_top_concept') == 'true':
            continue
        if entry['uri'] in parent_uris:
            continue
        if entry.get('broader_chain') != entry.get('broader'):
            continue
        cat = entry.get('broader_chain_label')
        if cat:
            registry.setdefault(cat, set()).add(entry['label'])

    return {k: sorted(v) for k, v in sorted(registry.items())}


@functools.lru_cache(maxsize=1)
def _get_alias_map() -> dict[str, dict]:
    """Load alias entries from config (excludes flux_quantities section)."""
    raw = config_loader.load_config_file_from_name('instrument_quantity_map')
    return {k: v for k, v in raw.items() if k != 'flux_quantities'}


@functools.lru_cache(maxsize=1)
def _get_name_corrections() -> dict[str, str]:
    """Load preferred→vocab-label corrections for incorrectly named vocab entries."""
    try:
        raw = config_loader.load_config_file_from_name('instrument_name_corrections')
        return raw.get('corrections', {}) or {}
    except Exception:
        return {}


@functools.lru_cache(maxsize=1)
def _get_pending_instruments() -> dict[str, str]:
    """Load pending instrument names (no vocab entry yet) mapped to their alias category."""
    try:
        raw = config_loader.load_config_file_from_name('instrument_name_corrections')
        return raw.get('pending', {}) or {}
    except Exception:
        return {}


@functools.lru_cache(maxsize=1)
def _get_flux_quantities() -> dict[str, list[str]]:
    """Load compound flux quantity definitions from config."""
    raw = config_loader.load_config_file_from_name('instrument_quantity_map')
    return raw.get('flux_quantities', {})


def _get_vocab_keys(alias: str) -> list[str]:
    alias_map = _get_alias_map()
    if alias not in alias_map:
        raise KeyError(
            f"Unknown instrument alias {alias!r}. "
            f"Valid aliases: {list(alias_map)}"
        )
    return alias_map[alias]['vocab_keys']


def list_types() -> list[str]:
    """Return all configured instrument aliases."""
    return list(_get_alias_map())


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
    missing = [k for k in vocab_keys if k not in vocab_registry]
    if missing:
        raise KeyError(
            f"Alias {instrument_type!r} has vocab_keys not found in the TERN "
            f"vocabulary: {missing}. Available: {list(vocab_registry)}"
        )
    instruments: set[str] = set()
    for k in vocab_keys:
        instruments.update(vocab_registry[k])
    return sorted(instruments)


def list_quantities(instrument_type: str) -> list[str]:
    """Return canonical quantity keys measured by a given instrument alias."""
    alias_map = _get_alias_map()
    if instrument_type not in alias_map:
        raise KeyError(
            f"Unknown instrument alias {instrument_type!r}. "
            f"Valid aliases: {list(alias_map)}"
        )
    return alias_map[instrument_type]['quantities']


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
        if any(resolved in vocab_registry.get(k, []) for k in cfg['vocab_keys']):
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
        name in vocab_registry.get(k, [])
        for cfg in alias_map.values()
        for k in cfg['vocab_keys']
    )


def get_quantities_for_instrument(name: str) -> list[str]:
    """Return the canonical quantities for a specific instrument label."""
    alias = get_instrument_type(name)
    return list_quantities(alias)


def list_instruments_for_quantity(quantity: str) -> list[str]:
    """Return all instruments that measure a given simple (non-compound) quantity.

    Args:
        quantity: canonical quantity key (e.g. 'Ta').

    Returns:
        Sorted list of instrument names, merged across all aliases that
        include the quantity.

    Raises:
        KeyError: if quantity is compound — use list_instruments_for_compound_quantity().
    """
    if is_compound_quantity(quantity):
        raise KeyError(
            f"{quantity!r} is a compound quantity requiring multiple instrument "
            f"types. Use list_instruments_for_compound_quantity() instead."
        )
    alias_map = _get_alias_map()
    vocab_registry = _get_vocab_registry()

    instruments: set[str] = set()
    for alias, cfg in alias_map.items():
        if quantity in cfg['quantities']:
            for k in cfg['vocab_keys']:
                instruments.update(vocab_registry.get(k, []))
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
    return {alias: list_instruments(alias) for alias in components}


def suggest_instruments(
    name: str,
    n: int = 5,
    score_cutoff: float = 60.0,
) -> list[tuple[str, float]]:
    """Return top-n fuzzy matches from the full TERN vocab.

    Uses rapidfuzz.token_set_ratio when available (handles word-order and
    brand-prefix variation); falls back to difflib.SequenceMatcher.

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

    try:
        from rapidfuzz import fuzz, process
        results = process.extract(
            name,
            candidates,
            scorer=fuzz.token_set_ratio,
            score_cutoff=score_cutoff,
            limit=n,
        )
        return [(match, float(score)) for match, score, _ in results]
    except ImportError:
        import difflib
        close = difflib.get_close_matches(name, candidates, n=n, cutoff=score_cutoff / 100)
        return [
            (m, round(difflib.SequenceMatcher(None, name.lower(), m.lower()).ratio() * 100, 1))
            for m in close
        ]
