# CLAUDE.md — flux_data_pipeline

## Development Environment

- **Conda environment**: `ep_cntl` — activate before running scripts or installing packages. Build it from `environment.yml` (`conda env create -f environment.yml`); update that file (`conda env export --from-history`, then re-add the `pip:` section) after installing anything new.
- `rapidfuzz` is installed in `ep_cntl` (used by `services/metadata/tern/instrument_registry.py` for fuzzy instrument name matching)
- `ruff` (formatting/linting, see `pyproject.toml`) is pip-installed in `ep_cntl`, not conda-installed
- **Site config files**: `/opt/TERN_EP/site_configs/operational/` — per-site YAML configs (e.g. `MyallValeA.yml`)

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
| `services/metadata/tern/site_registry.py` | **Canonical entry point for pipeline metadata.** `SiteRegistry` filters to only YML-configured sites. Defines the `SiteRegistry` class only — does not export a module-level instance; each consumer instantiates its own `SITE_REGISTRY = SiteRegistry()` singleton (see Key Patterns). |
| `services/metadata/tern/site_metadata_repository.py` | Broader TERN data source — all sites including decommissioned. Not for pipeline logic. |
| `services/metadata/core/canonical_quantity_registry.py` | Master registry of 100+ canonical quantities with units, long_name, valid ranges. Also exports `resolve_variance_units`. |
| `services/metadata/core/runtime_config_builder.py` | **Generic-core config assembly.** Builds `SiteRuntimeConfig` from a structurally-validated `SiteConfig` — name syntax, quantity/units checks, object assembly. No TERN calls: `instrument_uris` is an optional adapter-supplied enrichment map (defaults to none, leaving every `instrument_uri` as `None`), and `input_data_path` is optional adapter-supplied data for where the site's raw files live (defaults to `None`; required by `file_group_builder.build_file_groups`). Two entry points, both taking `input_data_path`: `build_runtime_config_from_file(file_path, input_data_path=None)` (raw YAML in, zero TERN dependency) and `build_runtime_config(validated_config, instrument_uris=None, input_data_path=None)` (already-validated/adapter-enriched object in) — the file variant also takes `input_data_path` directly so a standalone non-TERN caller has a genuine one-call path to a runnable config, not just the object variant. |
| `services/metadata/core/site_metadata_builder.py` | **Generic-core `SiteMetadata` assembly**, the other half of a `SiteContext`. Strict Pydantic schema (`SiteMetadataSchema`) plus `build_site_metadata_from_file(file_path) -> SiteMetadata` — reads a single-site metadata YAML (the shape of one value out of `configs/site_metadata.yml`'s `{site_name: <record>}` mapping, unwrapped to a standalone file). Deliberately strict (raises on malformed input), unlike `SiteMetadata.__init__`'s own tolerant log-and-keep-raw coercion, which stays untouched as TERN's accommodation for messy upstream RDF/yml data — never exercised by this path since validation happens first. Purely a standalone entry point for a non-TERN caller; TERN's own production pipeline is unaffected and keeps using `SiteRegistry.get_metadata()`. |
| `services/metadata/tern/runtime_config_loader.py` | **TERN-adapter orchestration** for loading a site's `SiteRuntimeConfig`: validates instrument names against the TERN registry, resolves instrument URIs against the RDF vocab, resolves the site's raw-data directory via `infrastructure.paths`, then delegates structural validation and assembly to `runtime_config_builder`. Entry point: `load_runtime_config(file_path)` — the TERN-integrated equivalent of `runtime_config_builder.build_runtime_config_from_file(file_path)`. |
| `services/metadata/core/variable_registry.py` | Builds `VariableSpec` objects (flat raw→canonical mapping) from a runtime config and file groups. Use `build_variable_registry(runtime_cfg, file_groups)`. |
| `services/metadata/core/file_group_builder.py` | Builds `FileGroup` objects (master path, format, backup files) for all file groups in a site config. Use `build_file_groups(runtime_cfg)` when the target file group is not known in advance. Reads the site's raw-data directory off `runtime_cfg.input_data_path` (adapter-populated); raises if unset — this function makes no `infrastructure.paths`/TERN calls itself. |
| `services/metadata/core/site_config_schema.py` | Pydantic schema models and structural validation for site YAML configs. Entry point: `validate_L1_config_structure(file)`. |
| `services/metadata/core/variable_name_parser.py` | Parses canonical variable names into components. `NameParser` class. |
| `services/metadata/tern/rdf_label_resolver.py` | Resolves RDF URI labels from the TERN data store. Used by `site_metadata_repository`. |
| `services/data/transform_service.py` | Unit conversion and derived quantity calculation registries (`@register_conversion`, `@register_calculation`). |
| `services/data/raw_data_loader.py` | Loads TOA5 and EddyPro file formats. |
| `orchestration/dataframe_builder.py` | Core ETL: loads raw data → converts units → merges instrument periods → renames to canonical names. Convenience API: `build_dataframe_from_site_name(site_name, quantities=None, start_date=None)` and `build_dataframe_from_context(ctx, ...)`. Low-level: `build_dataframe(file_groups, registry, quantities=None, ...)` for callers that already hold those objects. |
| `orchestration/dataset_builder.py` | High-level API: `build_dataset_from_site_name()`, `build_dataset_from_context()`. Orchestrates dataframe build → derived quantity padding → xarray Dataset with variable and global metadata. Exports `DatasetBuildIntermediate` (used by `derived_quantities`). |
| `orchestration/derived_quantities.py` | Derives missing RH↔AH and CO2 mole fraction; maintains metadata lineage. |
| `orchestration/build_L1_zarr.py` | Writes a per-site whole-history Zarr store (one store per site, no year-splitting) — the canonical L1 intermediate `build_L1_nc.py`'s operational path reads from. `update()` is the 30-min-cadence path (`construct_L1_zarr` task): checkpoints off the store's own last timestamp, tail-reads and appends only new records, falling back to a full rebuild on any failure (e.g. a site-config schema change breaking the append). `build()` is a full rebuild from all raw data — used to seed a new store and by the nightly `rebuild_L1_zarr` reconciliation task. `instrument_history` is stored in full structured form (not flattened/year-clipped like NetCDF's) since Zarr attrs are JSON-native; `build_L1_nc.build_from_zarr()` rehydrates it and reproduces the year-clipping itself. |
| `orchestration/build_L1_nc.py` | Export step: converts L1 xarray Dataset to annual NetCDF files. Adds spatial dims, QC flags, global/variable metadata. Separate from dataset construction by design. `build_from_zarr()` (operational path, used by `construct_L1_nc`) reads an already-processed site from its Zarr store (`orchestration/build_L1_zarr.py`) instead of rebuilding from raw data; `build()` (raw-data, from scratch) is kept for manual/legacy/bootstrap use. |
| `orchestration/site_details_construction.py` | RTMC site-details data source. `collate_site_info(context, midnight=None)` is the shared collation function (sunrise/sunset, flux logger info, missing-data %, latest 10Hz file, site metadata). `build_site_details_json()` writes `site_info.json` for all sites (successor to legacy `details_constructor.site_info_2_json`), consumed by `tasks/build_tasks.py::construct_site_details_json`. `build_site_details_toa5(site)` writes the per-site TOA5 details file (successor to `details_constructor.write_site_info`), consumed by `construct_site_details_toa5`. |
| `services/data/data_monitor.py` | Site health monitoring: record coverage (`analyse_missing_data`), flux variable quality (`analyse_variable_quality`), threshold checks (`analyse_threshold_quality`). Each is an independent orchestration-level task. |
| `services/network/state_task_orchestrator.py` | Fans monitoring tasks concurrently across all pipeline sites. `STATE_TASK_SPECS` registry — add one dict entry to register a new task. |
| `infrastructure/read_cs_files.py` | Low-level Campbell Scientific file reader. Detects and parses TOA5, TOB1, TOB3, and CSIXML formats. Entry point: `read_cs_files(filename, metaonly=False)` — returns `(data, meta)`, or just `meta` when `metaonly=True`. Not called directly outside `tob_codec.py` — go through that wrapper instead. |
| `infrastructure/tob_codec.py` | Pandas-oriented wrapper around `read_cs_files` for TOB1/TOB3 fast data. `read_tob(files)` → `(DataFrame, metadata dict)`; `split_by_interval(df, interval_minutes, freq_hz)` chops a day's data into calendar-aligned blocks; `get_file_info(file)` reads just the header (station name, format, creation date) without loading data. |
| `services/data/tob_file_processor.py` | Site-level fast-flux (10 Hz TOB3) processing. `process_daily_tob_files(site, is_aux=False)` scans a site's raw-data `TMP` landing directory for daily TOB3 files, splits each into 30-minute TOA5 blocks (`services/data/toa5_writer.py`), and archives the original into a dated `TOB3/%Y_%m` directory (hash-checked to skip already-archived duplicates). Wired to `tasks/build_tasks.py::parse_main_fast_data`/`parse_aux_fast_data`. |

### Production pipeline stages

```
dataframe_builder   →  pd.DataFrame  (ETL: load → unit-convert → merge → rename)
derived_quantities  →  pd.DataFrame  (pad RH↔AH, CO2 mole fraction)
dataset_builder     →  xr.Dataset    (xarray wrapping + variable/global metadata)
build_L1_zarr       →  .zarr store   (whole-history, one store per site; checkpoint+append on the 30-min cadence, full rebuild nightly)
build_L1_nc         →  .nc files     (export: year-split, QC flags, CRS)
```

`build_L1_nc.build_from_zarr()` (the operational path, used by `construct_L1_nc`) reads from the Zarr store `build_L1_zarr` maintains instead of re-running `dataframe_builder`/`dataset_builder` every cycle — `construct_L1_zarr` runs immediately before `construct_L1_nc` in the cron schedule for exactly this reason. `build_L1_nc.build()` (raw-data, from scratch) still runs the full `dataframe_builder` → `dataset_builder` chain directly, kept for manual/legacy/bootstrap use.

Monitoring (`services/data/data_monitor.py`) calls `dataframe_builder.build_dataframe(quantities=...)` directly to get unit-converted data for a variable subset, bypassing the dataset construction stages. `analyse_missing_data` is the exception — it loads the raw flux file directly since timestamp-gap counting does not require unit conversion.

### Generic-core / TERN-adapter / ops boundary (forward-looking, not yet split out)

Within the four architectural layers above, modules further sort into three groups relevant to a possible future extraction of a generic, network-agnostic EC processing core (see the split-decision history in project memory). This is documentation of an existing informal boundary, not a new physical split — with one exception: `services/metadata/` itself *is* physically split into `services/metadata/core/` (tier 1) and `services/metadata/tern/` (tier 2) subpackages, a pure move-and-fix-imports rehearsal for the eventual real package boundary, no behaviour change. Decision: keep the boundary as in-repo discipline for now overall; revisit real extraction only once it has proven stable in practice. `orchestration/` is the harder remaining case for this same subpackage treatment if it's ever picked up — `dataframe_builder.py`/`dataset_builder.py` each mix tier-1 (`build_dataframe`, `build_dataframe_from_context`) and tier-2 (`build_dataframe_from_site_name`) *functions in the same file*, so splitting it means splitting file contents, not just moving files. One misplaced-by-directory file (`data_monitor.py`) has been physically relocated to its correct tier as a low-risk step toward that eventual split — see the note under tier 3.

**1. Generic core** (portable to any EC flux-processing setup): `domain/`, `infrastructure/`, `services/data/` (including `data_monitor.py`'s analysis functions — `analyse_missing_data`, `analyse_variable_quality`, `analyse_threshold_quality` — generic EC data-quality/QC logic, same tier as `transform_service.py`), the core of `orchestration/` (`build_dataframe`, `build_dataset_from_context`, `derived_quantities.py`), and `services/metadata/core/`: `canonical_quantity_registry.py`, `site_config_schema.py`, `runtime_config_builder.py`, `site_metadata_builder.py`, `file_group_builder.py`, `variable_name_parser.py`, `variable_registry.py`, plus `services/config_loader.py` (one level up, not part of the `metadata` split). Contract objects (`SiteRuntimeConfig`, `SiteContext`, `VariableSpec`, `FileGroup`, `CanonicalQuantityMetadata`) are the seam: any adapter that produces these shapes can drive the core. Note: `data_monitor.py` still imports `services.metadata.tern.site_registry` (TERN-adapter tier, see below) for site metadata — genuine tier purity would need that injected instead; deferred, not yet done.

**2. TERN-EP adapter** (produces the contract objects from TERN's sourcing): `services/metadata/tern/`: `site_registry.py`, `site_metadata_repository.py`, `instrument_registry.py`, `rdf_label_resolver.py`, `runtime_config_loader.py` (instrument-name validation and URI resolution against the TERN registry/RDF vocab, *and* raw-data path resolution via `infrastructure.paths`, happen here — see Architecture Decisions below; it delegates the actual generic assembly to `core/runtime_config_builder.py`), `instrument_validation_cache.py`; plus the `*_from_site_name` convenience wrappers (in `orchestration/`, not yet physically split out — see above), and the TERN-specific config content in `configs/sites/*.yml`, `site_metadata.yml`, `nc_metadata.yml`, and the `remote:` section of `paths.yml`. `SiteMetadata` (location, tower height, `time_step`/`freq_hz`, etc.) is likewise sourced here for TERN's own pipeline (`SiteRegistry.get_metadata()`, from `site_metadata.yml` or the RDF endpoint) — unchanged. A generic-core loading path for it now also exists (`services/metadata/core/site_metadata_builder.py`) but is a standalone addition for non-TERN callers only; TERN's own sourcing was deliberately left untouched rather than routed through it. Deliberately kept as a separate file/format from the variables config (`SiteConfig`) rather than one merged config — a merged format would have zero real precedent anywhere in this repo, whereas both separate formats do: the variables file already is `configs/sites/*.yml` verbatim, and the metadata file's shape is one real, already-existing record out of `configs/site_metadata.yml`. `services/metadata/qc_config_schema.py` (L2 QC pipeline config) sits outside this split — separate, not-yet-classified concern, left in the `services/metadata/` parent rather than either subpackage.

**3. TERN-EP ops/data-movement**: `tasks/`, `tools/` (the instrument-audit CLI family), `ui/`, `run.py`, `orchestration/site_details_construction.py` (RTMC), and most of `services/network/` — site fan-out (`state_task_orchestrator.py`), physical logger connectivity (`logger_monitor.py`, `connectivity.py`), and NC-output freshness checks (`nc_monitor.py`). `data_monitor.py` used to live here (misplaced by directory) — moved to `services/data/` (tier 1) since it's generic EC logic with no dependency on any other `services/network/` module.

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
- Any TERN-specific resolution (RDF/SPARQL instrument lookups, vocab validation) must complete in the TERN-adapter layer (`services/metadata/tern/runtime_config_loader.py` et al.) before contract objects reach the generic core — the core's functions (`build_dataframe`, `build_dataset_from_context`, `derived_quantities.py`) must never themselves call out to TERN's RDF/vocab store. Concretely, the core has two supported entry points into config assembly: `runtime_config_builder.build_runtime_config_from_file(file_path)` for a raw YAML with no TERN dependency at all, and `runtime_config_builder.build_runtime_config(validated_config, instrument_uris=None, input_data_path=None)` for an already-validated `SiteConfig` an adapter has optionally enriched — `runtime_config_loader.load_runtime_config(file_path)` is TERN's own adapter built on top of the latter. The same "optional, adapter-supplied, `None` on the pure-core path" pattern used for `instrument_uri` also covers physical file location: `SiteRuntimeConfig.input_data_path` is populated by the TERN adapter (via `infrastructure.paths`) and consumed opaquely by `file_group_builder.build_file_groups`, which makes no path-resolution decisions of its own and raises if the field is unset.
- The per-site whole-history Zarr store (`orchestration/build_L1_zarr.py`) is the canonical L1 intermediate for NetCDF export — `construct_L1_nc` reads from it (`build_from_zarr()`) rather than rebuilding from raw data on the operational 30-min cadence. `instrument_history` is kept in full structured form in the Zarr store (not flattened/year-clipped, unlike NetCDF's own attrs) specifically so NetCDF export can still reproduce exact per-year clipping from it — do not re-flatten it at Zarr-write time without discussion.

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
