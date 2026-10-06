#!/usr/bin/env python3
"""Subprocess wrapper around the rclone CLI for local/remote file transfer."""

import json
import logging
import subprocess as spc
from collections.abc import Iterable
from pathlib import Path

APP_PATH = "rclone"
COPY_ARGS = ("--transfers", "10", "--checksum", "--timeout", "0")
logger = logging.getLogger(__name__)


class RcloneError(spc.CalledProcessError):
    """CalledProcessError whose message includes captured stderr.

    Makes the failure reason visible from a bare traceback even without
    logging configured.
    """

    def __str__(self) -> str:
        """Append stripped stderr (if any) to the standard error message."""
        stderr = (self.stderr or "").strip()
        if not stderr:
            return super().__str__()
        return f"{super().__str__()}\nstderr:\n{stderr}"


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
    """Execute an rclone copy operation.

    `rclone copy` semantics: `dst` is always a directory. A directory `src`
    has its contents copied into it; a file `src` is copied into it under
    its own name. To copy a single file to a specific path/name, use
    `transfer_file`.

    Args:
        src: Source path (local or remote)
        dst: Destination directory (local or remote)
        exclude_dirs: Optional directory patterns to exclude
        set_modtime: If False, disable rclone's SFTP modtime-setting
            (adds --sftp-set-modtime=false). If True (default), leave
            rclone's default modtime behavior in place.
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
        _validate_src(src)
        _validate_remote_if_applicable(dst)

    run_args = _build_copy_args(
        "copy",
        exclude_dirs=exclude_dirs,
        set_modtime=set_modtime,
        dry_run=dry_run,
    )

    return _run_transfer([APP_PATH, *run_args, str(src), str(dst)], timeout, dry_run)


def transfer_file(
    src: str,
    dst: str,
    *,
    set_modtime: bool = True,
    validate: bool = True,
    timeout: int = 600,
    dry_run: bool = False,
) -> spc.CompletedProcess:
    """Copy a single file to an exact destination path via `rclone copyto`.

    Unlike `transfer`, `dst` is the full destination file path (so the file
    can be renamed on the way); missing parent directories are created.

    Args:
        src: Source file path (local or remote)
        dst: Destination file path (local or remote)
        set_modtime: If False, add --sftp-set-modtime=false (see `transfer`)
        validate: Whether to check `src` exists and is a file, and that a
            remote `dst`'s parent directory is listable, before transfer
        timeout: Subprocess timeout in seconds
        dry_run: If True, pass --dry-run to rclone (no files are transferred)

    Returns:
        CompletedProcess

    Raises:
        FileNotFoundError
        IsADirectoryError: `src` is a directory (use `transfer` instead)
        subprocess.TimeoutExpired
        RcloneError (subclass of subprocess.CalledProcessError)
    """
    if validate:
        _validate_src(src, require_file=True)
        if _is_remote(dst):
            check_remote_available(_remote_parent(dst))

    run_args = _build_copy_args(
        "copyto",
        exclude_dirs=None,
        set_modtime=set_modtime,
        dry_run=dry_run,
    )

    return _run_transfer([APP_PATH, *run_args, str(src), str(dst)], timeout, dry_run)


def _run_transfer(cmd: list[str], timeout: int, dry_run: bool) -> spc.CompletedProcess:
    """Run an assembled rclone copy/copyto command with standard logging."""
    logger.info("Starting rclone transfer%s...", " (dry run)" if dry_run else "")
    result = _run_subprocess(cmd, timeout=timeout)

    logger.debug("rclone transfer stdout:\n%s", result.stdout or "")
    logger.debug("rclone transfer stderr:\n%s", result.stderr or "")
    logger.info("Transfer succeeded")

    return result


def stat_remote(remote_path: str, timeout: int = 60) -> dict:
    """Return rclone's `lsjson --stat` entry for a remote file or directory.

    Cheap (a single-entry lookup, no directory listing) and works for both
    files and directories. Raises FileNotFoundError if the path does not
    exist.
    """
    cmd = [APP_PATH, "lsjson", "--stat", remote_path]
    try:
        result = _run_subprocess(cmd, timeout=timeout)
    except RcloneError as exc:
        # rclone exit code 3 = directory not found, 4 = file not found
        if exc.returncode in (3, 4):
            raise FileNotFoundError(
                f"Remote path does not exist: {remote_path}"
            ) from exc
        raise
    return json.loads(result.stdout)


def check_remote_available(remote_path: str, timeout: int = 60) -> None:
    """Confirm a remote path is listable via `rclone lsd`; raises on failure."""
    cmd = [APP_PATH, "lsd", remote_path]
    _run_subprocess(cmd, timeout=timeout)


def check_remote_writable(remote_path: str, timeout: int = 60) -> None:
    """Confirm a remote path is writable, not just listable.

    `lsd` only confirms the path is listable, not writable, so this probes
    with a throwaway `touch` (removed on success) to catch permission-denied
    destinations before a real transfer is attempted.

    Raises on failure.
    """
    probe_path = f"{remote_path.rstrip('/')}/.rclone_write_test"
    _run_subprocess([APP_PATH, "touch", probe_path], timeout=timeout)
    _run_subprocess([APP_PATH, "deletefile", probe_path], timeout=timeout)


def check_local_exists(path: str) -> None:
    """Raise FileNotFoundError if `path` does not exist locally."""
    if not Path(path).exists():
        raise FileNotFoundError(f"Local path does not exist: {path}")


def _validate_src(path: str, require_file: bool = False) -> None:
    """Check that a local or remote source exists (and is a file, if required)."""
    if _is_remote(path):
        is_dir = stat_remote(str(path))["IsDir"]
    else:
        check_local_exists(path)
        is_dir = Path(path).is_dir()
    if require_file and is_dir:
        raise IsADirectoryError(
            f"Source is a directory, not a file: {path} (use transfer() instead)"
        )


def _validate_remote_if_applicable(path: str) -> None:
    """Run the remote-availability check only if `path` looks remote."""
    if _is_remote(path):
        check_remote_available(path)


def _remote_parent(remote_path: str) -> str:
    """Parent of a remote path, e.g. 'remote:a/b/f.dat' -> 'remote:a/b'."""
    remote, _, rel = str(remote_path).partition(":")
    parent = rel.rstrip("/").rpartition("/")[0]
    return f"{remote}:{parent}"


def _is_remote(path: str) -> bool:
    """Simple heuristic: rclone remotes contain ':' before first slash.

    e.g. 'remote_name:path/to/dir'
    """
    return ":" in str(path).split("/")[0]


def _build_copy_args(
    verb: str,
    *,
    exclude_dirs: Iterable[str] | None,
    set_modtime: bool,
    dry_run: bool = False,
) -> list[str]:
    """Assemble the list of arguments to pass to rclone via spc.

    Args:
        verb: rclone subcommand ("copy" or "copyto").
        exclude_dirs: directories to exclude.
        set_modtime: if False, append --sftp-set-modtime=false.
        dry_run: append --dry-run so no files are transferred.

    Returns:
        Valid rclone arg list.
    """
    args = [verb, *COPY_ARGS]

    if exclude_dirs:
        for d in exclude_dirs:
            args.extend(["--exclude", f"{d}/**"])

    if not set_modtime:
        args.append("--sftp-set-modtime=false")

    if dry_run:
        args.append("--dry-run")

    return args


def _run_subprocess(cmd: list[str], timeout: int) -> spc.CompletedProcess:
    """Centralized subprocess runner with JSON logging.

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
            exc.returncode,
            exc.cmd,
            output=exc.output,
            stderr=exc.stderr,
        ) from exc
