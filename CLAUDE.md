# CLAUDE.md — flux_data_pipeline

## Development Environment

- **Conda environment**: `ep_cntl` — activate before running scripts or installing packages
- `rapidfuzz` is installed in `ep_cntl` (used by `services/metadata/instrument_registry.py` for fuzzy instrument name matching)

## Project Purpose

A data pipeline for processing eddy covariance flux tower measurements from TERN (Terrestrial Ecosystem Research Network) sites. Converts raw instrument data (Campbell Scientific TOA5 loggers, LI-COR EddyPro) into canonical L1 NetCDF files with standardised units, metadata, and QC flags.

## Architecture

Four layers, strictly separated:

```
domain/          — enums, constants, Pydantic data models (no I/O, no external deps)
infrastructure/  — file I/O, paths, data conditioning, logging utilities
services/        — metadata services, data services (loaders, transforms, registries)
orchestration/   — high-level workflow: builds dataframes and NetCDF output
```

### Key modules

| Module | Role |
|---|---|
| `services/metadata/site_registry.py` | **Canonical entry point for pipeline metadata.** `SiteRegistry` filters to only YML-configured sites. Use `SITE_REGISTRY` module-level instance. |
| `services/metadata/site_metadata_repository.py` | Broader TERN data source — all sites including decommissioned. Not for pipeline logic. |
| `services/metadata/canonical_quantity_registry.py` | Master registry of 100+ canonical quantities with units, long_name, valid ranges. Also exports `resolve_variance_units`. |
| `services/metadata/runtime_config_loader.py` | Loads and assembles `SiteRuntimeConfig` from a site YAML config. Entry point: `load_runtime_config(file_path)`. |
| `services/metadata/variable_registry.py` | Builds `VariableSpec` objects (flat raw→canonical mapping) from a runtime config and file groups. Use `build_variable_registry(runtime_cfg, file_groups)`. |
| `services/metadata/file_group_builder.py` | Builds `FileGroup` objects (master path, format, backup files) for all file groups in a site config. Use `build_file_groups(runtime_cfg)` when the target file group is not known in advance. |
| `services/metadata/site_config_schema.py` | Pydantic schema models and structural validation for site YAML configs. Entry point: `validate_L1_config_structure(file)`. |
| `services/metadata/variable_name_parser.py` | Parses canonical variable names into components. `NameParser` class. |
| `services/metadata/rdf_label_resolver.py` | Resolves RDF URI labels from the TERN data store. Used by `site_metadata_repository`. |
| `services/data/transform_service.py` | Unit conversion and derived quantity calculation registries (`@register_conversion`, `@register_calculation`). |
| `services/data/raw_data_loader.py` | Loads TOA5 and EddyPro file formats. |
| `orchestration/dataframe_builder.py` | Core ETL: loads raw data → converts units → merges instrument periods → renames to canonical names. Convenience API: `build_dataframe_from_site_name(site_name, quantities=None, start_date=None)` and `build_dataframe_from_context(ctx, ...)`. Low-level: `build_dataframe(file_groups, registry, quantities=None, ...)` for callers that already hold those objects. |
| `orchestration/dataset_builder.py` | High-level API: `build_dataset_from_site_name()`, `build_dataset_from_context()`. Orchestrates dataframe build → derived quantity padding → xarray Dataset with variable and global metadata. Exports `DatasetBuildIntermediate` (used by `derived_quantities`). |
| `orchestration/derived_quantities.py` | Derives missing RH↔AH and CO2 mole fraction; maintains metadata lineage. |
| `orchestration/build_L1_nc.py` | Export step: converts L1 xarray Dataset to annual NetCDF files. Adds spatial dims, QC flags, global/variable metadata. Separate from dataset construction by design. |
| `services/network/data_monitor.py` | Site health monitoring: record coverage (`analyse_missing_data`), flux variable quality (`analyse_variable_quality`), threshold checks (`analyse_threshold_quality`). Each is an independent orchestration-level task. |
| `services/network/state_task_orchestrator.py` | Fans monitoring tasks concurrently across all pipeline sites. `STATE_TASK_SPECS` registry — add one dict entry to register a new task. |

### Production pipeline stages

```
dataframe_builder   →  pd.DataFrame  (ETL: load → unit-convert → merge → rename)
derived_quantities  →  pd.DataFrame  (pad RH↔AH, CO2 mole fraction)
dataset_builder     →  xr.Dataset    (xarray wrapping + variable/global metadata)
build_L1_nc         →  .nc files     (export: year-split, QC flags, CRS)
```

Monitoring (`services/network/data_monitor.py`) calls `dataframe_builder.build_dataframe(quantities=...)` directly to get unit-converted data for a variable subset, bypassing the dataset construction stages. `analyse_missing_data` is the exception — it loads the raw flux file directly since timestamp-gap counting does not require unit conversion.

## Variable Naming Conventions

- **Canonical form**: `{quantity}_{statistic_suffix}_{qualifier}` — e.g. `Fco2_Av`, `Ta_Sd_2m`
- **Processing aliases**: `{raw_name}_{group_id}` — e.g. `Fc_gp0`
- **Variance → Stdev**: `_Vr` suffix replaced with `_Sd` in output
- **QC flags**: `{variable}_QCFlag`

## Architecture Decisions (agreed, do not reverse without discussion)

- `SiteRegistry` is the canonical metadata entry point for pipeline-configured sites. Do not reach past it to `site_metadata_repository` for pipeline logic.
- `SITE_ALIASES = {'WombatStateForest': 'WombatForest'}` in `site_registry.py` is a deliberate temporary hack — legacy directory name kept until that directory is renamed. Remove when legacy code is switched off.
- Configuration objects (`SiteRuntimeConfig`, etc.) are immutable frozen dataclasses.
- Metadata is cached at the registry instance level (lazy-loaded on first access).

## Modules Deliberately Deferred — Do Not Patch in Isolation

These are broken and need a broader overhaul before touching:

- **`orchestration/site_info_construction.py`**: broken imports (`services.domain.*`, `gap_analysis`, `geospatial.TimeFunctions`, `get_flux_file_path`, `runtime_cfg.system_type`). Known fixes documented in memory but requires full overhaul.
- **`tasks/tasks.py`**: uses old `services.domain` import paths and `global_metadata_service`; needs `SITE_REGISTRY` migration.

## Configuration Files

- `configs/paths.yml` — local/remote resource paths with site placeholders
- `configs/site_metadata.yml` — TERN site metadata (location, commissioning, tower height)
- `configs/canonical_quantities.yml` — master quantity registry
- `configs/nc_metadata.yml` — NetCDF global attributes template
- `configs/sites/{SiteName}.yml` — per-site variable specs, file mappings, instrument metadata

### Site config: `instrument` field notation

Within `input_variables`, the `instrument` field has two valid forms:

**Single instrument** (scalar string) — used for all variables measured by one sensor:
```yaml
instrument: Campbell Scientific CSAT3B
```

**Compound instrument** (nested mapping) — used for flux/covariance variables that require two sensor types (sonic + IRGA). Keys must be `sonic_anemometer` and `irga`:
```yaml
instrument:
  sonic_anemometer: Campbell Scientific CSAT3B
  irga: LI-COR LI-7500RS
```

`Fh` (sensible heat flux) uses the **single** form (sonic only). Although air density correction involves humidity, this dependency is not considered significant enough to warrant compound notation. Comma-separated strings (e.g. `CSAT3B, LI-7500RS`) are **not** valid — do not use them.

## Key Patterns

- **Registry pattern**: `SiteRegistry`, conversion/calculation registries in `transform_service`
- **Decorator-based registration**: `@register_conversion()`, `@register_calculation()` in transform_service
- **Module-level singleton**: use `SITE_REGISTRY = SiteRegistry()` at module level (same pattern as `state_task_orchestrator.py`, `dataset_builder.py`)
- **Pydantic dataclasses** for all metadata/config objects — immutable, type-checked
- **Threshold variable matching**: `THRESHOLD_SPECS` keys may include instrument qualifiers (e.g. `'Diag_IRGA'`, `'Diag_SONIC'`); `var_def.quantity` is always the base quantity (e.g. `'Diag'`). Derive base quantities with `quantity.startswith(var_def.quantity)`; match canonical DataFrame columns with `col.startswith(quantity)`.
