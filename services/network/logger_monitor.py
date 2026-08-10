#!/usr/bin/env python3
"""Logger last-contact status check."""

import logging
from typing import Any

from infrastructure import logger_functions
from services.network.connectivity import SITE_IP, resolve_endpoint

logger = logging.getLogger(__name__)

SUMMARY_SUBSET = ["model"]
STATUS_SUBSET = [
    "SerialNumber",
    "OSVersion",
    "ProgName",
    "CardStatus",
    "Battery",
    "LithiumBattery",
    "SkippedScan",
    "WatchdogErrors",
]
NULL_RESULT: dict[str, Any] = {key: None for key in SUMMARY_SUBSET + STATUS_SUBSET} | {
    "error": None
}


def get_logger_status(ip_addr: str) -> dict[str, Any]:
    """Fetch and filter status fields from a Campbell datalogger.

    Calls the logger HTTP API, then extracts the ``model`` field from the
    environment summary and the fields listed in ``STATUS_SUBSET`` from the
    status table.

    Args:
        ip_addr: IP address of the datalogger.

    Returns:
        Flat dict containing ``model`` plus each field in ``STATUS_SUBSET``.
        Does not include an ``error`` key; see ``check_logger_status`` for
        the full uniform-shape result.
    """
    logger.debug("get_logger_status", extra={"ip_addr": ip_addr})
    summary, status = logger_functions.get_logger_status(ip_addr=ip_addr)
    return {key: summary[key] for key in SUMMARY_SUBSET} | {
        key: status[key] for key in STATUS_SUBSET
    }


def check_logger_status(site: str) -> dict[str, Any]:
    """Fetch datalogger status for a named pipeline site.

    Resolves the site's EC logger IP address from the VPN IP config and
    delegates to ``get_logger_status``. Network and API errors are caught and
    returned as a ``NULL_RESULT`` with the ``error`` key populated, so the
    output shape is always identical regardless of reachability. This allows
    the downstream aggregator to merge state files without needing per-task
    schema knowledge.

    Configuration errors (unknown site) are not caught and will propagate,
    since those indicate an operator mistake rather than a runtime failure.

    Args:
        site: Site name as it appears in the VPN IP config.

    Returns:
        Dict containing ``model``, each field in ``STATUS_SUBSET``, and
        ``error`` (``None`` on success, error string on failure).

    Raises:
        KeyError: If ``site`` is not present in the VPN IP config.
    """
    if site not in SITE_IP:
        raise KeyError(f"Site {site!r} not found in VPN IP config")

    ip_addr = resolve_endpoint(vpn_ip=SITE_IP[site]["host"], logger_type="ec")
    logger.info("check_logger_status", extra={"site": site, "ip_addr": ip_addr})

    try:
        return get_logger_status(ip_addr=ip_addr) | {"error": None}
    except Exception as exc:
        logger.warning(
            "logger_status_failed",
            extra={"site": site, "ip_addr": ip_addr, "error": str(exc)},
        )
        return NULL_RESULT | {"error": str(exc)}
