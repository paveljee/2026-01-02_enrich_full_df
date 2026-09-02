"""Regression and unit tests for appendwatch.py.

Run:
    pytest -q test_appendwatch.py

Override the script location when needed:
    APPENDWATCH_SCRIPT=/path/to/appendwatch.py pytest -q test_appendwatch.py

The suite intentionally combines direct unit tests with real Linux/inotify
subprocess tests. Tests requiring a privilege drop to ``nobody`` are skipped
unless pytest itself is running as root and that account exists.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import importlib.util
import os
import pwd
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Iterator

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="appendwatch uses Linux inotify")

APPENDWATCH_MODULE = (
    "src.detours.detour_ai_augment.src.control_centre.appendwatch.appendwatch"
)
APPENDWATCH_MODULE_SPEC = importlib.util.find_spec(APPENDWATCH_MODULE)
if APPENDWATCH_MODULE_SPEC is None or APPENDWATCH_MODULE_SPEC.origin is None:
    raise RuntimeError(f"cannot locate {APPENDWATCH_MODULE}")
SCRIPT = Path(
    os.environ.get(
        "APPENDWATCH_SCRIPT",
        APPENDWATCH_MODULE_SPEC.origin,
    )
).resolve()

WATCHER_PYTHON = os.environ.get("APPENDWATCH_PYTHON", sys.executable)


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("appendwatch_under_test", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def aw() -> ModuleType:
    assert SCRIPT.is_file(), f"script not found: {SCRIPT}"
    return _load_module()


@pytest.fixture
def watcher_factory(aw: ModuleType, tmp_path: Path) -> Iterator[Callable[..., Any]]:
    opened: list[Any] = []

    def make(*, root: Path | None = None, report: Path | str | None = None, debounce_ms: int = 0):
        actual_root = root or (tmp_path / f"root-{len(opened)}")
        actual_root.mkdir(parents=True, exist_ok=True)
        actual_report = report if report is not None else tmp_path / f"report-{len(opened)}.txt"
        watcher = aw.AppendWatch(str(actual_root), str(actual_report), debounce_ms)
        opened.append(watcher)
        return watcher

    yield make

    for watcher in opened:
        try:
            watcher.ino.close()
        except Exception:
            pass


def wait_until(
    predicate: Callable[[], bool],
    *,
    timeout: float = 8.0,
    interval: float = 0.025,
) -> None:
    deadline = time.monotonic() + timeout
    last_error: BaseException | None = None
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except (FileNotFoundError, PermissionError, OSError) as exc:
            last_error = exc
        time.sleep(interval)
    if last_error is not None:
        raise AssertionError(f"condition not met; last error: {last_error}") from last_error
    raise AssertionError("condition not met before timeout")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


class RunningWatcher:
    def __init__(
        self,
        root: Path,
        report: Path,
        *,
        debounce_ms: int = 0,
        preexec_fn: Callable[[], None] | None = None,
    ) -> None:
        self.root = root
        self.report = report
        command = [
            WATCHER_PYTHON,
            str(SCRIPT),
            str(root),
            "--report",
            str(report),
            "--debounce-ms",
            str(debounce_ms),
        ]
        if os.environ.get("APPENDWATCH_COVERAGE") == "1":
            command = [
                WATCHER_PYTHON,
                "-m",
                "coverage",
                "run",
                "--branch",
                "--parallel-mode",
                str(SCRIPT),
                str(root),
                "--report",
                str(report),
                "--debounce-ms",
                str(debounce_ms),
            ]
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=preexec_fn,
        )
        wait_until(lambda: report.exists() or self.process.poll() is not None)
        if self.process.poll() is not None:
            stdout, stderr = self.process.communicate(timeout=1)
            raise AssertionError(
                f"watcher exited during startup with {self.process.returncode}\n"
                f"stdout:\n{stdout}\nstderr:\n{stderr}"
            )

    def text(self) -> str:
        return read_text(self.report)

    def wait_for(self, needle: str, *, timeout: float = 8.0) -> str:
        wait_until(lambda: needle in self.text(), timeout=timeout)
        return self.text()

    def wait_without(self, needle: str, *, timeout: float = 8.0) -> str:
        wait_until(lambda: needle not in self.text(), timeout=timeout)
        return self.text()

    def stop(self, sig: int = signal.SIGINT, *, timeout: float = 5.0) -> tuple[str, str]:
        if self.process.poll() is None:
            self.process.send_signal(sig)
        try:
            return self.process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            stdout, stderr = self.process.communicate(timeout=2)
            raise AssertionError(
                f"watcher did not stop after signal {sig}; stdout={stdout!r}, stderr={stderr!r}"
            )


@pytest.fixture
def running_watchers() -> Iterator[list[RunningWatcher]]:
    running: list[RunningWatcher] = []
    yield running
    for watcher in running:
        if watcher.process.poll() is None:
            watcher.stop()


def start_running(
    running: list[RunningWatcher],
    root: Path,
    report: Path,
    *,
    debounce_ms: int = 0,
    preexec_fn: Callable[[], None] | None = None,
) -> RunningWatcher:
    watcher = RunningWatcher(
        root, report, debounce_ms=debounce_ms, preexec_fn=preexec_fn
    )
    running.append(watcher)
    return watcher


def nobody_credentials() -> tuple[int, int] | None:
    if os.geteuid() != 0:
        return None
    try:
        account = pwd.getpwnam("nobody")
    except KeyError:
        return None
    return account.pw_uid, account.pw_gid


def drop_privileges(uid: int, gid: int) -> Callable[[], None]:
    def drop() -> None:
        os.setgroups([])
        os.setgid(gid)
        os.setuid(uid)

    return drop


# ---------------------------------------------------------------------------
# Core content and status logic
# ---------------------------------------------------------------------------


def test_default_debounce_is_zero(
    aw: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), str(root)])
    assert aw.parse_args().debounce_ms == 0


def test_negative_debounce_is_rejected(
    aw: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), str(root), "--debounce-ms", "-1"])
    with pytest.raises(SystemExit) as exc:
        aw.parse_args()
    assert exc.value.code == 2


def test_hash_fd_returns_full_and_old_prefix_digests(aw: ModuleType, tmp_path: Path) -> None:
    path = tmp_path / "data"
    payload = b"old-prefix" + b"-appended-data"
    path.write_bytes(payload)
    fd = os.open(path, os.O_RDONLY)
    try:
        full, prefix = aw.AppendWatch.hash_fd(fd, len(payload), len(b"old-prefix"))
    finally:
        os.close(fd)
    assert full == hashlib.sha256(payload).digest()
    assert prefix == hashlib.sha256(b"old-prefix").digest()


def test_hash_fd_rejects_short_reads(aw: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(aw.os, "pread", lambda _fd, _count, _offset: b"")
    with pytest.raises(OSError) as exc:
        aw.AppendWatch.hash_fd(123, 1, 0)
    assert exc.value.errno == errno.EIO


def test_append_stays_ok_and_updates_baseline(
    aw: ModuleType, watcher_factory: Callable[..., Any], tmp_path: Path
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    path = root / "app.log"
    path.write_bytes(b"abc")
    watcher = watcher_factory(root=root)

    assert watcher.inspect(str(path)) is True
    with path.open("ab", buffering=0) as stream:
        stream.write(b"def")
    watcher.inspect(str(path))

    rec = watcher.records["app.log"]
    assert rec.status == "OK"
    assert rec.size == 6
    assert rec.digest == hashlib.sha256(b"abcdef").digest()


def test_truncate_is_compromised(
    watcher_factory: Callable[..., Any], tmp_path: Path
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    path = root / "app.log"
    path.write_bytes(b"abcdef")
    watcher = watcher_factory(root=root)
    watcher.inspect(str(path))

    path.write_bytes(b"abc")
    watcher.inspect(str(path))

    rec = watcher.records["app.log"]
    assert rec.status == "COMPROMISED"
    assert rec.reason == "file shrank from 6 to 3 bytes"


def test_same_size_prefix_rewrite_is_compromised(
    watcher_factory: Callable[..., Any], tmp_path: Path
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    path = root / "app.log"
    path.write_bytes(b"abcdef")
    watcher = watcher_factory(root=root)
    watcher.inspect(str(path))

    with path.open("r+b", buffering=0) as stream:
        stream.seek(1)
        stream.write(b"Z")
        os.fsync(stream.fileno())
    watcher.inspect(str(path))

    rec = watcher.records["app.log"]
    assert rec.status == "COMPROMISED"
    assert rec.reason == "previous content is no longer a prefix"


def test_atomic_replacement_is_compromised(
    watcher_factory: Callable[..., Any], tmp_path: Path
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    path = root / "app.log"
    path.write_bytes(b"before")
    watcher = watcher_factory(root=root)
    watcher.inspect(str(path))

    replacement = root / ".replacement"
    replacement.write_bytes(b"before-after")
    os.replace(replacement, path)
    watcher.inspect(str(path))

    rec = watcher.records["app.log"]
    assert rec.status == "COMPROMISED"
    assert rec.reason == "file was replaced or recreated"


def test_first_compromise_reason_is_preserved(aw: ModuleType) -> None:
    rec = aw.Record(1, 2, 3, 4, 5, b"digest")
    watcher = object.__new__(aw.AppendWatch)
    assert watcher.compromise(rec, "first") is True
    assert watcher.compromise(rec, "second") is False
    assert rec.reason == "first"


def test_created_file_uses_empty_baseline_then_accepts_append(
    watcher_factory: Callable[..., Any], tmp_path: Path
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    path = root / "created.log"
    path.write_bytes(b"first write")
    watcher = watcher_factory(root=root)

    assert watcher.seed_created_file(str(path)) is True
    assert watcher.records["created.log"].size == 0
    watcher.inspect(str(path))
    assert watcher.records["created.log"].status == "OK"
    assert watcher.records["created.log"].size == len(b"first write")


def test_new_file_moved_into_tree_is_accepted_as_initial_baseline(
    watcher_factory: Callable[..., Any], tmp_path: Path
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.log"
    outside.write_bytes(b"existing external contents")
    watcher = watcher_factory(root=root)
    watcher.reconcile(initial=True)

    target = root / "incoming.log"
    os.replace(outside, target)
    watcher.reconcile()

    assert watcher.records["incoming.log"].status == "OK"


# ---------------------------------------------------------------------------
# Non-regular substitutions and report retention
# ---------------------------------------------------------------------------


def _replace_with_socket(path: Path) -> socket.socket:
    sock: socket.socket | None = None
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(str(path))
    except PermissionError:
        if sock is not None:
            sock.close()
        pytest.skip("Unix sockets are unavailable in this execution environment")
    assert sock is not None
    return sock


@pytest.mark.parametrize(
    ("kind", "expected_reason"),
    [
        ("directory", "path was replaced by a directory"),
        ("fifo", "path was replaced by a FIFO"),
        ("symlink", "path was replaced by a symbolic link"),
        ("socket", "path was replaced by a non-regular file"),
    ],
)
def test_inspect_flags_nonregular_substitution_without_blocking(
    kind: str,
    expected_reason: str,
    watcher_factory: Callable[..., Any],
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    path = root / "victim.log"
    path.write_bytes(b"baseline")
    watcher = watcher_factory(root=root)
    watcher.inspect(str(path))
    path.unlink()

    sock: socket.socket | None = None
    if kind == "directory":
        path.mkdir()
    elif kind == "fifo":
        os.mkfifo(path)
    elif kind == "symlink":
        os.symlink("target-does-not-need-to-exist", path)
    elif kind == "socket":
        sock = _replace_with_socket(path)
    else:  # pragma: no cover - parameter guard
        raise AssertionError(kind)

    started = time.monotonic()
    try:
        watcher.inspect(str(path))
    finally:
        if sock is not None:
            sock.close()
    assert time.monotonic() - started < 1.0

    rec = watcher.records["victim.log"]
    assert rec.status == "COMPROMISED"
    assert rec.exists is False
    assert rec.reason == expected_reason
    report = watcher.render_tree()
    assert "removed or replaced (no longer a regular file):" in report
    assert expected_reason in report


def test_new_fifo_is_ignored_and_does_not_block(
    watcher_factory: Callable[..., Any], tmp_path: Path
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    fifo = root / "new.pipe"
    os.mkfifo(fifo)
    watcher = watcher_factory(root=root)

    started = time.monotonic()
    assert watcher.inspect(str(fifo)) is False
    assert time.monotonic() - started < 1.0
    assert watcher.records == {}


def test_inspect_open_flags_include_nonblock(
    aw: ModuleType,
    watcher_factory: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    watcher = watcher_factory(root=root)
    captured: dict[str, int] = {}

    def fake_open(_path: str, flags: int) -> int:
        captured["flags"] = flags
        raise FileNotFoundError

    monkeypatch.setattr(aw.os, "open", fake_open)
    watcher.inspect(str(root / "missing"))
    assert captured["flags"] & os.O_NONBLOCK


def test_replacement_reason_covers_device_types(aw: ModuleType) -> None:
    expected = "path was replaced by a non-regular file"
    assert aw.AppendWatch.replacement_reason(stat.S_IFCHR) == expected
    assert aw.AppendWatch.replacement_reason(stat.S_IFBLK) == expected


def test_plain_delete_is_not_rendered_as_an_incident(
    watcher_factory: Callable[..., Any], tmp_path: Path
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    path = root / "plain.log"
    path.write_bytes(b"baseline")
    watcher = watcher_factory(root=root)
    watcher.inspect(str(path))

    path.unlink()
    watcher.reconcile()

    rec = watcher.records["plain.log"]
    assert rec.exists is False
    assert rec.status == "OK"
    report = watcher.render_tree()
    assert "plain.log" not in report
    assert "removed or replaced" not in report


def test_rename_preserves_history_and_append_only_status(
    watcher_factory: Callable[..., Any], tmp_path: Path
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    old = root / "old.log"
    new = root / "new.log"
    old.write_bytes(b"baseline")
    watcher = watcher_factory(root=root)
    watcher.inspect(str(old))
    old_identity = watcher.records["old.log"].identity

    old.rename(new)
    watcher.reconcile()

    assert watcher.records["old.log"].exists is False
    assert watcher.records["new.log"].identity == old_identity
    assert watcher.records["new.log"].status == "OK"

    with new.open("ab", buffering=0) as stream:
        stream.write(b"-append")
    watcher.inspect(str(new))
    assert watcher.records["new.log"].status == "OK"


def test_render_tree_has_only_binary_file_statuses(
    watcher_factory: Callable[..., Any], tmp_path: Path
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "unverified.log").write_bytes(b"data")
    watcher = watcher_factory(root=root)
    report = watcher.render_tree()
    assert "COMPROMISED unverified.log  [not yet verified]" in report
    assert "UNKNOWN" not in report


def test_report_and_atomic_temp_files_are_excluded(
    watcher_factory: Callable[..., Any], tmp_path: Path
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    data = root / "data.log"
    report = root / "tree.txt"
    data.write_bytes(b"data")
    watcher = watcher_factory(root=root, report=report)
    watcher.inspect(str(data))
    watcher.write_report()

    text = report.read_text(encoding="utf-8")
    assert "data.log" in text
    assert "tree.txt" not in text
    assert not list(root.glob(".tree.txt.tmp.*"))


# ---------------------------------------------------------------------------
# inotify bookkeeping, overflow, watch limits, and pruning
# ---------------------------------------------------------------------------


class FakeLibc:
    def __init__(
        self,
        *,
        add_errno: int | None = None,
        add_wd: int = 10,
        remove_errno: int | None = None,
        remove_check: Callable[[], None] | None = None,
    ) -> None:
        self.add_errno = add_errno
        self.add_wd = add_wd
        self.remove_errno = remove_errno
        self.remove_check = remove_check
        self.add_calls = 0
        self.remove_calls = 0

    def inotify_add_watch(self, _fd: int, _raw: bytes, _mask: int) -> int:
        self.add_calls += 1
        if self.add_errno is not None:
            ctypes.set_errno(self.add_errno)
            return -1
        return self.add_wd

    def inotify_rm_watch(self, _fd: int, _wd: int) -> int:
        self.remove_calls += 1
        if self.remove_check is not None:
            self.remove_check()
        if self.remove_errno is not None:
            ctypes.set_errno(self.remove_errno)
            return -1
        return 0


def make_fake_inotify(aw: ModuleType, libc: FakeLibc) -> Any:
    ino = object.__new__(aw.Inotify)
    ino.libc = libc
    ino.fd = 123
    ino.wd_to_dir = {}
    ino.dir_to_wd = {}
    ino.unwatched_dirs = {}
    ino.warned_enospc = False
    ino.degraded_reason = ""
    return ino


def test_add_eacces_marks_only_the_directory(aw: ModuleType) -> None:
    ino = make_fake_inotify(aw, FakeLibc(add_errno=errno.EACCES))
    assert ino.add("/private") is True
    assert ino.unwatched_dirs == {
        "/private": "directory could not be watched: permission denied"
    }
    assert ino.degraded_reason == ""


def test_add_enospc_warns_once_and_sets_global_degradation(
    aw: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    libc = FakeLibc(add_errno=errno.ENOSPC)
    ino = make_fake_inotify(aw, libc)
    assert ino.add("/one") is False
    assert ino.add("/two") is False
    stderr = capsys.readouterr().err
    assert stderr.count("inotify watch limit reached") == 1
    assert ino.degraded_reason == "inotify watch limit reached; monitoring was incomplete"


def test_remove_drops_maps_before_syscall_and_tolerates_einval(aw: ModuleType) -> None:
    holder: dict[str, Any] = {}

    def check_removed_first() -> None:
        ino = holder["ino"]
        assert "/gone" not in ino.dir_to_wd
        assert 9 not in ino.wd_to_dir

    libc = FakeLibc(remove_errno=errno.EINVAL, remove_check=check_removed_first)
    ino = make_fake_inotify(aw, libc)
    holder["ino"] = ino
    ino.dir_to_wd["/gone"] = 9
    ino.wd_to_dir[9] = "/gone"
    ino.unwatched_dirs["/gone"] = "reason"

    ino.remove("/gone")
    assert libc.remove_calls == 1
    assert "/gone" not in ino.unwatched_dirs


def test_remove_tolerates_ebadf_but_raises_other_errors(aw: ModuleType) -> None:
    for tolerated in (errno.EBADF,):
        ino = make_fake_inotify(aw, FakeLibc(remove_errno=tolerated))
        ino.dir_to_wd["/gone"] = 9
        ino.wd_to_dir[9] = "/gone"
        ino.remove("/gone")

    ino = make_fake_inotify(aw, FakeLibc(remove_errno=errno.EIO))
    ino.dir_to_wd["/gone"] = 9
    ino.wd_to_dir[9] = "/gone"
    with pytest.raises(OSError) as exc:
        ino.remove("/gone")
    assert exc.value.errno == errno.EIO


def test_read_suppresses_unknown_ignored_but_preserves_queue_overflow(
    aw: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    ino = make_fake_inotify(aw, FakeLibc())
    packets = [
        aw.EVENT.pack(1234, aw.IN_IGNORED, 0, 0)
        + aw.EVENT.pack(-1, aw.IN_Q_OVERFLOW, 0, 0)
    ]

    def fake_read(_fd: int, _size: int) -> bytes:
        if packets:
            return packets.pop(0)
        raise BlockingIOError

    monkeypatch.setattr(aw.os, "read", fake_read)
    events = list(ino.read())
    assert events == [("", aw.IN_Q_OVERFLOW, 0, "")]


def test_queue_overflow_fail_closes_all_active_files(
    watcher_factory: Callable[..., Any], tmp_path: Path
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    watcher = watcher_factory(root=root)
    for index in range(20):
        path = root / f"{index}.log"
        path.write_text(str(index), encoding="utf-8")
        watcher.inspect(str(path))

    assert watcher.mark_all_compromised("inotify queue overflowed") is True
    assert all(rec.status == "COMPROMISED" for rec in watcher.records.values())
    assert {rec.reason for rec in watcher.records.values()} == {"inotify queue overflowed"}


def test_rebuild_prunes_moved_out_watch_and_ignored_event_is_suppressed(
    aw: ModuleType, watcher_factory: Callable[..., Any], tmp_path: Path
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    sub = root / "sub"
    sub.mkdir()
    outside = tmp_path / "outside"
    watcher = watcher_factory(root=root)
    assert watcher.rebuild_watches() is True
    assert str(sub) in watcher.ino.dir_to_wd

    sub.rename(outside)
    assert watcher.rebuild_watches() is True
    assert str(sub) not in watcher.ino.dir_to_wd
    assert str(outside) not in watcher.ino.dir_to_wd

    # Drain move and explicit-removal notifications. The stale IN_IGNORED wd
    # has already been removed from the maps and must not be yielded.
    time.sleep(0.05)
    events = list(watcher.ino.read())
    assert not any(mask & aw.IN_IGNORED for _path, mask, _cookie, _base in events)

    (outside / "outside.log").write_text("outside", encoding="utf-8")
    time.sleep(0.05)
    later = list(watcher.ino.read())
    assert not any(path.startswith(str(outside)) for path, _mask, _cookie, _base in later)


# ---------------------------------------------------------------------------
# Permission-loss scoping and shutdown fail-closed behavior
# ---------------------------------------------------------------------------


def test_existing_watch_dynamic_scandir_failure_sets_and_clears_marker(
    aw: ModuleType,
    watcher_factory: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    vault = root / "vault"
    vault.mkdir()
    watcher = watcher_factory(root=root)
    watcher.rebuild_watches()
    assert str(vault) in watcher.ino.dir_to_wd

    real_scandir = os.scandir

    def denied(path: str | os.PathLike[str]):
        if os.path.realpath(path) == os.path.realpath(vault):
            raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), str(path))
        return real_scandir(path)

    monkeypatch.setattr(aw.os, "scandir", denied)
    watcher.rebuild_watches()
    assert watcher.ino.unwatched_dirs[str(vault)] == (
        "directory could not be watched: permission denied"
    )

    monkeypatch.setattr(aw.os, "scandir", real_scandir)
    watcher.rebuild_watches()
    assert str(vault) not in watcher.ino.unwatched_dirs


def test_unwatched_marker_compromises_only_its_subtree(
    watcher_factory: Callable[..., Any], tmp_path: Path
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    vault = root / "vault"
    other = root / "other"
    vault.mkdir()
    other.mkdir()
    inside = vault / "inside.log"
    elsewhere = other / "elsewhere.log"
    inside.write_bytes(b"inside")
    elsewhere.write_bytes(b"elsewhere")
    watcher = watcher_factory(root=root)
    watcher.inspect(str(inside))
    watcher.inspect(str(elsewhere))

    watcher.ino.unwatched_dirs[str(vault)] = (
        "directory could not be watched: permission denied"
    )
    watcher.mark_unwatched_compromised()

    assert watcher.records["vault/inside.log"].status == "COMPROMISED"
    assert watcher.records["other/elsewhere.log"].status == "OK"
    report = watcher.render_tree()
    assert "COMPROMISED vault/" in report
    assert "OK          elsewhere.log" in report


def test_enospc_fail_closed_is_global(
    watcher_factory: Callable[..., Any], tmp_path: Path
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    watcher = watcher_factory(root=root)
    for index in range(20):
        path = root / f"{index}.log"
        path.write_bytes(b"data")
        watcher.inspect(str(path))

    watcher.ino.degraded_reason = "inotify watch limit reached; monitoring was incomplete"
    watcher.mark_all_compromised(watcher.ino.degraded_reason)
    assert sum(rec.status == "COMPROMISED" for rec in watcher.records.values()) == 20


def test_shutdown_marks_files_discovered_after_unwatched_root_interval(
    aw: ModuleType,
    watcher_factory: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    watcher = watcher_factory(root=root)
    watcher.stop = True
    reason = "directory could not be watched: permission denied"
    watcher.ino.unwatched_dirs[str(root)] = reason
    calls = {"reconcile": 0}
    snapshots: list[dict[str, str]] = []

    def fake_reconcile(*, initial: bool = False) -> bool:
        calls["reconcile"] += 1
        if not initial:
            for name in ("a.log", "b.log"):
                watcher.records[name] = aw.Record(
                    dev=1,
                    ino=len(watcher.records) + 1,
                    size=1,
                    mtime_ns=1,
                    ctime_ns=1,
                    digest=hashlib.sha256(b"x").digest(),
                )
        return True

    monkeypatch.setattr(watcher, "reconcile", fake_reconcile)
    monkeypatch.setattr(watcher, "rebuild_watches", lambda: True)
    monkeypatch.setattr(
        watcher,
        "write_report",
        lambda: snapshots.append({name: rec.status for name, rec in watcher.records.items()}),
    )

    assert watcher.run() == 0
    assert calls["reconcile"] == 2
    assert snapshots[-1] == {"a.log": "COMPROMISED", "b.log": "COMPROMISED"}
    assert all(
        rec.reason == "file was inside an unwatched directory; monitoring was incomplete"
        for rec in watcher.records.values()
    )


# ---------------------------------------------------------------------------
# Real subprocess/inotify regressions
# ---------------------------------------------------------------------------


def test_cli_detects_delayed_directory_fifo_symlink_and_socket_substitutions(
    running_watchers: list[RunningWatcher], tmp_path: Path
) -> None:
    cases = {
        "directory.log": "path was replaced by a directory",
        "fifo.log": "path was replaced by a FIFO",
        "symlink.log": "path was replaced by a symbolic link",
        "socket.log": "path was replaced by a non-regular file",
    }

    for index, (name, reason) in enumerate(cases.items()):
        root = tmp_path / f"root-{index}"
        root.mkdir()
        report = tmp_path / f"report-{index}.txt"
        path = root / name
        path.write_bytes(b"baseline")
        runner = start_running(running_watchers, root, report)
        runner.wait_for(name)

        path.unlink()
        runner.wait_without(name)

        sock: socket.socket | None = None
        if name.startswith("directory"):
            path.mkdir()
        elif name.startswith("fifo"):
            os.mkfifo(path)
        elif name.startswith("symlink"):
            os.symlink("elsewhere", path)
        else:
            sock = _replace_with_socket(path)
        try:
            runner.wait_for(reason)
        finally:
            if sock is not None:
                sock.close()
        assert runner.process.poll() is None
        runner.stop()


def test_cli_fifo_cannot_blind_watcher_and_sigint_stops_cleanly(
    running_watchers: list[RunningWatcher], tmp_path: Path
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    report = tmp_path / "report.txt"
    victim = root / "victim.log"
    victim.write_bytes(b"baseline")
    runner = start_running(running_watchers, root, report)
    runner.wait_for("victim.log")

    victim.unlink()
    runner.wait_without("victim.log")
    os.mkfifo(victim)
    runner.wait_for("path was replaced by a FIFO")

    stdout, stderr = runner.stop(signal.SIGINT)
    assert runner.process.returncode == 0, (stdout, stderr)


def test_cli_append_then_shrink_proves_append_baseline_was_processed(
    running_watchers: list[RunningWatcher], tmp_path: Path
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    report = tmp_path / "report.txt"
    path = root / "app.log"
    path.write_bytes(b"abc")
    runner = start_running(running_watchers, root, report)
    runner.wait_for("OK          app.log")

    with path.open("ab", buffering=0) as stream:
        stream.write(b"def")
        os.fsync(stream.fileno())
    # An OK append does not rewrite the report, so allow the close-write event
    # to be consumed before shrinking back to the original length.
    time.sleep(0.25)
    path.write_bytes(b"abc")
    text = runner.wait_for("file shrank from 6 to 3 bytes")
    assert "COMPROMISED app.log" in text


def test_cli_atomic_replacement_and_plain_delete_reporting(
    running_watchers: list[RunningWatcher], tmp_path: Path
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    report = tmp_path / "report.txt"
    replaced = root / "replaced.log"
    deleted = root / "deleted.log"
    replaced.write_bytes(b"old")
    deleted.write_bytes(b"delete me")
    runner = start_running(running_watchers, root, report)
    runner.wait_for("deleted.log")

    temp = root / ".new"
    temp.write_bytes(b"new")
    os.replace(temp, replaced)
    runner.wait_for("file was replaced or recreated")

    deleted.unlink()
    wait_until(lambda: "deleted.log" not in runner.text())
    text = runner.text()
    assert "deleted.log" not in text
    assert "replaced.log" in text


def test_cli_rename_history_remains_ok(
    running_watchers: list[RunningWatcher], tmp_path: Path
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    report = tmp_path / "report.txt"
    old = root / "old.log"
    new = root / "new.log"
    old.write_bytes(b"baseline")
    runner = start_running(running_watchers, root, report)
    runner.wait_for("old.log")

    old.rename(new)
    text = runner.wait_for("new.log")
    assert "OK          new.log" in text
    assert "COMPROMISED new.log" not in text
    assert "old.log" not in text


def _permission_test_tree() -> tuple[Path, Path, Path, int, int]:
    credentials = nobody_credentials()
    if credentials is None:
        pytest.skip("requires root and a nobody account for real EACCES integration")
    uid, gid = credentials
    base = Path(tempfile.mkdtemp(prefix="appendwatch-permission-", dir="/tmp"))
    os.chmod(base, 0o755)
    root = base / "root"
    report_dir = base / "reports"
    root.mkdir()
    report_dir.mkdir()
    os.chown(root, uid, gid)
    os.chown(report_dir, uid, gid)
    os.chmod(root, 0o755)
    os.chmod(report_dir, 0o755)
    return base, root, report_dir / "tree.txt", uid, gid


@pytest.mark.needs_sudo
def test_cli_static_eacces_is_scoped_and_recovered_files_fail_closed(
    running_watchers: list[RunningWatcher],
) -> None:
    base, root, report, uid, gid = _permission_test_tree()
    try:
        app = root / "app.log"
        app.write_bytes(b"app")
        os.chown(app, uid, gid)
        private = root / "private"
        private.mkdir()
        inside = private / "inside.log"
        inside.write_bytes(b"inside")
        os.chown(private, 0, 0)
        os.chmod(private, 0o700)

        runner = start_running(
            running_watchers,
            root,
            report,
            preexec_fn=drop_privileges(uid, gid),
        )
        text = runner.wait_for("directory could not be watched: permission denied")
        assert "OK          app.log" in text
        assert "COMPROMISED private/" in text

        appeared = private / "appeared.log"
        appeared.write_bytes(b"appeared while blind")
        os.chown(private, uid, gid)
        os.chmod(private, 0o755)
        text = runner.wait_for(
            "file was inside an unwatched directory; monitoring was incomplete"
        )
        assert "COMPROMISED appeared.log" in text
    finally:
        shutil.rmtree(base, ignore_errors=True)


@pytest.mark.needs_sudo
def test_cli_dynamic_eacces_existing_watch_is_detected_and_scoped(
    running_watchers: list[RunningWatcher],
) -> None:
    base, root, report, uid, gid = _permission_test_tree()
    try:
        vault = root / "vault"
        other = root / "other"
        vault.mkdir()
        other.mkdir()
        os.chown(vault, uid, gid)
        os.chown(other, uid, gid)
        os.chmod(vault, 0o755)
        os.chmod(other, 0o755)
        inside = vault / "inside.log"
        elsewhere = other / "elsewhere.log"
        inside.write_bytes(b"inside")
        elsewhere.write_bytes(b"elsewhere")
        os.chown(inside, uid, gid)
        os.chown(elsewhere, uid, gid)

        runner = start_running(
            running_watchers,
            root,
            report,
            preexec_fn=drop_privileges(uid, gid),
        )
        runner.wait_for("OK          elsewhere.log")

        os.chown(vault, 0, 0)
        os.chmod(vault, 0o700)
        runner.wait_for("COMPROMISED vault/  [directory could not be watched: permission denied]")

        appeared = vault / "appeared.log"
        appeared.write_bytes(b"appeared while blind")
        os.chown(vault, uid, gid)
        os.chmod(vault, 0o755)
        text = runner.wait_for(
            "file was inside an unwatched directory; monitoring was incomplete"
        )
        assert "COMPROMISED appeared.log" in text
        assert "OK          elsewhere.log" in text
    finally:
        shutil.rmtree(base, ignore_errors=True)


@pytest.mark.needs_sudo
def test_cli_shutdown_reconcile_marks_files_from_unwatched_root_interval(
    running_watchers: list[RunningWatcher],
) -> None:
    base, root, report, uid, gid = _permission_test_tree()
    try:
        a = root / "a.log"
        b = root / "b.log"
        a.write_bytes(b"a")
        b.write_bytes(b"b")
        os.chown(root, 0, 0)
        os.chmod(root, 0o700)

        runner = start_running(
            running_watchers,
            root,
            report,
            preexec_fn=drop_privileges(uid, gid),
        )
        runner.wait_for(".  [COMPROMISED: directory could not be watched: permission denied]")

        os.chown(root, uid, gid)
        os.chmod(root, 0o755)
        runner.stop(signal.SIGINT)
        text = read_text(report)
        assert "COMPROMISED a.log" in text
        assert "COMPROMISED b.log" in text
        assert text.count("file was inside an unwatched directory; monitoring was incomplete") >= 2
    finally:
        shutil.rmtree(base, ignore_errors=True)
