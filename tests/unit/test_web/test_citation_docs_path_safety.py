"""Regression tests for citation-validation document path safety."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("flask")

os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key")

from deepr.web.app import _read_markdown_docs_within_root


def test_read_markdown_docs_within_root_skips_symlink_escape(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "safe.md").write_text("safe source", encoding="utf-8")
    outside = tmp_path / "outside.md"
    outside.write_text("outside secret", encoding="utf-8")

    try:
        (docs_dir / "escaped.md").symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable in this environment")

    docs = _read_markdown_docs_within_root(docs_dir)

    assert docs == {"safe.md": "safe source"}
