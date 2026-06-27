"""Tests for `deepr expert memory-card`."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from deepr.cli.commands.semantic.expert_memory_card import expert_memory_card
from deepr.cli.main import cli
from deepr.core.contracts import Claim, ExpertManifest, Gap
from deepr.experts.profile import ExpertProfile


def _profile() -> ExpertProfile:
    profile = ExpertProfile(
        name="Memory Card Expert",
        vector_store_id="vs-memory-card",
        domain="agent memory",
        knowledge_cutoff_date=datetime(2026, 6, 26, tzinfo=UTC),
        last_knowledge_refresh=datetime(2026, 6, 26, tzinfo=UTC),
    )
    manifest = ExpertManifest(
        expert_name=profile.name,
        domain="agent memory",
        claims=[Claim.create("Experts need derived memory cards.", "agent memory", 0.88)],
        gaps=[Gap.create("wiki update review", questions=["What should regenerate the wiki?"], ev_cost_ratio=6.0)],
    )
    profile.get_manifest = lambda: manifest  # type: ignore[method-assign]
    return profile


def _patch_store(profile):
    return patch(
        "deepr.cli.commands.semantic.expert_memory_card.ExpertStore",
        return_value=MagicMock(load=MagicMock(return_value=profile)),
    )


def test_memory_card_registered_in_expert_help():
    result = CliRunner().invoke(cli, ["expert", "memory-card", "--help"])

    assert result.exit_code == 0
    assert "wiki-style expert.md" in result.output.lower()


def test_memory_card_json_output():
    with _patch_store(_profile()):
        result = CliRunner().invoke(expert_memory_card, ["Memory Card Expert", "--focus-limit", "1", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "deepr-expert-memory-card-v1"
    assert payload["kind"] == "deepr.expert.memory_card"
    assert payload["expert"]["name"] == "Memory Card Expert"
    assert payload["contract"]["cost_usd"] == 0.0
    assert len(payload["beliefs"]) == 1


def test_memory_card_markdown_output():
    with _patch_store(_profile()):
        result = CliRunner().invoke(expert_memory_card, ["Memory Card Expert", "--markdown"])

    assert result.exit_code == 0, result.output
    assert "# Memory Card Expert" in result.output
    assert "## Update Policy" in result.output


def test_memory_card_write_output_path(tmp_path):
    output_path = tmp_path / "EXPERT.md"

    with _patch_store(_profile()):
        result = CliRunner().invoke(
            expert_memory_card,
            ["Memory Card Expert", "--write", "--output", str(output_path), "--json"],
        )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["artifact"]["written_path"] == str(output_path)
    assert output_path.exists()


def test_memory_card_missing_expert_exits_nonzero():
    with _patch_store(None):
        result = CliRunner().invoke(expert_memory_card, ["Ghost Expert"])

    assert result.exit_code != 0
    assert "not found" in result.output.lower()
