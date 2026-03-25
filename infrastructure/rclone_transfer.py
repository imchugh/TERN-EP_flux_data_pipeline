#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Feb 17 09:14:02 2026

@author: imchugh
"""

###############################################################################
### BEGIN IMPORTS ###
###############################################################################

from pathlib import Path
import subprocess as spc
import logging
from typing import Iterable

###############################################################################
### END IMPORTS ###
###############################################################################


###############################################################################
### BEGIN INITS ###
###############################################################################

APP_PATH = "rclone"
COPY_ARGS = (
    'copy', '--transfers', '10', '--progress', '--checksum', '--timeout', '0'
    )
logger = logging.getLogger(__name__)

###############################################################################
### END INITS ###
###############################################################################


###############################################################################
### BEGIN FUNCTIONS ###
###############################################################################

# -----------------------------------------------------------------------------
# Public API

def transfer(
    src: str,
    dst: str,
    *,
    exclude_dirs: Iterable[str] | None = None,
    set_modtime: bool = True,
    validate: bool = True,
    timeout: int = 600,
    ) -> spc.CompletedProcess:
    """
    Execute an rclone copy operation.

    Args:
        src: Source path (local or remote)
        dst: Destination path (local or remote)
        exclude_dirs: Optional directory patterns to exclude
        set_modtime: Whether to preserve modtime (SFTP specific)
        validate: Whether to validate src/dst before transfer
        timeout: Subprocess timeout in seconds

    Returns:
        CompletedProcess

    Raises:
        FileNotFoundError
        subprocess.TimeoutExpired
        subprocess.CalledProcessError
    """

    if validate:
        _validate_local_if_applicable(src)
        _validate_remote_if_applicable(dst)

    run_args = _build_copy_args(
        exclude_dirs=exclude_dirs,
        set_modtime=set_modtime,
    )

    cmd = [APP_PATH, *run_args, str(src), str(dst)]

    logger.info("Starting rclone transfer...")
    result = _run_subprocess(cmd, timeout=timeout)
    
    logger.debug("rclone transfer stdout:\n%s", result.stdout or "")
    logger.debug("rclone transfer stderr:\n%s", result.stderr or "")
    logger.info("Transfer succeeded")

    return result
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def check_remote_available(remote_path: str, timeout: int = 60) -> None:
    """
    Public remote health check.

    Raises on failure.
    """
    cmd = [APP_PATH, "lsd", remote_path]
    _run_subprocess(cmd, timeout=timeout)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def check_local_exists(path: str) -> None:
    """
    Public local existence check.
    """
    if not Path(path).exists():
        raise FileNotFoundError(f"Local path does not exist: {path}")
# -----------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def _validate_local_if_applicable(path: str) -> None:
    """
    Only validate if path looks local.
    """
    if not _is_remote(path):
        check_local_exists(path)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def _validate_remote_if_applicable(path: str) -> None:
    """
    Only validate if path looks remote.
    """
    if _is_remote(path):
        check_remote_available(path)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def _is_remote(path: str) -> bool:
    """
    Simple heuristic: rclone remotes contain ':' before first slash.
    e.g. 'remote_name:path/to/dir'
    """

    return ":" in str(path).split("/")[0]
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def _build_copy_args(
    *,
    exclude_dirs: Iterable[str] | None,
    set_modtime: bool,
    ) -> list[str]:
    """
    Assemble the list of arguments to pass to rclone via spc.

    Args:
        exclude_dirs (Iterable[str] | None): directories to exclude.
        set_modtime: makes it work.

    Returns:
        list[str]: valid rclone arg list.

    """

    args = list(COPY_ARGS)

    if exclude_dirs:
        for d in exclude_dirs:
            args.extend(["--exclude", f"{d}/**"])

    if not set_modtime:
        args.append("--sftp-set-modtime=false")

    return args
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
       
def _run_subprocess(cmd: list[str], timeout: int) -> spc.CompletedProcess:
    """
    Centralized subprocess runner with JSON logging.

    Args:
        cmd: command to run (list of strings or Paths)
        timeout: timeout in seconds
    """
    cmd_str = " ".join(map(str, cmd))  # Ensure Paths are strings

    try:
        result = spc.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
        logger.info(
            "subprocess_succeeded",
            extra={
                "cmd": cmd_str,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "returncode": result.returncode,
            },
        )
        return result

    except spc.TimeoutExpired as exc:
        logger.error(
            "subprocess_timeout",
            extra={
                "cmd": cmd_str,
                "timeout": timeout,
                "stdout": getattr(exc, "stdout", ""),
                "stderr": getattr(exc, "stderr", ""),
            },
            exc_info=True,
        )
        raise

    except spc.CalledProcessError as exc:
        logger.error(
            "subprocess_failed",
            extra={
                "cmd": cmd_str,
                "returncode": exc.returncode,
                "stdout": exc.stdout.strip(),
                "stderr": exc.stderr.strip(),
            },
            exc_info=True,
        )
        raise        
# -----------------------------------------------------------------------------        