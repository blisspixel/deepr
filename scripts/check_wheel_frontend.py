"""Fail when a Deepr wheel omits the built dashboard."""

from __future__ import annotations

import sys
from pathlib import Path
from zipfile import ZipFile


def check_wheel(path: Path) -> None:
    with ZipFile(path) as wheel:
        names = set(wheel.namelist())
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


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        raise SystemExit("usage: check_wheel_frontend.py PATH_TO_WHEEL")
    wheel = Path(argv[0]).resolve()
    if not wheel.is_file():
        raise SystemExit(f"wheel not found: {wheel}")
    check_wheel(wheel)
    print(f"Packaged frontend verified: {wheel.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
