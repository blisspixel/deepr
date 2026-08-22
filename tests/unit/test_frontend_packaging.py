from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tarfile import TarInfo
from tarfile import open as open_tar
from zipfile import ZIP_STORED, ZipFile

import pytest

from scripts import build_frontend_archive
from scripts.check_wheel_frontend import check_sdist, check_wheel


def _write_valid_wheel(path: Path, *, extra_members: dict[str, str] | None = None) -> None:
    members = {
        "deepr/web/frontend/dist/index.html": "<main>Deepr</main>",
        "deepr/web/frontend/dist/assets/app.js": "console.log('deepr')",
        "deepr/web/frontend/dist/assets/app.css": "body{}",
        "deepr/config/system_message.json": "{}",
        "deepr/skills/recon/skill.yaml": "name: recon",
        "deepr/skills/recon/prompt.md": "# Recon",
        "deepr/templates/documentation_research.md": "# Research",
    }
    members.update(extra_members or {})
    with ZipFile(path, "w") as archive:
        for name, value in members.items():
            archive.writestr(name, value)


def _write_sdist(path: Path, names: tuple[str, ...]) -> None:
    with open_tar(path, "w:gz") as archive:
        for name in names:
            payload = b"content"
            info = TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, BytesIO(payload))


def test_frontend_archive_is_deterministic(monkeypatch, tmp_path: Path):
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    index = dist / "index.html"
    javascript = assets / "app.js"
    uppercase_asset = assets / "Z.js"
    lowercase_asset = assets / "a.js"
    index.write_bytes(b"<main>\r\nDeepr\r\r\n</main>\r\n")
    javascript.write_bytes(b"const name = 'deepr';\r\nconsole.log(name);\r\n")
    uppercase_asset.write_bytes(b"export const upper = true;\r\n")
    lowercase_asset.write_bytes(b"export const lower = true;\r\n")
    archive = tmp_path / "frontend-dist.zip"
    monkeypatch.setattr(build_frontend_archive, "DIST_ROOT", dist)
    monkeypatch.setattr(build_frontend_archive, "ARCHIVE_PATH", archive)

    build_frontend_archive.build_archive()
    first = archive.read_bytes()
    index.write_bytes(index.read_bytes().replace(b"\r\n", b"\n"))
    javascript.write_bytes(javascript.read_bytes().replace(b"\r\n", b"\n"))
    uppercase_asset.write_bytes(uppercase_asset.read_bytes().replace(b"\r\n", b"\n"))
    lowercase_asset.write_bytes(lowercase_asset.read_bytes().replace(b"\r\n", b"\n"))
    build_frontend_archive.build_archive()

    assert archive.read_bytes() == first
    with ZipFile(archive) as built:
        assert built.namelist() == ["assets/Z.js", "assets/a.js", "assets/app.js", "index.html"]
        assert {entry.create_system for entry in built.infolist()} == {3}
        assert {entry.external_attr >> 16 for entry in built.infolist()} == {0o644}
        assert {entry.compress_type for entry in built.infolist()} == {ZIP_STORED}
        assert built.read("index.html") == b"<main>\nDeepr\n</main>\n"


def test_wheel_frontend_check_requires_index_javascript_and_css(tmp_path: Path):
    wheel = tmp_path / "deepr.whl"
    _write_valid_wheel(wheel)

    check_wheel(wheel)


def test_wheel_frontend_check_rejects_missing_assets(tmp_path: Path):
    wheel = tmp_path / "deepr.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr("deepr/web/frontend/dist/index.html", "<main>Deepr</main>")

    with pytest.raises(SystemExit, match="no packaged frontend JavaScript assets"):
        check_wheel(wheel)


@pytest.mark.parametrize(
    "member",
    [
        "deepr/web/frontend/node_modules/flatted/python/flatted.py",
        "deepr/web/frontend/frontend-dist.zip",
        "deepr/web/frontend/__pycache__/asset.cpython-312.pyc",
    ],
)
def test_wheel_frontend_check_rejects_build_only_members(tmp_path: Path, member: str):
    wheel = tmp_path / "deepr.whl"
    _write_valid_wheel(wheel, extra_members={member: "leak"})

    with pytest.raises(SystemExit, match="build-only frontend member was packaged"):
        check_wheel(wheel)


def test_wheel_frontend_check_rejects_duplicate_members(tmp_path: Path):
    wheel = tmp_path / "deepr.whl"
    _write_valid_wheel(wheel)
    with pytest.warns(UserWarning, match="Duplicate name"):
        with ZipFile(wheel, "a") as archive:
            archive.writestr("deepr/web/frontend/dist/index.html", "duplicate")

    with pytest.raises(SystemExit, match="duplicate archive member"):
        check_wheel(wheel)


def test_sdist_check_accepts_only_the_frontend_archive(tmp_path: Path):
    sdist = tmp_path / "deepr.tar.gz"
    _write_sdist(
        sdist,
        (
            "deepr_research-2.50.6/pyproject.toml",
            "deepr_research-2.50.6/src/deepr/web/frontend/frontend-dist.zip",
        ),
    )

    check_sdist(sdist)


def test_sdist_check_rejects_frontend_dependency_files(tmp_path: Path):
    sdist = tmp_path / "deepr.tar.gz"
    _write_sdist(
        sdist,
        (
            "deepr_research-2.50.6/src/deepr/web/frontend/frontend-dist.zip",
            "deepr_research-2.50.6/src/deepr/web/frontend/node_modules/pkg/tool.py",
        ),
    )

    with pytest.raises(SystemExit, match="generated frontend member was packaged"):
        check_sdist(sdist)


def test_sdist_check_rejects_duplicate_members(tmp_path: Path):
    sdist = tmp_path / "deepr.tar.gz"
    archive_name = "deepr_research-2.50.6/src/deepr/web/frontend/frontend-dist.zip"
    _write_sdist(sdist, (archive_name, archive_name))

    with pytest.raises(SystemExit, match="duplicate archive member"):
        check_sdist(sdist)
