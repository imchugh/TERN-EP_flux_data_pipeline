#!/usr/bin/env python3

"""Daily network scan state updater.

Purpose:
    - Scan all configured sites
    - Persist ONLY operational state
    - Track last successful connection timestamp
    - Maintain consecutive failure counts

Designed for cron/systemd timer execution.
"""

import logging
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from infrastructure import paths
from infrastructure.connections import PortScanError, scan_tcp_port
from infrastructure.datetime_utils import get_utc_now
from infrastructure.file_io import read_json, write_json
from services import config_loader

logger = logging.getLogger(__name__)

SITE_IP = config_loader.load_config_file_from_name("vpn_ip")
STATE_DIR = paths.get_local_stream_path(resource="network", stream="state")

DEFAULT_STATE = {"updated_at": None, "sites": {}}

SUBNET_IP = {"gateway": 1, "ec": 100, "soil": 101, "profile": 102}
LOGGER_DEFAULT_PORT = 6785


@dataclass(frozen=True)
class ConnectivityCheckResult:
    """Result of one TCP connectivity scan against a site endpoint."""

    reachable: bool
    port: int
    latency_ms: int | None = None
    error: str | None = None


def connectivity_sites() -> list[str]:
    """Return site names available for connectivity scanning."""
    return list(SITE_IP.keys())


def resolve_endpoint(vpn_ip: str, logger_type: str = "ec") -> str:
    """Build the on-site subnet IP for a logger type from its VPN gateway IP."""
    if logger_type not in SUBNET_IP:
        raise ValueError(
            f"Logger type {logger_type} not implemented. "
            f"Choices: {list(SUBNET_IP.keys())}"
        )
    subnet_addr = SUBNET_IP[logger_type]
    return f"192.168.{vpn_ip.split('.')[-1]}.{subnet_addr}"


def load_state(path: Path) -> dict[str, Any]:
    """Load existing network state file."""
    if not path.exists():
        return deepcopy(DEFAULT_STATE)

    return read_json(file_path=path)


def save_state(state: dict[str, Any], path: Path) -> None:
    """Save state file."""
    write_json(file_path=path, data=state, sort_keys=True)


def ensure_site_block(
    state: dict[str, Any],
    site_name: str,
) -> dict[str, Any]:
    """Ensure per-site state block exists, returning it for in-place mutation."""
    return state.setdefault("sites", {}).setdefault(
        site_name,
        {
            "last_attempt": None,
            "last_success": None,
            "last_latency_ms": None,
            "consecutive_failures": 0,
        },
    )


def run_endpoint_scan(host: str, port: int) -> ConnectivityCheckResult:
    """Scan one host/port endpoint, wrapping the result as a ConnectivityCheckResult."""
    try:
        result = scan_tcp_port(
            host=host,
            port=port,
        )

        output = ConnectivityCheckResult(
            reachable=True,
            port=port,
            latency_ms=result.latency_ms,
        )

    except PortScanError as exc:
        output = ConnectivityCheckResult(
            reachable=False,
            port=port,
            error=str(exc),
        )

    return output


def run_site_connectivity(site: str, hardware: str = "gateway") -> dict[str, Any]:
    """Run a connectivity check for a single site.

    Intended as the per-site callable for ``run_task_for_all_sites`` in the
    orchestrator. Returns a plain dict so results are immediately serialisable
    and consistent with the ``{'error': ...}`` dicts emitted by the concurrent
    runner on failure.

    Args:
        site: Site name as it appears in the VPN IP config.
        hardware: Hardware type to scan. One of 'gateway', 'ec', 'soil',
            'profile'. Defaults to 'gateway'.

    Returns:
        Dict with keys: reachable, port, latency_ms, error.

    Raises:
        KeyError: If site is not present in the VPN IP config.
    """
    if site not in SITE_IP:
        raise KeyError(f"Site {site!r} not found in VPN IP config")

    hardware_config = SITE_IP[site]
    host = hardware_config["host"]
    port = hardware_config["port"]

    if hardware != "gateway":
        host = resolve_endpoint(vpn_ip=host, logger_type=hardware)
        port = LOGGER_DEFAULT_PORT

    result = run_endpoint_scan(host=host, port=port)

    return {
        "reachable": result.reachable,
        "port": result.port,
        "latency_ms": result.latency_ms,
        "error": str(result.error) if result.error is not None else None,
    }


def persist_connectivity_state(
    results: dict[str, Any],
    task_name: str,
) -> None:
    """Stateful read-modify-write persist function for connectivity scan results.

    Loads the per-hardware state file (``<STATE_DIR>/<task_name>.json``),
    merges new scan results into each site block, then writes the updated state
    back. Matches the ``Callable[[dict, str], None]`` persist interface expected
    by ``run_task_for_all_sites``.

    Consecutive-failure counters are preserved across runs: a reachable result
    resets the counter; any other result (unreachable or error dict) increments
    it.

    Args:
        results: Per-site results as returned by ``run_site_connectivity``, or
            ``{'error': <str>}`` dicts emitted by the concurrent runner for
            sites that raised exceptions.
        task_name: Hardware type label (e.g. ``'gateway'``, ``'ec'``). Used to
            derive the state file path (``<STATE_DIR>/<task_name>.json``).
    """
    path = STATE_DIR / f"{task_name}.json"
    state = load_state(path=path)
    now = get_utc_now(as_iso=True)

    for site_name, result in results.items():
        site_block = ensure_site_block(state=state, site_name=site_name)
        site_block["last_attempt"] = now

        if isinstance(result, dict) and result.get("reachable"):
            site_block["last_success"] = now
            site_block["last_latency_ms"] = result.get("latency_ms")
            site_block["consecutive_failures"] = 0
        else:
            site_block["consecutive_failures"] += 1

    state["updated_at"] = now
    save_state(state=state, path=path)
