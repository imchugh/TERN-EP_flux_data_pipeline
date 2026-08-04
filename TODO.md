# TODO

## RTMC site-details migration (site_details_construction.py)

Replacing the legacy `data_constructors.details_constructor` (old repo) with
`orchestration/site_details_construction.py` in this pipeline.

### Done

- [x] `collate_site_info(context, midnight=None)` — shared per-site collation
      (metadata, sunrise/sunset, flux logger info, missing-data %, latest 10Hz
      file). Single source of truth for both outputs below.
- [x] `build_site_details_json()` — JSON writer, successor to
      `details_constructor.site_info_2_json`. Writes
      `/opt/TERN_EP/network/info/site_info.json` (new `network.info` stream
      in `configs/paths.yml`). Concurrent across sites via
      `infrastructure.parallel_executor.run_concurrent` (~59s for 29 sites,
      down from ~3m35s serial).
- [x] Wired into `tasks/build_tasks.py::construct_site_details_json()`,
      replacing the legacy import. Verified via `tasks.tasks.run_task(...)`.
- [x] LICOR/EddyPro sites (no TOA5 info line): `format='LICOR'`,
      `logger_type='SmartFlux'`, rest blank — confirmed against
      `CumberlandPlain`.
- [x] Module renamed `site_info_construction.py` → `site_details_construction.py`
      to match the `construct_site_details_toa5`/`construct_site_details_json`
      task names. CLAUDE.md updated (stale "Modules Deliberately Deferred"
      section removed; both entries there had already been fixed).
- [x] `build_site_details_toa5(site, midnight=None)` — TOA5 writer, successor
      to `details_constructor.write_site_info`. Consumes `collate_site_info`
      directly (not the JSON file) — keeps the two outputs decoupled but
      never out of sync with each other. Writes `<site>_details.dat` into
      the shared `homogenised_data.toa5` directory, alongside
      `<site>_merged_std.dat`, so `push_rtmc_toa5` picks it up automatically
      with no new push task needed. Confirmed against `AliceSpringsMulga`
      (CSI), `CumberlandPlain` (LICOR), and `WombatStateForest` (aliased
      site).
- [x] Wired into `tasks/build_tasks.py::construct_site_details_toa5(site)`,
      replacing the legacy import. Verified via
      `tasks.tasks.run_task('construct_site_details_toa5', site=...)`.
- [x] Moved `construct_site_details_toa5`/`construct_site_details_json` from
      `tasks/monitor_tasks.py` to `tasks/build_tasks.py` — the output is
      mostly static site characteristics (location, vegetation, logger info)
      plus one monitoring-flavored field (`pct_missing`), not a health check;
      `monitor_tasks.py`'s other task (`construct_status_geojson`) wraps
      genuine health checks via `state_task_orchestrator`, whereas this is a
      data product for RTMC, same category as `construct_toa5_from_nc`.
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
- [x] `tasks/transfer_tasks.py::push_details_json` wired up to push
      `build_site_details_json`'s `site_info.json` output. It was already
      registered but pointed at `state_task_orchestrator.SITE_SUMMARY_PATH`
      (`network/state/site_summary.json`, a different file entirely — the
      health-monitoring aggregate — that has also never actually been
      generated). Repointed at `network.info/site_info.json`. Also hit and
      fixed a real bug surfaced by actually running it: the sftpgo remote
      (`flux-status-test.tern.org.au`) doesn't support SFTP `SetModTime`
      (`SSH_FX_OP_UNSUPPORTED`) — needed `set_modtime=False`. Verified: push
      succeeded, file confirmed present on the remote via `rclone lsl`.

### To do

- [ ] Once both outputs are validated, cut over from parallel-run to
      production: this pipeline currently writes to test paths
      (`/opt/TERN_EP/network/info/site_info.json`,
      `/store/Homogenised_data/TOA5_test/<site>_details.dat`) and pushes to
      a test remote (`flux-status-test.tern.org.au`), not the real
      production paths/remote the old cron writes to, so the two coexist
      without colliding. Cutover means switching off whatever cron trigger
      still invokes the old repo's `details_constructor.write_site_info`/
      `site_info_2_json`, and pointing this pipeline's output paths/remotes
      at production. (No legacy import remains in this repo — both task
      bodies were already fully replaced.)
- [ ] Optional: pre-warm `instrument_registry`'s vocab cache (one `get_context()`
      call) before `build_site_details_json`'s thread pool dispatch — first run
      currently fires 8 concurrent SPARQL queries to `graphdb.tern.org.au`
      before the `lru_cache` catches up (self-resolves in ~8-10s, not
      currently a real problem, but same root cause likely affects
      `state_task_orchestrator`'s other concurrent site tasks too).
- [ ] `tasks/transfer_tasks.py::push_status_geojson` (pushes `GEOJSON_PATH` to
      the same sftpgo remote as `push_details_json`) likely has the same
      `SetModTime` bug just fixed in `push_details_json` — it doesn't pass
      `set_modtime=False` either. Not yet exercised/confirmed broken (its
      source file already exists), and not fixed — flagged only, since it
      wasn't part of what was asked.

### Decided against

- No dedicated push task for the TOA5 site-details files. They already live
  in the same `homogenised_data.toa5` directory as `<site>_merged_std.dat`,
  so `push_rtmc_toa5` already covers them — and this whole legacy
  TOA5/RTMC push pipeline is being shut down soon, so a new task isn't
  worth adding for the remaining lifetime.

## COSMOZ data push migration (send_cosmoz_data.sh → push_cosmoz)

Replacing the legacy bash/subprocess push of each site's COSMOZ cosmic-ray
neutron soil-moisture file (`code/shell/send_cosmoz_data.sh` +
`code/file_transfers/sftp_transfer.py::push_cosmoz`) with a
`tasks/transfer_tasks.py::push_cosmoz(site)` task in this pipeline.

### Done

- [x] Replaced the pre-existing stub (`push_cosmoz` was already `@register`ed,
      calling a nonexistent `infrastructure.sftp_transfer` module) with a
      plain `rclone_transfer.transfer()` call — same shape as every other
      task in the file, including the pipeline's other genuine SFTP
      destination (`sftpgo:`). No bash script and no bespoke
      `infrastructure/sftp_transfer.py`/subprocess layer in this repo at all;
      the legacy shell script and its Python wrapper are fully superseded,
      not duplicated.
- [x] Added a `cosmoz` stream to `configs/paths.yml` under `raw_data`:
      local `Ancillary/<site>_cosmoz_CRNS.dat`, remote `cosmoz:/incoming`.
- [x] CSIRO's own site-naming convention for the remote `incoming/`
      subdirectory (`AliceSpringsMulga`→`AliceMulga`,
      `GreatWesternWoodlands`→`GWW`) is kept in a local `COSMOZ_ALIASES` dict
      in `transfer_tasks.py`, deliberately separate from `paths.yml`'s global
      `remote_aliases` map — that map applies to every remote stream for a
      site, and `GreatWesternWoodlands` isn't aliased anywhere else (its
      `uqrdm:` fast-flux/profile paths use the full name), so reusing it here
      would have silently broken those transfers.
- [x] Added a `push_cosmoz` column to `configs/tasks.csv`, `TRUE` for the
      same 7 sites as the legacy CSV: `AliceSpringsMulga`, `Fletcherview`,
      `GreatWesternWoodlands`, `Litchfield`, `MyallValeA`, `MyallValeB`,
      `Tumbarumba`.
- [x] Rewrote `tests/test_transfer_tasks.py::test_push_cosmoz` (previously
      mocked the nonexistent `infrastructure.sftp_transfer` module) to mock
      `rclone_transfer.transfer` like every sibling test; added an aliased-
      site case (`GreatWesternWoodlands` → `GWW`) in `TestRemoteAlias`.
- [x] New `cosmoz:` rclone remote registered (SFTP backend, host
      `pftp.csiro.au`, user `cosmoz_station`, key
      `~/.ssh/cosmoz_station_key`) — connectivity confirmed via
      `rclone lsd cosmoz:/incoming` (per-site directories present, including
      `AliceMulga`/`GWW`, confirming the alias mapping).
- [x] Verified end-to-end with a real push:
      `tasks.tasks.run_task('push_cosmoz', site='Litchfield')` succeeded, and
      `Litchfield_cosmoz_CRNS.dat` confirmed present on the remote via
      `rclone lsl cosmoz:/incoming/Litchfield`.
- [x] Wired into `/etc/cron.d/epcn_tasks_new`:
      `25 * * * * imchugh $HANDLER_PATH push_cosmoz` (own slot, hourly —
      matches legacy cadence). No shared resources with any other cron
      entry (own local file, own remote), so it doesn't matter whether it
      shares a time slot with another line or not — cron doesn't serialize
      across separate lines anyway (only same-line args, run sequentially by
      `task_handler.sh`'s loop, are guaranteed ordered).
- [x] Committed: `72a2864`.

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
      `construct_site_details_toa5`, which builds the TOA5 details file). Different
      code path from `state_task_orchestrator.py` (already concurrent) and from
      `build_site_details_json` (concurrent internally, but registered as a
      global task so it bypasses `_run_site_task` entirely). Pipeline-wide
      change, not scoped to this migration — noted for later discussion.
