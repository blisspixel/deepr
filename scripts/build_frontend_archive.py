"""Create the deterministic frontend archive embedded in Python builds."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = ROOT / "src" / "deepr" / "web" / "frontend"
DIST_ROOT = FRONTEND_ROOT / "dist"
ARCHIVE_PATH = FRONTEND_ROOT / "frontend-dist.zip"
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def build_archive() -> Path:
    index = DIST_ROOT / "index.html"
    if not index.is_file():
        raise SystemExit(f"frontend build missing: {index}")
    files = sorted(path for path in DIST_ROOT.rglob("*") if path.is_file())
    if not files:
        raise SystemExit(f"frontend build is empty: {DIST_ROOT}")

    temporary = ARCHIVE_PATH.with_suffix(".zip.tmp")
    with ZipFile(temporary, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = path.relative_to(DIST_ROOT).as_posix()
            info = ZipInfo(relative, date_time=ZIP_TIMESTAMP)
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes(), compress_type=ZIP_DEFLATED, compresslevel=9)
    temporary.replace(ARCHIVE_PATH)
    return ARCHIVE_PATH


if __name__ == "__main__":
    built = build_archive()
    print(f"Frontend archive built: {built.relative_to(ROOT)}")
