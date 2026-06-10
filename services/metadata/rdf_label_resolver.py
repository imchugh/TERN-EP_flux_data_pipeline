#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Dec  9 12:02:01 2025

@author: imchugh
"""

import requests
from functools import lru_cache

# Some CV URIs return JSON-LD, some RDF/XML, some Turtle
ACCEPT_HEADERS = {
    "Accept": (
        "application/ld+json, application/json, "
        "text/turtle, application/rdf+xml;q=0.9, */*;q=0.1"
    )
}

# Common label predicates
LABEL_PREDICATES = {
    "http://www.w3.org/2004/02/skos/core#prefLabel",
    "http://www.w3.org/2000/01/rdf-schema#label",
    "http://purl.org/dc/terms/title",
}


@lru_cache(maxsize=1024)
def fetch_label(uri: str):
    """
    Dereference a TERN CV UUID URI and extract a human-readable label.
    Supports JSON-LD, RDF/XML, and Turtle.
    Returns a string or None.
    """

    try:
        response = requests.get(uri, headers=ACCEPT_HEADERS, timeout=15)
        response.raise_for_status()
    except Exception:
        return None  # network errors or 404 -> no label available

    # ---- Try JSON-LD first (preferred) --------------------------------------
    try:
        data = response.json()
        # Could be @graph or single object
        graph = data.get("@graph", [data])

        for node in graph:
            if isinstance(node, dict) and node.get("@id") == uri:
                for key, val in node.items():
                    if key in LABEL_PREDICATES:
                        # value might be list or dict
                        if isinstance(val, list):
                            return val[0].get("@value")
                        elif isinstance(val, dict):
                            return val.get("@value")
                        elif isinstance(val, str):
                            return val
    except Exception:
        pass  # Not JSON-LD – try RDF/XML/Turtle

    # ---- Fallback: regex text scan for literal labels -----------------------
    # (works for RDF/XML or Turtle if lightweight)
    text = response.text

    import re

    # Look for simple literal labels
    for pred in LABEL_PREDICATES:
        # Handles cases like: skos:prefLabel "Frequency (Hz)"
        pred_local = pred.split("#")[-1]  # prefLabel, label, title
        pattern = rf'{pred_local}\s+"([^"]+)"'
        match = re.search(pattern, text)
        if match:
            return match.group(1)

    return None  # No usable label found


def dereference_labels(uris):
    """
    Given a list of UUID URIs, return a mapping: URI → label or None.
    """
    results = {}
    for uri in uris:
        results[uri] = fetch_label(uri)
    return results
