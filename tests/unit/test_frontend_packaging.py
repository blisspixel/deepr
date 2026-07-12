from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts import build_frontend_archive
from scripts.check_wheel_frontend import check_wheel


def test_frontend_archive_is_deterministic(monkeypatch, tmp_path: Path):
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<main>Deepr</main>", encoding="utf-8")
    (assets / "app.js").write_text("console.log('deepr')", encoding="utf-8")
    archive = tmp_path / "frontend-dist.zip"
    monkeypatch.setattr(build_frontend_archive, "DIST_ROOT", dist)
    monkeypatch.setattr(build_frontend_archive, "ARCHIVE_PATH", archive)

    build_frontend_archive.build_archive()
    first = archive.read_bytes()
    build_frontend_archive.build_archive()

    assert archive.read_bytes() == first
    with ZipFile(archive) as built:
        assert built.namelist() == ["assets/app.js", "index.html"]


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
