#!/usr/bin/env python3
"""Created on Thu Jul  9 20:10:21 2026

@author: imchugh
"""

from pathlib import Path

import yaml

from infrastructure import file_io
from services import config_loader
from services.metadata import instrument_registry


def make_file_name(site: str, logger: str, table: str) -> str:
    """Build file name

    Args:
        site: name of site.
        logger: name of logger (e.g. EC).
        table: name of table.

    Returns:
        name stem (no extension - not used in modern config).

    """
    return f"{site}_{logger}_{table}"


def convert_file(input_path: str | Path, output_path: str | Path) -> None:
    """Restack the flat yml file with modern config nested structure.

    Args:
        input_path: valid path to input file.
        output_path: valid output path for restacked configuration.

    Returns:
        None.

    """
    legacy = config_loader.load_config_file(file=input_path)

    site = Path(input_path).stem

    new_dict = {}
    file_list = set()
    for variable, attrs in legacy.items():
        file = make_file_name(site=site, logger=attrs["logger"], table=attrs["table"])
        file_list.add(file)
        new_dict[variable] = {
            "statistic_type": attrs["statistic_type"],
            "height": float(attrs["height"].replace("m", "")),
            "input_variables": {
                attrs["name"]: {
                    "instrument": attrs["instrument"],
                    "units": attrs["units"],
                    "file": file,
                }
            },
        }

    file_formats = {file: "CSI" for file in file_list}

    output_dict = {
        "site": site,
        "file_formats": file_formats,
        "variables": new_dict,
        "flux_system": "LEGACY",
    }

    with open(output_path, mode="w") as f:
        yaml.dump(data=output_dict, stream=f, sort_keys=False)


def get_instrument_replace_map(input_path: str | Path, first_only: bool = True):
    """Args:
        input_path (TYPE): DESCRIPTION.
        first_only (TYPE, optional): DESCRIPTION. Defaults to True.

    Returns:
        rslt (TYPE): DESCRIPTION.

    """
    cfg = config_loader.load_config_file(file=input_path)
    rslt = {}
    for canon_var, attrs in cfg["variables"].items():
        for values in attrs["input_variables"].values():
            inst_list = values["instrument"].split(",")
            for inst in inst_list:
                if inst in rslt:
                    continue
                if not instrument_registry.is_valid_instrument(name=inst):
                    sgst_inst = instrument_registry.suggest_instruments(name=inst)
                    if first_only:
                        sgst_inst = sgst_inst[0][0]
                    rslt[inst] = sgst_inst
    return rslt


def apply_instrument_replace_map(input_path, instrument_map, output_path):

    cfg = config_loader.load_config_file(file=input_path)
    for canon_var, attrs in cfg["variables"].items():
        for key, values in attrs["input_variables"].items():
            inst_list = [i.strip() for i in values["instrument"].split(",")]
            new_list = []
            for inst in inst_list:
                if instrument_registry.is_valid_instrument(name=inst):
                    new_list.append(inst)
                else:
                    new_list.append(instrument_map[inst])
            values["instrument"] = ",".join(new_list)
    file_io.write_yml_file(file_path=output_path, data=cfg)
