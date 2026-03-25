#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Feb 26 09:44:00 2026

@author: imchugh
"""

import logging
import socket
import time

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
def scan_endpoint(host: str, ports: list[int], timeout: float = 2.0) -> dict:
    """
    Attempt to connect to an IP endpoint on one or more ports.

    Args:
        ip: IP address of the endpoint to scan.
        ports: List of ports to attempt in order.
        timeout: Connection timeout per port in seconds.

    Returns:
        dict containing:
            - reachable (bool)
            - port (int | None)
            - latency_ms (int | None)

    Raises:
        RuntimeError: If none of the ports are reachable.
    """
    # logger.debug(
    #     "scan_endpoint_start",
    #     extra={"ip": ip, "ports": ports, "timeout_s": timeout},
    # )

    for port in ports:
        start_time = time.monotonic()
        try:
            logger.debug(
                "trying_port",
                extra={"host": host, "port": port},
            )

            with socket.create_connection((host, port), timeout=timeout):
                latency_ms = int((time.monotonic() - start_time) * 1000)
                logger.debug(
                    "port_reachable",
                    extra={
                        "host": host,
                        "port": port,
                        "latency_ms": latency_ms,
                    },
                )
                return {
                    "reachable": True,
                    "port": port,
                    "latency_ms": latency_ms,
                }

        except OSError as exc:
            logger.debug(
                "port_unreachable",
                extra={"host": host, "port": port, "error": str(exc)},
            )

    # No ports reachable
    logger.warning(
        "endpoint_unreachable",
        extra={"host": host, "ports": ports},
    )
    raise RuntimeError(f"No ports reachable for endpoint {host}")
# -----------------------------------------------------------------------------