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
    'copy', '--transfers', '10', '--checksum', '--timeout', '0'
    )
logger = logging.getLogger(__name__)

###############################################################################
### END INITS ###
###############################################################################


###############################################################################
### BEGIN EXCEPTIONS ###
###############################################################################

class RcloneError(spc.CalledProcessError):
    """
    CalledProcessError whose default message includes captured stderr, so the
    failure reason is visible from a bare traceback even without logging
    configured.
    """

    def __str__(self) -> str:
        stderr = (self.stderr or "").strip()
        if not stderr:
            return super().__str__()
        return f"{super().__str__()}\nstderr:\n{stderr}"

###############################################################################
### END EXCEPTIONS ###
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
    dry_run: bool = False,
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
        dry_run: If True, pass --dry-run to rclone (no files are transferred)

    Returns:
        CompletedProcess

    Raises:
        FileNotFoundError
        subprocess.TimeoutExpired
        RcloneError (subclass of subprocess.CalledProcessError)
    """

    if validate:
        _validate_local_if_applicable(src)
        _validate_remote_if_applicable(dst)

    run_args = _build_copy_args(
        exclude_dirs=exclude_dirs,
        set_modtime=set_modtime,
        dry_run=dry_run,
    )

    cmd = [APP_PATH, *run_args, str(src), str(dst)]

    logger.info("Starting rclone transfer%s...", " (dry run)" if dry_run else "")
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
def check_remote_writable(remote_path: str, timeout: int = 60) -> None:
    """
    Public remote write-permission check.

    `lsd` only confirms the path is listable, not writable, so this probes
    with a throwaway `touch` (removed on success) to catch permission-denied
    destinations before a real transfer is attempted.

    Raises on failure.
    """
    probe_path = f"{remote_path.rstrip('/')}/.rclone_write_test"
    _run_subprocess([APP_PATH, "touch", probe_path], timeout=timeout)
    _run_subprocess([APP_PATH, "deletefile", probe_path], timeout=timeout)
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
    dry_run: bool = False,
    ) -> list[str]:
    """
    Assemble the list of arguments to pass to rclone via spc.

    Args:
        exclude_dirs (Iterable[str] | None): directories to exclude.
        set_modtime: makes it work.
        dry_run: append --dry-run so no files are transferred.

    Returns:
        list[str]: valid rclone arg list.

    """

    args = list(COPY_ARGS)

    if exclude_dirs:
        for d in exclude_dirs:
            args.extend(["--exclude", f"{d}/**"])

    if not set_modtime:
        args.append("--sftp-set-modtime=false")

    if dry_run:
        args.append("--dry-run")

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
        raise RcloneError(
            exc.returncode, exc.cmd, output=exc.output, stderr=exc.stderr,
        ) from exc
# -----------------------------------------------------------------------------