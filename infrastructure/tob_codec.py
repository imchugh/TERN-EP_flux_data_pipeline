# -*- coding: utf-8 -*-
"""Decoder for Campbell Scientific TOB1 and TOB3 binary files."""

import datetime as dt
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pandas as pd

from infrastructure import read_cs_files as rcf

DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

_INFO_NAMES = [
    'format', 'station_name', 'logger_type', 'serial_num', 'OS_version',
    'program_name', 'program_sig',
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def read_tob(files: Path | list[Path]) -> tuple[pd.DataFrame, dict]:
    """
    Parse one or more TOB1/TOB3 files into a conditioned DataFrame.

    Multiple files are concatenated, deduplicated, and sorted. Metadata is
    taken from the first (chronologically earliest) file.

    Args:
        files: single path or list of paths.

    Returns:
        (data, metadata) where data has a DatetimeIndex named TIMESTAMP and
        metadata is a dict with keys 'format', 'info', and 'headers'.
        'info' is the flat list of values from the Campbell info line.
        'headers' is [variables, units, sampling] — each a list excluding
        TIMESTAMP, matching the convention used by toa5_writer.

    Raises:
        RuntimeError: if a file contains no data.
        TypeError: if files do not all share the same format.
    """
    if isinstance(files, (str, Path)):
        files = [Path(files)]
    else:
        files = sorted(Path(f) for f in files)

    frames = []
    first_raw_meta = None
    file_fmt = None

    for file in files:
        contents = rcf.read_cs_files(filename=file)
        if not contents[0]:
            raise RuntimeError(f'No data in file {file.name}')

        raw_meta = contents[1]
        fmt = raw_meta[0][0]

        if file_fmt is None:
            file_fmt = fmt
            first_raw_meta = raw_meta
        elif fmt != file_fmt:
            raise TypeError(
                f'Mixed formats: expected {file_fmt}, got {fmt} in {file.name}'
            )

        header_idx = 2 if fmt == 'TOB3' else 1
        df = (
            pd.DataFrame(dict(zip(raw_meta[header_idx], contents[0])))
            .set_index('TIMESTAMP')
        )
        frames.append(df)

    data = pd.concat(frames).sort_index()
    data = data[~data.index.duplicated()]
    data = _condition_dtypes(data)

    return data, _build_metadata(first_raw_meta, file_fmt)


def split_by_interval(
    df: pd.DataFrame,
    interval_minutes: int,
    freq_hz: int,
) -> Iterator[tuple[dt.datetime, pd.DataFrame]]:
    """
    Partition a DataFrame into fixed-length interval windows across a calendar day.

    Only non-empty windows are yielded. The first sample in each window is
    offset from the window start by one sample period (1/freq_hz seconds),
    matching the Campbell logger convention.

    Args:
        df: DataFrame with DatetimeIndex, as returned by read_tob.
        interval_minutes: window length in minutes (e.g. 30).
        freq_hz: data collection frequency in Hz; determines the
            first-sample offset.

    Yields:
        (end_datetime, subset_df) for each non-empty window.
    """
    if df.empty:
        return

    first_ts = df.index[0]
    day_start = dt.datetime(first_ts.year, first_ts.month, first_ts.day)
    first_sample_offset = dt.timedelta(microseconds=10 ** 6 // freq_hz)
    n_periods = 24 * 60 // interval_minutes

    for i in range(n_periods):
        start = (
            day_start
            + dt.timedelta(minutes=i * interval_minutes)
            + first_sample_offset
        )
        end = day_start + dt.timedelta(minutes=(i + 1) * interval_minutes)
        subset = df.loc[start:end]
        if not subset.empty:
            yield end, subset


def get_file_info(file: Path) -> dict:
    """
    Read the info header of a TOB file without loading data.

    Args:
        file: path to the TOB file.

    Returns:
        dict with keys: format, station_name, logger_type, serial_num,
        OS_version, program_name, program_sig, and either creation_date
        (TOB3) or table_name (TOB1).
    """
    raw_meta = rcf.read_cs_files(filename=file, metaonly=True)
    fmt = raw_meta[0][0]
    last_key = 'creation_date' if fmt == 'TOB3' else 'table_name'
    return dict(zip(_INFO_NAMES + [last_key], raw_meta[0]))


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_metadata(raw_meta: list, fmt: str) -> dict:
    meta = list(raw_meta)
    if fmt == 'TOB3':
        meta.pop(1)  # remove the TOB3-specific frame-descriptor line

    last_key = 'creation_date' if fmt == 'TOB3' else 'table_name'
    info = list(dict(zip(_INFO_NAMES + [last_key], meta[0])).values())

    # Strip TIMESTAMP (first entry) from each header list — the writer
    # adds it back, matching the convention in raw_data_loader / toa5_writer.
    variables = meta[1][1:]
    units = meta[2][1:]
    sampling = meta[3][1:]

    return {'format': fmt, 'info': info, 'headers': [variables, units, sampling]}


def _condition_dtypes(data: pd.DataFrame) -> pd.DataFrame:
    for col in data.select_dtypes('float'):
        s = data[col].replace([np.inf, -np.inf], np.nan)
        if ((s.dropna() % 1) == 0).all():
            data[col] = np.round(s).astype('Int32')
        else:
            data[col] = s.astype('float32').apply(lambda x: float(f'{x:.7g}'))
    return data
