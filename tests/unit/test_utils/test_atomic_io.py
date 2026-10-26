"""Tests for deepr.utils.atomic_io.

Verifies the crash-safe write helpers used across the storage layer.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from deepr.utils import atomic_io
from deepr.utils.atomic_io import (
    append_jsonl_durable,
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
)


class TestAtomicWriteJson:
    def test_writes_full_payload(self, tmp_path: Path):
        path = tmp_path / "out.json"
        atomic_write_json(path, {"a": 1, "b": [2, 3]})
        assert json.loads(path.read_text()) == {"a": 1, "b": [2, 3]}

    def test_overwrites_existing_file(self, tmp_path: Path):
        path = tmp_path / "out.json"
        path.write_text("stale")
        atomic_write_json(path, [1, 2, 3])
        assert json.loads(path.read_text()) == [1, 2, 3]

    def test_creates_parent_dir(self, tmp_path: Path):
        path = tmp_path / "deep" / "nested" / "out.json"
        atomic_write_json(path, {"ok": True})
        assert path.exists()
        assert json.loads(path.read_text()) == {"ok": True}

    def test_serialization_error_does_not_touch_target(self, tmp_path: Path):
        path = tmp_path / "out.json"
        path.write_text('{"ok": "previous"}')
        with pytest.raises(TypeError):
            atomic_write_json(path, {"bad": object()})  # non-JSON-able
        assert path.read_text() == '{"ok": "previous"}'

    def test_tempfile_cleanup_on_failure(self, tmp_path: Path):
        path = tmp_path / "out.json"

        # Force os.replace to fail so we can verify the tempfile is removed.
        with patch("deepr.utils.atomic_io.os.replace", side_effect=OSError("boom")):
            with pytest.raises(OSError):
                atomic_write_json(path, {"x": 1})

        # No stray tempfiles named .<target>.* should remain.
        leftovers = list(tmp_path.glob(f".{path.name}.*"))
        assert leftovers == []

    def test_with_default_serializer(self, tmp_path: Path):
        path = tmp_path / "out.json"
        atomic_write_json(path, {"set": {1, 2, 3}}, default=list)
        data = json.loads(path.read_text())
        assert sorted(data["set"]) == [1, 2, 3]


class TestAtomicWriteText:
    def test_writes_utf8(self, tmp_path: Path):
        path = tmp_path / "out.txt"
        atomic_write_text(path, "héllo wörld")
        assert path.read_text(encoding="utf-8") == "héllo wörld"

    def test_with_alternate_encoding(self, tmp_path: Path):
        path = tmp_path / "out.txt"
        atomic_write_text(path, "ABC", encoding="ascii")
        assert path.read_bytes() == b"ABC"

    def test_no_replace_creates_a_complete_file(self, tmp_path: Path):
        path = tmp_path / "new.txt"
        atomic_write_text(path, "complete", overwrite=False)
        assert path.read_text(encoding="utf-8") == "complete"

    def test_no_replace_preserves_an_existing_file(self, tmp_path: Path):
        path = tmp_path / "existing.txt"
        path.write_text("operator-owned", encoding="utf-8")
        with pytest.raises(FileExistsError):
            atomic_write_text(path, "replacement", overwrite=False)
        assert path.read_text(encoding="utf-8") == "operator-owned"
        assert list(tmp_path.glob(f".{path.name}.*")) == []


class TestAtomicWriteBytes:
    def test_writes_raw_bytes(self, tmp_path: Path):
        path = tmp_path / "out.bin"
        atomic_write_bytes(path, b"\x00\x01\x02")
        assert path.read_bytes() == b"\x00\x01\x02"

    def test_with_fsync(self, tmp_path: Path):
        path = tmp_path / "out.bin"
        atomic_write_bytes(path, b"payload", fsync=True)
        assert path.read_bytes() == b"payload"

    def test_trusted_preparation_runs_on_empty_open_tempfile_before_payload(self, tmp_path: Path):
        target = tmp_path / "private.bin"
        observed = []

        def prepare(descriptor, temporary):
            assert os.fstat(descriptor).st_size == 0
            assert temporary.read_bytes() == b""
            assert not target.exists()
            observed.append(descriptor)

        atomic_write_bytes(target, b"private payload", prepare_tempfile=prepare)
        assert target.read_bytes() == b"private payload"
        assert len(observed) == 1
        with pytest.raises(OSError):
            os.fstat(observed[0])

    @pytest.mark.parametrize("failure", [RuntimeError, KeyboardInterrupt])
    def test_preparation_failure_closes_empty_file_and_preserves_target(self, tmp_path: Path, failure):
        target = tmp_path / "private.bin"
        target.write_bytes(b"previous")
        observed = []

        def reject(descriptor, temporary):
            assert os.fstat(descriptor).st_size == 0
            observed.append(descriptor)
            raise failure("protection failed")

        with pytest.raises(failure, match="protection failed"):
            atomic_write_bytes(target, b"never written", prepare_tempfile=reject)
        assert target.read_bytes() == b"previous"
        assert list(tmp_path.glob(".private.bin.*")) == []
        with pytest.raises(OSError):
            os.fstat(observed[0])

    @pytest.mark.parametrize("kind", ["text", "json"])
    def test_text_and_json_forward_preparation_before_bytes(self, tmp_path: Path, kind):
        observed = []

        def prepare(descriptor, temporary):
            assert os.fstat(descriptor).st_size == 0
            observed.append(temporary)

        target = tmp_path / "wrapped"
        if kind == "text":
            atomic_write_text(target, "payload", prepare_tempfile=prepare)
            assert target.read_text() == "payload"
        else:
            atomic_write_json(target, {"payload": True}, prepare_tempfile=prepare)
            assert json.loads(target.read_text()) == {"payload": True}
        assert len(observed) == 1

    @pytest.mark.parametrize("kind", ["text", "json"])
    def test_unknown_preparation_preserves_legacy_delegate_keywords(self, tmp_path: Path, monkeypatch, kind):
        observed = []

        def legacy_writer(path, data, *, fsync=False, fsync_parent=False, overwrite=True):
            observed.append((path, data, fsync, fsync_parent, overwrite))

        target = tmp_path / "legacy"
        if kind == "text":
            monkeypatch.setattr(atomic_io, "atomic_write_bytes", legacy_writer)
            atomic_write_text(target, "payload", prepare_tempfile=None)
        else:
            monkeypatch.setattr(atomic_io, "atomic_write_text", legacy_writer)
            atomic_write_json(target, {"payload": True}, prepare_tempfile=None)
        assert len(observed) == 1
        assert observed[0][2:] == (False, False, True)

    def test_directory_sync_is_opt_in(self, tmp_path: Path, monkeypatch):
        sync = patch.object(atomic_io, "_fsync_parent_chain")
        with sync as observed:
            atomic_write_bytes(tmp_path / "default.bin", b"default", fsync=True)
            observed.assert_not_called()
            atomic_write_bytes(tmp_path / "durable.bin", b"durable", fsync=True, fsync_parent=True)
            observed.assert_called_once_with(tmp_path)

    def test_directory_sync_requires_file_sync_before_creating_parent(self, tmp_path: Path):
        path = tmp_path / "new" / "out.bin"
        with pytest.raises(ValueError, match="requires file fsync"):
            atomic_write_bytes(path, b"payload", fsync_parent=True)
        assert not path.parent.exists()

    def test_durable_write_syncs_new_directory_ancestry(self, tmp_path: Path, monkeypatch):
        path = tmp_path / "new-operation" / "study-chunks" / "out.bin"
        if os.name == "nt":
            # Windows has no portable directory fsync. Its documented guarantee
            # is file fsync plus atomic replacement, exercised by this write.
            atomic_write_bytes(path, b"payload", fsync=True, fsync_parent=True)
            assert path.read_bytes() == b"payload"
            return
        real_open, real_close, real_fsync = os.open, os.close, os.fsync
        opened = {}
        directories = []
        events = []

        def open_descriptor(name, flags, *args, **kwargs):
            descriptor = real_open(name, flags, *args, **kwargs)
            opened[descriptor] = Path(name)
            return descriptor

        def close_descriptor(descriptor):
            opened.pop(descriptor, None)
            return real_close(descriptor)

        def sync_descriptor(descriptor):
            directory = stat.S_ISDIR(os.fstat(descriptor).st_mode)
            if directory:
                assert path.read_bytes() == b"payload", "replacement precedes directory persistence"
                directories.append(opened[descriptor])
            events.append("directory" if directory else "file")
            return real_fsync(descriptor)

        monkeypatch.setattr(atomic_io.os, "open", open_descriptor)
        monkeypatch.setattr(atomic_io.os, "close", close_descriptor)
        monkeypatch.setattr(atomic_io.os, "fsync", sync_descriptor)
        atomic_write_bytes(path, b"payload", fsync=True, fsync_parent=True)
        assert events[0] == "file"
        assert directories == [path.parent, *path.parent.parents]

    def test_windows_directory_flush_has_honest_portable_fallback(self, tmp_path: Path, monkeypatch):
        # Replace this module's os reference without changing pathlib's host OS.
        monkeypatch.setattr(atomic_io, "os", SimpleNamespace(name="nt"))
        atomic_io._fsync_parent_chain(tmp_path)

    def test_directory_sync_failure_propagates(self, tmp_path: Path, monkeypatch):
        def fail(_):
            raise OSError("directory sync failed")

        monkeypatch.setattr(atomic_io, "_fsync_parent_chain", fail)
        with pytest.raises(OSError, match="directory sync failed"):
            atomic_write_bytes(tmp_path / "out.bin", b"payload", fsync=True, fsync_parent=True)


class TestAppendJsonlDurable:
    def test_private_lock_preparation_precedes_append_file_open(self, tmp_path: Path):
        target = tmp_path / "private.jsonl"
        observed = []

        def prepare(path):
            assert path == target.with_name("private.jsonl.append.lock")
            assert path.is_file()
            assert not target.exists()
            observed.append(path)

        append_jsonl_durable(target, {"private": True}, lock_mode=0o600, prepare_lock=prepare)
        assert len(observed) == 1
        assert json.loads(target.read_text()) == {"private": True}

    def test_lock_preparation_failure_writes_no_payload(self, tmp_path: Path):
        target = tmp_path / "private.jsonl"

        def reject(path):
            raise RuntimeError("lock protection failed")

        with pytest.raises(RuntimeError, match="lock protection failed"):
            append_jsonl_durable(target, {"private": True}, prepare_lock=reject)
        assert not target.exists()

    def test_appends_with_newline(self, tmp_path: Path):
        path = tmp_path / "log.jsonl"
        append_jsonl_durable(path, {"a": 1}, fsync=False)
        append_jsonl_durable(path, {"b": 2}, fsync=False)
        lines = path.read_text(encoding="utf-8").splitlines()
        assert [json.loads(line) for line in lines] == [{"a": 1}, {"b": 2}]

    def test_creates_parent_dir(self, tmp_path: Path):
        path = tmp_path / "nested" / "log.jsonl"
        append_jsonl_durable(path, {"ok": True}, fsync=False)
        assert json.loads(path.read_text().strip()) == {"ok": True}

    def test_creates_sibling_append_lock(self, tmp_path: Path):
        path = tmp_path / "log.jsonl"
        append_jsonl_durable(path, {"ok": True}, fsync=False)
        assert (tmp_path / "log.jsonl.append.lock").exists() or path.exists()
