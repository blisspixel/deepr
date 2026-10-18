"""Verify a clean core wheel and its native entry points on the current platform."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True, help="New isolated directory, including spaces")
    args = parser.parse_args()
    wheels = list(args.dist_dir.resolve().glob("deepr_research-*-py3-none-any.whl"))
    if len(wheels) != 1:
        parser.error("dist-dir must contain exactly one Deepr wheel")
    runtime = args.runtime_root.resolve()
    runtime.mkdir(parents=True, exist_ok=False)
    work = runtime / "work"
    work.mkdir()
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper()
        in {
            "PATH",
            "SYSTEMROOT",
            "WINDIR",
            "COMSPEC",
            "TEMP",
            "TMP",
            "TMPDIR",
            "LANG",
            "LC_ALL",
            "HOME",
            "USERPROFILE",
            "APPDATA",
            "LOCALAPPDATA",
        }
    }
    env.update(
        PYTHON_DOTENV_DISABLED="1",
        CI="1",
        PYYAML_FORCE_LIBYAML="0",
        UV_CACHE_DIR=str(runtime / "uv cache"),
        DEEPR_DATA_DIR=str(runtime / "data"),
        DEEPR_EXPERTS_PATH=str(runtime / "experts"),
        DEEPR_REPORTS_PATH=str(runtime / "reports"),
        DEEPR_COST_DATA_DIR=str(runtime / "costs"),
    )

    def run(label: str, argv: list[str]) -> str:
        result = subprocess.run(argv, cwd=work, env=env, capture_output=True, text=True, timeout=600)
        (runtime / f"{label}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"{label} failed ({result.returncode}); see {runtime / (label + '.log')}")
        return result.stdout

    venv = runtime / "clean wheel"
    run("create-environment", ["uv", "venv", "--python", sys.executable, str(venv)])
    scripts = venv / ("Scripts" if os.name == "nt" else "bin")
    python = scripts / ("python.exe" if os.name == "nt" else "python")
    cli = scripts / ("deepr.exe" if os.name == "nt" else "deepr")
    mcp = scripts / ("deepr-mcp.exe" if os.name == "nt" else "deepr-mcp")
    run("install-core", ["uv", "pip", "install", "--python", str(python), str(wheels[0])])
    env["PATH"] = str(scripts) + os.pathsep + env.get("PATH", "")
    probe = r"""
import importlib.metadata, json, sys
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy
import yaml
from deepr.experts.okf_publication import publish_okf_directory
assert yaml.safe_load('nested:\n  safe: true\n') == {'nested': {'safe': True}}
try:
    yaml.safe_load("!!python/object/apply:os.system ['exit 1']")
except yaml.YAMLError:
    pass
else:
    raise AssertionError('unsafe YAML accepted')
assert float(numpy.dot([1., 2.], [3., 4.])) == 11.
with TemporaryDirectory(dir=Path.cwd()) as directory:
    output = Path(directory) / 'export'
    publish_okf_directory({'index.md': 'fixture\n'}, output, force=False, okf_version='0.2')
    assert (output / 'index.md').read_text() == 'fixture\n'
print(json.dumps({'version': importlib.metadata.version('deepr-research'), 'python': list(sys.version_info[:2]), 'releaselevel': sys.version_info.releaselevel, 'implementation': sys.implementation.name, 'numpy': numpy.__version__, 'yaml': yaml.__version__, 'yaml_c_extension': yaml.__with_libyaml__}))
"""
    receipt = json.loads(run("runtime-boundaries", [str(python), "-c", probe]))
    assert receipt["python"] == list(sys.version_info[:2])
    assert receipt["implementation"] == "cpython"
    assert receipt["releaselevel"] == "final", "Platform acceptance requires a final CPython release"
    assert wheels[0].name == f"deepr_research-{receipt['version']}-py3-none-any.whl"
    assert receipt["version"] in run("version", [str(cli), "--version"])
    run("help", [str(cli), "--help"])
    doctor = json.loads(run("doctor", [str(cli), "doctor", "--skip-connectivity", "--json"]))
    assert doctor["capacity"]["generation_tested"] is False
    assert json.loads(run("inventory", [str(cli), "expert", "list", "--json"]))["count"] == 0
    preview = json.loads(run("preview", [str(cli), "research", "Platform installation fixture", "--preview", "--json"]))
    assert preview["executed"] is False
    run("protocol", [str(cli), "mcp", "conformance", "--json"])
    run(
        "stdio",
        [
            str(python),
            str(ROOT / "scripts/check_agent_plugin_install.py"),
            "--package-root",
            str(ROOT / "packages/deepr-agent-plugin"),
            "--data-root",
            str(runtime / "plugin data"),
            "--command",
            str(mcp),
        ],
    )
    run(
        "host",
        [
            str(python),
            str(ROOT / "scripts/check_host_profile_install.py"),
            "--fixture",
            str(ROOT / "tests/fixtures/hosts/openclaw/v2026.7.1-2/profile.json"),
            "--data-root",
            str(runtime / "host data"),
            "--mcp-command",
            str(mcp),
            "--deepr-command",
            str(cli),
        ],
    )
    (runtime / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    print("Clean core wheel, YAML/NumPy/publication boundaries, CLI, MCP and host checks passed at $0.")


if __name__ == "__main__":
    main()
