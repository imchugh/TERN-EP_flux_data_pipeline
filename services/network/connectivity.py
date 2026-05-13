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

import json
import logging
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

# -----------------------------------------------------------------------------

from services.network_scanner import scan_network

###############################################################################
### END IMPORTS ###
###############################################################################



###############################################################################
### BEGIN INITS ###
###############################################################################

logger = logging.getLogger(__name__)

STATE_PATH = Path("/opt/TERN_EP/state/network_last_seen.json")

DEFAULT_STATE = {
    "updated_at": None,
    "sites": {}
}

###############################################################################
### END INITS ###
###############################################################################



###############################################################################
### BEGIN FUNCTIONS ###
###############################################################################

# -----------------------------------------------------------------------------
def load_state(path: Path = STATE_PATH) -> dict:
    """
    Load existing network state file.
    """

    if not path.exists():
        return deepcopy(DEFAULT_STATE)

    with open(path, "r") as f:
        return json.load(f)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def save_state(state: dict, path: Path = STATE_PATH) -> None:
    """
    Atomically save state file.
    """

    tmp_path = path.with_suffix(".tmp")

    with open(tmp_path, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)

    tmp_path.replace(path)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def utc_now_iso() -> str:
    """
    Generate UTC ISO8601 timestamp.
    """

    return datetime.now(timezone.utc).isoformat()
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

    now = utc_now_iso()

    for site_name, result in scan_results.items():

        hw_block = ensure_site_hardware_block(
            state=state,
            site_name=site_name,
            hardware=hardware,
        )

        hw_block["last_attempt"] = now

        if result["reachable"]:

            hw_block["last_success"] = now
            hw_block["last_latency_ms"] = result.get("latency_ms")
            hw_block["consecutive_failures"] = 0

        else:

            hw_block["consecutive_failures"] += 1

    state["updated_at"] = now

    return state
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def run_daily_scan(hardware: str = "gateway") -> dict:
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
    results = scan_network(hardware=hardware)

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

###############################################################################
### END FUNCTIONS ###
###############################################################################



###############################################################################
### BEGIN SCRIPT ###
###############################################################################

if __name__ == "__main__":

    # Example:
    # Scan gateways daily
    run_daily_scan(hardware="gateway")

    # Optional:
    # run_daily_scan(hardware="EC")
    # run_daily_scan(hardware="soil")

###############################################################################
### END SCRIPT ###
###############################################################################