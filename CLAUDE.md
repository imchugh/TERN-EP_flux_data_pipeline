# CLAUDE.md — flux_data_pipeline (TERN-EP)

## Development Environment

- **Conda environment**: `ep_cntl` — activate before running scripts or installing packages. Build it from `environment.yml` (`conda env create -f environment.yml`); update that file (`conda env export --from-history`, then re-add the `pip:` section) after installing anything new.
- **`fluxcore`** (the generic processing core, `/opt/TERN_EP/fluxcore`, GitHub `imchugh/fluxcore`) is pip-installed **editable** into `ep_cntl` (`pip install -e /opt/TERN_EP/fluxcore`, listed in `environment.yml`). Core edits there take effect here immediately; core docs live in that repo's own `CLAUDE.md`.
- `rapidfuzz` is installed in `ep_cntl` (used by `services/metadata/instrument_registry.py` for fuzzy instrument name matching)
- `ruff` (formatting/linting, see `pyproject.toml`) and `git-filter-repo` are pip-installed in `ep_cntl`, not conda-installed
- Tests: `python -m unittest discover -s tests` (pytest isn't installed).
- **Site config files**: `/opt/TERN_EP/site_configs/operational/` — per-site YAML configs (e.g. `MyallValeA.yml`), a separate git repo.

## Project Purpose

TERN Ecosystem Processes' flux pipeline: the TERN-specific adapter and operations layer over **fluxcore**, the network-agnostic eddy covariance processing core. fluxcore turns raw logger files (Campbell Scientific TOA5, LI-COR EddyPro) into per-site, per-level Zarr stores (L1 homogenised, L2 QC'd). This repo supplies everything TERN-specific: resolving sites to fluxcore's contract objects (site registry, RDF/vocab instrument lookups, `paths.yml` directory templating, the site metadata DB cache), scheduling (cron → `tasks/`), data movement (rclone, 10 Hz TOB3 unpacking), network monitoring, the RTMC site-details feed, and the NetCDF export for Grafana.

## Relationship to fluxcore

The generic core was extracted **2026-10-14** into `fluxcore` with its git history (`git filter-repo`; `main` tagged `pre-split` just before the cutover). Before that it lived here as `domain/`, `services/metadata/core/`, `services/config_loader.py` and the core modules of `infrastructure/`, `services/data/` and `orchestration/` (TERN code then sat in `tern/` subpackages of those, flattened 2026-10-15). Import core modules as `fluxcore.<path>` (e.g. `from fluxcore.orchestration import build_L1_zarr`); a bare `orchestration.`/`infrastructure.`/`services.` import is always this repo's TERN code. `tests/test_import_targets.py` fails on any import of a local module path that doesn't exist (catches stale function-level imports of the old core paths).

- **Dependency direction:** this repo depends on fluxcore, never the reverse (fluxcore's `tests/test_self_contained.py` enforces its side).
- **Import fluxcore's public API** (`from fluxcore import X`; the list is fluxcore's `__all__` / its CLAUDE.md "Public API"). Deeper `fluxcore.*` paths are internal; the only ones used here are a few `fluxcore.infrastructure` utilities (`file_io`, `data_conditioning`, `datetime_utils`), listed in fluxcore's CLAUDE.md as known borrowers.
- **Contract objects are the seam:** `SiteContext` (`SiteRuntimeConfig` + `SiteMetadata`), `SiteQCConfig`, `VariableSpec`, `FileGroup` — all defined in `fluxcore.services.metadata.core`. TERN builds them; fluxcore consumes them.
- **Locations are data.** fluxcore takes every directory as an argument; `paths.py` + `configs/paths.yml` (TERN's directory templating) stay here and are applied by the wrappers in `orchestration/build_runner.py`.
- **Two front doors (agreed design):** TERN always uses fluxcore's live-object entry points ("function 1"). fluxcore's planned per-level file-in wrappers ("function 2", `run_L1`/`run_L2`, PyFluxPro-style control files with optional `site_metadata:`/`global_attrs:` sections) are for non-TERN users; TERN site configs never carry those sections.
- **Layout:** `infrastructure/`, `services/{data,metadata,network}/`, `orchestration/`, `tasks/`, `tools/`, `ui/`, `run.py`, `configs/` — all TERN. `fluxtools/` is the exception: see below. The per-layer names mirror fluxcore's but are separate top-level packages; nothing here shadows `fluxcore.*`.

## fluxtools (tools layered on fluxcore)

`fluxtools/` holds what fluxcore deliberately doesn't (fluxcore only *reads* raw files and keeps no general-purpose helpers): raw-file splicing and writing (`toa5_concatenator` — manual gap-filling of user-submitted data; `eddypro_concatenator` — the scheduled SmartFlux splice; `concat_common`; `toa5_writer`/`eddypro_writer`), `file_io` (JSON/YAML writers, file finders, atomic TOA5/EddyPro CSV writers), `datetime_utils` (current/local time, UTC offsets, `floor_to_interval`, TOA5 sub-second timestamps), `data_diagnostics` (gap/duplicate analysis) and `inspection` (e.g. `files_for_variable`). **It imports fluxcore but never TERN code** (`infrastructure`, `services`, ...), so it can become its own package by moving the directory once it needs its own release cycle. Moved out of fluxcore 2026-10-15.

## Key modules

| Module | Role |
|---|---|
| `services/metadata/site_registry.py` | **Canonical entry point for pipeline metadata.** `SiteRegistry` filters to only YML-configured sites. Defines the `SiteRegistry` class only — does not export a module-level instance; each consumer instantiates its own `SITE_REGISTRY = SiteRegistry()` singleton (see Key Patterns). |
| `services/metadata/site_metadata_repository.py` | Broader TERN data source — all sites including decommissioned. Not for pipeline logic. |
| `services/metadata/runtime_config_loader.py` | **TERN-adapter orchestration** for loading a site's `SiteRuntimeConfig`: validates instrument names against the TERN registry, resolves instrument URIs against the RDF vocab, resolves the site's raw-data directory via `infrastructure.paths`, then delegates structural validation and assembly to `runtime_config_builder`. Entry point: `load_runtime_config(file_path)` — the TERN-integrated equivalent of `runtime_config_builder.build_runtime_config_from_file(file_path)`. |
| `services/metadata/rdf_label_resolver.py` | Resolves RDF URI labels from the TERN data store. Used by `site_metadata_repository`. |
| `orchestration/site_runner.py` | **TERN-adapter** convenience wrappers: `build_dataframe_from_site_name(site_name, ...)` and `build_dataset_from_site_name(site_name, ...)` resolve a bare site name to a `SiteContext` via `SiteRegistry`, then delegate to `dataframe_builder`/`dataset_builder`'s `*_from_context` entry points. Both are interactive-use conveniences with no production callers (the build wrappers in `orchestration/build_runner.py` resolve a `SiteContext` themselves and call the core builders); `build_dataframe_from_site_name` is the way to get a unit-converted DataFrame for ad-hoc analysis without the full Dataset build. |
| `orchestration/build_runner.py` | **TERN-adapter** site-name wrappers and CLI (`python -m orchestration.build_runner {L1-zarr,L1-nc,L2-zarr,L2-nc} SITE ...`) for the four core builders: `build_L1_zarr_for_site`/`update_L1_zarr_for_site`, `build_L1_nc_from_zarr_for_site`, `build_L2_zarr_for_site`/`update_L2_zarr_for_site`, `build_L2_nc_from_zarr_for_site`. Each resolves the `SiteContext` (`SiteRegistry`, incl. `legacy=`) or `SiteQCConfig` (`qc_config_loader`), defaults the directories from the `homogenised_data` streams in `paths.yml`, and passes `configs/nc_metadata.yml` as `global_attrs`. What `tasks/build_tasks.py` calls. NetCDF is always exported from a Zarr store (`--zarr-dir` to export a non-default one, e.g. a `--legacy` store); there is no raw-to-NetCDF path. |
| `orchestration/site_details_construction.py` | RTMC site-details data source. `collate_site_info(context, midnight=None)` is the shared collation function (sunrise/sunset, flux logger info, missing-data %, latest 10Hz file, site metadata). `build_site_details_json()` writes `site_info.json` for all sites (successor to legacy `details_constructor.site_info_2_json`), consumed by `tasks/build_tasks.py::construct_site_details_json`. `build_site_details_toa5(site)` writes the per-site TOA5 details file (successor to `details_constructor.write_site_info`), consumed by `construct_site_details_toa5`. |
| `services/network/data_monitor.py` | Site health monitoring: record coverage (`analyse_missing_data`), flux variable quality (`analyse_variable_quality`), threshold checks (`analyse_threshold_quality`). Each is an independent orchestration-level task. TERN-side (moved from `services/data/` 2026-10-06 — not part of the processing package). |
| `services/network/state_task_orchestrator.py` | Fans monitoring tasks concurrently across all pipeline sites. `STATE_TASK_SPECS` registry — add one dict entry to register a new task. |
| `infrastructure/read_cs_files.py` | Low-level Campbell Scientific file reader. Detects and parses TOA5, TOB1, TOB3, and CSIXML formats. Entry point: `read_cs_files(filename, metaonly=False)` — returns `(data, meta)`, or just `meta` when `metaonly=True`. Not called directly outside `tob_codec.py` — go through that wrapper instead. |
| `infrastructure/tob_codec.py` | Pandas-oriented wrapper around `read_cs_files` for TOB1/TOB3 fast data. `read_tob(files)` → `(DataFrame, metadata dict)`; `split_by_interval(df, interval_minutes, freq_hz)` chops a day's data into calendar-aligned blocks; `get_file_info(file)` reads just the header (station name, format, creation date) without loading data. |
| `services/network/tob_file_processor.py` | Site-level fast-flux (10 Hz TOB3) processing. `process_daily_tob_files(site, is_aux=False)` scans a site's raw-data `TMP` landing directory for daily TOB3 files, splits each into 30-minute TOA5 blocks (`services/data/toa5_writer.py`), and archives the original into a dated `TOB3/%Y_%m` directory (hash-checked to skip already-archived duplicates). Wired to `tasks/build_tasks.py::parse_main_fast_data`/`parse_aux_fast_data`. Moved from `services/data/` 2026-10-01 (misplaced by directory, the reverse of `data_monitor.py`'s earlier move): it's site-name- and `paths.yml`-driven throughout, hence tier-3 ops despite processing the same TOB3/TOA5 formats `infrastructure/tob_codec.py`/`services/data/toa5_writer.py` handle. |

### Production pipeline (fluxcore stages, driven from here)

```
fluxcore dataframe_builder → derived_quantities → dataset_builder   (L1 dataset)
fluxcore build_L1_zarr   → {site}_L1.zarr  (30-min update: construct_L1_zarr; nightly full rebuild: rebuild_L1_zarr)
fluxcore build_L1_nc     → annual L1 NetCDF from the Zarr store (30-min current year: construct_L1_nc; nightly all years: rebuild_L1_nc) → push_L1_nc
fluxcore build_L2_zarr   → {site}_L2.zarr  (nightly full rebuild: rebuild_L2_zarr, chained after rebuild_L1_zarr)
```

All four are called through `orchestration/build_runner.py` (`tasks/build_tasks.py`), which supplies the `SiteContext` / `SiteQCConfig`, the `homogenised_data` directories and `configs/nc_metadata.yml` as `global_attrs`. The nightly line is `rebuild_L1_zarr rebuild_L1_nc rebuild_L2_zarr`: `rebuild_L1_nc` exists because `construct_L1_nc` only rewrites the current year, so without it a site-config rename/removal never reaches earlier years' files (and `construct_toa5_from_nc`, which merges the last two years, fails on the mismatched names — AlpinePeatland/Calperum, 2026-10-01 to 2026-10-15). L2 `update()` is unscheduled — whether L2 needs a 30-min cadence at all is undecided (L1 is 30-min only for Grafana; L2 has no consumer).

Monitoring (`services/network/data_monitor.py`) calls fluxcore's `dataframe_builder.build_dataframe(quantities=...)` directly for a unit-converted variable subset; `analyse_missing_data` loads the raw flux file directly. Ad-hoc analysis: `orchestration/site_runner.py`'s `build_dataframe_from_site_name(site_name, ...)`.

### NetCDF export

NetCDF is export-only, never a pipeline input. L1 NetCDF is produced every 30 min (`construct_L1_nc` → `push_L1_nc`) **only** because a downstream process feeds Grafana from it. No L2 NetCDF use case: `build_L2_nc` runs on demand only (`python -m orchestration.build_runner L2-nc SITE`). Otherwise NetCDF is supplied externally on request.

## Architecture Decisions (agreed, do not reverse without discussion)

- `SiteRegistry` is the canonical metadata entry point for pipeline-configured sites. Do not reach past it to `site_metadata_repository` for pipeline logic.
- `SITE_ALIASES = {'WombatStateForest': 'WombatForest'}` in `site_registry.py` is a deliberate temporary hack — legacy directory name kept until that directory is renamed. Remove when legacy code is switched off.
- Any TERN-specific resolution (RDF/SPARQL instrument lookups, vocab validation, `paths.yml` locations) completes here, in the adapter (`services/metadata/runtime_config_loader.py` et al.), before contract objects reach fluxcore — fluxcore never calls out to TERN's stores. `runtime_config_loader.load_runtime_config(file_path)` is TERN's adapter on top of fluxcore's `runtime_config_builder.build_runtime_config(validated_config, instrument_uris, input_data_path)`.
- TERN's site metadata keeps coming from the DB (local cache, `configs/site_metadata.yml` / RDF) via `SiteRegistry.get_metadata()` — not from fluxcore's file-based metadata route.
- The per-site whole-history Zarr store is the canonical L1 intermediate for NetCDF export (`construct_L1_nc` uses `build_from_zarr()`); `instrument_history` stays in full structured form in the store so NetCDF export can reproduce per-year clipping — do not re-flatten it at Zarr-write time without discussion.

## Configuration Files

TERN config lives in `configs/` (`infrastructure.paths.CONFIG_PATH`); load by name with `infrastructure.config_loader.load_config_file_from_name(name)` (defaults to `paths.CONFIG_PATH`). fluxcore's own configs (`canonical_quantities`, `nc_dim_attrs`, `nc_global_attrs`, `qc/` defaults) ship inside the fluxcore package.

- `configs/paths.yml` — local/remote resource paths with site placeholders
- `configs/site_metadata.yml` — TERN site metadata (location, commissioning, tower height)
- `configs/nc_metadata.yml` — TERN/OzFlux NetCDF global attributes (`acknowledgement`, `publisher_name`, `metadata_link`, `ozflux_link`, `data_link`), passed by `build_runner` as `global_attrs` over fluxcore's core attrs. Interim mechanism; agreed direction is in project memory.
- `configs/tasks.csv` (per-site task enablement), `vpn_ip.yml`, `soil_variables.yml`, `sparql_query_configs.yml`, `instrument_quantity_map.yml`, `instrument_name_corrections.yml`
- `/opt/TERN_EP/site_configs/operational/{SiteName}.yml` — **L1** per-site variable specs (fluxcore's site-config schema), file mappings, instrument metadata; `legacy/` holds earlier-generation snapshots, `templates/` PyFluxPro reference control files.
- `/opt/TERN_EP/site_configs/operational/L2/{SiteName}.yml` — **L2** per-site QC overrides (deltas over fluxcore's `qc/` defaults; semantics in fluxcore's CLAUDE.md), the `site_config_files_L2` stream in `paths.yml`, loaded by `services/metadata/qc_config_loader.py`.

L1 and L2 configs deliberately live in separate folders: `SiteRegistry.names()` and `ui/app.py` derive site names from `SITE_CONFIG_DIR.glob("*.yml")` (non-recursive), so an L2 file in the L1 folder would register as a bogus site.

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

### Site config: horizontal-location descriptions

The canonical name's horizontal-location qualifier (`Ts_a`, `Sws_b`, …) is a bare letter that groups co-located sensor arrays (e.g. one soil pit) but carries no meaning of its own. A site describes its letters in its own site config, beside the variable names that use them:

```yaml
custom_metadata:
  horizontal_location:
    belowground: {a: bare soil array 1, b: mulga array 1}
    aboveground: {...}
```

Validated by `HorizontalLocationConfig` (single-letter keys), carried onto `SiteRuntimeConfig.custom_metadata`. Deliberately the site config, not TERN's central site database: the letters are defined by the config's own variable names and change with sensor deployments, and non-TERN core users have no central database (the TERN adapter could still fill it from one later, like `instrument_uri`). Set at AliceSpringsMulga, Boyagin, Fletcherview and Ridgefield (migrated 2026-10-13 from the retired `configs/site_custom_metadata.yml`). **Not yet emitted to output** — the follow-up is a per-variable NetCDF attribute (e.g. `Ts_a: horizontal_location = "bare soil array 1"`).

## Key Patterns

- **Registry pattern**: `SiteRegistry`, conversion registry in `unit_conversions`, calculation registry in `calculations`
- **Decorator-based registration**: `@register_conversion()` (`unit_conversions`), `@register_calculation()` (`calculations`)
- **Module-level singleton**: use `SITE_REGISTRY = SiteRegistry()` at module level (same pattern as `state_task_orchestrator.py`, `dataset_builder.py`)
- **Pydantic dataclasses** for all metadata/config objects — immutable, type-checked
- **Threshold variable matching**: `THRESHOLD_SPECS` keys may include instrument qualifiers (e.g. `'Diag_IRGA'`, `'Diag_SONIC'`); `var_def.quantity` is always the base quantity (e.g. `'Diag'`). Derive base quantities with `quantity.startswith(var_def.quantity)`; match canonical DataFrame columns with `col.startswith(quantity)`.
