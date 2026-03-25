#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Feb 27 15:31:00 2026

@author: imchugh
"""

import requests

def post(
    url: str,
    *,
    data: str | bytes,
    headers: dict[str, str],
    auth: tuple[str, str] | None = None,
    timeout: int = 60,
) -> requests.Response:
    
    response = requests.post(
        url,
        data=data,
        headers=headers,
        auth=auth,
        timeout=timeout,
    )
    response.raise_for_status()
    return response