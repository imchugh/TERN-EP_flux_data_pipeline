#!/usr/bin/env python3
"""Load this pipeline's config files (yml/csv/txt) by path or by name.

Name lookups default to this repo's configs/ (paths.CONFIG_PATH). fluxcore's
own packaged configs are loaded by fluxcore itself.
"""

import pathlib

import pandas as pd
from fluxcore.infrastructure.file_io import read_yml

from infrastructure import paths

ConfigType = dict | str | pd.DataFrame
ALLOWED_CONFIG_TYPES = (".yml", ".txt", ".csv")


def load_config_file(file: pathlib.Path | str) -> ConfigType:
    """Load a config file: dict (yml), str (txt), or DataFrame (csv).

    Raises:
        ValueError: for an unsupported file suffix.
    """
    file = pathlib.Path(file)
    if file.suffix == ".yml":
        return read_yml(file_path=file)
    if file.suffix == ".txt":
        return file.read_text(encoding="utf-8")
    if file.suffix == ".csv":
        return pd.read_csv(file)
    raise ValueError(f"Unsupported config file type: {file.suffix}")


def load_config_file_from_name(
    name: str, config_dir: pathlib.Path = paths.CONFIG_PATH
) -> ConfigType:
    """Load the config file named `name` (any allowed suffix) in config_dir.

    Raises:
        FileNotFoundError: if no config of that name exists in config_dir.
    """
    for file in sorted(pathlib.Path(config_dir).glob(f"{name}.*")):
        if file.suffix in ALLOWED_CONFIG_TYPES:
            return load_config_file(file)
    raise FileNotFoundError(f"No file with name {name} found in {config_dir}")
