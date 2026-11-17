#!/usr/bin/env python3
"""TOA5 file concatenator.

Splices a master TOA5 file with one or more slave files, patching gaps in the
master with records from the slaves.  Master data always takes priority: for
any timestamp present in both master and a slave the master record is kept.
Slave files are consumed in order; the first slave to provide a record for a
missing timestamp wins.

Note on deduplication: the sort-and-dedup logic here intentionally differs
from ``fluxcore.infrastructure.data_conditioning.condition_dataframe``, which pads the
output to a uniform time index.  The concatenator preserves only timestamps
that appear in at least one input file — no NaN rows are inserted for gaps
that no file covers.

``write_toa5_patch`` is the non-destructive alternative to
``concatenate_toa5``: instead of a spliced copy of the master, it writes only
the missing records, as a numbered ``.patch`` file beside the master's raw
directory (fluxcore reads it after the master and its backups), plus a YAML
sidecar recording where the records came from and why.
"""

import datetime
import getpass
import pathlib
import re

import pandas as pd
from fluxcore import load_raw_data, load_raw_header
from fluxcore.infrastructure import file_io as core_file_io
from fluxcore.infrastructure.data_conditioning import infer_interval

from fluxtools import data_diagnostics, file_io, toa5_writer
from fluxtools.concat_common import validate_headers, validate_interval

_HEADER_LABELS = ("variable", "units", "sampling")


def _load_header(file_path: pathlib.Path) -> tuple[list, list[list]]:
    """Return (info, [variable, units, sampling]) for a TOA5 file."""
    raw = load_raw_header(file_path=file_path, file_format="TOA5")
    info = raw.pop("info")
    return info, list(raw.values())


def analyse_gap_fill(
    master: str | pathlib.Path,
    slaves: list[str | pathlib.Path],
) -> dict:
    """Report which gaps in the master file each slave would fill.

    Applies the same header/interval validation as ``concatenate_toa5`` and
    simulates its slave-priority rule (first slave to cover a missing
    timestamp wins), without writing any output.

    Args:
        master:
            Path to the authoritative TOA5 file.
        slaves:
            Paths to supplementary files to check against the master's gaps.

    Returns:
        Report dict with keys:
            'master_gaps'         — number of timestamps missing from the
                                    master's uniform time index (spanning its
                                    first to last record).
            'gap_timestamps'      — sorted list of those missing timestamps.
            'slave_fill'          — {filename: {'fills': int, 'timestamps':
                                    [...]}} for each slave that covers at
                                    least one gap, in the order slaves are
                                    consumed.
            'unfilled_gaps'       — number of gaps no slave covers.
            'unfilled_timestamps' — sorted list of those timestamps.

    Raises:
        ValueError: if any slave has incompatible headers or a different time
            step from the master.
        TypeError: if any loaded DataFrame does not have a DatetimeIndex.
    """
    master = pathlib.Path(master)
    slaves = [pathlib.Path(s) for s in slaves]

    master_headers = _load_header(master)[1]
    master_df = load_raw_data(file_path=master, file_format="TOA5")
    master_df = master_df.sort_index(kind="stable")
    master_df = master_df[~master_df.index.duplicated(keep="first")]

    interval = infer_interval(master_df)
    remaining_gaps = data_diagnostics.analyse_data_gaps(
        df=master_df, interval_minutes=interval
    )["missing_timestamps"]

    report = {
        "master_gaps": len(remaining_gaps),
        "gap_timestamps": list(remaining_gaps),
        "slave_fill": {},
    }

    for slave_path in slaves:
        slave_headers = _load_header(slave_path)[1]
        validate_headers(master_headers, slave_path, slave_headers, _HEADER_LABELS)

        slave_df = load_raw_data(file_path=slave_path, file_format="TOA5")
        validate_interval(master_df, slave_df, slave_path)

        filled = remaining_gaps.intersection(slave_df.index)
        if len(filled):
            report["slave_fill"][slave_path.name] = {
                "fills": len(filled),
                "timestamps": list(filled),
            }
        remaining_gaps = remaining_gaps.difference(filled)

    report["unfilled_gaps"] = len(remaining_gaps)
    report["unfilled_timestamps"] = list(remaining_gaps)

    return report


def concatenate_toa5(
    master: str | pathlib.Path,
    slaves: list[str | pathlib.Path],
    output: str | pathlib.Path,
    min_timestamp: str | pd.Timestamp | None = None,
) -> dict:
    """Splice TOA5 files, patching gaps in master with data from slave files.

    Master data takes priority: for any timestamp present in both master and a
    slave the master record is kept.  Slaves are consumed in order; the first
    slave to supply a record for a missing timestamp wins.  Slave records may
    extend before or after the master's own date range (e.g. a slave that
    starts logging earlier than the master file).

    Datalogger clock resets (e.g. a program change or power loss that resets
    the clock to the CR1000X default power-on epoch of 1990-01-01) can plant
    a spurious record with a wildly wrong timestamp. There is no reliable
    automatic way to distinguish this from a genuine, correctly-timestamped
    record that happens to be isolated because of real data loss elsewhere
    in the record (the RECORD column is not a safe signal either, since it
    resets on ordinary program changes too). Pass ``min_timestamp`` to
    manually drop everything earlier than a known-good date if a slave file
    turns out to contain one of these artifacts.

    The RECORD column is preserved as-is.  At patch boundaries the record
    numbers will jump or reset — this is intentional and reflects the
    provenance of the data.

    Args:
        master:
            Path to the authoritative TOA5 file.
        slaves:
            Paths to supplementary files used to fill gaps in the master.
        output:
            Destination path for the spliced output file.
        min_timestamp:
            Optional manual floor. Records earlier than this are dropped
            from the final output.

    Returns:
        Report dict with keys:
            'master_records'     — records contributed by the master file.
            'slave_contributions'— {filename: n_records} for each slave that
                                   added at least one new record.
            'dropped_below_min'  — records dropped by ``min_timestamp``, if
                                   provided.
            'total_records'      — total records in the output file.

    Raises:
        ValueError: if any slave has incompatible headers or a different time
            step from the master.
        TypeError: if any loaded DataFrame does not have a DatetimeIndex.
    """
    master = pathlib.Path(master)
    slaves = [pathlib.Path(s) for s in slaves]

    # Load master

    master_info, master_headers = _load_header(master)
    combined = load_raw_data(file_path=master, file_format="TOA5")
    combined = combined.sort_index(kind="stable")
    combined = combined[~combined.index.duplicated(keep="first")]

    report = {"master_records": len(combined), "slave_contributions": {}}

    # Load and merge slaves

    for slave_path in slaves:
        _, slave_headers = _load_header(slave_path)
        validate_headers(master_headers, slave_path, slave_headers, _HEADER_LABELS)

        slave_df = load_raw_data(file_path=slave_path, file_format="TOA5")
        validate_interval(combined, slave_df, slave_path)

        before = len(combined)
        combined = (
            pd.concat([combined, slave_df])
            .sort_index(kind="stable")
            .loc[lambda df: ~df.index.duplicated(keep="first")]
        )
        added = len(combined) - before
        if added:
            report["slave_contributions"][slave_path.name] = added

    if min_timestamp is not None:
        min_timestamp = pd.Timestamp(min_timestamp)
        before = len(combined)
        combined = combined[combined.index >= min_timestamp]
        report["dropped_below_min"] = before - len(combined)

    report["total_records"] = len(combined)

    # Write output

    toa5_writer.write_toa5(
        data=combined,
        headers=master_headers,
        file_path=output,
        info=master_info,
    )

    return report


def next_patch_path(
    master: str | pathlib.Path, patch_dir: str | pathlib.Path
) -> pathlib.Path:
    """Path the next patch for `master` gets in `patch_dir`.

    LoggerNet's append-only backup numbering: `<name>.patch` first, then
    `<name>.1.patch`, `<name>.2.patch`, ... (highest existing + 1; gaps in
    the numbering are not reused).
    """
    master, patch_dir = pathlib.Path(master), pathlib.Path(patch_dir)
    existing = core_file_io.get_numbered_files(
        master, suffix="patch", directory=patch_dir
    )
    if not existing:
        return patch_dir / f"{master.name}.patch"
    number = re.fullmatch(
        rf"{re.escape(master.name)}(?:\.(\d+))?\.patch", existing[-1].name
    ).group(1)
    return patch_dir / f"{master.name}.{int(number or 0) + 1}.patch"


def _covered_timestamps(
    master: pathlib.Path, patch_dir: pathlib.Path
) -> tuple[pd.DataFrame, pd.Index, list[pathlib.Path]]:
    """Load the master; return it, the covered timestamps, and their files.

    Covered means present in the master, its backups or existing patches.
    """
    master_df = load_raw_data(file_path=master, file_format="TOA5")
    files = [
        master,
        *core_file_io.get_backup_files(master),
        *core_file_io.get_numbered_files(master, suffix="patch", directory=patch_dir),
    ]
    covered = master_df.index
    for path in files[1:]:
        covered = covered.union(load_raw_data(file_path=path, file_format="TOA5").index)
    return master_df, covered.dropna().unique(), files


def write_toa5_patch(
    master: str | pathlib.Path,
    slaves: list[str | pathlib.Path],
    patch_dir: str | pathlib.Path,
    reason: str,
    min_timestamp: str | pd.Timestamp | None = None,
    author: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Write the records `slaves` can add to `master` as a new `.patch` file.

    Never touches the master or anything else in its directory. A record is
    taken from a slave only if its timestamp is in none of: the master, the
    master's `.backup` files, or the patches already in `patch_dir`. So
    patches never overlap the logger's own data or each other, and fluxcore
    (which reads master > backups > patches) only ever uses them to fill
    gaps. Slaves are consumed in order; the first to supply a timestamp
    wins. As in ``concatenate_toa5``, records may lie outside the master's
    own date range, and slaves must match the master's headers and interval.

    Alongside the patch, writes `<patch>.yml` recording the master, each
    slave (name, sha256, records contributed), the reason, the author, the
    creation time (UTC), and the patch's record count and time range.

    Args:
        master: the live raw file being patched (e.g. `Site_EC_flux.dat`).
        slaves: files to take missing records from, in priority order.
        patch_dir: where patches live (TERN: the `flux_slow_patch` stream,
            `<site>/Flux/Slow_patch`); created if missing.
        reason: why the patch exists (e.g. "comms outage, data retrieved
            from logger card"); required, recorded in the sidecar.
        min_timestamp: optional floor; slave records earlier than this are
            ignored (see ``concatenate_toa5`` on clock-reset artifacts).
        author: recorded in the sidecar; defaults to the current user.
        dry_run: if True, compute the report but write nothing.

    Returns:
        Report dict: 'patch_file' (Path, or None if there was nothing to
        add), 'records', 'first', 'last', 'slave_contributions'
        ({filename: n_records}), 'dropped_below_min', and 'checked_against'
        (names of the files whose timestamps were treated as covered).

    Raises:
        ValueError: if `reason` is blank, or a slave's headers or time step
            don't match the master's.
        FileExistsError: if the computed patch path already exists.
    """
    if not reason or not reason.strip():
        raise ValueError("A reason is required for every patch.")
    master, patch_dir = pathlib.Path(master), pathlib.Path(patch_dir)
    slaves = [pathlib.Path(s) for s in slaves]
    if min_timestamp is not None:
        min_timestamp = pd.Timestamp(min_timestamp)

    master_info, master_headers = _load_header(master)
    master_df, covered, checked = _covered_timestamps(master, patch_dir)

    pieces, contributions, dropped_below_min = [], {}, 0
    for slave_path in slaves:
        _, slave_headers = _load_header(slave_path)
        validate_headers(master_headers, slave_path, slave_headers, _HEADER_LABELS)
        slave_df = load_raw_data(file_path=slave_path, file_format="TOA5")
        validate_interval(master_df, slave_df, slave_path)

        slave_df = slave_df[slave_df.index.notna()]
        slave_df = slave_df[~slave_df.index.duplicated(keep="first")]
        if min_timestamp is not None:
            below = slave_df.index < min_timestamp
            dropped_below_min += int(below.sum())
            slave_df = slave_df[~below]
        new = slave_df[~slave_df.index.isin(covered)]
        if len(new):
            pieces.append(new)
            contributions[slave_path.name] = len(new)
            covered = covered.union(new.index)

    report = {
        "patch_file": None,
        "records": 0,
        "first": None,
        "last": None,
        "slave_contributions": contributions,
        "dropped_below_min": dropped_below_min,
        "checked_against": [path.name for path in checked],
    }
    if not pieces:
        return report

    patch = pd.concat(pieces).sort_index(kind="stable")
    patch_path = next_patch_path(master, patch_dir)
    report.update(
        patch_file=patch_path,
        records=len(patch),
        first=patch.index[0],
        last=patch.index[-1],
    )
    if dry_run:
        return report

    sidecar_path = patch_path.with_name(patch_path.name + ".yml")
    for path in (patch_path, sidecar_path):
        if path.exists():
            raise FileExistsError(f"{path} already exists; not overwriting.")

    toa5_writer.write_toa5(
        data=patch, headers=master_headers, file_path=patch_path, info=master_info
    )
    file_io.write_yml_file(
        sidecar_path,
        {
            "patch": patch_path.name,
            "master": master.name,
            "reason": reason.strip(),
            "author": author or getpass.getuser(),
            "created_utc": datetime.datetime.now(datetime.UTC).isoformat(
                timespec="seconds"
            ),
            "records": len(patch),
            "first": str(patch.index[0]),
            "last": str(patch.index[-1]),
            "min_timestamp": None if min_timestamp is None else str(min_timestamp),
            "sources": [
                {
                    "file": str(slave_path),
                    "sha256": file_io.file_sha256(slave_path),
                    "records": contributions.get(slave_path.name, 0),
                }
                for slave_path in slaves
            ],
            "checked_against": report["checked_against"],
        },
    )
    return report
