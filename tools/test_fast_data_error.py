#!/usr/bin/env python3
"""WIP investigation: TOB3/TOA5 fast-data filename vs. header timestamp mismatches."""

import datetime as dt
from pathlib import Path

from infrastructure.file_io import read_lines

path = "/store/Raw_data/Calperum/Flux/Fast/TOA5"


def get_no_match_files():
    """Find fast-data files where the filename date disagrees with the header date.

    Note: currently accumulates `no_match`/`match` but does not return
    either — still WIP.
    """
    no_match, match = {}, []
    for file in sorted(Path(path).rglob("*.dat")):
        print(file.name)
        folder_name_date = dt.datetime.strptime(
            "_".join([file.parents[1].name, file.parents[0].name]), "%Y_%m_%d"
        ).date()

        file_name_date = dt.datetime.strptime(
            "_".join(file.stem.split("_")[3:]), "%Y_%m_%d_%H_%M"
        )

        header_date = dt.datetime.strptime(
            read_lines(file, end=0)[0][-1], "%Y-%m-%d %H:%M:%S"
        )

        if not file_name_date == header_date:
            no_match[file.name] = {
                "parent_directory": file.parent,
                "date_from_name": file_name_date,
                "date_from_header": header_date,
            }
            continue

        match.append(file.name)


def get_no_date_headers():
    """Return {filename: raw_value} for files whose header timestamp doesn't parse."""
    rslt = {}
    for file in sorted(Path(path).rglob("*.dat")):
        print(file.name)

        last_slot = read_lines(file, end=0)[0][-1]
        try:
            dt.datetime.strptime(last_slot, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            rslt[file.name] = last_slot

    return rslt


# for root, dir_names, files in Path(path).walk():
#     if root == Path(path):
#         month_dirs = dir_names
#         continue

#     if len(dir_names) != 0:
#         if len(files) == 0:
#             print (f'Parent directory is {root}')
#         if len(files) == 0:

#     print(root)
#     print (dir_names)
