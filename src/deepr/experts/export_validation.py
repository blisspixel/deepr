"""Local $0 validators for exported derived views (ROADMAP item 7).

Exported artifacts - handoff payloads, OKF bundles, SKILL.md exports - are
generated views over canonical expert state. Before one ships to another
host, an operator can prove it carries the required provenance, schema
version, trust metadata, and artifact-class markers. Every check here is
form-only: presence, shape, and known constants. Nothing judges whether the
content is true; that stays with calibrated review paths.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

EXPORT_VALIDATION_SCHEMA_VERSION = "deepr-export-validation-v1"
EXPORT_VALIDATION_KIND = "deepr.expert.export_validation"

ARTIFACT_CLASS_HANDOFF = "handoff_payload"
ARTIFACT_CLASS_OKF = "okf_bundle"
ARTIFACT_CLASS_SKILL = "skill_export"
ARTIFACT_CLASS_UNKNOWN = "unknown"

_SKILL_REQUIRED_FRONTMATTER = ("name", "description", "version", "mcp_server")
_HANDOFF_REQUIRED_KEYS = ("schema_version", "kind", "generated_at", "contract", "expert", "summary")


def _check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"check": name, "status": "pass" if passed else "fail", "detail": detail}


def _contract() -> dict[str, Any]:
    return {
        "read_only": True,
        "cost_usd": 0.0,
        "model_calls": False,
        "semantic_judgment": False,
        "scope": "form-only presence, shape, and known-constant checks",
    }


def _classify(path: Path) -> str:
    if path.is_dir():
        return ARTIFACT_CLASS_OKF if (path / "index.md").is_file() else ARTIFACT_CLASS_UNKNOWN
    if path.name.upper() == "SKILL.MD":
        return ARTIFACT_CLASS_SKILL
    if path.suffix.lower() == ".json":
        return ARTIFACT_CLASS_HANDOFF
    return ARTIFACT_CLASS_UNKNOWN


def _validate_handoff(path: Path) -> list[dict[str, Any]]:
    from deepr.experts.handoff import HANDOFF_KIND, HANDOFF_SCHEMA_VERSION

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        # ValueError covers both JSONDecodeError and UnicodeDecodeError.
        return [_check("parseable_json", False, str(exc))]
    if not isinstance(payload, dict):
        return [_check("parseable_json", False, "payload is not a JSON object")]

    checks = [_check("parseable_json", True, "valid JSON object")]
    schema_version = str(payload.get("schema_version", "") or "")
    checks.append(
        _check(
            "schema_version",
            schema_version == HANDOFF_SCHEMA_VERSION,
            f"expected {HANDOFF_SCHEMA_VERSION}, found {schema_version or '(missing)'}",
        )
    )
    checks.append(
        _check(
            "kind",
            str(payload.get("kind", "") or "") == HANDOFF_KIND,
            f"expected {HANDOFF_KIND}, found {payload.get('kind') or '(missing)'}",
        )
    )
    missing = [key for key in _HANDOFF_REQUIRED_KEYS if key not in payload]
    checks.append(
        _check(
            "required_keys",
            not missing,
            "all required keys present" if not missing else f"missing: {', '.join(missing)}",
        )
    )
    raw_contract = payload.get("contract")
    contract = raw_contract if isinstance(raw_contract, dict) else {}
    declares_view_class = bool(contract.get("canonical_state")) and bool(contract.get("derived_views"))
    checks.append(
        _check(
            "generated_view_class",
            declares_view_class,
            "contract names canonical state and derived views"
            if declares_view_class
            else "contract does not declare the canonical-state/derived-view boundary",
        )
    )
    raw_summary = payload.get("summary")
    summary = raw_summary if isinstance(raw_summary, dict) else {}
    checks.append(
        _check(
            "grounding_assurance",
            isinstance(summary.get("grounding_assurance"), dict),
            "summary carries grounding assurance counts"
            if isinstance(summary.get("grounding_assurance"), dict)
            else "summary.grounding_assurance is missing",
        )
    )
    raw_expert = payload.get("expert")
    expert = raw_expert if isinstance(raw_expert, dict) else {}
    checks.append(
        _check(
            "expert_provenance",
            bool(str(expert.get("name", "") or "")),
            "expert name present" if expert.get("name") else "expert.name is missing",
        )
    )
    checks.append(
        _check(
            "generated_at",
            bool(str(payload.get("generated_at", "") or "")),
            "generation timestamp present" if payload.get("generated_at") else "generated_at is missing",
        )
    )
    return checks


def _validate_okf_bundle(path: Path) -> list[dict[str, Any]]:
    from deepr.experts.okf import OKF_PROFILE_SCHEMA_VERSION, OKF_SCHEMA_VERSION, _split_frontmatter

    # index.md presence is what classified this path as an OKF bundle, so
    # only log.md needs its own presence check here.
    checks = [_check("log_present", (path / "log.md").is_file(), "log.md")]
    allowed_versions = {OKF_SCHEMA_VERSION, OKF_PROFILE_SCHEMA_VERSION}
    markdown_files = sorted(path.rglob("*.md"))
    unreadable: list[str] = []
    bad_versions: list[str] = []
    for markdown_file in markdown_files:
        try:
            text = markdown_file.read_text(encoding="utf-8")
        except (OSError, ValueError):
            unreadable.append(markdown_file.name)
            continue
        fields, _body = _split_frontmatter(text)
        if str(fields.get("schema_version", "") or "") not in allowed_versions:
            bad_versions.append(markdown_file.name)
    checks.append(_check("readable_files", not unreadable, ", ".join(unreadable[:5]) or "all markdown files readable"))
    checks.append(
        _check(
            "frontmatter_schema_versions",
            not bad_versions,
            f"{len(markdown_files)} markdown file(s) carry a known OKF schema version"
            if not bad_versions
            else f"missing or unknown schema_version in: {', '.join(bad_versions[:5])}",
        )
    )
    return checks


def _validate_skill_export(path: Path) -> list[dict[str, Any]]:
    from deepr.experts.okf import _split_frontmatter

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        return [_check("readable_file", False, str(exc))]

    # _split_frontmatter never raises; missing or malformed frontmatter
    # simply yields no fields.
    fields, body = _split_frontmatter(text)
    checks = [
        _check("readable_file", True, "file read as UTF-8"),
        _check("frontmatter_present", bool(fields), "frontmatter block present" if fields else "no frontmatter"),
    ]
    missing = [key for key in _SKILL_REQUIRED_FRONTMATTER if not str(fields.get(key, "") or "")]
    checks.append(
        _check(
            "required_frontmatter",
            not missing,
            "name, description, version, mcp_server present" if not missing else f"missing: {', '.join(missing)}",
        )
    )
    has_mcp_reference = "mcp" in body.lower()
    checks.append(
        _check(
            "mcp_reference_present",
            has_mcp_reference,
            "body mentions MCP"
            if has_mcp_reference
            else "body never mentions MCP; a Deepr skill export is expected to reference MCP consultation",
        )
    )
    return checks


def validate_export(path: Path) -> dict[str, Any]:
    """Validate one exported derived view; returns a form-only report."""
    artifact_class = _classify(path) if path.exists() else ARTIFACT_CLASS_UNKNOWN
    if not path.exists():
        checks = [_check("path_exists", False, str(path))]
    elif artifact_class == ARTIFACT_CLASS_HANDOFF:
        checks = _validate_handoff(path)
    elif artifact_class == ARTIFACT_CLASS_OKF:
        checks = _validate_okf_bundle(path)
    elif artifact_class == ARTIFACT_CLASS_SKILL:
        checks = _validate_skill_export(path)
    else:
        checks = [
            _check(
                "artifact_class",
                False,
                "unrecognized export; expected a handoff .json, an OKF bundle directory with index.md, or a SKILL.md",
            )
        ]

    failed = [c for c in checks if c["status"] == "fail"]
    return {
        "schema_version": EXPORT_VALIDATION_SCHEMA_VERSION,
        "kind": EXPORT_VALIDATION_KIND,
        "contract": _contract(),
        "artifact_class": artifact_class,
        "status": "valid" if not failed else "invalid",
        "check_count": len(checks),
        "failed_count": len(failed),
        "checks": checks,
    }


__all__ = [
    "ARTIFACT_CLASS_HANDOFF",
    "ARTIFACT_CLASS_OKF",
    "ARTIFACT_CLASS_SKILL",
    "ARTIFACT_CLASS_UNKNOWN",
    "EXPORT_VALIDATION_KIND",
    "EXPORT_VALIDATION_SCHEMA_VERSION",
    "validate_export",
]
