"""Offline hard-form validation for the pinned Agent Skills contract."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

AGENT_SKILLS_REVISION = "69ef37e9424c0a7ea9dd2293b559e43ec8176379"
AGENT_SKILLS_SPEC_SHA256 = "b9079c0c10b7930e8c6a20ff2bc10cda2a3343c55185120e3f1116a1a529b220"
AGENT_SKILLS_SPEC_URL = (
    f"https://raw.githubusercontent.com/agentskills/agentskills/{AGENT_SKILLS_REVISION}/docs/specification.mdx"
)

_MAX_SKILL_BYTES = 256 * 1024
_ALLOWED_FIELDS = frozenset({"name", "description", "license", "compatibility", "metadata", "allowed-tools"})
_NAME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


@dataclass(frozen=True)
class SkillViolation:
    """One deterministic Agent Skills hard-form violation."""

    code: str
    detail: str


@dataclass(frozen=True)
class SkillValidationResult:
    """Validation result for one SKILL.md file."""

    path: Path
    fields: dict[str, Any]
    violations: tuple[SkillViolation, ...]

    @property
    def valid(self) -> bool:
        return not self.violations


def _violation(code: str, detail: str) -> SkillViolation:
    return SkillViolation(code=code, detail=detail)


def _frontmatter(text: str) -> tuple[dict[str, Any], str | None]:
    if not text.startswith("---\n"):
        return {}, "SKILL.md must start with a YAML frontmatter delimiter"
    closing = text.find("\n---\n", 4)
    if closing < 0:
        return {}, "SKILL.md frontmatter is not terminated"
    source = text[4:closing]
    try:
        parsed = yaml.safe_load(source)
    except (yaml.YAMLError, ValueError) as exc:
        return {}, f"frontmatter is not parseable YAML: {exc}"
    if not isinstance(parsed, dict):
        return {}, "frontmatter must be a YAML mapping"
    if not all(isinstance(key, str) for key in parsed):
        return {}, "frontmatter keys must be strings"
    return parsed, None


def _validate_required_strings(fields: dict[str, Any]) -> list[SkillViolation]:
    violations: list[SkillViolation] = []
    name = fields.get("name")
    if not isinstance(name, str) or not 1 <= len(name) <= 64:
        violations.append(_violation("invalid_name", "name must be a string of 1 to 64 characters"))
    elif not _NAME_PATTERN.fullmatch(name) or "--" in name:
        violations.append(
            _violation("invalid_name", "name must contain lowercase ASCII letters, digits, and single hyphens")
        )
    description = fields.get("description")
    if not isinstance(description, str) or not description.strip() or len(description) > 1024:
        violations.append(
            _violation("invalid_description", "description must be a non-empty string of at most 1024 characters")
        )
    return violations


def _validate_optional_fields(fields: dict[str, Any]) -> list[SkillViolation]:
    violations: list[SkillViolation] = []
    for key in ("license", "allowed-tools"):
        if key in fields and not isinstance(fields[key], str):
            violations.append(_violation(f"invalid_{key}", f"{key} must be a string"))
    if "compatibility" in fields:
        value = fields["compatibility"]
        if not isinstance(value, str) or not 1 <= len(value) <= 500:
            violations.append(
                _violation("invalid_compatibility", "compatibility must be a string of 1 to 500 characters")
            )
    if "metadata" in fields:
        metadata = fields["metadata"]
        if not isinstance(metadata, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in metadata.items()
        ):
            violations.append(_violation("invalid_metadata", "metadata must map string keys to string values"))
    return violations


def validate_agent_skill(path: Path) -> SkillValidationResult:
    """Validate one SKILL.md without network or model calls."""
    violations: list[SkillViolation] = []
    if path.name != "SKILL.md":
        violations.append(_violation("invalid_filename", "the skill entry file must be named SKILL.md"))
    try:
        size = path.stat().st_size
        if size > _MAX_SKILL_BYTES:
            violations.append(
                _violation("file_too_large", f"SKILL.md exceeds the {_MAX_SKILL_BYTES}-byte validation limit")
            )
            return SkillValidationResult(path=path, fields={}, violations=tuple(violations))
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        violations.append(_violation("unreadable", str(exc)))
        return SkillValidationResult(path=path, fields={}, violations=tuple(violations))

    fields, parse_error = _frontmatter(text)
    if parse_error:
        violations.append(_violation("invalid_frontmatter", parse_error))
        return SkillValidationResult(path=path, fields=fields, violations=tuple(violations))

    unknown = sorted(set(fields) - _ALLOWED_FIELDS)
    if unknown:
        violations.append(_violation("unknown_fields", f"unsupported frontmatter fields: {', '.join(unknown)}"))
    violations.extend(_validate_required_strings(fields))
    violations.extend(_validate_optional_fields(fields))
    name = fields.get("name")
    if isinstance(name, str) and path.parent.name != name:
        violations.append(
            _violation("directory_name_mismatch", f"skill name {name!r} must match directory {path.parent.name!r}")
        )
    return SkillValidationResult(path=path, fields=fields, violations=tuple(violations))


__all__ = [
    "AGENT_SKILLS_REVISION",
    "AGENT_SKILLS_SPEC_SHA256",
    "AGENT_SKILLS_SPEC_URL",
    "SkillValidationResult",
    "SkillViolation",
    "validate_agent_skill",
]
