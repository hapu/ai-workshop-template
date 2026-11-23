"""OS-managed POSIX advisory locks for proposal transactions."""
from __future__ import annotations

import errno
import math
import os
import stat
import time
from contextlib import ExitStack, contextmanager
from typing import Iterator

from .filesystem import FilesystemSafetyError, _component, require_posix_support


class LockTimeoutError(TimeoutError):
    """Raised when a cooperating workshop process holds a required lock."""


@contextmanager
def advisory_lock(
    state_dir_fd: int, name: str, timeout: float = 10.0
) -> Iterator[None]:
    """Hold an exclusive flock on a private lock file relative to state_dir_fd."""
    require_posix_support()
    import fcntl

    state_info = os.fstat(state_dir_fd)
    if not stat.S_ISDIR(state_info.st_mode) or state_info.st_uid != os.getuid():
        raise FilesystemSafetyError("Lock directory must be owned by the current user")
    state_mode = stat.S_IMODE(state_info.st_mode)
    if state_mode & 0o077 or state_mode & 0o300 != 0o300:
        raise FilesystemSafetyError("Lock directory must be private and owner-writable")

    name = _component(name)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout < 0:
        raise ValueError("Lock timeout must be a finite non-negative number")
    flags = os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
    try:
        descriptor = os.open(name, flags, 0o600, dir_fd=state_dir_fd)
    except OSError as exc:
        raise FilesystemSafetyError(f"Cannot safely open lock file: {name}") from exc

    locked = False
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise FilesystemSafetyError(f"Lock path is not a regular file: {name}")
        if info.st_uid != os.getuid():
            raise FilesystemSafetyError(f"Lock file is not owned by the current user: {name}")
        if info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077:
            raise FilesystemSafetyError(f"Lock file permissions or link count are unsafe: {name}")

        deadline = time.monotonic() + float(timeout)
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise LockTimeoutError(f"Timed out waiting for lock: {name}") from exc
                time.sleep(min(0.05, remaining))
        yield
    finally:
        try:
            if locked:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


@contextmanager
def transaction_locks(
    state_dir_fd: int,
    proposal_lock_name: str,
    repository_lock_name: str = "repository.lock",
    timeout: float = 10.0,
) -> Iterator[None]:
    """Acquire proposal then repository locks using one shared timeout budget."""
    proposal_lock_name = _component(proposal_lock_name)
    repository_lock_name = _component(repository_lock_name)
    if proposal_lock_name == repository_lock_name:
        raise ValueError("Proposal and repository lock names must be different")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout < 0:
        raise ValueError("Lock timeout must be a finite non-negative number")

    deadline = time.monotonic() + float(timeout)
    with ExitStack() as stack:
        stack.enter_context(advisory_lock(
            state_dir_fd, proposal_lock_name, max(0.0, deadline - time.monotonic())
        ))
        stack.enter_context(advisory_lock(
            state_dir_fd, repository_lock_name, max(0.0, deadline - time.monotonic())
        ))
        yield
