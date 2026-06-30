"""Tests for `deepr expert semantic-recall`."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from deepr.cli.commands.semantic.expert_semantic_recall import expert_refresh_semantic_recall, expert_semantic_recall
from deepr.cli.main import cli
from deepr.experts.beliefs import Belief, BeliefStore
from deepr.experts.profile import ExpertProfile


def _profile() -> ExpertProfile:
    return ExpertProfile(
        name="Recall CLI Expert",
        vector_store_id="vs-recall-cli",
        domain="ai infrastructure",
        knowledge_cutoff_date=datetime(2026, 6, 29, tzinfo=UTC),
    )


def _store(tmp_path) -> BeliefStore:
    return BeliefStore("Recall CLI Expert", storage_dir=tmp_path / "beliefs")


def _patch_dependencies(profile: ExpertProfile | None, store: BeliefStore):
    return (
        patch(
            "deepr.cli.commands.semantic.expert_semantic_recall.ExpertStore",
            return_value=MagicMock(load=MagicMock(return_value=profile)),
        ),
        patch("deepr.cli.commands.semantic.expert_semantic_recall.BeliefStore", return_value=store),
    )


def test_semantic_recall_registered_in_expert_help():
    result = CliRunner().invoke(cli, ["expert", "semantic-recall", "--help"])

    assert result.exit_code == 0
    assert "candidate beliefs" in result.output.lower()


def test_refresh_semantic_recall_registered_in_expert_help():
    result = CliRunner().invoke(cli, ["expert", "refresh-semantic-recall", "--help"])

    assert result.exit_code == 0
    assert "precomputed belief vectors" in result.output.lower()


def test_semantic_recall_json_output_is_read_only_contract(tmp_path):
    store = _store(tmp_path)
    belief, _ = store.add_belief(
        Belief(
            claim="Power delivery constrains accelerator rack deployment.",
            confidence=0.84,
            domain="ai-infra",
        )
    )

    profile_patch, belief_store_patch = _patch_dependencies(_profile(), store)
    with profile_patch as mock_profile_store, belief_store_patch as mock_belief_store:
        result = CliRunner().invoke(
            expert_semantic_recall,
            ["Recall CLI Expert", "accelerator power deployment", "--json"],
        )

    assert result.exit_code == 0, result.output
    mock_profile_store.assert_called_once()
    mock_belief_store.assert_called_once_with("Recall CLI Expert")
    payload = json.loads(result.output)
    assert payload["schema_version"] == "deepr-expert-semantic-recall-v1"
    assert payload["contract"]["cost_usd"] == 0.0
    assert payload["contract"]["writes_graph"] is False
    assert payload["contract"]["embedding_generation"] == "not_performed"
    assert payload["candidates"][0]["item_id"] == belief.id
    assert payload["candidates"][0]["verdict"] == "candidate_only"


def test_refresh_semantic_recall_indexes_precomputed_vectors(tmp_path):
    store = _store(tmp_path)
    first, _ = store.add_belief(
        Belief(
            claim="Power delivery constrains accelerator rack deployment.",
            confidence=0.84,
            domain="ai-infra",
        )
    )
    second, _ = store.add_belief(
        Belief(
            claim="Audit retention affects governance workflows.",
            confidence=0.82,
            domain="governance",
        )
    )
    vector_path = tmp_path / "belief-vectors.json"
    vector_path.write_text(json.dumps({first.id: [1.0, 0.0], second.id: [0.0, 1.0]}), encoding="utf-8")

    profile_patch, belief_store_patch = _patch_dependencies(_profile(), store)
    with profile_patch as mock_profile_store, belief_store_patch as mock_belief_store:
        result = CliRunner().invoke(
            expert_refresh_semantic_recall,
            [
                "Recall CLI Expert",
                "--embedding-model",
                "local-test",
                "--embeddings-json",
                str(vector_path),
                "--json",
            ],
        )

    assert result.exit_code == 0, result.output
    mock_profile_store.assert_called_once()
    mock_belief_store.assert_called_once_with("Recall CLI Expert")
    payload = json.loads(result.output)
    assert payload["schema_version"] == "deepr-expert-semantic-recall-refresh-v1"
    assert payload["contract"]["cost_usd"] == 0.0
    assert payload["contract"]["estimated_external_cost_usd"] == 0.0
    assert payload["contract"]["writes_graph"] is False
    assert payload["contract"]["writes_beliefs"] is False
    assert payload["contract"]["writes_belief_vectors"] is True
    assert payload["contract"]["embedding_generation"] == "not_performed_by_deepr"
    assert payload["summary"] == {
        "status": "indexed",
        "requested_count": 2,
        "indexed_count": 2,
        "skipped_count": 0,
    }
    assert store.missing_belief_embedding_ids(embedding_model="local-test") == []
    candidates = store.recall_belief_candidates(
        "power bottleneck",
        query_embedding=[0.99, 0.01],
        embedding_model="local-test",
        include_lexical_fallback=False,
    )
    assert candidates[0].item_id == first.id


def test_refresh_semantic_recall_rejects_missing_precomputed_vectors_without_writing(tmp_path):
    store = _store(tmp_path)
    belief, _ = store.add_belief(Belief(claim="A belief needs a vector.", confidence=0.8, domain="memory"))
    vector_path = tmp_path / "belief-vectors.json"
    vector_path.write_text(json.dumps({"other-belief": [1.0, 0.0]}), encoding="utf-8")

    profile_patch, belief_store_patch = _patch_dependencies(_profile(), store)
    with profile_patch, belief_store_patch:
        result = CliRunner().invoke(
            expert_refresh_semantic_recall,
            [
                "Recall CLI Expert",
                "--embedding-model",
                "local-test",
                "--embeddings-json",
                str(vector_path),
            ],
        )

    assert result.exit_code == 2
    assert belief.id in result.output
    assert store.missing_belief_embedding_ids(embedding_model="local-test") == [belief.id]


def test_refresh_semantic_recall_blocks_declared_cost_over_budget(tmp_path):
    store = _store(tmp_path)
    belief, _ = store.add_belief(Belief(claim="A metered vector needs a budget.", confidence=0.8, domain="memory"))
    vector_path = tmp_path / "belief-vectors.json"
    vector_path.write_text(json.dumps({belief.id: [1.0, 0.0]}), encoding="utf-8")

    profile_patch, belief_store_patch = _patch_dependencies(_profile(), store)
    with profile_patch, belief_store_patch:
        result = CliRunner().invoke(
            expert_refresh_semantic_recall,
            [
                "Recall CLI Expert",
                "--embedding-model",
                "metered-test",
                "--embeddings-json",
                str(vector_path),
                "--estimated-cost-per-belief",
                "0.01",
                "--budget",
                "0",
                "--json",
            ],
        )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["summary"]["status"] == "blocked"
    assert payload["contract"]["writes_belief_vectors"] is False
    assert "exceeds budget" in payload["refresh"]["blocked_reason"]
    assert store.missing_belief_embedding_ids(embedding_model="metered-test") == [belief.id]


def test_semantic_recall_vector_mode_requires_valid_embedding_model(tmp_path):
    store = _store(tmp_path)
    store.add_belief(Belief(claim="A belief exists.", confidence=0.8, domain="test"))

    profile_patch, belief_store_patch = _patch_dependencies(_profile(), store)
    with profile_patch, belief_store_patch:
        result = CliRunner().invoke(
            expert_semantic_recall,
            ["Recall CLI Expert", "belief", "--query-embedding", "[1.0]", "--json"],
        )

    assert result.exit_code == 2
    assert "embedding_model is required" in result.output


def test_semantic_recall_rejects_invalid_query_embedding(tmp_path):
    store = _store(tmp_path)

    profile_patch, belief_store_patch = _patch_dependencies(_profile(), store)
    with profile_patch, belief_store_patch:
        result = CliRunner().invoke(
            expert_semantic_recall,
            ["Recall CLI Expert", "belief", "--query-embedding", "[NaN]", "--embedding-model", "local-test"],
        )

    assert result.exit_code == 2
    assert "must be JSON" in result.output or "must be finite" in result.output
