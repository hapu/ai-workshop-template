"""POSIX descriptor-relative filesystem primitives for proposal application.

This module exposes inspection-only helpers at implementation stage 1. It does
not create, replace, rename, or delete repository targets.
"""
from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from typing import Iterable

_REQUIRED_DIR_FD_FUNCTIONS = (os.open, os.stat, os.unlink, os.rename, os.link)


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
