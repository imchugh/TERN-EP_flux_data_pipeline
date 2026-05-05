#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Feb 19 11:00:09 2026

@author: imchugh
"""

import datetime as dt
import pathlib
import logging

from fast_file_handling.fast_file_parser import CSFileConverter, DailyPartitioner
from fast_file_handling.fast_file_output import write_toa5_file, get_file_hash

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------

def convert_fast_daily(
    site: str,
    csfile: CSFileConverter,
    output_dir: pathlib.Path,
    time_step: int,
    freq_hz: int,
    ):
    """
    Process a single TOB3 daily file for a site:
      - Partition into blocks
      - Create date-based output directories
      - Write each block with site + interval + timestamp filenames

    Args:
        site: site name (used in output filename)
        csfile: loaded TOB3 file converter
        output_dir: directory to write TOA5 block files
        time_step: site averaging interval (minutes)
        freq_hz: data collection frequency (Hz)
    """
    
    # Pass converter to the partitioner
    partitioner = DailyPartitioner(
        csfile=csfile, 
        time_step=time_step, 
        freq_hz=freq_hz
        )
       
    # Make sure the output path exists (create if not)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get the header lines and reformat for TOA5
    headers = csfile.metadata[:4].copy()
    headers[0][0] = 'TOA5'
    headers[0][-1] = csfile.ex_meta[0]   

    # Create block counters
    blocks_total = 0
    blocks_written = 0
    empty_blocks = 0

    # Iterate over blocks
    for block_num, block_info in partitioner.file_reference.iterrows():

        # Increment total blocks
        blocks_total += 1

        # Get the block
        data_block = partitioner.get_data_by_file_num(num=block_num)

        # Skip if empty
        if data_block.empty:
            empty_blocks += 1
            continue        

        # Build output filename
        output_file = (
            output_dir / 
            build_TOA5_file_name(
                site=site, 
                freq_hz=freq_hz, 
                input_date=block_info['end_date']
                )
            )

        # Write block
        write_toa5_file(
            output_file=output_file, 
            data_block=data_block, 
            headers=headers,
            )
        
        # Increment written blocks
        blocks_written += 1
    
    # Return block status
    return {
        "blocks_total": blocks_total,
        "blocks_written": blocks_written,
        "empty_blocks": empty_blocks,
        }
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------  

def archive_fast_daily(
    *,
    input_file: pathlib.Path,
    output_file: pathlib.Path
    ) -> str:
    """
    Archive processed TOB3 file with deduplication protection.    

    Args:
        input_file (pathlib.Path): absolute path of file to be archived.
        archive_dir (pathlib.Path): absolute path of archive directory.

    Raises:
        FileExistsError: raised if non-identical files are detected in the 
        destination directory.

    Returns:
        "archived" | "duplicate_removed"

    """

    # Make sure the output path exists (create if not)
    archive_dir = output_file.parent
    archive_dir.mkdir(parents=True, exist_ok=True)

    # Check for existence of identically-named files in destination
    if output_file.exists():
        
        # If file hash is the same, dump the file in the TMP dir
        if get_file_hash(input_file) == get_file_hash(output_file):
            input_file.unlink(missing_ok=True)
            return 'duplicate_removed'
            
        # Or raise if two non-identical files with same name
        else:
            raise FileExistsError(
                f"Conflict: non-identical file already archived at {output_file}"
            )

    # Move the file
    input_file.replace(output_file)
    return 'archived'
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def _process_single_fast_daily(
    *,
    site: str,
    root_dir: pathlib.Path,
    input_file: pathlib.Path,
    time_step: int,
    freq_hz: int,
    ) -> None:
    """
    

    Args:
        site: name of site.
        root_dir: root directory to which to append output paths.
        input_file: absolute path to input file.
        time_step: site averaging interval (minutes)
        freq_hz: data collection frequency (Hz)

    Returns:
        None.

    """

    # Get the file data converter
    csfile = CSFileConverter(input_file).load()
    creation_date = dt.datetime.strptime(
        csfile.get_file_info()["creation_date"], 
        "%Y-%m-%d %H:%M:%S"
        )
    
    # Convert
    output_dir = build_TOA5_file_path(
        input_date=creation_date, root_dir=root_dir
        )
    convert_result = convert_fast_daily(
        site=site,
        csfile=csfile,
        output_dir=output_dir,
        time_step=time_step,
        freq_hz=freq_hz,
    )
    
    # Defensive validation of contract
    if not isinstance(convert_result, dict):
        raise TypeError("convert_fast_daily did not return expected dict")
    
    blocks_total = convert_result.get("blocks_total", 0)
    blocks_written = convert_result.get("blocks_written", 0)
    empty_blocks = convert_result.get("empty_blocks", 0)

    # Archive only if conversion completes (catch and log in multi-file 
    # orchestration wrapper)
    output_file = (
        build_TOB3_file_path(
            input_date=creation_date, root_dir=root_dir
            ) / 
        build_TOB3_file_name(
            site=site, freq_hz=freq_hz, input_date=creation_date
            )
        )
    archive_status = archive_fast_daily(
        input_file=input_file,
        output_file=output_file,
        )
    
    return {
        "archive_status": archive_status,
        "blocks_total": blocks_total,
        "blocks_written": blocks_written,
        "empty_blocks": empty_blocks,
        }
# -----------------------------------------------------------------------------      

# -----------------------------------------------------------------------------        

def build_TOB3_file_name(
    site: str, freq_hz: int, input_date: dt.datetime, 
    ) -> str:
    """
    Build TOB3-formatted raw data file archive name (name only, no path).

    Args:
        site: name of site.
        freq_hz: data collection frequency (Hz)
        input_date: date to use for building file name.

    Returns:
        output file name.

    """
    
    file_part = _build_file_name_section(fmt='TOB3', site=site, freq_hz=freq_hz)
    return f'{file_part}_{input_date:%Y_%m_%d}.dat'
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------        

def build_TOA5_file_name(
    site: str, freq_hz: int, input_date: dt.datetime, 
    ) -> str:
    """
    Build TOA5-formatted raw data file archive name (name only, no path).

    Args:
        site: name of site.
        freq_hz: data collection frequency (Hz)
        input_date: date to use for building file name.

    Returns:
        output file name.

    """
    
    file_part = _build_file_name_section(fmt='TOA5', site=site, freq_hz=freq_hz)
    return f'{file_part}_{input_date:%Y_%m_%d_%H_%M}.dat'
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def _build_file_name_section(fmt: str, site: str, freq_hz: int) -> str:
    """
    Helper function for file naming.

    Args:
        fmt: format name to embed in file (TOA5 or TOB3)
        site: name of site.
        freq_hz: data collection frequency (Hz)


    Returns:
        output file name substring.

    """
    
    interval = str(int(1000 / freq_hz)) + 'ms'
    return f'{fmt}_{site}_{interval}'
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------        

def build_TOB3_file_path(
    *,
    input_date: str,
    root_dir: pathlib.Path,
    ) -> pathlib.Path:
    """
    Build TOB3-formatted raw data file archive path.

    Args:
        input_date: date to use for building directory path.
        root_dir: root directory to which to append output paths.

    Returns:
        output path.

    """
    
    return root_dir / 'TOB3' / input_date.strftime("%Y_%m")
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def build_TOA5_file_path(
    *,
    input_date: dt.datetime,
    root_dir: pathlib.Path,
    ) -> pathlib.Path:
    """
    Build TOA5-formatted raw data file archive path.

    Args:
        input_date: date to use for building directory path.
        root_dir: root directory to which to append output paths.

    Returns:
        output path.

    """
     
    return root_dir / 'TOA5' / input_date.strftime("%Y_%m/%d")
# -----------------------------------------------------------------------------        

# -----------------------------------------------------------------------------

def process_all_fast_daily(
    site: str,
    input_dir: pathlib.Path,
    root_dir,
    time_step: int,
    freq_hz: int,
    pattern: str = "*.dat",
    ) -> dict:
    """
    Process all matching TOB3 daily files for a single site.

    Args:
        site: site name (used in filenames)
        input_dir: directory containing TOB3 daily files
        root_dir: root directory to which to append output paths
        time_step: averaging interval (minutes)
        freq_hz: sampling frequency (Hz)
        pattern: glob pattern for selecting files
    """

    # Get the list of input files and return if none
    input_files = sorted(input_dir.glob(pattern))
    if not input_files:
        logger.warning(
            "No TOB3 files found", 
            extra={"site": site, "directory": str(input_dir)}
            )
        return {"status": "failure", "processed": 0, "failed": 0}

    logger.info(
        "processing_tob3_files_start",
        extra={"site": site, "num_files": len(input_files)},
        )

    # Create counters for success / fail
    processed = 0
    failed = 0
    empty_blocks_total = 0

    # Iterate over file list and process
    for input_file in input_files:
        try:
            result = _process_single_fast_daily(
                site=site,
                root_dir=root_dir,
                input_file=input_file,
                time_step=time_step,
                freq_hz=freq_hz,
                )
            
            processed += 1
            empty_blocks = result.get("empty_blocks", 0)
            empty_blocks_total += empty_blocks
            
            # Log if any empty blocks detected
            if empty_blocks > 0:
                logger.warning(
                    "empty_blocks_detected",
                    extra={"site": site, "file": input_file.name, "empty_blocks": empty_blocks},
                )

            # Log file processing
            logger.info(
                "file_processed",
                extra={
                    "site": site,
                    "file": input_file.name,
                    "archive_status": result.get("archive_status", "unknown"),
                    "blocks_written": result.get("blocks_written", None),
                    },
                )
            
        except Exception:
            
            failed += 1
            logger.exception(
                "file_processing_failed",
                extra={"site": site, "file": input_file.name},
                )
            
    
    status = "success" if failed == 0 else "failure"
    logger.info(
        "processing_tob3_files_complete",
        extra={
            "site": site,
            "processed": processed,
            "failed": failed,
            "empty_blocks_total": empty_blocks_total,
            "status": status,
        },
    )
            
    return {
        "status": status,
        "processed": processed,
        "failed": failed,
        "empty_blocks_total": empty_blocks_total,
        "site": site,
        }
# -----------------------------------------------------------------------------
