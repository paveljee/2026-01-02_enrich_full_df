#!/usr/bin/env python3
"""Watch a Linux directory tree and flag non-append-only file changes.

No third-party packages are required.  Uses Linux inotify via ctypes.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import dataclasses
import errno
import hashlib
import os
import select
import signal
import stat
import struct
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

# linux/inotify.h
IN_MODIFY = 0x00000002
IN_ATTRIB = 0x00000004
IN_CLOSE_WRITE = 0x00000008
IN_MOVED_FROM = 0x00000040
IN_MOVED_TO = 0x00000080
IN_CREATE = 0x00000100
IN_DELETE = 0x00000200
IN_DELETE_SELF = 0x00000400
IN_MOVE_SELF = 0x00000800
IN_Q_OVERFLOW = 0x00004000
IN_IGNORED = 0x00008000
IN_ISDIR = 0x40000000
IN_ONLYDIR = 0x01000000
IN_DONT_FOLLOW = 0x02000000
IN_EXCL_UNLINK = 0x04000000

WATCH_MASK = (
    IN_MODIFY
    | IN_ATTRIB
    | IN_CLOSE_WRITE
    | IN_MOVED_FROM
    | IN_MOVED_TO
    | IN_CREATE
    | IN_DELETE
    | IN_DELETE_SELF
    | IN_MOVE_SELF
    | IN_ONLYDIR
    | IN_DONT_FOLLOW
    | IN_EXCL_UNLINK
)
EVENT = struct.Struct("iIII")
EMPTY_DIGEST = hashlib.sha256(b"").digest()


@dataclasses.dataclass
class Record:
    dev: int
    ino: int
    size: int
    mtime_ns: int
    ctime_ns: int
    digest: bytes
    status: str = "OK"
    reason: str = ""
    exists: bool = True

    @property
    def identity(self) -> Tuple[int, int]:
        return self.dev, self.ino


class Inotify:
    def __init__(self) -> None:
        libc_name = ctypes.util.find_library("c")
        if not libc_name:
            raise RuntimeError("cannot find libc")
        self.libc = ctypes.CDLL(libc_name, use_errno=True)
        self.libc.inotify_init1.argtypes = [ctypes.c_int]
        self.libc.inotify_init1.restype = ctypes.c_int
        self.libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
        self.libc.inotify_add_watch.restype = ctypes.c_int
        self.fd = -1
        self.wd_to_dir: Dict[int, str] = {}
        self.open()

    def open(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
        flags = os.O_NONBLOCK | os.O_CLOEXEC
        self.fd = self.libc.inotify_init1(flags)
        if self.fd < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        self.wd_to_dir.clear()

    def add(self, directory: str) -> None:
        raw = os.fsencode(directory)
        wd = self.libc.inotify_add_watch(self.fd, raw, WATCH_MASK)
        if wd < 0:
            err = ctypes.get_errno()
            if err in (errno.ENOENT, errno.ENOTDIR, errno.EACCES):
                return
            raise OSError(err, os.strerror(err), directory)
        self.wd_to_dir[wd] = directory

    def read(self) -> Iterable[Tuple[str, int, int, str]]:
        while True:
            try:
                data = os.read(self.fd, 1024 * 1024)
            except BlockingIOError:
                return
            if not data:
                return
            offset = 0
            while offset + EVENT.size <= len(data):
                wd, mask, cookie, name_len = EVENT.unpack_from(data, offset)
                offset += EVENT.size
                raw_name = data[offset : offset + name_len].split(b"\0", 1)[0]
                offset += name_len
                base = self.wd_to_dir.get(wd, "")
                name = os.fsdecode(raw_name)
                path = os.path.join(base, name) if name else base
                yield path, mask, cookie, base

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1


class AppendWatch:
    def __init__(self, root: str, report: str, debounce_ms: int) -> None:
        self.root = os.path.realpath(root)
        self.report = report
        self.debounce = debounce_ms / 1000.0
        self.records: Dict[str, Record] = {}
        self.ino = Inotify()
        self.stop = False
        self.pending: Dict[str, float] = {}
        self.report_abs: Optional[str] = None
        self.report_tmp_prefix: Optional[str] = None

        if report != "-":
            self.report_abs = os.path.realpath(report)
            report_dir = os.path.dirname(self.report_abs)
            report_name = os.path.basename(self.report_abs)
            self.report_tmp_prefix = os.path.join(report_dir, f".{report_name}.tmp.")

    def rel(self, path: str) -> str:
        return os.path.relpath(path, self.root)

    def excluded(self, path: str) -> bool:
        absolute = os.path.abspath(path)
        if self.report_abs and absolute == self.report_abs:
            return True
        if self.report_tmp_prefix and absolute.startswith(self.report_tmp_prefix):
            return True
        return False

    @staticmethod
    def regular_lstat(path: str) -> Optional[os.stat_result]:
        try:
            st = os.lstat(path)
        except (FileNotFoundError, PermissionError, OSError):
            return None
        return st if stat.S_ISREG(st.st_mode) else None

    def walk_regular(self) -> Dict[str, os.stat_result]:
        found: Dict[str, os.stat_result] = {}
        stack = [self.root]
        while stack:
            directory = stack.pop()
            try:
                with os.scandir(directory) as it:
                    entries = list(it)
            except (FileNotFoundError, NotADirectoryError, PermissionError, OSError):
                continue
            for entry in entries:
                path = entry.path
                if self.excluded(path):
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(path)
                    elif entry.is_file(follow_symlinks=False):
                        st = entry.stat(follow_symlinks=False)
                        found[self.rel(path)] = st
                except (FileNotFoundError, PermissionError, OSError):
                    continue
        return found

    def rebuild_watches(self) -> None:
        self.ino.open()
        stack = [self.root]
        while stack:
            directory = stack.pop()
            self.ino.add(directory)
            try:
                with os.scandir(directory) as it:
                    entries = list(it)
            except (FileNotFoundError, NotADirectoryError, PermissionError, OSError):
                continue
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False) and not self.excluded(entry.path):
                        stack.append(entry.path)
                except OSError:
                    continue

    @staticmethod
    def hash_fd(fd: int, size: int, prefix_size: int) -> Tuple[bytes, bytes]:
        full = hashlib.sha256()
        prefix = hashlib.sha256()
        remaining = size
        prefix_remaining = min(prefix_size, size)
        offset = 0
        while remaining:
            chunk = os.pread(fd, min(1024 * 1024, remaining), offset)
            if not chunk:
                break
            full.update(chunk)
            if prefix_remaining:
                part = chunk[:prefix_remaining]
                prefix.update(part)
                prefix_remaining -= len(part)
            offset += len(chunk)
            remaining -= len(chunk)
        if remaining:
            raise OSError(errno.EIO, "short read while hashing")
        return full.digest(), prefix.digest()

    def compromise(self, rec: Record, reason: str) -> bool:
        changed = rec.status != "COMPROMISED"
        rec.status = "COMPROMISED"
        if not rec.reason:
            rec.reason = reason
        return changed

    def inspect(self, path: str, *, new_path: bool = False) -> bool:
        """Check one path. Return True if visible report state changed."""
        if self.excluded(path):
            return False
        rel = self.rel(path)
        rec = self.records.get(rel)

        flags = os.O_RDONLY | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(path, flags)
        except (FileNotFoundError, PermissionError, OSError):
            if rec and rec.exists:
                rec.exists = False
                return True
            return False

        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                return False

            if rec is None:
                full_digest, _ = self.hash_fd(fd, before.st_size, 0)
                after = os.fstat(fd)
                stable = (
                    before.st_size == after.st_size
                    and before.st_mtime_ns == after.st_mtime_ns
                    and before.st_ctime_ns == after.st_ctime_ns
                )
                self.records[rel] = Record(
                    dev=after.st_dev,
                    ino=after.st_ino,
                    size=after.st_size if stable else 0,
                    mtime_ns=after.st_mtime_ns if stable else 0,
                    ctime_ns=after.st_ctime_ns if stable else 0,
                    digest=full_digest if stable else EMPTY_DIGEST,
                )
                return True

            visible_changed = not rec.exists
            rec.exists = True

            identity_changed = rec.identity != (before.st_dev, before.st_ino)
            if identity_changed:
                visible_changed |= self.compromise(rec, "file was replaced or recreated")

            old_size = 0 if identity_changed else rec.size
            old_digest = EMPTY_DIGEST if identity_changed else rec.digest

            if before.st_size < old_size:
                visible_changed |= self.compromise(
                    rec, f"file shrank from {old_size} to {before.st_size} bytes"
                )

            full_digest, prefix_digest = self.hash_fd(fd, before.st_size, old_size)
            after = os.fstat(fd)

            if before.st_size >= old_size and prefix_digest != old_digest:
                visible_changed |= self.compromise(rec, "previous content is no longer a prefix")

            stable = (
                before.st_size == after.st_size
                and before.st_mtime_ns == after.st_mtime_ns
                and before.st_ctime_ns == after.st_ctime_ns
            )
            if stable:
                rec.dev = after.st_dev
                rec.ino = after.st_ino
                rec.size = after.st_size
                rec.mtime_ns = after.st_mtime_ns
                rec.ctime_ns = after.st_ctime_ns
                rec.digest = full_digest
            return visible_changed
        except (FileNotFoundError, PermissionError, OSError):
            return False
        finally:
            os.close(fd)

    def seed_created_file(self, path: str) -> bool:
        """Establish an empty baseline as close as possible to IN_CREATE."""
        if self.excluded(path):
            return False
        st = self.regular_lstat(path)
        if st is None:
            return False
        rel = self.rel(path)
        rec = self.records.get(rel)
        if rec is None:
            self.records[rel] = Record(
                dev=st.st_dev,
                ino=st.st_ino,
                size=0,
                mtime_ns=0,
                ctime_ns=0,
                digest=EMPTY_DIGEST,
            )
            return True
        changed = not rec.exists
        rec.exists = True
        if rec.identity != (st.st_dev, st.st_ino):
            changed |= self.compromise(rec, "file was replaced or recreated")
        return changed

    def reconcile(self, *, initial: bool = False) -> bool:
        current = self.walk_regular()
        visible_changed = False
        old_active = {p: r for p, r in self.records.items() if r.exists}
        unmatched_old = {p: r for p, r in old_active.items() if p not in current}
        by_identity: Dict[Tuple[int, int], list[Tuple[str, Record]]] = {}
        for path, rec in unmatched_old.items():
            by_identity.setdefault(rec.identity, []).append((path, rec))

        # Existing paths first.
        for rel, st in current.items():
            rec = self.records.get(rel)
            if rec and rec.exists:
                if initial:
                    continue
                if (
                    rec.identity != (st.st_dev, st.st_ino)
                    or rec.size != st.st_size
                    or rec.mtime_ns != st.st_mtime_ns
                    or rec.ctime_ns != st.st_ctime_ns
                ):
                    visible_changed |= self.inspect(os.path.join(self.root, rel))

        # New paths: preserve history across renames when the inode matches.
        for rel, st in current.items():
            rec = self.records.get(rel)
            if rec and rec.exists:
                continue
            candidates = by_identity.get((st.st_dev, st.st_ino), [])
            source = candidates.pop() if candidates else None
            if source:
                source_path, source_rec = source
                moved = dataclasses.replace(source_rec, exists=True)
                prior = self.records.get(rel)
                if prior is not None and prior is not source_rec:
                    moved.status = "COMPROMISED"
                    moved.reason = prior.reason or "path was replaced or reused"
                self.records[rel] = moved
                self.records[source_path] = dataclasses.replace(source_rec, exists=False)
                visible_changed = True
            elif rec is not None:
                rec.exists = True
                visible_changed = True
                visible_changed |= self.inspect(os.path.join(self.root, rel))
            else:
                # A file moved into the tree is accepted as its initial baseline.
                visible_changed |= self.inspect(os.path.join(self.root, rel), new_path=True)

        for rel, rec in old_active.items():
            if rel not in current and rec.exists:
                rec.exists = False
                visible_changed = True

        if initial:
            # Initial files are trusted baselines.
            for rel in current:
                if rel not in self.records:
                    self.inspect(os.path.join(self.root, rel), new_path=True)
            visible_changed = True
        return visible_changed

    @staticmethod
    def display_name(name: str) -> str:
        if any(ord(ch) < 32 or 0xD800 <= ord(ch) <= 0xDFFF for ch in name):
            return repr(name)
        return name

    def render_tree(self) -> str:
        lines = ["."]

        def visit(directory: str, prefix: str) -> None:
            try:
                with os.scandir(directory) as it:
                    entries = [e for e in it if not self.excluded(e.path)]
            except (FileNotFoundError, PermissionError, OSError):
                return

            visible = []
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False) or entry.is_file(follow_symlinks=False):
                        visible.append(entry)
                except OSError:
                    continue
            visible.sort(key=lambda e: e.name)

            for index, entry in enumerate(visible):
                last = index == len(visible) - 1
                branch = "└── " if last else "├── "
                child_prefix = prefix + ("    " if last else "│   ")
                name = self.display_name(entry.name)
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    continue
                if is_dir:
                    lines.append(f"{prefix}{branch}{name}/")
                    visit(entry.path, child_prefix)
                else:
                    rec = self.records.get(self.rel(entry.path))
                    status = rec.status if rec else "OK"
                    suffix = ""
                    if rec and rec.status == "COMPROMISED" and rec.reason:
                        suffix = f"  [{rec.reason}]"
                    lines.append(f"{prefix}{branch}{status:<11} {name}{suffix}")

        visit(self.root, "")
        return "\n".join(lines) + "\n"

    def write_report(self) -> None:
        text = self.render_tree()
        if self.report == "-":
            stamp = time.strftime("%Y-%m-%d %H:%M:%S %z")
            sys.stdout.write(f"# {stamp}\n{text}")
            sys.stdout.flush()
            return

        assert self.report_abs is not None
        directory = os.path.dirname(self.report_abs) or "."
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            prefix=f".{os.path.basename(self.report_abs)}.tmp.", dir=directory, text=True
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", errors="backslashreplace") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.report_abs)
        finally:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass

    def mark_all_compromised(self, reason: str) -> bool:
        changed = False
        for rec in self.records.values():
            if rec.exists:
                changed |= self.compromise(rec, reason)
        return changed

    def run(self) -> int:
        if not os.path.isdir(self.root):
            raise SystemExit(f"not a directory: {self.root}")

        self.reconcile(initial=True)
        self.rebuild_watches()
        self.write_report()
        print(f"appendwatch: watching {self.root}", file=sys.stderr)

        poller = select.poll()
        poller.register(self.ino.fd, select.POLLIN)

        while not self.stop:
            now = time.monotonic()
            timeout_ms = 1000
            if self.pending:
                timeout_ms = max(0, int((min(self.pending.values()) - now) * 1000))
            events = poller.poll(timeout_ms)
            visible_changed = False
            topology_changed = False

            if events:
                modified: set[str] = set()
                for path, mask, _cookie, _base in self.ino.read():
                    if mask & IN_Q_OVERFLOW:
                        visible_changed |= self.mark_all_compromised("inotify queue overflowed")
                        topology_changed = True
                        continue
                    if self.excluded(path):
                        continue
                    if mask & IN_IGNORED:
                        topology_changed = True
                        continue
                    if mask & IN_ISDIR:
                        if mask & (IN_CREATE | IN_DELETE | IN_MOVED_FROM | IN_MOVED_TO | IN_DELETE_SELF | IN_MOVE_SELF):
                            topology_changed = True
                        continue

                    if mask & IN_CREATE:
                        visible_changed |= self.seed_created_file(path)
                        modified.add(path)
                    if mask & (IN_DELETE | IN_MOVED_FROM | IN_MOVED_TO):
                        topology_changed = True
                    if mask & (IN_MODIFY | IN_ATTRIB | IN_CLOSE_WRITE):
                        modified.add(path)

                due = time.monotonic() + self.debounce
                for path in modified:
                    if self.debounce:
                        self.pending[path] = due
                    else:
                        visible_changed |= self.inspect(path)

            now = time.monotonic()
            ready = [p for p, due in self.pending.items() if due <= now]
            for path in ready:
                self.pending.pop(path, None)
                visible_changed |= self.inspect(path)

            if topology_changed:
                visible_changed |= self.reconcile()
                self.rebuild_watches()
                poller = select.poll()
                poller.register(self.ino.fd, select.POLLIN)

            if visible_changed:
                self.write_report()

        # Flush any final visible state.
        self.reconcile()
        self.write_report()
        self.ino.close()
        return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Flag files whose observed history is not append-only. Linux only."
    )
    parser.add_argument("directory", help="directory tree to monitor")
    parser.add_argument(
        "--report",
        default="-",
        help="atomically rewrite this tree report; '-' prints snapshots to stdout",
    )
    parser.add_argument(
        "--debounce-ms",
        type=int,
        default=0,
        help="coalesce rapid events for this many milliseconds (default: 0)",
    )
    args = parser.parse_args()
    if args.debounce_ms < 0:
        parser.error("--debounce-ms must be nonnegative")
    return args


def main() -> int:
    args = parse_args()
    watcher = AppendWatch(args.directory, args.report, args.debounce_ms)

    def stop(_signum: int, _frame: object) -> None:
        watcher.stop = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    return watcher.run()


if __name__ == "__main__":
    raise SystemExit(main())
