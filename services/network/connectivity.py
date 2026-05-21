#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Daily network scan state updater.

Purpose:
    - Scan all configured sites
    - Persist ONLY operational state
    - Track last successful connection timestamp
    - Maintain consecutive failure counts

Designed for cron/systemd timer execution.
"""

###############################################################################
### BEGIN IMPORTS ###
###############################################################################

from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

# -----------------------------------------------------------------------------

from infrastructure.connections import scan_tcp_port, PortScanError
from infrastructure.file_io import read_json, write_json
from infrastructure.datetime_utils import get_utc_now
from infrastructure import paths
from services import config_loader

###############################################################################
### END IMPORTS ###
###############################################################################



###############################################################################
### BEGIN INITS ###
###############################################################################

logger = logging.getLogger(__name__)

SITE_IP = config_loader.load_config_file_from_name('vpn_ip')
STATE_PATH = (
    paths.get_local_stream_path(resource='network', stream='state') / 
    'hardware_connections.json'
    )

DEFAULT_STATE = {
    "updated_at": None,
    "sites": {}
}

SUBNET_IP = {'gateway': 1, 'ec': 100, 'soil': 101, 'profile': 102}
LOGGER_DEFAULT_PORT = 6785

###############################################################################
### END INITS ###
###############################################################################

@dataclass(frozen=True)
class ConnectivityCheckResult:
    
    reachable: bool
    port: int
    latency_ms: int | None = None
    error: str | None = None
    
###############################################################################
### BEGIN FUNCTIONS ###
###############################################################################

# -----------------------------------------------------------------------------
def resolve_endpoint(vpn_ip, logger_type='ec'):
    
    if logger_type not in SUBNET_IP:
        raise ValueError(
            f'Logger type {logger_type} not implemented. '
            f'Choices: {list(SUBNET_IP.keys())}'
            )
    subnet_addr = SUBNET_IP[logger_type]
    return f'192.168.{str(vpn_ip.split('.')[-1])}.{subnet_addr}'
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def load_state(path: Path = STATE_PATH) -> dict:
    """
    Load existing network state file.
    """

    if not path.exists():
        return deepcopy(DEFAULT_STATE)

    return read_json(file_path=path)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def save_state(state: dict, path: Path = STATE_PATH) -> None:
    """
    Save state file.
    """

    write_json(file_path=path, data=state, sort_keys=True)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def ensure_site_hardware_block(
        state: dict,
        site_name: str,
        hardware: str
        ) -> dict:
    """
    Ensure nested state structure exists.
    """

    sites = state.setdefault("sites", {})
    site_block = sites.setdefault(site_name, {})

    hw_block = site_block.setdefault(
        hardware,
        {
            "last_attempt": None,
            "last_success": None,
            "last_latency_ms": None,
            "consecutive_failures": 0,
            },
        )

    return hw_block
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def update_state_from_scan(
        state: dict,
        scan_results: dict,
        hardware: str
        ) -> dict:
    """
    Update state using current scan results.
    """

    now = get_utc_now(as_iso=True)

    for site_name, result in scan_results.items():

        hw_block = ensure_site_hardware_block(
            state=state,
            site_name=site_name,
            hardware=hardware,
        )

        hw_block["last_attempt"] = now

        if result.reachable:

            hw_block["last_success"] = now
            hw_block["last_latency_ms"] = result.latency_ms
            hw_block["consecutive_failures"] = 0

        else:

            hw_block["consecutive_failures"] += 1

    state["updated_at"] = now

    return state
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def run_endpoint_scan(host, port):
    
    try:

        result = scan_tcp_port(
            host=host, 
            port=port
            )

        output = ConnectivityCheckResult(
            reachable=True, 
            port=port, 
            latency_ms=result.latency_ms
            )

    except PortScanError as exc:

        output = ConnectivityCheckResult(
            reachable=False, 
            port=port,
            error=exc
            )
        
    return output
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def run_network_scan(hardware: str="gateway") -> dict:
    """
    Execute network scan and persist state.
    """

    logger.info(
        "daily_network_scan_start",
        extra={"hardware": hardware},
    )

    # Load existing state
    state = load_state()

    # Run scan
    results = {}
    for site, hardware_config in SITE_IP.items():

        host = hardware_config['host']
        port = hardware_config['port']
        if hardware != 'gateway':
            host = resolve_endpoint(vpn_ip=host, logger_type=hardware)
            port = LOGGER_DEFAULT_PORT
            
        results[site] = run_endpoint_scan(
            host=host, 
            port=port
            )

    # Update operational state
    state = update_state_from_scan(
        state=state,
        scan_results=results,
        hardware=hardware,
        )

    # Persist
    save_state(state)

    logger.info(
        "daily_network_scan_complete",
        extra={
            "hardware": hardware,
            "site_count": len(results),
        },
    )

    return state
# -----------------------------------------------------------------------------

# ###############################################################################
# ### END FUNCTIONS ###
# ###############################################################################



# ###############################################################################
# ### BEGIN SCRIPT ###
# ###############################################################################

# if __name__ == "__main__":

#     # Example:
#     # Scan gateways daily
#     run_daily_scan(hardware="gateway")

#     # Optional:
#     # run_daily_scan(hardware="EC")
#     # run_daily_scan(hardware="soil")

# ###############################################################################
# ### END SCRIPT ###
# ###############################################################################