"""Pinned Agent Skills hard-form conformance tests."""

from __future__ import annotations

from pathlib import Path

from deepr.skills.contract import validate_agent_skill


def _write_skill(tmp_path: Path, name: str, frontmatter: str, body: str = "Use the Deepr MCP server.\n") -> Path:
    directory = tmp_path / name
    directory.mkdir()
    path = directory / "SKILL.md"
    path.write_text(f"---\n{frontmatter}\n---\n\n{body}", encoding="utf-8")
    return path


def test_repository_skill_matches_pinned_contract() -> None:
    result = validate_agent_skill(Path("skills/deepr-research/SKILL.md"))

    assert result.valid, result.violations
    assert result.fields["metadata"]["deepr-version"] == "2.50.2"
    assert result.fields["metadata"]["deepr-mcp-server"] == "deepr"


def test_generated_skill_matches_pinned_contract(tmp_path: Path) -> None:
    from deepr.skills.expert_skill import build_expert_skill

    directory = tmp_path / "deepr-expert-ai-strategy-expert"
    path = build_expert_skill("AI Strategy Expert").generate(directory)

    result = validate_agent_skill(path)
    assert result.valid, result.violations


def test_unknown_top_level_extension_is_rejected(tmp_path: Path) -> None:
    path = _write_skill(tmp_path, "research", "name: research\ndescription: Research tasks.\nversion: 1")

    result = validate_agent_skill(path)

    assert not result.valid
    assert {item.code for item in result.violations} == {"unknown_fields"}


def test_metadata_must_map_strings_to_strings(tmp_path: Path) -> None:
    path = _write_skill(
        tmp_path,
        "research",
        "name: research\ndescription: Research tasks.\nmetadata:\n  deepr-version: 2.49",
    )

    result = validate_agent_skill(path)

    assert not result.valid
    assert "invalid_metadata" in {item.code for item in result.violations}


def test_description_must_contain_non_whitespace_text(tmp_path: Path) -> None:
    path = _write_skill(tmp_path, "research", 'name: research\ndescription: "   "')

    result = validate_agent_skill(path)

    assert not result.valid
    assert "invalid_description" in {item.code for item in result.violations}


def test_name_constraints_and_directory_identity_are_enforced(tmp_path: Path) -> None:
    path = _write_skill(tmp_path, "different", "name: research--worker\ndescription: Research tasks.")

    result = validate_agent_skill(path)
    codes = {item.code for item in result.violations}

    assert codes == {"invalid_name", "directory_name_mismatch"}


def test_optional_fields_keep_declared_types_and_limits(tmp_path: Path) -> None:
    path = _write_skill(
        tmp_path,
        "research",
        "name: research\ndescription: Research tasks.\nlicense: Apache-2.0\n"
        "compatibility: Requires Python 3.12 and a local Deepr MCP server.\n"
        "allowed-tools: deepr_status deepr_list_experts",
    )

    assert validate_agent_skill(path).valid
