"""Tests for deepr.utils.atomic_io.

Verifies the crash-safe write helpers used across the storage layer.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

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


class TestAtomicWriteBytes:
    def test_writes_raw_bytes(self, tmp_path: Path):
        path = tmp_path / "out.bin"
        atomic_write_bytes(path, b"\x00\x01\x02")
        assert path.read_bytes() == b"\x00\x01\x02"

    def test_with_fsync(self, tmp_path: Path):
        # Should not raise even when fsync isn't supported on the
        # underlying filesystem; the helper swallows fsync errors.
        path = tmp_path / "out.bin"
        atomic_write_bytes(path, b"payload", fsync=True)
        assert path.read_bytes() == b"payload"


class TestAppendJsonlDurable:
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
