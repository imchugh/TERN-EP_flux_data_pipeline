#!/usr/bin/env python3
"""JSON/YAML helpers, file finders, and atomic TOA5/EddyPro CSV writers."""

import csv
import json
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

logger = logging.getLogger(__name__)


def _atomic_text_write(file_path: Path, write_fn, atomic: bool) -> None:
    """Write text content to `file_path` via `write_fn(file_handle)`.

    If `atomic`, writes to a temporary file (fsync'd) and atomically renames
    it into place; the temporary file is removed if `write_fn` raises.
    """
    if atomic:
        tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
        try:
            with open(tmp_path, "w", newline="\n") as f:
                write_fn(f)
                f.flush()
                os.fsync(f.fileno())
            tmp_path.replace(file_path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
    else:
        with open(file_path, "w", newline="\n") as f:
            write_fn(f)


def get_most_recent_file(
    *,
    root: Path,
    pattern: str = "*",
    recursive: bool = False,
) -> Path | None:
    """Return the most recently modified file in `root` matching `pattern`.

    Returns:
        Path to the most recent match, or None if no file matches.
    """
    if not root.exists():
        raise FileNotFoundError(f"Directory not found: {root}")

    iterator = root.rglob(pattern) if recursive else root.glob(pattern)

    files = [p for p in iterator if p.is_file()]

    if not files:
        return None

    return max(files, key=lambda p: p.stat().st_mtime)


def list_available_files(dir_path: Path | str, pattern: str | list[str]) -> list[Path]:
    """Return sorted files under `dir_path` matching one or more glob patterns.

    Args:
        dir_path: directory to search (non-recursive).
        pattern: a single glob pattern, or a list of patterns whose matches
            are unioned.

    Returns:
        Sorted list of matching paths.
    """
    if isinstance(pattern, str):
        pattern_list = [pattern]
    elif isinstance(pattern, list):
        pattern_list = pattern
    files = set()
    for this_pattern in pattern_list:
        files.update(Path(dir_path).glob(this_pattern))
    return sorted(files)


def read_json(file_path: Path) -> dict | list:
    """Load a JSON file."""
    with open(file_path, encoding="utf-8") as f:
        return json.load(f)


def write_json(
    *,
    file_path: Path,
    data: Any,
    indent: int = 2,
    sort_keys: bool = False,
    atomic: bool = True,
) -> None:
    """Write JSON data to disk.

    Args:
        file_path:
            Destination path.

        data:
            JSON-serializable object.

        indent:
            JSON indentation level.

        sort_keys:
            Whether to sort dictionary keys.

        atomic:
            If True, write via temporary file replacement to avoid
            partially-written/corrupted files.
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)

    if atomic:
        tmp_path = file_path.with_suffix(f"{file_path.suffix}.tmp")

        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                indent=indent,
                sort_keys=sort_keys,
            )

            f.flush()
            os.fsync(f.fileno())

        tmp_path.replace(file_path)

    else:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                indent=indent,
                sort_keys=sort_keys,
            )


def write_toa5_csv(
    *,
    file_path: Path,
    headers: list[list],
    data: pd.DataFrame,
    atomic: bool = True,
) -> None:
    """Write headers and data to a TOA5-format CSV file.

    Handles raw I/O mechanics only: TOA5 CSV quoting conventions, atomic
    write via a temporary file, and fsync.  All domain concerns (building
    the info line, concatenating multiple DataFrames, validating column
    counts) are the caller's responsibility.

    Args:
        file_path:
            Destination path.  Parent directories are created automatically.
        headers:
            Ordered list of rows to write before the data.  For a standard
            TOA5 file this is four lists: info, variable-names, units, and
            sampling-type.
        data:
            DataFrame to write.  Written without its index; the caller must
            include any timestamp column explicitly as a data column.
        atomic:
            If True (default), write via a temporary file that is atomically
            renamed to ``file_path`` on success.  The temporary file is
            removed on failure.  Set False only when atomicity is guaranteed
            by the caller.
    """
    _SEP = ","
    _NA = "NAN"
    _FLOAT_FMT = "%.7g"  # matches Campbell logger's 7-significant-figure output

    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    def _write(f) -> None:
        # Headers: every cell quoted (QUOTE_ALL), standard TOA5 convention.
        writer = csv.writer(f, delimiter=_SEP, quoting=csv.QUOTE_ALL)
        for row in headers:
            writer.writerow(row)

        # Data rows: per-column-type formatting written directly, bypassing
        # to_csv so that float_format and quoting can be controlled
        # independently.
        #   - string  columns → quoted         e.g. "2025-01-01 00:00:00"
        #   - integer columns → bare integer   e.g. 190
        #   - float   columns → %.7g, unquoted e.g. 0, 16.31809, 6.704941e-05
        #   - NaN in any column → "NAN" (quoted, matching logger output)
        col_fmt = []
        for col in data.columns:
            s = data[col]
            if pd.api.types.is_string_dtype(s):
                col_fmt.append([f'"{v}"' if pd.notna(v) else f'"{_NA}"' for v in s])
            elif pd.api.types.is_integer_dtype(s):
                col_fmt.append([_NA if pd.isna(v) else str(v) for v in s])
            else:  # float
                arr = s.to_numpy(dtype=float, na_value=np.nan)
                nan_mask = np.isnan(arr)
                formatted = np.empty(len(arr), dtype=object)
                formatted[nan_mask] = f'"{_NA}"'
                formatted[~nan_mask] = [
                    (_FLOAT_FMT % v).replace("e", "E") for v in arr[~nan_mask]
                ]
                col_fmt.append(formatted.tolist())

        for row in zip(*col_fmt, strict=False):
            f.write(_SEP.join(row) + "\n")

    _atomic_text_write(file_path, _write, atomic)

    logger.info("Wrote TOA5 file: %s", file_path.name)


def write_eddypro_csv(
    *,
    file_path: Path,
    headers: list[list],
    data: pd.DataFrame,
    atomic: bool = True,
) -> None:
    """Write headers and data to an EddyPro-format (tab-separated) CSV file.

    Handles raw I/O mechanics only: EddyPro's tab-delimited, minimally-quoted
    convention, atomic write via a temporary file, and fsync. All domain
    concerns (building the header rows, validating column counts) are the
    caller's responsibility. Unlike ``write_toa5_csv``, there is no legacy
    logger format to replicate byte-for-bit, so data rows are written with
    plain ``DataFrame.to_csv`` rather than manual per-column formatting.

    Args:
        file_path:
            Destination path. Parent directories are created automatically.
        headers:
            Ordered list of rows to write before the data. For a standard
            EddyPro file this is two lists: variable-names and units.
        data:
            DataFrame to write. Written without its index; the caller must
            include the DATAH/filename/date/time columns explicitly as data
            columns.
        atomic:
            If True (default), write via a temporary file that is
            atomically renamed to ``file_path`` on success. The temporary
            file is removed on failure. Set False only when atomicity is
            guaranteed by the caller.
    """
    _SEP = "\t"
    _NA = "NaN"

    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    def _write(f) -> None:
        writer = csv.writer(f, delimiter=_SEP, quoting=csv.QUOTE_MINIMAL)
        for row in headers:
            writer.writerow(row)

        data.to_csv(
            f,
            header=False,
            index=False,
            na_rep=_NA,
            sep=_SEP,
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\n",
        )

    _atomic_text_write(file_path, _write, atomic)

    logger.info("Wrote EddyPro file: %s", file_path.name)


def write_yml_file(
    file_path: str | Path,
    data: dict,
    *,
    sort_keys: bool = False,
    default_flow_style: bool = False,
) -> None:
    """Write a dictionary to a YAML file.

    Args:
        file_path: output file path.
        data: dictionary to write.
        sort_keys: sort dictionary keys alphabetically. Defaults to False.
        default_flow_style: write in inline YAML format. Defaults to False.
    """
    file = Path(file_path)

    with file.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            data,
            f,
            sort_keys=sort_keys,
            default_flow_style=default_flow_style,
            allow_unicode=True,
        )
