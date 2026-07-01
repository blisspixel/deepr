from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _script_env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["DEEPR_DATA_DIR"] = str(tmp_path / "data")
    env["DEEPR_REPORTS_PATH"] = str(tmp_path / "reports")
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    return env


def test_discover_models_show_registry_uses_src_layout(tmp_path: Path):
    result = subprocess.run(
        [sys.executable, "scripts/discover_models.py", "--show-registry"],
        cwd=ROOT,
        env=_script_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "openai/gpt-5.4" in result.stdout
    assert "src/deepr/providers/registry.py" not in result.stderr


def test_create_demo_experts_uses_configured_experts_root(tmp_path: Path):
    result = subprocess.run(
        [sys.executable, "scripts/create_demo_experts.py"],
        cwd=ROOT,
        env=_script_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    profile_paths = sorted((tmp_path / "data" / "experts").rglob("profile.json"))
    assert len(profile_paths) == 3
    worldview_paths = sorted((tmp_path / "data" / "experts").rglob("worldview.json"))
    assert len(worldview_paths) == 3
    for worldview_path in worldview_paths:
        worldview = json.loads(worldview_path.read_text(encoding="utf-8"))
        assert len(worldview["beliefs"]) > 0
        assert len(worldview["knowledge_gaps"]) > 0
        for belief in worldview["beliefs"]:
            assert belief["statement"]
            assert belief["confidence"] > 0
            assert len(belief["evidence"]) > 0
    assert "Created 'Climate Science'" in result.stdout


def test_create_demo_experts_refreshes_stale_demo_profiles(tmp_path: Path):
    env = _script_env(tmp_path)
    first = subprocess.run(
        [sys.executable, "scripts/create_demo_experts.py"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert first.returncode == 0, first.stderr

    profile_path = next(
        path
        for path in (tmp_path / "data" / "experts").rglob("profile.json")
        if json.loads(path.read_text(encoding="utf-8"))["name"] == "Climate Science"
    )
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["source_files"] = []
    profile["total_documents"] = 0
    profile["description"] = "IPCC reports, carbon budgets, climate modeling, and emissions pathways"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")

    second = subprocess.run(
        [sys.executable, "scripts/create_demo_experts.py"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert second.returncode == 0, second.stderr
    refreshed = json.loads(profile_path.read_text(encoding="utf-8"))
    assert refreshed["total_documents"] == 12
    assert len(refreshed["source_files"]) == 12
    assert refreshed["knowledge_cutoff_date"]
    assert "Refreshed 'Climate Science'" in second.stdout
