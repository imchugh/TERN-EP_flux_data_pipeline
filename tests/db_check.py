#!/usr/bin/env python3
"""Created on Mon Jun  1 14:30:33 2026

@author: imchugh
"""

import pandas as pd

from services.metadata import site_metadata_repository

sites_file = "~/Documents/gsheet_content.csv"


# Create sheets dataframe
sheets_df = (
    pd.read_csv("~/Documents/gsheet_content.csv")
    .rename({"soil_type": "soil"}, axis=1)
    .set_index(keys="name")
)
sheets_df.index = [x.replace(" ", "") for x in sheets_df.index]

# Create rdf dataframe
rdf_df = pd.DataFrame(
    site_metadata_repository.get_flux_tower_fields_from_rdf(query="extended")
).T

# Create site common set
common_sites = sorted(set(rdf_df.index.tolist()) & set(sheets_df.index.tolist()))
common_vars = sorted(set(rdf_df.columns.tolist()) & set(sheets_df.columns.tolist()))

# Rebase the indices to the common sites
sheets_df = sheets_df.loc[common_sites, common_vars]
rdf_df = rdf_df.loc[common_sites, common_vars]

rslt = {}
for variable in common_vars:
    rdf_series = rdf_df[variable].rename("rdf")
    sheets_series = sheets_df[variable].rename("sheets")
    rslt[variable] = pd.concat([rdf_series, sheets_series], axis=1)

output_path = "~/Documents/db_check.xlsx"
with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
    for sheet_name, df in rslt.items():
        df.to_excel(writer, sheet_name=sheet_name[:31])
