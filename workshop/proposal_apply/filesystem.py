"""POSIX descriptor-relative inspection and private transaction-storage primitives.

Private transaction state may be created and durably updated. Repository target
files remain read-only throughout these helpers and the preparation stage.
"""
from __future__ import annotations

import os
import secrets
import stat
from dataclasses import dataclass
from typing import Iterable

_REQUIRED_DIR_FD_FUNCTIONS = (os.open, os.stat, os.unlink, os.rename, os.link, os.mkdir)


class FilesystemSafetyError(RuntimeError):
    """Raised when the platform or filesystem object fails a safety check."""


@dataclass(frozen=True)
class DirectoryIdentity:
    device: int
    inode: int


def require_posix_support() -> None:
    """Fail closed unless the required POSIX descriptor-relative APIs exist."""
    if os.name != "posix":
        raise FilesystemSafetyError("Proposal application requires a POSIX platform")
    if not all(hasattr(os, flag) for flag in ("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC", "O_NONBLOCK")):
        raise FilesystemSafetyError("Required POSIX open flags are unavailable")
    if any(function not in os.supports_dir_fd for function in _REQUIRED_DIR_FD_FUNCTIONS):
        raise FilesystemSafetyError("Required descriptor-relative filesystem operations are unavailable")
    if os.stat not in os.supports_follow_symlinks:
        raise FilesystemSafetyError("No-follow stat support is unavailable")
    if os.listdir not in os.supports_fd or not all(hasattr(os, name) for name in ("fchmod", "fsync")):
        raise FilesystemSafetyError("Required private transaction storage primitives are unavailable")
    try:
        import fcntl  # noqa: F401
    except ImportError as exc:
        raise FilesystemSafetyError("POSIX advisory file locking is unavailable") from exc


def _component(name: str) -> str:
    if (not isinstance(name, str) or not name or name in {".", ".."}
            or "/" in name or "\\" in name or "\x00" in name):
        raise FilesystemSafetyError("Expected one safe path component")
    return name


def open_repository_root(path: str | os.PathLike[str]) -> int:
    """Open an existing directory by walking from / without following links."""
    require_posix_support()
    root = os.path.abspath(os.fspath(path))
    try:
        before = os.stat(root, follow_symlinks=False)
    except OSError as exc:
        raise FilesystemSafetyError("Repository root cannot be inspected") from exc
    if not stat.S_ISDIR(before.st_mode):
        raise FilesystemSafetyError("Repository root must be an existing real directory")

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        filesystem_root_fd = os.open("/", flags)
        try:
            components = [part for part in root.split("/") if part]
            descriptor = open_existing_parent(filesystem_root_fd, components)
        finally:
            os.close(filesystem_root_fd)
    except OSError as exc:
        raise FilesystemSafetyError("Repository root could not be opened safely") from exc

    try:
        after = os.fstat(descriptor)
        if (not stat.S_ISDIR(after.st_mode) or before.st_dev != after.st_dev
                or before.st_ino != after.st_ino):
            raise FilesystemSafetyError("Repository root changed while it was being opened")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def directory_identity(descriptor: int) -> DirectoryIdentity:
    info = os.fstat(descriptor)
    if not stat.S_ISDIR(info.st_mode):
        raise FilesystemSafetyError("Descriptor does not refer to a directory")
    return DirectoryIdentity(info.st_dev, info.st_ino)


def open_directory_at(parent_fd: int, name: str) -> int:
    require_posix_support()
    """Open one existing child directory without following a symlink."""
    name = _component(name)
    try:
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
            raise FilesystemSafetyError(f"Path component is not a real directory: {name}")
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=parent_fd,
        )
    except FilesystemSafetyError:
        raise
    except OSError as exc:
        raise FilesystemSafetyError(f"Cannot safely open directory component: {name}") from exc
    try:
        after = os.fstat(descriptor)
        if (not stat.S_ISDIR(after.st_mode) or before.st_dev != after.st_dev
                or before.st_ino != after.st_ino):
            raise FilesystemSafetyError(f"Directory component changed while opening: {name}")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def open_existing_parent(root_fd: int, components: Iterable[str]) -> int:
    require_posix_support()
    """Traverse existing directory components and return the final descriptor.

    The caller owns the returned descriptor. An empty component sequence
    returns a duplicate of root_fd, also owned by the caller.
    """
    current = os.dup(root_fd)
    try:
        for item in components:
            child = open_directory_at(current, item)
            os.close(current)
            current = child
        return current
    except BaseException:
        os.close(current)
        raise


def open_regular_file_at(parent_fd: int, name: str) -> int:
    require_posix_support()
    """Open an existing single-link regular file read-only, without following links."""
    name = _component(name)
    try:
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise FilesystemSafetyError(f"Cannot inspect target file safely: {name}") from exc
    if not stat.S_ISREG(before.st_mode):
        raise FilesystemSafetyError(f"Target is not a regular file: {name}")
    if before.st_nlink != 1:
        raise FilesystemSafetyError(f"Hard-linked targets are not supported: {name}")

    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
            dir_fd=parent_fd,
        )
    except OSError as exc:
        raise FilesystemSafetyError(f"Cannot safely open target file: {name}") from exc
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_dev != before.st_dev
                or info.st_ino != before.st_ino):
            raise FilesystemSafetyError(f"Target changed while it was being opened: {name}")
        if info.st_nlink != 1:
            raise FilesystemSafetyError(f"Hard-linked targets are not supported: {name}")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _verify_private_directory(descriptor: int) -> None:
    info = os.fstat(descriptor)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise FilesystemSafetyError("Private state directory must be owned by the current user")
    mode = stat.S_IMODE(info.st_mode)
    if mode & 0o077 or mode & 0o700 != 0o700:
        raise FilesystemSafetyError("Private state directory must have owner-only 0700 permissions")


def open_private_directory_at(parent_fd: int, name: str, *, create: bool = False) -> int:
    require_posix_support()
    """Open or create an owner-only private child directory."""
    name = _component(name)
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
            fsync_directory(parent_fd)
        except FileExistsError:
            pass
        except OSError as exc:
            raise FilesystemSafetyError(f"Cannot create private directory: {name}") from exc
    descriptor = open_directory_at(parent_fd, name)
    try:
        _verify_private_directory(descriptor)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def create_private_directory_at(parent_fd: int, name: str) -> int:
    require_posix_support()
    """Create a new private child directory; fail if the name already exists."""
    name = _component(name)
    try:
        os.mkdir(name, 0o700, dir_fd=parent_fd)
        fsync_directory(parent_fd)
    except OSError as exc:
        raise FilesystemSafetyError(f"Cannot exclusively create private directory: {name}") from exc
    descriptor = open_directory_at(parent_fd, name)
    try:
        _verify_private_directory(descriptor)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def fsync_directory(directory_fd: int) -> None:
    require_posix_support()
    """Flush directory metadata or fail explicitly when the filesystem cannot."""
    try:
        os.fsync(directory_fd)
    except OSError as exc:
        raise FilesystemSafetyError(
            "Directory fsync is unavailable; durable transaction preparation is unsupported"
        ) from exc


def _write_all(descriptor: int, content: bytes) -> None:
    view = memoryview(content)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("Short write while preparing private transaction data")
        view = view[written:]


def create_private_file_at(directory_fd: int, name: str, content: bytes) -> None:
    require_posix_support()
    """Create a new owner-only private file, flush its bytes and directory entry."""
    name = _component(name)
    if not isinstance(content, bytes):
        raise TypeError("Private transaction file content must be bytes")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    descriptor = os.open(name, flags, 0o600, dir_fd=directory_fd)
    try:
        os.fchmod(descriptor, 0o600)
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
            raise FilesystemSafetyError("New private file failed ownership or mode checks")
        _write_all(descriptor, content)
        os.fsync(descriptor)
    except BaseException:
        try:
            os.unlink(name, dir_fd=directory_fd)
            fsync_directory(directory_fd)
        except OSError:
            pass
        raise
    finally:
        os.close(descriptor)
    fsync_directory(directory_fd)


def read_private_file_at(directory_fd: int, name: str, *, max_bytes: int = 1024 * 1024) -> bytes:
    require_posix_support()
    """Read a bounded owner-only regular file without following links."""
    name = _component(name)
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except OSError as exc:
        raise FilesystemSafetyError(f"Cannot safely open private file: {name}") from exc
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
            raise FilesystemSafetyError(f"Private file ownership or mode is unsafe: {name}")
        if info.st_size > max_bytes:
            raise FilesystemSafetyError(f"Private file exceeds the size limit: {name}")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if len(content) > max_bytes:
            raise FilesystemSafetyError(f"Private file exceeds the size limit: {name}")
        return content
    finally:
        os.close(descriptor)


def replace_private_file_at(directory_fd: int, name: str, content: bytes) -> None:
    require_posix_support()
    """Atomically replace one private file using a flushed same-directory temp."""
    name = _component(name)
    try:
        existing = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        existing = None
    if existing is not None:
        if (not stat.S_ISREG(existing.st_mode) or existing.st_uid != os.getuid()
                or existing.st_nlink != 1 or stat.S_IMODE(existing.st_mode) != 0o600):
            raise FilesystemSafetyError(f"Refusing to replace unsafe private file: {name}")

    temporary = ".txn-" + secrets.token_hex(16) + ".tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    descriptor = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
    try:
        os.fchmod(descriptor, 0o600)
        _write_all(descriptor, content)
        os.fsync(descriptor)
    except BaseException:
        os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=directory_fd)
            fsync_directory(directory_fd)
        except OSError:
            pass
        raise
    else:
        os.close(descriptor)
    try:
        os.rename(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        fsync_directory(directory_fd)
    except BaseException:
        try:
            os.unlink(temporary, dir_fd=directory_fd)
            fsync_directory(directory_fd)
        except OSError:
            pass
        raise
