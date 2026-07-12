"""Setuptools hooks that keep the packaged dashboard complete."""

from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist

_ROOT = Path(__file__).resolve().parent
_FRONTEND_ARCHIVE = _ROOT / "src" / "deepr" / "web" / "frontend" / "frontend-dist.zip"


def _require_frontend_archive() -> None:
    if _FRONTEND_ARCHIVE.is_file():
        return
    raise RuntimeError(
        "Packaged web frontend archive is missing. Run the frontend build and "
        "`python scripts/build_frontend_archive.py` before building the Python package."
    )


def _extract_frontend(build_lib: str) -> None:
    frontend_root = Path(build_lib) / "deepr" / "web" / "frontend"
    target = frontend_root / "dist"
    with ZipFile(_FRONTEND_ARCHIVE) as archive:
        for member in archive.infolist():
            relative = PurePosixPath(member.filename)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or "\\" in member.filename
                or any(":" in part for part in relative.parts)
            ):
                raise RuntimeError(f"unsafe frontend archive member: {member.filename}")
            destination = target.joinpath(*relative.parts)
            if not destination.resolve().is_relative_to(target.resolve()):
                raise RuntimeError(f"unsafe frontend archive member: {member.filename}")
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(member))
    # The source archive is needed by sdists, but a wheel needs only the
    # extracted runtime assets. Avoid shipping both copies.
    (frontend_root / _FRONTEND_ARCHIVE.name).unlink(missing_ok=True)


class _BuildPyWithFrontend(build_py):
    def run(self) -> None:
        _require_frontend_archive()
        super().run()
        _extract_frontend(self.build_lib)


class _SdistWithFrontend(sdist):
    def run(self) -> None:
        _require_frontend_archive()
        super().run()


setup(cmdclass={"build_py": _BuildPyWithFrontend, "sdist": _SdistWithFrontend})
