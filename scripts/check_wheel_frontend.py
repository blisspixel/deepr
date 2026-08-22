"""Verify dashboard assets and reject build-only distribution contents."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path, PurePosixPath
from tarfile import open as open_tar
from zipfile import ZipFile


def _unsafe_archive_name(name: str) -> bool:
    path = PurePosixPath(name)
    return path.is_absolute() or ".." in path.parts or "\\" in name or any(":" in part for part in path.parts)


def _forbidden_frontend_members(names: set[str]) -> list[str]:
    return sorted(
        name
        for name in names
        if "/node_modules/" in name
        or name.endswith("/frontend-dist.zip")
        or "__pycache__" in PurePosixPath(name).parts
        or name.endswith((".pyc", ".pyo"))
    )


def _duplicate_names(names: list[str]) -> list[str]:
    return sorted(name for name, count in Counter(names).items() if count > 1)


def check_wheel(path: Path) -> None:
    with ZipFile(path) as wheel:
        member_names = wheel.namelist()
        corrupt_member = wheel.testzip()
    if corrupt_member is not None:
        raise SystemExit(f"{path.name}: corrupt wheel member: {corrupt_member}")
    duplicates = _duplicate_names(member_names)
    if duplicates:
        raise SystemExit(f"{path.name}: duplicate archive member: {duplicates[0]}")
    names = set(member_names)
    unsafe = sorted(name for name in names if _unsafe_archive_name(name))
    if unsafe:
        raise SystemExit(f"{path.name}: unsafe archive member: {unsafe[0]}")
    forbidden = _forbidden_frontend_members(names)
    if forbidden:
        raise SystemExit(f"{path.name}: build-only frontend member was packaged: {forbidden[0]}")
    index = "deepr/web/frontend/dist/index.html"
    if index not in names:
        raise SystemExit(f"{path.name}: missing {index}")
    assets = [name for name in names if name.startswith("deepr/web/frontend/dist/assets/")]
    if not any(name.endswith(".js") for name in assets):
        raise SystemExit(f"{path.name}: no packaged frontend JavaScript assets")
    if not any(name.endswith(".css") for name in assets):
        raise SystemExit(f"{path.name}: no packaged frontend CSS assets")
    required_runtime_assets = {
        "deepr/config/system_message.json",
        "deepr/skills/recon/skill.yaml",
        "deepr/skills/recon/prompt.md",
        "deepr/templates/documentation_research.md",
    }
    missing = sorted(required_runtime_assets - names)
    if missing:
        raise SystemExit(f"{path.name}: missing runtime package assets: {', '.join(missing)}")


def check_sdist(path: Path) -> None:
    with open_tar(path, mode="r:gz") as archive:
        members = archive.getmembers()
    member_names = [member.name for member in members]
    duplicates = _duplicate_names(member_names)
    if duplicates:
        raise SystemExit(f"{path.name}: duplicate archive member: {duplicates[0]}")
    links = sorted(member.name for member in members if member.issym() or member.islnk())
    if links:
        raise SystemExit(f"{path.name}: linked archive member is not portable: {links[0]}")
    names = set(member_names)
    unsafe = sorted(name for name in names if _unsafe_archive_name(name))
    if unsafe:
        raise SystemExit(f"{path.name}: unsafe archive member: {unsafe[0]}")
    forbidden = sorted(
        name
        for name in names
        if "/node_modules/" in name
        or "/frontend/dist/" in name
        or "__pycache__" in PurePosixPath(name).parts
        or name.endswith((".pyc", ".pyo"))
    )
    if forbidden:
        raise SystemExit(f"{path.name}: generated frontend member was packaged: {forbidden[0]}")
    frontend_archives = [name for name in names if name.endswith("/frontend/frontend-dist.zip")]
    if len(frontend_archives) != 1:
        raise SystemExit(f"{path.name}: expected one frontend-dist.zip, found {len(frontend_archives)}")


def main(argv: list[str]) -> int:
    if not argv:
        raise SystemExit("usage: check_wheel_frontend.py PATH_TO_DISTRIBUTION [...]")
    for value in argv:
        distribution = Path(value).resolve()
        if not distribution.is_file():
            raise SystemExit(f"distribution not found: {distribution}")
        if distribution.suffix == ".whl":
            check_wheel(distribution)
        elif distribution.name.endswith(".tar.gz"):
            check_sdist(distribution)
        else:
            raise SystemExit(f"unsupported distribution: {distribution.name}")
        print(f"Distribution verified: {distribution.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
