"""Every third-party module the package imports is a declared dependency.

The development environment carries build and test tooling, so an import can
pass the whole suite while a clean install lacks it. That shipped once:
`packaging` was imported by opt-in preparation but never declared, so
`--prepare` crashed on the public installer (#309).

Imports whose distribution is not installed here (platform-guarded or optional
modules such as `win32api`) cannot be resolved and are not judged.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from importlib.metadata import packages_distributions
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SOURCE = _REPO_ROOT / "src" / "deepr"


def _declared() -> set[str]:
    project = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    requirements = list(project["dependencies"])
    for extra in project.get("optional-dependencies", {}).values():
        requirements.extend(extra)
    return {canonicalize_name(Requirement(item).name) for item in requirements}


def _imported_top_level_modules() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for path in sorted(_SOURCE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            else:
                continue
            for name in names:
                if name not in sys.stdlib_module_names and name not in {"deepr", "__future__"}:
                    found.setdefault(name, set()).add(path.relative_to(_REPO_ROOT).as_posix())
    return found


def test_every_resolvable_third_party_import_is_declared():
    declared = _declared()
    installed = packages_distributions()
    undeclared = {}
    for module, files in _imported_top_level_modules().items():
        distributions = {canonicalize_name(name) for name in installed.get(module, [])}
        if distributions and not distributions & declared:
            undeclared[module] = sorted(files)[:3]
    assert undeclared == {}, f"imported but not declared in pyproject dependencies or extras: {undeclared}"


def test_the_scan_sees_the_preparation_imports_it_guards():
    # Guards the guard: if the scan stopped finding these, the test above would pass vacuously.
    modules = _imported_top_level_modules()
    assert "src/deepr/experts/preparation_service.py" in modules["packaging"]
    assert "src/deepr/utils/pinned_http.py" in modules["urllib3"]
    assert canonicalize_name("packaging") in {canonicalize_name(name) for name in packages_distributions()["packaging"]}
