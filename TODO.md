# TODO

## RTMC site-details migration (site_details_construction.py)

Replacing the legacy `data_constructors.details_constructor` (old repo) with
`orchestration/site_details_construction.py` in this pipeline.

### Done

- [x] `collate_site_info(context, midnight=None)` — shared per-site collation
      (metadata, sunrise/sunset, flux logger info, missing-data %, latest 10Hz
      file). Single source of truth for both outputs below.
- [x] `generate_site_info()` — JSON writer, successor to
      `details_constructor.site_info_2_json`. Writes
      `/opt/TERN_EP/network/info/site_info.json` (new `network.info` stream
      in `configs/paths.yml`). Concurrent across sites via
      `infrastructure.parallel_executor.run_concurrent` (~59s for 29 sites,
      down from ~3m35s serial).
- [x] Wired into `tasks/monitor_tasks.py::construct_site_details_json()`,
      replacing the legacy import. Verified via `tasks.tasks.run_task(...)`.
- [x] LICOR/EddyPro sites (no TOA5 info line): `format='LICOR'`,
      `logger_type='SmartFlux'`, rest blank — confirmed against
      `CumberlandPlain`.
- [x] Module renamed `site_info_construction.py` → `site_details_construction.py`
      to match the `construct_site_details*` task names. CLAUDE.md updated
      (stale "Modules Deliberately Deferred" section removed; both entries
      there had already been fixed).
- [x] `build_site_details_toa5(site, midnight=None)` — TOA5 writer, successor
      to `details_constructor.write_site_info`. Consumes `collate_site_info`
      directly (not the JSON file) — keeps the two outputs decoupled but
      never out of sync with each other. Writes `<site>_details.dat` into
      the shared `homogenised_data.toa5` directory, alongside
      `<site>_merged_std.dat`, so `push_rtmc_toa5` picks it up automatically
      with no new push task needed. Confirmed against `AliceSpringsMulga`
      (CSI), `CumberlandPlain` (LICOR), and `WombatStateForest` (aliased
      site).
- [x] Wired into `tasks/monitor_tasks.py::construct_site_details(site)`,
      replacing the legacy import. Verified via
      `tasks.tasks.run_task('construct_site_details', site=...)`.
- [x] Diffed the new TOA5 output against the real production file
      (`/store/Homogenised_data/TOA5/Calperum_details.dat`). Info-line
      content matched exactly (same dummy placeholders, station_name = site
      name); column set had two extras (`site`, `dsa_label`) not in the
      legacy file — dropped via `TOA5_EXCLUDED_FIELDS` in
      `build_site_details_toa5` (kept in the JSON output, where `site` is
      the per-record key and `dsa_label` is harmless). Column names/order now
      match the historical file exactly.
- [x] Info-line quoting (`serial_num`/`program_sig` unquoted in the old
      `details_constructor` output, quoted in the new `write_toa5_csv`
      output) — resolved, not a bug. Confirmed against a genuine CR6 logger
      file (`AliceSpringsMulga_EC_slow_core.dat`): real TOA5 info lines quote
      every field, including numeric ones (e.g. `"18242"`, `"30768"`). The
      old writer's unquoted `9999` was its own artifact, not real TOA5
      convention — the new all-quoted output is the more correct match. No
      change needed.

### To do

- [ ] Once both JSON and TOA5 outputs are validated in production, retire the
      legacy cron/task path entirely (the old `data_constructors.details_constructor`
      import can be dropped from `monitor_tasks.py`).
- [ ] Optional: pre-warm `instrument_registry`'s vocab cache (one `get_context()`
      call) before `generate_site_info`'s thread pool dispatch — first run
      currently fires 8 concurrent SPARQL queries to `graphdb.tern.org.au`
      before the `lru_cache` catches up (self-resolves in ~8-10s, not
      currently a real problem, but same root cause likely affects
      `state_task_orchestrator`'s other concurrent site tasks too).

## Known, out-of-scope issues noticed along the way

- [ ] `WombatStateForest` sunrise/sunset comes back blank — RDF graph query
      returns no `elevation` for this site specifically (looks like a data
      issue in the TERN metadata source, not a pipeline bug).
- [ ] 10Hz fast-data processing needs attention ("get that processing working
      again" — per-site `TOB3` fast files largely absent from
      `/store/Raw_data/<site>/Flux/Fast/TOB3`). Separate task, not started.
- [ ] `services/network/data_monitor.py::analyse_missing_data` calls
      `paths.get_local_stream_path(..., file_name=...)` — that kwarg doesn't
      exist on `get_local_stream_path` (removed when `paths.py` was
      refactored to Pydantic models). Currently broken; noticed while
      investigating site-details flux-file path resolution, not yet fixed.
- [ ] `tasks/tasks.py::_run_site_task` (line ~177) runs every site-scoped task
      strictly sequentially (`for s in site_list: ...`) — no `run_concurrent`
      or thread pool. Affects every `@register`ed task with a `site` param
      (`construct_L1_nc`, `construct_toa5_from_nc`, `update_EddyPro_master`,
      `process_profile_data`, `parse_main_fast_data`/`parse_aux_fast_data`,
      all pull/push tasks in `transfer_tasks.py`, and now
      `construct_site_details`, which builds the TOA5 details file). Different
      code path from `state_task_orchestrator.py` (already concurrent) and from
      `generate_site_info` (concurrent internally, but registered as a
      global task so it bypasses `_run_site_task` entirely). Pipeline-wide
      change, not scoped to this migration — noted for later discussion.
