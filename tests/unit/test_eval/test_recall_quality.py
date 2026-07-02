"""Tests for the $0 recall-route quality eval."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from deepr.cli.main import cli
from deepr.evals.recall_quality import (
    RECALL_EVAL_REPORT_SCHEMA_VERSION,
    RecallEvalCase,
    load_recall_eval_cases,
    run_recall_quality_eval,
    write_recall_eval_report,
)
from deepr.experts.beliefs import Belief, BeliefStore


def _store(tmp_path) -> BeliefStore:
    return BeliefStore("Recall Eval Expert", storage_dir=tmp_path / "beliefs")


def _seeded_store(tmp_path) -> tuple[BeliefStore, Belief, Belief]:
    store = _store(tmp_path)
    power, _ = store.add_belief(
        Belief(
            claim="Power delivery constrains accelerator rack deployment.",
            confidence=0.84,
            domain="ai-infra",
        )
    )
    retention, _ = store.add_belief(
        Belief(
            claim="Audit retention affects governance workflows.",
            confidence=0.82,
            domain="governance",
        )
    )
    return store, power, retention


class TestLoadCases:
    def test_valid_cases_load_with_deduplicated_ids(self):
        cases = load_recall_eval_cases(
            [
                {
                    "case_id": "c1",
                    "query": "power constraints",
                    "relevant_belief_ids": ["b1", "b1", " b2 "],
                }
            ]
        )

        assert cases == [RecallEvalCase(case_id="c1", query="power constraints", relevant_belief_ids=("b1", "b2"))]

    @pytest.mark.parametrize(
        ("payload", "match"),
        [
            ([], "non-empty JSON array"),
            ([{"query": "q", "relevant_belief_ids": ["b"]}], "missing case_id"),
            ([{"case_id": "c1", "relevant_belief_ids": ["b"]}], "missing query"),
            ([{"case_id": "c1", "query": "q", "relevant_belief_ids": []}], "non-empty relevant_belief_ids"),
            ([{"case_id": "c1", "query": "q", "relevant_belief_ids": [None]}], "must all be strings"),
            ([{"case_id": "c1", "query": "q", "relevant_belief_ids": [123, "b"]}], "must all be strings"),
            (
                [
                    {"case_id": "c1", "query": "q", "relevant_belief_ids": ["b"]},
                    {"case_id": "c1", "query": "q2", "relevant_belief_ids": ["b"]},
                ],
                "duplicate case_id",
            ),
        ],
    )
    def test_invalid_cases_are_rejected(self, payload, match):
        with pytest.raises(ValueError, match=match):
            load_recall_eval_cases(payload)


class TestRunEval:
    async def test_lexical_only_report_records_skip_reason(self, tmp_path):
        store, power, _ = _seeded_store(tmp_path)
        cases = [RecallEvalCase("c1", "accelerator power deployment", (power.id,))]

        report = await run_recall_quality_eval(store, cases, expert_name="Recall Eval Expert")

        assert report["schema_version"] == RECALL_EVAL_REPORT_SCHEMA_VERSION
        assert report["contract"]["cost_usd"] == 0.0
        assert report["contract"]["semantic_verdict"] is False
        assert report["contract"]["relevance_labels"] == "operator_supplied"
        assert report["routes"]["lexical_router"]["hit_at_k"] == 1.0
        assert report["comparison"]["vector_route_evaluated"] is False
        assert "no query embeddings supplied" in report["comparison"]["skip_reason"]

    async def test_vector_route_wins_when_index_matches_labels(self, tmp_path):
        store, power, retention = _seeded_store(tmp_path)
        store.upsert_belief_embedding(power.id, [1.0, 0.0], model="nomic-embed-text")
        store.upsert_belief_embedding(retention.id, [0.0, 1.0], model="nomic-embed-text")
        # A query with no lexical token overlap: only the vector route can hit.
        cases = [RecallEvalCase("c1", "GPU cluster energy ceilings", (power.id,))]

        async def embed_queries(queries):
            assert queries == ["GPU cluster energy ceilings"]
            return [(0.99, 0.01)]

        report = await run_recall_quality_eval(
            store,
            cases,
            top_k=1,
            embedding_model="nomic-embed-text",
            embed_queries=embed_queries,
        )

        assert report["comparison"]["vector_route_evaluated"] is True
        assert report["routes"]["vector_similarity"]["hit_at_k"] == 1.0
        assert report["routes"]["lexical_router"]["hit_at_k"] == 0.0
        assert report["comparison"]["winners_by_metric"]["hit_at_k"] == "vector_similarity"
        assert report["cases"][0]["routes"]["vector_similarity"]["candidate_ids"] == [power.id]

    async def test_vector_route_skips_honestly_when_index_has_no_usable_vectors(self, tmp_path):
        store, power, _ = _seeded_store(tmp_path)
        cases = [RecallEvalCase("c1", "accelerator power deployment", (power.id,))]

        async def embed_queries(queries):
            return [(1.0, 0.0)]

        report = await run_recall_quality_eval(
            store,
            cases,
            embedding_model="never-indexed-model",
            embed_queries=embed_queries,
        )

        assert report["comparison"]["vector_route_evaluated"] is False
        assert "no usable belief vectors indexed" in report["comparison"]["skip_reason"]
        assert "never-indexed-model" in report["comparison"]["skip_reason"]
        assert "vector_similarity" not in report["routes"]
        assert report["index"]["current_vector_count"] == 0
        assert "path" not in report["index"]

    async def test_index_coverage_is_reported_alongside_vector_results(self, tmp_path):
        store, power, retention = _seeded_store(tmp_path)
        store.upsert_belief_embedding(power.id, [1.0, 0.0], model="nomic-embed-text")
        store.upsert_belief_embedding(retention.id, [0.0, 1.0], model="nomic-embed-text")
        cases = [RecallEvalCase("c1", "accelerator power deployment", (power.id,))]

        async def embed_queries(queries):
            return [(1.0, 0.0)]

        report = await run_recall_quality_eval(
            store,
            cases,
            embedding_model="nomic-embed-text",
            embed_queries=embed_queries,
        )

        assert report["comparison"]["vector_route_evaluated"] is True
        assert report["index"]["current_vector_count"] == 2
        assert report["index"]["embedding_model"] == "nomic-embed-text"
        assert "path" not in report["index"]

    async def test_precomputed_embeddings_require_full_case_coverage(self, tmp_path):
        store, power, _ = _seeded_store(tmp_path)
        cases = [RecallEvalCase("c1", "power", (power.id,))]

        with pytest.raises(ValueError, match="missing case id"):
            await run_recall_quality_eval(
                store,
                cases,
                embedding_model="nomic-embed-text",
                query_embeddings_by_case_id={"other": (1.0, 0.0)},
            )

    async def test_embedder_count_mismatch_is_rejected(self, tmp_path):
        store, power, _ = _seeded_store(tmp_path)
        cases = [RecallEvalCase("c1", "power", (power.id,))]

        async def embed_queries(queries):
            return []

        with pytest.raises(ValueError, match="returned 0 vector"):
            await run_recall_quality_eval(
                store,
                cases,
                embedding_model="nomic-embed-text",
                embed_queries=embed_queries,
            )

    async def test_report_saves_under_supplied_directory(self, tmp_path):
        store, power, _ = _seeded_store(tmp_path)
        cases = [RecallEvalCase("c1", "accelerator power deployment", (power.id,))]
        report = await run_recall_quality_eval(store, cases)

        path = write_recall_eval_report(report, output_dir=tmp_path / "benchmarks")

        assert path.exists()
        assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == RECALL_EVAL_REPORT_SCHEMA_VERSION


class TestEvalRecallCommand:
    def _write_cases(self, tmp_path, belief_id: str):
        cases_path = tmp_path / "cases.json"
        cases_path.write_text(
            json.dumps(
                [
                    {
                        "case_id": "c1",
                        "query": "accelerator power deployment",
                        "relevant_belief_ids": [belief_id],
                    }
                ]
            ),
            encoding="utf-8",
        )
        return cases_path

    def test_eval_recall_reports_lexical_route_json(self, tmp_path, monkeypatch):
        store, power, _ = _seeded_store(tmp_path)
        cases_path = self._write_cases(tmp_path, power.id)
        monkeypatch.setattr("deepr.experts.beliefs.BeliefStore", lambda name: store)
        monkeypatch.setattr(
            "deepr.experts.profile.ExpertStore",
            lambda: type("S", (), {"load": staticmethod(lambda name: object())})(),
        )

        result = CliRunner().invoke(
            cli,
            ["eval", "recall", "Recall Eval Expert", "--cases", str(cases_path), "--json"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["schema_version"] == RECALL_EVAL_REPORT_SCHEMA_VERSION
        assert payload["routes"]["lexical_router"]["hit_at_k"] == 1.0
        assert payload["comparison"]["vector_route_evaluated"] is False

    def test_eval_recall_json_save_keeps_stdout_one_json_document(self, tmp_path, monkeypatch):
        store, power, _ = _seeded_store(tmp_path)
        cases_path = self._write_cases(tmp_path, power.id)
        saved_dir = tmp_path / "benchmarks"
        monkeypatch.setattr("deepr.experts.beliefs.BeliefStore", lambda name: store)
        monkeypatch.setattr(
            "deepr.experts.profile.ExpertStore",
            lambda: type("S", (), {"load": staticmethod(lambda name: object())})(),
        )
        monkeypatch.setattr("deepr.evals.recall_quality.runtime_data_path", lambda kind: saved_dir)

        result = CliRunner().invoke(
            cli,
            ["eval", "recall", "Recall Eval Expert", "--cases", str(cases_path), "--json", "--save"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["saved_to"].endswith(".json")
        assert (saved_dir / Path(payload["saved_to"]).name).exists()

    def test_eval_recall_rejects_both_embedding_sources(self, tmp_path):
        cases_path = tmp_path / "cases.json"
        cases_path.write_text("[]", encoding="utf-8")
        vectors_path = tmp_path / "vectors.json"
        vectors_path.write_text("{}", encoding="utf-8")

        result = CliRunner().invoke(
            cli,
            [
                "eval",
                "recall",
                "Whoever",
                "--cases",
                str(cases_path),
                "--local-embedding-model",
                "nomic-embed-text",
                "--query-embeddings-json",
                str(vectors_path),
            ],
        )

        assert result.exit_code != 0
        assert "not both" in result.output

    def test_eval_recall_requires_model_label_for_precomputed_vectors(self, tmp_path):
        cases_path = tmp_path / "cases.json"
        cases_path.write_text("[]", encoding="utf-8")
        vectors_path = tmp_path / "vectors.json"
        vectors_path.write_text("{}", encoding="utf-8")

        result = CliRunner().invoke(
            cli,
            ["eval", "recall", "Whoever", "--cases", str(cases_path), "--query-embeddings-json", str(vectors_path)],
        )

        assert result.exit_code != 0
        assert "--embedding-model is required" in result.output
