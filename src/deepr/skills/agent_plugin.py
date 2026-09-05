"""Deterministic Agent Plugins 1.0.0 package validation and assembly."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from deepr import __version__ as DEEPR_VERSION
from deepr.mcp.contained_env import build_contained_read_only_env
from deepr.skills.contract import validate_agent_skill

AGENT_PLUGINS_VERSION = "1.0.0"
AGENT_PLUGINS_REVISION = "ff8ab5e392cc87bd88d87c060815a87490e51003"
PLUGIN_SCHEMA_ID = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA_ID = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"

_MAX_MANIFEST_BYTES = 64 * 1024
_MAX_PACKAGE_FILE_BYTES = 1024 * 1024
_MAX_PACKAGE_BYTES = 2 * 1024 * 1024
_EXPECTED_FILES = frozenset(
    {
        "LICENSE",
        "SHA256SUMS",
        "mcp.json",
        "plugin.json",
        "skills/deepr-research/SKILL.md",
        "skills/deepr-research/references/capability_boundary.md",
    }
)
_EXPECTED_ENV = build_contained_read_only_env("${PLUGIN_DATA}", advertise_full_tool_list=True)
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_WINDOWS_DEVICES = re.compile(r"^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?$", re.IGNORECASE)


@dataclass(frozen=True)
class PluginViolation:
    """One deterministic package violation."""

    code: str
    detail: str


@dataclass(frozen=True)
class PluginValidationResult:
    """Validation result for a complete Agent Plugin source directory."""

    root: Path
    files: tuple[str, ...]
    violations: tuple[PluginViolation, ...]

    @property
    def valid(self) -> bool:
        return not self.violations


def _violation(code: str, detail: str) -> PluginViolation:
    return PluginViolation(code=code, detail=detail)


def _is_link(path: Path) -> bool:
    try:
        is_junction = getattr(path, "is_junction", None)
        return path.is_symlink() or bool(is_junction and is_junction())
    except OSError:
        return True


def _portable_path(relative: str) -> bool:
    path = PurePosixPath(relative)
    if path.is_absolute() or relative in {"", "."} or _WINDOWS_DRIVE.match(relative):
        return False
    for part in path.parts:
        if part in {"", ".", ".."} or ":" in part or _WINDOWS_DEVICES.fullmatch(part):
            return False
        if any(ord(character) < 32 for character in part):
            return False
    return True


def _inventory(root: Path) -> tuple[list[str], list[PluginViolation]]:
    files: list[str] = []
    violations: list[PluginViolation] = []
    total_bytes = 0
    if not root.is_dir() or _is_link(root):
        return files, [_violation("invalid_root", "plugin root must be a real directory")]
    for current, directories, names in os.walk(root, followlinks=False):
        current_path = Path(current)
        retained: list[str] = []
        for name in sorted(directories):
            child = current_path / name
            if _is_link(child):
                relative = child.relative_to(root).as_posix()
                violations.append(_violation("linked_entry", f"linked directory is forbidden: {relative}"))
            else:
                retained.append(name)
        directories[:] = retained
        for name in sorted(names):
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if not _portable_path(relative):
                violations.append(_violation("nonportable_path", relative))
            elif _is_link(path) or not path.is_file():
                violations.append(_violation("linked_entry", f"regular files only: {relative}"))
            else:
                size = path.stat().st_size
                if size > _MAX_PACKAGE_FILE_BYTES:
                    violations.append(_violation("file_too_large", relative))
                total_bytes += size
                files.append(relative)
    if total_bytes > _MAX_PACKAGE_BYTES:
        violations.append(_violation("package_too_large", f"package contains {total_bytes} bytes"))
    return sorted(files), violations


def _load_json(path: Path) -> tuple[dict[str, Any] | None, PluginViolation | None]:
    try:
        if path.stat().st_size > _MAX_MANIFEST_BYTES:
            return None, _violation("manifest_too_large", f"{path.name} exceeds {_MAX_MANIFEST_BYTES} bytes")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        return None, _violation("invalid_manifest", f"{path.name}: {exc}")
    if not isinstance(payload, dict):
        return None, _violation("invalid_manifest", f"{path.name} must contain a JSON object")
    return payload, None


def _validate_plugin_manifest(payload: dict[str, Any]) -> list[PluginViolation]:
    violations: list[PluginViolation] = []
    allowed = {
        "$schema",
        "name",
        "version",
        "description",
        "author",
        "homepage",
        "repository",
        "license",
        "keywords",
        "extensions",
    }
    if set(payload) - allowed:
        violations.append(_violation("plugin_schema", "plugin.json contains unknown properties"))
    if payload.get("$schema") != PLUGIN_SCHEMA_ID or payload.get("name") != "deepr-research":
        violations.append(_violation("plugin_identity", "plugin schema and name must match the Deepr package"))
    if payload.get("version") != DEEPR_VERSION:
        violations.append(_violation("version_drift", "plugin version must match the Deepr package version"))
    if "author" in payload:
        violations.append(_violation("attribution_field", "the distributable manifest must not contain attribution"))
    string_fields = ("description", "homepage", "repository", "license")
    if any(field in payload and not isinstance(payload[field], str) for field in string_fields):
        violations.append(_violation("plugin_schema", "plugin manifest text fields must be strings"))
    keywords = payload.get("keywords")
    if keywords is not None and (
        not isinstance(keywords, list) or not all(isinstance(keyword, str) for keyword in keywords)
    ):
        violations.append(_violation("plugin_schema", "plugin keywords must be an array of strings"))
    extensions = payload.get("extensions")
    if extensions is not None and (
        not isinstance(extensions, dict) or not all(isinstance(value, dict) for value in extensions.values())
    ):
        violations.append(_violation("plugin_schema", "plugin extensions must map namespaces to objects"))
    return violations


def _validate_mcp_manifest(payload: dict[str, Any]) -> list[PluginViolation]:
    if set(payload) != {"$schema", "mcpServers"} or payload.get("$schema") != MCP_SCHEMA_ID:
        return [_violation("mcp_schema", "mcp.json root does not match Agent Plugins 1.0.0")]
    servers = payload.get("mcpServers")
    if not isinstance(servers, dict) or set(servers) != {"deepr"}:
        return [_violation("mcp_servers", "exactly one local Deepr server is required")]
    server = servers["deepr"]
    if not isinstance(server, dict):
        return [_violation("mcp_server", "Deepr MCP server declaration must be an object")]
    violations: list[PluginViolation] = []
    if set(server) != {"type", "command", "cwd", "env"}:
        violations.append(_violation("mcp_server", "only type, command, cwd, and env are permitted"))
    if server.get("type") != "stdio" or server.get("command") != "deepr-mcp":
        violations.append(_violation("mcp_transport", "the bridge must use the installed deepr-mcp stdio command"))
    if server.get("cwd") != "${PLUGIN_DATA}":
        violations.append(_violation("mcp_cwd", "the MCP working directory must be the plugin data root"))
    if server.get("env") != _EXPECTED_ENV:
        violations.append(
            _violation("mcp_environment", "the MCP environment must match the contained read-only profile")
        )
    return violations


def _expected_checksums(root: Path, files: list[str]) -> str:
    lines = []
    for relative in files:
        if relative == "SHA256SUMS":
            continue
        digest = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        lines.append(f"{digest}  {relative}")
    return "\n".join(lines) + "\n"


def validate_agent_plugin(root: Path) -> PluginValidationResult:
    """Validate the closed, contained Deepr Agent Plugin package."""
    root = Path(os.path.abspath(root))
    files, violations = _inventory(root)
    unexpected = sorted(set(files) - _EXPECTED_FILES)
    missing = sorted(_EXPECTED_FILES - set(files))
    if unexpected:
        violations.append(_violation("unexpected_files", ", ".join(unexpected)))
    if missing:
        violations.append(_violation("missing_files", ", ".join(missing)))
    if not missing:
        plugin, plugin_error = _load_json(root / "plugin.json")
        mcp, mcp_error = _load_json(root / "mcp.json")
        for error in (plugin_error, mcp_error):
            if error:
                violations.append(error)
        if plugin is not None:
            violations.extend(_validate_plugin_manifest(plugin))
        if mcp is not None:
            violations.extend(_validate_mcp_manifest(mcp))
        skill_result = validate_agent_skill(root / "skills" / "deepr-research" / "SKILL.md")
        violations.extend(_violation(f"skill_{item.code}", item.detail) for item in skill_result.violations)
        try:
            checksums = (root / "SHA256SUMS").read_text(encoding="ascii")
            if checksums != _expected_checksums(root, files):
                violations.append(
                    _violation("checksum_mismatch", "SHA256SUMS is not the exact sorted package manifest")
                )
        except (OSError, UnicodeError) as exc:
            violations.append(_violation("checksum_mismatch", str(exc)))
    return PluginValidationResult(root=root, files=tuple(files), violations=tuple(violations))


def _safe_output_path(source_root: Path, destination: Path) -> Path:
    destination = Path(os.path.abspath(destination))
    if destination.is_relative_to(source_root):
        raise ValueError("Agent Plugin output must be outside the immutable package source")

    unresolved: list[str] = []
    existing_parent = destination.parent
    while not existing_parent.exists():
        unresolved.append(existing_parent.name)
        existing_parent = existing_parent.parent
    predicted_parent = existing_parent.resolve(strict=True).joinpath(*reversed(unresolved))
    if predicted_parent.is_relative_to(source_root):
        raise ValueError("Agent Plugin output must be outside the immutable package source")

    destination.parent.mkdir(parents=True, exist_ok=True)
    resolved_parent = destination.parent.resolve(strict=True)
    output = resolved_parent / destination.name
    if output.is_relative_to(source_root):
        raise ValueError("Agent Plugin output must be outside the immutable package source")
    return output


def build_agent_plugin(source: Path, destination: Path) -> str:
    """Build a byte-reproducible gzip-compressed tar archive and return SHA-256."""
    result = validate_agent_plugin(source)
    if not result.valid:
        detail = "; ".join(f"{item.code}: {item.detail}" for item in result.violations)
        raise ValueError(f"invalid Agent Plugin package: {detail}")
    source_root = result.root.resolve(strict=True)
    destination = _safe_output_path(source_root, destination)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as archive:
                    for relative in result.files:
                        payload = (source_root / relative).read_bytes()
                        info = tarfile.TarInfo(name=f"deepr-research/{relative}")
                        info.size = len(payload)
                        info.mode = 0o644
                        info.mtime = 0
                        info.uid = 0
                        info.gid = 0
                        info.uname = ""
                        info.gname = ""
                        archive.addfile(info, fileobj=io.BytesIO(payload))
            raw.flush()
            os.fsync(raw.fileno())
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return hashlib.sha256(destination.read_bytes()).hexdigest()


__all__ = [
    "AGENT_PLUGINS_REVISION",
    "AGENT_PLUGINS_VERSION",
    "MCP_SCHEMA_ID",
    "PLUGIN_SCHEMA_ID",
    "PluginValidationResult",
    "PluginViolation",
    "build_agent_plugin",
    "validate_agent_plugin",
]
