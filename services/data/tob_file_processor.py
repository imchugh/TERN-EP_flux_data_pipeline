"""Site-level TOB file processing: unpack and partition fast-flux data files."""

import datetime as dt
import hashlib
import logging
from pathlib import Path

from infrastructure import paths
from infrastructure import tob_codec as tob
from services.data.toa5_writer import write_toa5
from services.metadata.site_registry import SiteRegistry

logger = logging.getLogger(__name__)

SITE_REGISTRY = SiteRegistry()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def process_daily_tob_files(site: str, is_aux: bool = False) -> list[Path]:
    """Process all daily TOB3 files waiting in a site's TMP directory.

    For each eligible file (TOB3 format, creation date before today):
    - reads the full file
    - splits into interval-length blocks matched to the site's averaging period
    - writes each block as a TOA5 file under a date-structured output directory
    - archives the original TOB3 file

    Output naming: ``TOA5_{site}_{freq_str}_{YYYY_MM_DD_HH_MM}.dat``
    Archive naming: ``TOB3_{site}_{freq_str}_{YYYY_MM_DD}.dat``

    Args:
        site: pipeline site name.
        is_aux: if True, processes the auxiliary fast-flux stream.

    Returns:
        Paths of all TOA5 files written during this call.
    """
    stream = "flux_fast_aux" if is_aux else "flux_fast"
    src_dir = paths.get_local_stream_path("raw_data", stream, site=site) / "TMP"
    out_base = src_dir.parent

    site_meta = SITE_REGISTRY.get_context(site=site).metadata
    time_step = int(site_meta.time_step)
    freq_hz = int(site_meta.freq_hz)
    freq_str = _freq_str(freq_hz)
    today = dt.date.today()

    written = []

    for file in sorted(src_dir.rglob("*.dat")):
        info = tob.get_file_info(file)

        if info["format"] != "TOB3":
            logger.error("not_tob3", extra={"file": file.name})
            continue

        if info["station_name"] != f"{site}_EC":
            logger.warning(
                "station_name_mismatch",
                extra={"file": file.name, "station": info["station_name"]},
            )

        creation_date = _parse_date(info["creation_date"])
        if creation_date >= today:
            continue

        try:
            df, metadata = tob.read_tob(file)
        except Exception as exc:
            logger.error("read_failed", extra={"file": file.name, "error": str(exc)})
            continue

        out_dir = out_base / creation_date.strftime("TOA5/%Y_%m/%d")
        out_dir.mkdir(parents=True, exist_ok=True)

        for end_dt, subset in tob.split_by_interval(df, time_step, freq_hz):
            filename = f"TOA5_{site}_{freq_str}_{end_dt.strftime('%Y_%m_%d_%H_%M')}.dat"
            out_file = out_dir / filename
            try:
                write_toa5(
                    data=subset,
                    headers=metadata["headers"],
                    file_path=out_file,
                    info=metadata["info"],
                )
                written.append(out_file)
                logger.info("wrote_toa5", extra={"file": filename})
            except Exception as exc:
                logger.error(
                    "write_failed", extra={"file": filename, "error": str(exc)}
                )

        try:
            _archive_tob3(
                site=site,
                file=file,
                freq_str=freq_str,
                creation_date=creation_date,
                out_base=out_base,
            )
        except FileExistsError as exc:
            logger.error("archive_failed", extra={"file": file.name, "error": str(exc)})

    return written


def get_last_tob_file(site: str, is_aux: bool = False) -> Path:
    """Return the most recently archived TOB3 file for a site.

    Args:
        site: pipeline site name.
        is_aux: if True, searches the auxiliary fast-flux stream.

    Raises:
        FileNotFoundError: if no archived files exist.
    """
    stream = "flux_fast_aux" if is_aux else "flux_fast"
    search_dir = paths.get_local_stream_path("raw_data", stream, site=site)
    files = sorted(f for f in search_dir.rglob("TOB3_*.dat") if "TMP" not in f.parts)
    if not files:
        raise FileNotFoundError(f"No archived TOB3 files found for {site}")
    return files[-1]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _parse_date(date_str: str) -> dt.date:
    return dt.datetime.strptime(date_str, tob.DATE_FORMAT).date()


def _freq_str(freq_hz: int) -> str:
    return f"{1000 // freq_hz}ms"


def _archive_tob3(
    site: str,
    file: Path,
    freq_str: str,
    creation_date: dt.date,
    out_base: Path,
) -> None:
    archive_dir = out_base / creation_date.strftime("TOB3/%Y_%m")
    archive_dir.mkdir(parents=True, exist_ok=True)

    dest = archive_dir / (
        f"TOB3_{site}_{freq_str}_{creation_date.strftime('%Y_%m_%d')}.dat"
    )

    if dest.exists():
        if _file_hash(file) != _file_hash(dest):
            raise FileExistsError(f"A non-identical file already exists at {dest.name}")
        file.unlink()
        logger.info("archive_duplicate_removed", extra={"file": file.name})
        return

    file.rename(dest)
    logger.info("archived_tob3", extra={"dest": dest.name})


def _file_hash(file: Path) -> str:
    return hashlib.sha256(file.read_bytes()).hexdigest()
