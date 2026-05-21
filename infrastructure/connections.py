#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Feb 26 09:44:00 2026

@author: imchugh
"""

from __future__ import annotations

###############################################################################
### BEGIN IMPORTS ###
###############################################################################

import socket
import time
from dataclasses import dataclass

###############################################################################
### END IMPORTS ###
###############################################################################



###############################################################################
### BEGIN DATACLASSES ###
###############################################################################

@dataclass(frozen=True)
class PortScanResult:
    """
    Result of a successful TCP port scan.
    """

    host: str
    port: int
    latency_ms: int

###############################################################################
### END DATACLASSES ###
###############################################################################



###############################################################################
### BEGIN EXCEPTIONS ###
###############################################################################

class PortScanError(Exception):
    """
    Base exception for TCP scan failures.
    """


class PortTimeoutError(PortScanError):
    """
    Raised when a TCP connection attempt times out.
    """


class PortConnectionError(PortScanError):
    """
    Raised when a TCP connection attempt fails for non-timeout reasons.
    """

###############################################################################
### END EXCEPTIONS ###
###############################################################################



###############################################################################
### BEGIN FUNCTIONS ###
###############################################################################

# -----------------------------------------------------------------------------
def scan_tcp_port(
        host: str,
        port: int,
        timeout: float = 2.0,
        ) -> PortScanResult:
    """
    Attempt a TCP connection to a single host/port endpoint.

    Args:
        host:
            IP address or hostname.

        port:
            TCP port number.

        timeout:
            Socket timeout in seconds.

    Returns:
        PortScanResult containing endpoint latency information.

    Raises:
        PortTimeoutError:
            Connection attempt exceeded timeout.

        PortConnectionError:
            Connection failed for another socket-related reason.
    """

    start_time = time.monotonic()

    try:

        with socket.create_connection(
                address=(host, port),
                timeout=timeout,
                ):

            latency_ms = int(
                (time.monotonic() - start_time) * 1000
                )

            return PortScanResult(
                host=host,
                port=port,
                latency_ms=latency_ms,
            )

    except TimeoutError as exc:

        raise PortTimeoutError(
            f"Connection timed out for {host}:{port}"
        ) from exc

    except OSError as exc:

        raise PortConnectionError(
            f"Connection failed for {host}:{port}"
        ) from exc
# -----------------------------------------------------------------------------

###############################################################################
### END FUNCTIONS ###
###############################################################################