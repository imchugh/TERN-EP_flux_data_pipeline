#!/usr/bin/env python3
"""Thin, typed wrapper around `requests` for GET/POST calls."""

from __future__ import annotations

import requests


class HTTPRequestError(Exception):
    """Raised when an HTTP request fails."""


def get(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict | None = None,
    timeout: int = 60,
    stream: bool = False,
) -> requests.Response:
    """Execute an HTTP GET request, raising HTTPRequestError on failure."""
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
        raise HTTPRequestError(f"GET request failed for {url}: {exc}") from exc


def post(
    url: str,
    *,
    data: str | bytes,
    headers: dict[str, str],
    auth: tuple[str, str] | None = None,
    timeout: int = 60,
) -> requests.Response:
    """Execute an HTTP POST request, raising HTTPRequestError on failure."""
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
        raise HTTPRequestError(f"POST request failed for {url}: {exc}") from exc
