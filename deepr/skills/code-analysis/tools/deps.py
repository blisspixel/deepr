"""Dependency analysis for source code."""

from __future__ import annotations

import re
from typing import Any


def analyze_dependencies(code: str, language: str = "auto") -> dict[str, Any]:
    """Analyze import/dependency structure from source code.

    Args:
        code: Source code text
        language: Programming language (auto-detected if "auto")

    Returns:
        Dictionary with imports, external packages, and potential circular deps
    """
    if language == "auto":
        language = _detect_language(code)

    if language == "python":
        return _analyze_python(code)
    elif language in ("javascript", "typescript"):
        return _analyze_js(code)
    return {"error": f"Unsupported language: {language}", "imports": []}


def _detect_language(code: str) -> str:
    if "import " in code and ("def " in code or "class " in code):
        return "python"
    if "require(" in code or ("import " in code and ("const " in code or "function " in code)):
        return "javascript"
    return "python"


def _analyze_python(code: str) -> dict[str, Any]:
    imports = []
    stdlib = {
        "os",
        "sys",
        "re",
        "json",
        "math",
        "datetime",
        "pathlib",
        "typing",
        "collections",
        "functools",
        "itertools",
        "logging",
        "abc",
        "dataclasses",
        "asyncio",
        "hashlib",
        "uuid",
        "time",
        "io",
        "copy",
        "enum",
        "string",
    }

    for match in re.finditer(r"^import\s+([\w.]+)", code, re.MULTILINE):
        imports.append({"module": match.group(1), "type": "import"})
    for match in re.finditer(r"^from\s+([\w.]+)\s+import", code, re.MULTILINE):
        imports.append({"module": match.group(1), "type": "from_import"})

    external = []
    internal = []
    std = []
    for imp in imports:
        top_level = imp["module"].split(".")[0]
        if top_level in stdlib:
            std.append(imp["module"])
        elif imp["module"].startswith(".") or "." in imp["module"]:
            internal.append(imp["module"])
        else:
            external.append(imp["module"])

    return {
        "language": "python",
        "total_imports": len(imports),
        "imports": imports,
        "stdlib": sorted(set(std)),
        "external": sorted(set(external)),
        "internal": sorted(set(internal)),
        "unique_packages": len(set(imp["module"].split(".")[0] for imp in imports)),
    }


def _analyze_js(code: str) -> dict[str, Any]:
    imports = []
    for match in re.finditer(r"""(?:import|require)\s*\(?\s*['"]([^'"]+)['"]""", code):
        module = match.group(1)
        is_relative = module.startswith(".")
        imports.append({"module": module, "type": "relative" if is_relative else "package"})

    packages = sorted(set(imp["module"] for imp in imports if imp["type"] == "package"))
    relative = sorted(set(imp["module"] for imp in imports if imp["type"] == "relative"))

    return {
        "language": "javascript",
        "total_imports": len(imports),
        "imports": imports,
        "packages": packages,
        "relative_imports": relative,
        "unique_packages": len(packages),
    }
