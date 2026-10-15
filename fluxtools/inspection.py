#!/usr/bin/env python3
"""Helpers for inspecting fluxcore objects interactively."""

from pathlib import Path

from fluxcore import FileGroup


def files_for_variable(file_group: FileGroup, variable: str) -> list[Path]:
    """Return the files (master and backups) whose header contains variable."""
    return [
        file
        for file, variables in file_group.variables_by_file.items()
        if variable in variables
    ]
