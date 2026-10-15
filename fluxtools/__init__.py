"""Flux data tools layered on fluxcore: raw-file splicing/writing and helpers.

Imports fluxcore but nothing from the TERN pipeline, so it can become its own
package by moving this directory. Holds what fluxcore deliberately doesn't:
writing raw files (fluxcore only reads them), and general-purpose helpers.
"""
