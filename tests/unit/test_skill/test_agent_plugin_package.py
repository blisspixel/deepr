"""Agent Plugins 1.0.0 package conformance and reproducibility tests."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from deepr.mcp.contained_env import build_contained_read_only_env
from deepr.skills.agent_plugin import build_agent_plugin, validate_agent_plugin

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "packages" / "deepr-agent-plugin"
SCHEMAS = ROOT / "docs" / "schemas" / "vendor" / "agent-plugins" / "1.0.0"


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _refresh_checksums(root: Path) -> None:
    paths = sorted(
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file() and path.name != "SHA256SUMS"
    )
    lines = [f"{hashlib.sha256((root / path).read_bytes()).hexdigest()}  {path}" for path in paths]
    (root / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="ascii")


def test_committed_package_passes_closed_offline_contract() -> None:
    result = validate_agent_plugin(PACKAGE)

    assert result.valid, result.violations
    assert result.files == (
        "SHA256SUMS",
        "mcp.json",
        "plugin.json",
        "skills/deepr-research/SKILL.md",
        "skills/deepr-research/references/capability_boundary.md",
    )


def test_manifests_validate_against_pinned_official_schemas() -> None:
    for filename in ("plugin.json", "mcp.json"):
        schema = json.loads((SCHEMAS / f"{filename.removesuffix('.json')}.schema.json").read_text(encoding="utf-8"))
        payload = json.loads((PACKAGE / filename).read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(payload)


def test_plugin_manifest_has_no_attribution_field() -> None:
    payload = json.loads((PACKAGE / "plugin.json").read_text(encoding="utf-8"))

    assert "author" not in payload


def test_mcp_profile_is_local_read_only_and_zero_spend() -> None:
    payload = json.loads((PACKAGE / "mcp.json").read_text(encoding="utf-8"))
    server = payload["mcpServers"]["deepr"]
    env = server["env"]

    assert server["type"] == "stdio"
    assert server["command"] == "deepr-mcp"
    assert server["cwd"] == "${PLUGIN_DATA}"
    assert env["DEEPR_RESEARCH_MODE"] == "read_only"
    assert env["DEEPR_MCP_AUTO_APPROVE"] == "0"
    assert env["DEEPR_MCP_ADVERTISE_FULL_TOOL_LIST"] == "0"
    assert env == build_contained_read_only_env("${PLUGIN_DATA}")
    assert all(env[name] == "0" for name in env if "MAX_COST" in name or name.endswith("_LIMIT"))
    assert all(
        value.startswith("${PLUGIN_DATA}/deepr")
        for name, value in env.items()
        if name.endswith(("_DIR", "_PATH", "_FILE"))
    )


def test_build_is_reproducible_and_does_not_mutate_source(tmp_path: Path) -> None:
    before = _tree_digest(PACKAGE)
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"

    first_digest = build_agent_plugin(PACKAGE, first)
    second_digest = build_agent_plugin(PACKAGE, second)

    assert first.read_bytes() == second.read_bytes()
    assert first_digest == second_digest == hashlib.sha256(first.read_bytes()).hexdigest()
    assert _tree_digest(PACKAGE) == before
    with tarfile.open(first, "r:gz") as archive:
        members = archive.getmembers()
        assert [member.name for member in members] == [
            f"deepr-research/{path}" for path in validate_agent_plugin(PACKAGE).files
        ]
        assert all(member.mtime == 0 and member.uid == 0 and member.gid == 0 for member in members)
        assert all(member.mode == 0o644 and member.isfile() for member in members)


def test_tampering_or_undeclared_files_fail_closed(tmp_path: Path) -> None:
    copied = tmp_path / "plugin"
    shutil.copytree(PACKAGE, copied)
    (copied / "plugin.json").write_text("{}\n", encoding="utf-8")
    (copied / "notes.md").write_text("untracked\n", encoding="utf-8")

    result = validate_agent_plugin(copied)
    codes = {item.code for item in result.violations}

    assert {"unexpected_files", "plugin_identity", "version_drift", "checksum_mismatch"} <= codes


def test_production_validation_enforces_optional_manifest_types(tmp_path: Path) -> None:
    copied = tmp_path / "plugin"
    shutil.copytree(PACKAGE, copied)
    manifest_path = copied / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["keywords"] = 42
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    _refresh_checksums(copied)

    result = validate_agent_plugin(copied)

    assert not result.valid
    assert "plugin_schema" in {item.code for item in result.violations}
    with pytest.raises(ValueError, match="plugin_schema"):
        build_agent_plugin(copied, tmp_path / "invalid.tar.gz")


def test_builder_refuses_to_write_inside_package_source(tmp_path: Path) -> None:
    copied = tmp_path / "plugin"
    shutil.copytree(PACKAGE, copied)

    try:
        build_agent_plugin(copied, copied / "nested.tar.gz")
    except ValueError as exc:
        assert "outside" in str(exc)
    else:
        raise AssertionError("builder accepted an output inside its immutable source")

    assert not (copied / "nested.tar.gz").exists()


def test_builder_atomically_replaces_hardlinked_destination(tmp_path: Path) -> None:
    copied = tmp_path / "plugin"
    shutil.copytree(PACKAGE, copied)
    manifest = copied / "plugin.json"
    before = manifest.read_bytes()
    destination = tmp_path / "plugin.tar.gz"
    os.link(manifest, destination)

    build_agent_plugin(copied, destination)

    assert manifest.read_bytes() == before
    assert destination.read_bytes().startswith(b"\x1f\x8b")


def test_builder_rejects_parent_alias_into_source(tmp_path: Path) -> None:
    copied = tmp_path / "plugin"
    shutil.copytree(PACKAGE, copied)
    alias = tmp_path / "source-alias"
    if os.name == "nt":
        created = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(alias), str(copied)],
            capture_output=True,
            check=False,
            text=True,
        )
        if created.returncode:
            pytest.skip("directory junctions are unavailable")
    else:
        try:
            alias.symlink_to(copied, target_is_directory=True)
        except OSError:
            pytest.skip("directory symlinks are unavailable")

    with pytest.raises(ValueError, match="outside"):
        build_agent_plugin(copied, alias / "nested" / "plugin.tar.gz")

    assert not (copied / "nested").exists()
