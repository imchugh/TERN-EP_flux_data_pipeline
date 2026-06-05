# CLAUDE.md — flux_data_pipeline

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
| `services/metadata/canonical_quantity_registry.py` | Master registry of 100+ canonical quantities with units, long_name, valid ranges. |
| `services/data/transform_service.py` | Unit conversion and derived quantity calculation registries (`@register_conversion`, `@register_calculation`). |
| `services/data/raw_data_loader.py` | Loads TOA5 and EddyPro file formats. |
| `orchestration/dataframe_builder.py` | Core ETL: loads raw data → converts units → merges instrument periods → renames to canonical names. Returns `DataframeBuildResult`. |
| `orchestration/L1_constructor.py` | High-level API: `build_dataset_from_site_name()`, `build_dataframe_from_site_name()`, etc. Applies derived quantity padding. |
| `orchestration/derived_quantities.py` | Derives missing RH↔AH and CO2 mole fraction; maintains metadata lineage. |
| `orchestration/build_L1_nc.py` | Converts L1 dataset to annual NetCDF files. Adds spatial dims, QC flags, global/variable metadata. |

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
- **`services/metadata/file_mapping_service.py`**: `build_file_groups` calls `runtime_cfg.file_formats.resolve()` but `SiteRuntimeConfig` has no `file_formats` attribute.

## Configuration Files

- `configs/paths.yml` — local/remote resource paths with site placeholders
- `configs/site_metadata.yml` — TERN site metadata (location, commissioning, tower height)
- `configs/canonical_quantities.yml` — master quantity registry
- `configs/nc_metadata.yml` — NetCDF global attributes template
- `configs/sites/{SiteName}.yml` — per-site variable specs, file mappings, instrument metadata

## Key Patterns

- **Registry pattern**: `SiteRegistry`, conversion/calculation registries in `transform_service`
- **Decorator-based registration**: `@register_conversion()`, `@register_calculation()` in transform_service
- **Module-level singleton**: use `SITE_REGISTRY = SiteRegistry()` at module level (same pattern as `state_task_orchestrator.py`, `L1_constructor.py`)
- **Pydantic dataclasses** for all metadata/config objects — immutable, type-checked
