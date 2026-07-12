from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_STORED, ZipFile

import pytest

from scripts import build_frontend_archive
from scripts.check_wheel_frontend import check_wheel


def test_frontend_archive_is_deterministic(monkeypatch, tmp_path: Path):
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    index = dist / "index.html"
    javascript = assets / "app.js"
    index.write_bytes(b"<main>\r\nDeepr\r\r\n</main>\r\n")
    javascript.write_bytes(b"const name = 'deepr';\r\nconsole.log(name);\r\n")
    archive = tmp_path / "frontend-dist.zip"
    monkeypatch.setattr(build_frontend_archive, "DIST_ROOT", dist)
    monkeypatch.setattr(build_frontend_archive, "ARCHIVE_PATH", archive)

    build_frontend_archive.build_archive()
    first = archive.read_bytes()
    index.write_bytes(index.read_bytes().replace(b"\r\n", b"\n"))
    javascript.write_bytes(javascript.read_bytes().replace(b"\r\n", b"\n"))
    build_frontend_archive.build_archive()

    assert archive.read_bytes() == first
    with ZipFile(archive) as built:
        assert built.namelist() == ["assets/app.js", "index.html"]
        assert {entry.create_system for entry in built.infolist()} == {3}
        assert {entry.external_attr >> 16 for entry in built.infolist()} == {0o644}
        assert {entry.compress_type for entry in built.infolist()} == {ZIP_STORED}
        assert built.read("index.html") == b"<main>\nDeepr\n</main>\n"


def test_wheel_frontend_check_requires_index_javascript_and_css(tmp_path: Path):
    wheel = tmp_path / "deepr.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr("deepr/web/frontend/dist/index.html", "<main>Deepr</main>")
        archive.writestr("deepr/web/frontend/dist/assets/app.js", "console.log('deepr')")
        archive.writestr("deepr/web/frontend/dist/assets/app.css", "body{}")
        archive.writestr("deepr/config/system_message.json", "{}")
        archive.writestr("deepr/skills/recon/skill.yaml", "name: recon")
        archive.writestr("deepr/skills/recon/prompt.md", "# Recon")
        archive.writestr("deepr/templates/documentation_research.md", "# Research")

    check_wheel(wheel)


def test_wheel_frontend_check_rejects_missing_assets(tmp_path: Path):
    wheel = tmp_path / "deepr.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr("deepr/web/frontend/dist/index.html", "<main>Deepr</main>")

    with pytest.raises(SystemExit, match="no packaged frontend JavaScript assets"):
        check_wheel(wheel)
