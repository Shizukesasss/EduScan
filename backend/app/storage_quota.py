"""Serialize quota checks and publication on each storage root."""

import os
import stat
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import HTTPException

from .request_limits import MIB

LOCK_NAME = ".eduscan-quota.lock"
REPORT_WORK_DIR = ".report-work"


def quota_detail(category: str) -> str:
    return f"{category} storage quota exceeded. Free space in that category or increase its configured quota."


class StorageQuotaExceeded(HTTPException):
    def __init__(self, category: str) -> None:
        super().__init__(507, quota_detail(category))


@contextmanager
def storage_lock(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    with (root / LOCK_NAME).open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            except OSError as error:
                raise HTTPException(503, "Storage is busy. Try again shortly.") from error
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)


def require_capacity(root: Path, category: str, limit_mib: int, added: int, *,
                     replacing=(), extra_roots=(), skip_dirs=(), suffix: str | None = None,
                     recursive: bool = True) -> None:
    """Check retained bytes while the caller holds the root lock."""
    primary = root.resolve()
    roots = [primary]
    for directory in extra_roots:
        resolved = directory.resolve()
        if not any(resolved.is_relative_to(existing) for existing in roots):
            roots = [existing for existing in roots if not existing.is_relative_to(resolved)]
            roots.append(resolved)
    replaced = {path.resolve() for path in replacing}
    used = reclaimable = 0
    for directory in roots:
        for folder, folders, filenames in os.walk(directory, onerror=_check_scan_error):
            current = Path(folder)
            folders[:] = [name for name in folders if name not in skip_dirs
                          and not (current / name).is_junction()] if recursive else []
            for name in filenames:
                if name == LOCK_NAME or (suffix and not name.lower().endswith(suffix)):
                    continue
                candidate = current / name
                try:
                    info = candidate.lstat()
                except FileNotFoundError:
                    continue
                if stat.S_ISREG(info.st_mode):
                    used += info.st_size
                    if candidate in replaced:
                        reclaimable += info.st_size
    # An existing installation can shrink its usage even after lowering its quota.
    if added > reclaimable and used - reclaimable + added > limit_mib * MIB:
        raise StorageQuotaExceeded(category)


def _check_scan_error(error: OSError) -> None:
    if not isinstance(error, FileNotFoundError):
        raise error


@contextmanager
def atomic_write_path(target: Path):
    """Expose a scratch path and publish it only after the write succeeds."""
    with NamedTemporaryFile(dir=target.parent, prefix=".eduscan-write-", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        yield temporary
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
