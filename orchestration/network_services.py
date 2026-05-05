#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Feb  9 07:22:54 2026

@author: imchugh
"""

###############################################################################
### BEGIN IMPORTS ###
###############################################################################

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

# -----------------------------------------------------------------------------

from infrastructure import connections
from services.foundational import config_loader

###############################################################################
### END IMPORTS ###
###############################################################################



###############################################################################
### BEGIN INITS ###
###############################################################################

logger = logging.getLogger(__name__)
SITE_CONNS = config_loader.load_config_file_from_name(name='vpn_ip')
LOGGER_IP = {'EC': '100', 'soil': '101', 'profile': '103'}
DEFAULT_LOGGER_PORT = 6785
VALID_HARDWARE = ['gateway', 'EC', 'soil']

###############################################################################
### END INITS ###
###############################################################################


###############################################################################
### BEGIN FUNCTIONS ###
###############################################################################

# -----------------------------------------------------------------------------
def scan_site_by_name(
    site_name: str, hardware: str='gateway', timeout: int=2.0, 
    ports_override: list = None
    ) -> dict:
    """
    Check reachability for a site identified by name.

    Args:
        site_name: Registered site name
        hardware: 'gateway' | 'EC' | 'soil'
        timeout: socket timeout in seconds
        ports_override: optional override for configured ports
    Returns:
        results for passed site.

    """

    # Check hardware is valid
    if hardware not in VALID_HARDWARE:
        raise ValueError(f"Invalid hardware type: {hardware}")

    # Check site name is valid
    if site_name not in SITE_CONNS:
        raise KeyError(f"Unknown site: {site_name}")

    # Grab site-level configs and convert if not gateway
    base_cfg = SITE_CONNS[site_name]
    
    # Set ip addr and ports
    ip = base_cfg["ip"]
    ports = ports_override or base_cfg["ports"]
    
    # Do predictable ip translation for logger hardware
    if hardware != "gateway":
        ip = _resolve_logger_ip(gateway_ip=ip, logger_type=hardware)
        ports = [DEFAULT_LOGGER_PORT]
    
    logger.debug(
        "scan_site_resolved",
        extra={
            "site": site_name,
            "hardware": hardware,
            "ip": ip,
            "ports": ports,
            },
        )
    
    # Scan defined endpoint
    result = connections.scan_endpoint(host=ip, ports=ports, timeout=timeout)
    
    logger.debug(
        "scan_site_complete",
        extra={
            "site": site_name,
            **result,
        },
    )

    return result
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def scan_network(
        site_list: Optional[list[str]] = None, 
        hardware: str='gateway', 
        timeout: int=2.0, 
        max_workers: int=10
        ) -> dict:
    """
    Scan multiple sites concurrently.

    Args:
        site_list: Optional list of site names. Defaults to all configured sites.
        hardware: 'gateway' | 'EC' | 'soil' | 'profile'
        timeout: socket timeout in seconds
        max_workers: thread pool size

    Returns:
        dict containing results for all passed sites.

    """

    if site_list is None:
        site_list = list(SITE_CONNS.keys())

    logger.info(
        "network_scan_start",
        extra={
            "site_count": len(site_list),
            "hardware": hardware,
            "timeout": timeout,
            "max_workers": max_workers,
            },
        )

    results: dict[str, dict] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        
        future_to_site = {}
        
        for site_name in site_list:
            
            cfg = SITE_CONNS[site_name]
            ip = (
                cfg["ip"] if hardware == "gateway" else 
                _resolve_logger_ip(cfg["ip"], hardware)
                )
            ports = cfg["ports"] if hardware == "gateway" else [DEFAULT_LOGGER_PORT]
            future = pool.submit(connections.scan_endpoint, ip, ports, timeout)
            future_to_site[future] = site_name

        for future in as_completed(future_to_site):
            
            site_name = future_to_site[future]
            try:
                
                results[site_name] = future.result()
                
            except Exception as exc:
                
                logger.error(
                    "site_scan_failed",
                    extra={
                        "site": site_name, 
                        "error": str(exc)
                        },
                    )
                results[site_name] = {
                    "reachable": False, 
                    "port": None, 
                    "latency_ms": None
                    }


    logger.info("scan_network_complete", extra={"site_count": len(results)})
    return results
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def _resolve_logger_ip(gateway_ip, logger_type='EC'):
    
    host_addr = LOGGER_IP[logger_type]
    return f'192.168.{str(gateway_ip.split('.')[-1])}.{host_addr}'
# -----------------------------------------------------------------------------

###############################################################################
### END FUNCTIONS ###
###############################################################################
