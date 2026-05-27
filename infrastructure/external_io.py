#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Feb 27 15:31:00 2026

@author: imchugh
"""

from __future__ import annotations

###############################################################################
### BEGIN IMPORTS ###
###############################################################################

import requests

###############################################################################
### END IMPORTS ###
###############################################################################



###############################################################################
### BEGIN EXCEPTIONS ###
###############################################################################

class HTTPRequestError(Exception):
    """
    Raised when an HTTP request fails.
    """

###############################################################################
### END EXCEPTIONS ###
###############################################################################



###############################################################################
### BEGIN FUNCTIONS ###
###############################################################################

# -----------------------------------------------------------------------------
def get(
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict | None = None,
        timeout: int = 60,
        stream: bool = False,
        ) -> requests.Response:
    """
    Execute HTTP GET request.
    """

    try:

        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=timeout,
            stream=stream,
        )

        response.raise_for_status()

        return response

    except requests.RequestException as exc:

        raise HTTPRequestError(
            f"GET request failed for {url}: {exc}"
        ) from exc
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def post(
        url: str,
        *,
        data: str | bytes,
        headers: dict[str, str],
        auth: tuple[str, str] | None = None,
        timeout: int = 60,
        ) -> requests.Response:
    """
    Execute HTTP POST request.
    """

    try:

        response = requests.post(
            url,
            data=data,
            headers=headers,
            auth=auth,
            timeout=timeout,
        )

        response.raise_for_status()

        return response

    except requests.RequestException as exc:
        
        raise HTTPRequestError(
            f"POST request failed for {url}: {exc}"
        ) from exc
# -----------------------------------------------------------------------------

###############################################################################
### END FUNCTIONS ###
###############################################################################