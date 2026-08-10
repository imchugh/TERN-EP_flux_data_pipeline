#!/usr/bin/env python3
"""Site-specific raw-data normalizers for CO2 concentration-profile systems.

Each site's profile instrumentation is built differently, so each gets its
own normalizer function that reads that site's raw files and produces the
common `(time, height)` xr.Dataset contract (`CO2`/`Tair`/`P`) consumed by
`profile_storage.py`. `SITE_LOADERS` is a plain dict of real functions
rather than a decorator-based registry, so a site can't be "registered"
without its normalizer actually being written.
"""

from collections.abc import Callable
from pathlib import Path

import pandas as pd
import xarray as xr

from infrastructure import file_io, paths
from services.data import profile_storage, raw_data_loader

###############################################################################
### BEGIN SHARED HELPERS ###
###############################################################################


def _stack_to_series(df: pd.DataFrame, name: str) -> pd.Series:
    """Stack a wide (time x height) DataFrame into a (time, height)-indexed
    Series, using this module's canonical dim names.
    """
    series = df.stack(future_stack=True)
    series.name = name
    series.index.names = [profile_storage.TIME_DIM, profile_storage.HEIGHT_DIM]
    return series


def _load_toa5_with_backups(
    file_path: Path, usecols: list[str] | None = None
) -> pd.DataFrame:
    """Read a TOA5 file plus any `.backup` siblings, concatenated and
    de-duplicated on the time index (master takes precedence).
    """
    files = [file_path, *file_io.get_backup_files(file_path=file_path)]
    dfs = [
        raw_data_loader.load_raw_data(f, file_format="TOA5", usecols=usecols)
        for f in files
        if f.exists()
    ]
    if not dfs:
        raise FileNotFoundError(f"No data file(s) found for {file_path}")
    df = pd.concat(dfs).sort_index()
    return df[~df.index.duplicated(keep="first")]


###############################################################################
### END SHARED HELPERS ###
###############################################################################


###############################################################################
### BEGIN BOYAGIN ###
###############################################################################

_BOYAGIN_PROFILE_FILE = "Boyagin_CO2_prof_IRGA_avg.dat"
_BOYAGIN_MET_FILE = "Boyagin_EC_slow_all.dat"
_BOYAGIN_DATE_START = "2023-09-05 11:10"  # sensor commissioning date
_BOYAGIN_CO2_COLS = [
    "Cc_LI840_0_5m",
    "Cc_LI840_1m",
    "Cc_LI840_3m",
    "Cc_LI840_6m",
    "Cc_LI840_10m",
    "Cc_LI840_16m",
    "Cc_LI840_23m",
    "Cc_LI840_30m",
]


def _parse_boyagin_height(column: str) -> float:
    """'Cc_LI840_0_5m' -> 0.5; 'Cc_LI840_30m' -> 30.0."""
    return float(".".join(column.split("_")[2:]).replace("m", ""))


def load_boyagin_profile() -> xr.Dataset:
    """Normalize Boyagin's raw profile + met files into a (time, height)
    Dataset.

    The CO2 profile instrument has one parallel sensor per intake height.
    Tair and P are single-point measurements broadcast to every height
    (Tair from the separate flux-slow met file, P from the profile file's
    own barometer) — this is the site's actual instrumentation, not a
    simplification.
    """
    profile_dir = paths.get_local_stream_path(
        resource="raw_data",
        stream="profile",
        site="Boyagin",
    )
    met_dir = paths.get_local_stream_path(
        resource="raw_data",
        stream="flux_slow",
        site="Boyagin",
    )

    profile_df = _load_toa5_with_backups(
        profile_dir / _BOYAGIN_PROFILE_FILE,
        usecols=["TIMESTAMP", *_BOYAGIN_CO2_COLS, "P_atm_Avg"],
    ).loc[_BOYAGIN_DATE_START:]

    # Dedup sequencer artefacts: keep the minutes-4-through-29 mean of each
    # 30-min block, discarding the sensor's post-switch settling samples.
    profile_df = profile_df[profile_df.index.minute % 30 < 4].resample("30min").mean()

    heights = [_parse_boyagin_height(c) for c in _BOYAGIN_CO2_COLS]

    co2_series = _stack_to_series(
        profile_df[_BOYAGIN_CO2_COLS].rename(
            columns=dict(zip(_BOYAGIN_CO2_COLS, heights))
        ),
        "CO2",
    )
    p_series = _stack_to_series(
        pd.concat(
            [profile_df["P_atm_Avg"]] * len(heights),
            axis=1,
            keys=heights,
        )
        / 10,  # hPa -> kPa
        "P",
    )

    met_df = _load_toa5_with_backups(
        met_dir / _BOYAGIN_MET_FILE,
        usecols=["TIMESTAMP", "Ta_HMP_Avg"],
    ).loc[_BOYAGIN_DATE_START:]
    ta_series = _stack_to_series(
        pd.concat(
            [met_df["Ta_HMP_Avg"]] * len(heights),
            axis=1,
            keys=heights,
        ),
        "Tair",
    )

    ds = pd.concat([co2_series, ta_series, p_series], axis=1).to_xarray()
    ds["CO2"].attrs = {"units": "umol/mol"}
    ds["Tair"].attrs = {"units": "degC"}
    ds["P"].attrs = {"units": "kPa"}
    return ds


###############################################################################
### END BOYAGIN ###
###############################################################################


###############################################################################
### BEGIN CUMBERLAND PLAIN ###
###############################################################################

_CUP_INTAKE_HEIGHTS = [0.5, 1, 2, 3.5, 7, 12, 20, 29]
_CUP_CO2_LIMITS = (300, 1000)
_CUP_PROFILE_FILE = "CUP_AUTO_co2profile.dat"
_CUP_CLIMATE_FILE = "CUP_AUTO_climate.dat"
_CUP_EP_MASTER_FILE = "CumberlandPlain_EP_MASTER.txt"
_CUP_TAIR_LOWER = ("Ta_HMP_01_Avg", 7)
_CUP_TAIR_UPPER = ("Ta_HMP_155_Avg", 30)


def _timestack_CUP_CO2(df: pd.DataFrame) -> pd.DataFrame:
    """Unstack a single, valve-multiplexed CO2 stream into one column per
    intake height, on a regular 30-min time axis.

    `ValveNo` identifies which height is currently being sampled, encoded
    as the minute-of-half-hour at which that valve is read. The logger
    timestamps each scan ~1s before the labelled minute, so timestamps are
    nudged forward before matching against `ValveNo`.
    """
    df = df.copy()
    df.index = df.index + pd.Timedelta(seconds=1)
    minute_mod = (df.index.minute % 30).values
    df = df[minute_mod == df["ValveNo"].to_numpy()].drop_duplicates()

    df["Time"] = df.index.floor("30min")
    valve_map = dict(zip(sorted(df["ValveNo"].unique()), _CUP_INTAKE_HEIGHTS))
    df["Height"] = df["ValveNo"].map(valve_map)

    stacked = df.set_index(pd.MultiIndex.from_frame(df[["Time", "Height"]]))[
        "CO2_Avg"
    ].unstack()
    new_index = pd.date_range(stacked.index.min(), stacked.index.max(), freq="30min")
    return stacked.reindex(new_index)


def _interpolate_CUP_temperature(df: pd.DataFrame) -> pd.DataFrame:
    """Linearly interpolate the two measured air temperatures (7m, 30m) to
    all 8 intake heights.
    """
    lower_name, lower_ht = _CUP_TAIR_LOWER
    upper_name, upper_ht = _CUP_TAIR_UPPER
    dtdz = (df[upper_name] - df[lower_name]) / (upper_ht - lower_ht)
    return pd.concat(
        [df[lower_name] + (ht - lower_ht) * dtdz for ht in _CUP_INTAKE_HEIGHTS],
        axis=1,
        keys=_CUP_INTAKE_HEIGHTS,
    )


def load_cumberland_plain_profile() -> xr.Dataset:
    """Normalize CumberlandPlain's raw profile + climate + EddyPro-master
    files into a (time, height) Dataset.

    CO2 comes from a single multiplexed sensor cycling through 8 intake
    heights (unlike Boyagin's parallel sensors). Tair is measured at only
    two heights and vertically interpolated to all 8. P is a single-point
    measurement (from the EddyPro master file already maintained by
    `update_EddyPro_master`) broadcast to all heights.
    """
    profile_dir = paths.get_local_stream_path(
        resource="raw_data",
        stream="profile",
        site="CumberlandPlain",
    )
    met_dir = paths.get_local_stream_path(
        resource="raw_data",
        stream="flux_slow",
        site="CumberlandPlain",
    )

    profile_df = _load_toa5_with_backups(
        profile_dir / _CUP_PROFILE_FILE,
        usecols=["TIMESTAMP", "CO2_Avg", "ValveNo"],
    )
    co2_series = _stack_to_series(_timestack_CUP_CO2(profile_df), "CO2")
    co2_series = co2_series.where(
        (co2_series >= _CUP_CO2_LIMITS[0]) & (co2_series <= _CUP_CO2_LIMITS[1])
    )

    climate_df = _load_toa5_with_backups(
        met_dir / _CUP_CLIMATE_FILE,
        usecols=["TIMESTAMP", _CUP_TAIR_LOWER[0], _CUP_TAIR_UPPER[0]],
    )
    ta_series = _stack_to_series(_interpolate_CUP_temperature(climate_df), "Tair")

    ep_master_df = raw_data_loader.load_raw_data(
        met_dir / _CUP_EP_MASTER_FILE,
        file_format="EddyPro",
        usecols=["date", "time", "air_pressure"],
    )
    p_series = _stack_to_series(
        pd.concat(
            [ep_master_df["air_pressure"]] * len(_CUP_INTAKE_HEIGHTS),
            axis=1,
            keys=_CUP_INTAKE_HEIGHTS,
        )
        / 10**3,  # Pa -> kPa
        "P",
    )

    earliest_ts = min(
        co2_series.index.get_level_values(profile_storage.TIME_DIM).max(),
        ta_series.index.get_level_values(profile_storage.TIME_DIM).max(),
        p_series.index.get_level_values(profile_storage.TIME_DIM).max(),
    )

    ds = (
        pd.concat([co2_series, ta_series, p_series], axis=1)
        .loc[:earliest_ts]
        .to_xarray()
    )
    ds["CO2"].attrs = {"units": "umol/mol"}
    ds["Tair"].attrs = {"units": "degC"}
    ds["P"].attrs = {"units": "kPa"}
    return ds


###############################################################################
### END CUMBERLAND PLAIN ###
###############################################################################


###############################################################################
### BEGIN DISPATCH ###
###############################################################################

SITE_LOADERS: dict[str, Callable[[], xr.Dataset]] = {
    "Boyagin": load_boyagin_profile,
    "CumberlandPlain": load_cumberland_plain_profile,
}


def load_profile_dataset(site: str) -> xr.Dataset:
    """Load and validate the normalized profile Dataset for `site`."""
    try:
        loader = SITE_LOADERS[site]
    except KeyError:
        raise ValueError(
            f"No profile-data normalizer for site '{site}'. "
            f"Supported: {sorted(SITE_LOADERS)}"
        ) from None

    ds = loader()
    profile_storage.validate_profile_dataset(ds)
    return ds


###############################################################################
### END DISPATCH ###
###############################################################################
