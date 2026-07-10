"""Tests for the $0 recall-route quality eval."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from deepr.cli.main import cli
from deepr.evals.recall_quality import (
    MIN_SCHEDULER_PREFERENCE_CASES,
    RECALL_EVAL_CASE_LIBRARY_SCHEMA_VERSION,
    RECALL_EVAL_REPORT_SCHEMA_VERSION,
    RECALL_LIBRARY_INVENTORY_KIND,
    RECALL_LIBRARY_INVENTORY_SCHEMA_VERSION,
    RECALL_LIBRARY_VALIDATION_PLAN_KIND,
    RECALL_LIBRARY_VALIDATION_PLAN_SCHEMA_VERSION,
    RecallEvalCase,
    _case_metrics,
    _paired_bootstrap_comparison,
    build_recall_eval_case,
    build_recall_library_inventory,
    build_recall_library_validation_plan,
    load_recall_eval_case_library,
    load_recall_eval_cases,
    merge_recall_eval_case_library,
    recall_eval_case_id,
    recall_eval_case_library_path,
    run_recall_quality_eval,
    write_recall_eval_report,
)
from deepr.evals.retrieval_metrics import RETRIEVAL_METRIC_CASE_FIELDS
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


def _scheduler_cases(
    belief_ids: tuple[str, ...] = ("b1", "b2", "b3"),
) -> list[RecallEvalCase]:
    return [
        RecallEvalCase(
            f"case-{index:02d}",
            f"opaque retrieval query {index:02d}",
            (belief_ids[index % len(belief_ids)],),
        )
        for index in range(MIN_SCHEDULER_PREFERENCE_CASES)
    ]


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


class TestRetrievalMetrics:
    def test_case_metrics_cover_ranking_recall_and_duplicate_candidates(self):
        metrics = _case_metrics(
            ["irrelevant", "b1", "b1", "b2"],
            ["b1", "b2", "b3"],
            top_k=4,
        )

        assert metrics == {
            "candidate_ids": ["irrelevant", "b1", "b1", "b2"],
            "hit_at_k": True,
            "reciprocal_rank": 0.5,
            "precision_at_k": 0.5,
            "recall_at_k": 0.666667,
            "average_precision_at_k": 0.333333,
            "ndcg_at_k": 0.498189,
            "relevant_retrieved": 2,
            "relevant_total": 3,
        }

    def test_case_metrics_treat_missing_result_positions_as_non_relevant(self):
        metrics = _case_metrics(["irrelevant"], ["relevant"], top_k=3)

        assert metrics["candidate_ids"] == ["irrelevant"]
        assert metrics["hit_at_k"] is False
        assert metrics["reciprocal_rank"] == 0.0
        assert metrics["precision_at_k"] == 0.0
        assert metrics["recall_at_k"] == 0.0
        assert metrics["average_precision_at_k"] == 0.0
        assert metrics["ndcg_at_k"] == 0.0

    def test_paired_bootstrap_is_deterministic_and_exposes_uncertainty(self):
        tied = {
            "hit_at_k": False,
            "reciprocal_rank": 0.0,
            "precision_at_k": 0.0,
            "recall_at_k": 0.0,
            "average_precision_at_k": 0.0,
            "ndcg_at_k": 0.0,
            "relevant_retrieved": 0,
        }
        improved = {
            **tied,
            "hit_at_k": True,
            "reciprocal_rank": 1.0,
            "precision_at_k": 1.0,
            "recall_at_k": 1.0,
            "average_precision_at_k": 1.0,
            "ndcg_at_k": 1.0,
            "relevant_retrieved": 1,
        }
        lexical = [dict(tied) for _ in range(MIN_SCHEDULER_PREFERENCE_CASES)]
        vector = [dict(tied) for _ in range(MIN_SCHEDULER_PREFERENCE_CASES)]
        vector[0] = improved

        first = _paired_bootstrap_comparison(lexical, vector)
        second = _paired_bootstrap_comparison(lexical, vector)

        assert first == second
        assert first["method"] == "paired_percentile_bootstrap"
        assert first["case_count"] == MIN_SCHEDULER_PREFERENCE_CASES
        assert first["resamples"] == 9_999
        assert first["confidence_level"] == 0.95
        hit_evidence = first["metrics"]["hit_at_k"]
        assert hit_evidence["mean_difference"] > 0.0
        assert hit_evidence["confidence_interval"]["lower"] == 0.0
        assert hit_evidence["vector_superiority_supported"] is False

    def test_paired_bootstrap_uses_published_precision_for_superiority(self):
        baseline = [{field: 0.0 for field in RETRIEVAL_METRIC_CASE_FIELDS.values()}]
        candidate = [{field: 0.0000004 for field in RETRIEVAL_METRIC_CASE_FIELDS.values()}]

        evidence = _paired_bootstrap_comparison(baseline, candidate)["metrics"]["hit_at_k"]

        assert evidence["confidence_interval"]["lower"] == 0.0
        assert evidence["vector_superiority_supported"] is False


class TestRunEval:
    async def test_lexical_only_report_records_skip_reason(self, tmp_path):
        store, power, _ = _seeded_store(tmp_path)
        cases = [RecallEvalCase("c1", "accelerator power deployment", (power.id,))]

        report = await run_recall_quality_eval(store, cases, expert_name="Recall Eval Expert")

        assert report["schema_version"] == RECALL_EVAL_REPORT_SCHEMA_VERSION
        assert report["contract"]["cost_usd"] == 0.0
        assert report["contract"]["semantic_verdict"] is False
        assert report["contract"]["relevance_labels"] == "operator_supplied"
        assert report["request"]["domain"] == ""
        assert report["request"]["min_score"] == 0.0
        assert report["routes"]["lexical_router"]["hit_at_k"] == 1.0
        assert report["comparison"]["vector_route_evaluated"] is False
        assert "no query embeddings supplied" in report["comparison"]["skip_reason"]

    async def test_report_binds_the_evaluated_retrieval_contract(self, tmp_path):
        store, power, _ = _seeded_store(tmp_path)
        cases = [RecallEvalCase("c1", "accelerator power deployment", (power.id,))]

        report = await run_recall_quality_eval(
            store,
            cases,
            top_k=3,
            domain="ai-infra",
            min_score=0.0,
        )

        expected = {"top_k": 3, "domain": "ai-infra", "min_score": 0.0}
        assert report["request"] == {
            "case_count": 1,
            **expected,
            "embedding_model": "",
        }
        assert report["scheduler_preference"]["retrieval_contract"] == expected
        assert report["routes"]["lexical_router"]["hit_at_k"] == 1.0

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
        assert report["scheduler_preference"]["eligible"] is False
        assert "insufficient_case_count" in report["scheduler_preference"]["reasons"]
        assert report["cases"][0]["routes"]["vector_similarity"]["candidate_ids"] == [power.id]

    async def test_scheduler_preference_requires_enough_vector_wins(self, tmp_path):
        store = _store(tmp_path)
        first, _ = store.add_belief(
            Belief(claim="Power delivery constrains accelerator racks.", confidence=0.84, domain="infra")
        )
        second, _ = store.add_belief(
            Belief(claim="Audit retention shapes governance workflows.", confidence=0.82, domain="governance")
        )
        third, _ = store.add_belief(
            Belief(claim="Cooling headroom limits dense cluster deployment.", confidence=0.83, domain="infra")
        )
        store.upsert_belief_embedding(first.id, [1.0, 0.0, 0.0], model="nomic-embed-text")
        store.upsert_belief_embedding(second.id, [0.0, 1.0, 0.0], model="nomic-embed-text")
        store.upsert_belief_embedding(third.id, [0.0, 0.0, 1.0], model="nomic-embed-text")
        beliefs = (first, second, third)
        cases = [
            RecallEvalCase(f"c{index}", f"opaque retrieval query {index}", (beliefs[index % 3].id,))
            for index in range(MIN_SCHEDULER_PREFERENCE_CASES)
        ]

        async def embed_queries(queries):
            assert queries == [case.query for case in cases]
            basis = ((0.99, 0.01, 0.0), (0.0, 0.99, 0.01), (0.01, 0.0, 0.99))
            return [basis[index % 3] for index in range(len(queries))]

        report = await run_recall_quality_eval(
            store,
            cases,
            top_k=1,
            embedding_model="nomic-embed-text",
            embed_queries=embed_queries,
        )

        preference = report["scheduler_preference"]
        assert preference["eligible"] is True
        assert preference["preferred_route"] == "vector_similarity"
        assert preference["fallback_route"] == "lexical_router"
        assert preference["evaluated_case_count"] == MIN_SCHEDULER_PREFERENCE_CASES
        assert preference["confidence_supported_metrics"] == preference["required_win_metrics"]
        assert preference["reasons"] == []

    async def test_scheduler_preference_rejects_inconclusive_point_estimate_win(self):
        class MostlyTiedStore:
            def recall_belief_candidates(self, query, *, query_embedding=None, **kwargs):
                index = int(query.rsplit(" ", maxsplit=1)[-1])
                if query_embedding is None and index == 0:
                    return []
                return [SimpleNamespace(item_id=f"belief-{index}")]

            def belief_embedding_stats(self, *, embedding_model):
                return {
                    "current_vector_count": MIN_SCHEDULER_PREFERENCE_CASES,
                    "missing_or_stale_count": 0,
                    "record_count": MIN_SCHEDULER_PREFERENCE_CASES,
                    "belief_count": MIN_SCHEDULER_PREFERENCE_CASES,
                    "state_digest": "a" * 64,
                }

        cases = [
            RecallEvalCase(f"c{index}", f"paired query {index}", (f"belief-{index}",))
            for index in range(MIN_SCHEDULER_PREFERENCE_CASES)
        ]

        async def embed_queries(queries):
            return [(1.0,) for _ in queries]

        report = await run_recall_quality_eval(
            MostlyTiedStore(),
            cases,
            top_k=1,
            embedding_model="nomic-embed-text",
            embed_queries=embed_queries,
        )

        preference = report["scheduler_preference"]
        assert all(
            preference["winners_by_metric"][metric] == "vector_similarity"
            for metric in preference["required_win_metrics"]
        )
        assert preference["eligible"] is False
        assert "vector_route_superiority_not_confident" in preference["reasons"]
        assert preference["confidence_supported_metrics"] == []

    async def test_scheduler_preference_rejects_incomplete_vector_coverage(self):
        class IncompleteIndexStore:
            def recall_belief_candidates(self, query, *, query_embedding=None, **kwargs):
                if query_embedding is None:
                    return []
                index = int(query.rsplit(" ", maxsplit=1)[-1])
                return [SimpleNamespace(item_id=f"belief-{index}")]

            def belief_embedding_stats(self, *, embedding_model):
                return {
                    "current_vector_count": MIN_SCHEDULER_PREFERENCE_CASES - 1,
                    "missing_or_stale_count": 1,
                    "record_count": MIN_SCHEDULER_PREFERENCE_CASES - 1,
                    "belief_count": MIN_SCHEDULER_PREFERENCE_CASES,
                    "state_digest": "b" * 64,
                }

        cases = [
            RecallEvalCase(f"c{index}", f"paired query {index}", (f"belief-{index}",))
            for index in range(MIN_SCHEDULER_PREFERENCE_CASES)
        ]

        async def embed_queries(queries):
            return [(1.0,) for _ in queries]

        report = await run_recall_quality_eval(
            IncompleteIndexStore(),
            cases,
            top_k=1,
            embedding_model="nomic-embed-text",
            embed_queries=embed_queries,
        )

        assert report["scheduler_preference"]["eligible"] is False
        assert "belief_vector_index_incomplete" in report["scheduler_preference"]["reasons"]

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
        assert report["scheduler_preference"]["eligible"] is False
        assert "vector_route_not_evaluated" in report["scheduler_preference"]["reasons"]
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


class TestRecallCaseLibrary:
    def test_case_library_merges_by_case_id_deterministically(self, tmp_path):
        first = [RecallEvalCase("b-case", "power limits", ("b1",)), RecallEvalCase("a-case", "retention", ("b2",))]
        meta = merge_recall_eval_case_library("Recall Eval Expert", first, output_dir=tmp_path / "cases")

        assert meta["schema_version"] == RECALL_EVAL_CASE_LIBRARY_SCHEMA_VERSION
        assert meta["case_count"] == 2
        assert meta["added_count"] == 2
        path = recall_eval_case_library_path("Recall Eval Expert", output_dir=tmp_path / "cases")
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["contract"]["writes_graph"] is False
        assert payload["contract"]["semantic_verdict"] is False
        assert [case["case_id"] for case in payload["cases"]] == ["a-case", "b-case"]

        updated = [RecallEvalCase("a-case", "audit retention", ("b2", "b3"))]
        update_meta = merge_recall_eval_case_library("Recall Eval Expert", updated, output_dir=tmp_path / "cases")

        assert update_meta["case_count"] == 2
        assert update_meta["added_count"] == 0
        assert update_meta["updated_count"] == 1
        loaded = load_recall_eval_case_library("Recall Eval Expert", output_dir=tmp_path / "cases")
        assert loaded == [
            RecallEvalCase("a-case", "audit retention", ("b2", "b3")),
            RecallEvalCase("b-case", "power limits", ("b1",)),
        ]

        before_noop = path.read_text(encoding="utf-8")
        noop_meta = merge_recall_eval_case_library("Recall Eval Expert", updated, output_dir=tmp_path / "cases")

        assert noop_meta["unchanged_count"] == 1
        assert path.read_text(encoding="utf-8") == before_noop

    def test_case_library_accepts_raw_array_for_migration(self, tmp_path):
        path = recall_eval_case_library_path("Recall Eval Expert", output_dir=tmp_path / "cases")
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps([{"case_id": "c1", "query": "power", "relevant_belief_ids": ["b1"]}]),
            encoding="utf-8",
        )

        loaded = load_recall_eval_case_library("Recall Eval Expert", output_dir=tmp_path / "cases")

        assert loaded == [RecallEvalCase("c1", "power", ("b1",))]

    def test_missing_case_library_reports_actionable_error(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="pass --cases first"):
            load_recall_eval_case_library("Recall Eval Expert", output_dir=tmp_path / "cases")

    def test_single_operator_case_id_is_deterministic(self):
        first = recall_eval_case_id("What context was missed?", ["b2", "b1"])
        second = recall_eval_case_id("  What context was missed?  ", ["b1", "b2"])

        assert first == second
        assert first.startswith("operator_")

        case = build_recall_eval_case(
            case_id=None,
            query="  What   context  was missed?  ",
            relevant_belief_ids=["b1", "b1", "b2"],
        )

        assert case.case_id == first
        assert case.query == "What context was missed?"
        assert case.relevant_belief_ids == ("b1", "b2")

    def test_case_library_inventory_lists_ready_and_blocked_libraries(self, tmp_path):
        root = tmp_path / "cases"
        merge_recall_eval_case_library(
            "Ready Expert",
            _scheduler_cases(),
            output_dir=root,
        )
        merge_recall_eval_case_library(
            "Needs Labels",
            [RecallEvalCase("c1", "power", ("b1",))],
            output_dir=root,
        )
        (root / "broken.json").write_text('{"schema_version":"wrong"}', encoding="utf-8")

        inventory = build_recall_library_inventory(output_dir=root)

        assert inventory["schema_version"] == RECALL_LIBRARY_INVENTORY_SCHEMA_VERSION
        assert inventory["kind"] == RECALL_LIBRARY_INVENTORY_KIND
        assert inventory["contract"]["runs_retrieval"] is False
        assert inventory["summary"]["library_count"] == 3
        assert inventory["summary"]["ready_for_scheduler_preference_eval_count"] == 1
        by_name = {record["expert"]["name"]: record for record in inventory["libraries"]}
        assert by_name["Ready Expert"]["ready_for_scheduler_preference_eval"] is True
        assert by_name["Needs Labels"]["ready_for_scheduler_preference_eval"] is False
        assert by_name["broken"]["status"] == "invalid"

    def test_case_library_validation_plan_lists_only_ready_commands(self, tmp_path):
        root = tmp_path / "cases"
        merge_recall_eval_case_library(
            "Ready Expert",
            _scheduler_cases(),
            output_dir=root,
        )
        merge_recall_eval_case_library(
            "Needs Labels",
            [RecallEvalCase("c1", "power", ("b1",))],
            output_dir=root,
        )

        plan = build_recall_library_validation_plan(
            output_dir=root,
            top_k=3,
            local_embedding_model="nomic-embed-text",
        )

        assert plan["schema_version"] == RECALL_LIBRARY_VALIDATION_PLAN_SCHEMA_VERSION
        assert plan["kind"] == RECALL_LIBRARY_VALIDATION_PLAN_KIND
        assert plan["contract"]["executes_commands"] is False
        assert plan["contract"]["runs_retrieval"] is False
        assert plan["summary"]["ready_for_operator_validation_count"] == 1
        by_name = {step["expert"]["name"]: step for step in plan["steps"]}
        assert by_name["Ready Expert"]["eval_command_argv"] == [
            "deepr",
            "eval",
            "recall",
            "Ready Expert",
            "--top-k",
            "3",
            "--save",
            "--local-embedding-model",
            "nomic-embed-text",
        ]
        assert by_name["Needs Labels"]["eval_command_argv"] == []
        assert "insufficient_case_count_for_scheduler_preference" in by_name["Needs Labels"]["blockers"]


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

    def test_eval_recall_libraries_json_outputs_inventory(self, tmp_path, monkeypatch):
        case_root = tmp_path / "case-library"
        merge_recall_eval_case_library(
            "Recall Eval Expert",
            _scheduler_cases(),
            output_dir=case_root / "benchmarks" / "recall_cases",
        )
        monkeypatch.setattr("deepr.evals.recall_quality.runtime_data_path", lambda *parts: case_root.joinpath(*parts))

        result = CliRunner().invoke(cli, ["eval", "recall-libraries", "--json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["schema_version"] == RECALL_LIBRARY_INVENTORY_SCHEMA_VERSION
        assert payload["summary"]["library_count"] == 1
        assert payload["libraries"][0]["expert"]["name"] == "Recall Eval Expert"
        assert payload["libraries"][0]["ready_for_scheduler_preference_eval"] is True

    def test_eval_recall_libraries_json_outputs_validation_plan(self, tmp_path, monkeypatch):
        case_root = tmp_path / "case-library"
        merge_recall_eval_case_library(
            "Recall Eval Expert",
            _scheduler_cases(),
            output_dir=case_root / "benchmarks" / "recall_cases",
        )
        monkeypatch.setattr("deepr.evals.recall_quality.runtime_data_path", lambda *parts: case_root.joinpath(*parts))

        result = CliRunner().invoke(
            cli,
            [
                "eval",
                "recall-libraries",
                "--validation-plan",
                "--local-embedding-model",
                "nomic-embed-text",
                "--top-k",
                "3",
                "--json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["schema_version"] == RECALL_LIBRARY_VALIDATION_PLAN_SCHEMA_VERSION
        assert payload["summary"]["ready_for_operator_validation_count"] == 1
        assert payload["steps"][0]["eval_command_argv"][-2:] == ["--local-embedding-model", "nomic-embed-text"]

    def test_eval_recall_libraries_rejects_model_without_validation_plan(self):
        result = CliRunner().invoke(
            cli,
            ["eval", "recall-libraries", "--local-embedding-model", "nomic-embed-text"],
        )

        assert result.exit_code != 0
        assert "--local-embedding-model only applies with --validation-plan" in result.output

    def test_eval_recall_records_cases_into_runtime_library(self, tmp_path, monkeypatch):
        store, power, _ = _seeded_store(tmp_path)
        cases_path = self._write_cases(tmp_path, power.id)
        case_root = tmp_path / "case-library"
        monkeypatch.setattr("deepr.experts.beliefs.BeliefStore", lambda name: store)
        monkeypatch.setattr(
            "deepr.experts.profile.ExpertStore",
            lambda: type("S", (), {"load": staticmethod(lambda name: object())})(),
        )
        monkeypatch.setattr("deepr.evals.recall_quality.runtime_data_path", lambda *parts: case_root.joinpath(*parts))

        result = CliRunner().invoke(
            cli,
            [
                "eval",
                "recall",
                "Recall Eval Expert",
                "--cases",
                str(cases_path),
                "--record-cases",
                "--json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["case_library"]["schema_version"] == RECALL_EVAL_CASE_LIBRARY_SCHEMA_VERSION
        assert payload["case_library"]["added_count"] == 1
        library_path = Path(payload["case_library"]["path"])
        assert library_path.exists()
        assert json.loads(library_path.read_text(encoding="utf-8"))["cases"][0]["case_id"] == "c1"

    def test_eval_recall_uses_accumulated_case_library_when_cases_are_omitted(self, tmp_path, monkeypatch):
        store, power, _ = _seeded_store(tmp_path)
        case_root = tmp_path / "case-library"
        merge_recall_eval_case_library(
            "Recall Eval Expert",
            [RecallEvalCase("c1", "accelerator power deployment", (power.id,))],
            output_dir=case_root / "benchmarks" / "recall_cases",
        )
        monkeypatch.setattr("deepr.experts.beliefs.BeliefStore", lambda name: store)
        monkeypatch.setattr(
            "deepr.experts.profile.ExpertStore",
            lambda: type("S", (), {"load": staticmethod(lambda name: object())})(),
        )
        monkeypatch.setattr("deepr.evals.recall_quality.runtime_data_path", lambda *parts: case_root.joinpath(*parts))

        result = CliRunner().invoke(cli, ["eval", "recall", "Recall Eval Expert", "--json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["request"]["case_count"] == 1
        assert payload["case_library"]["source"] == "accumulated_library"
        assert payload["routes"]["lexical_router"]["hit_at_k"] == 1.0
        assert payload["operator_validation"]["case_source"] == "accumulated_library"
        assert payload["operator_validation"]["eligible_for_explicit_sync_preference"] is False
        assert payload["operator_validation"]["default_routing_change_allowed"] is False
        assert "missing_embedding_model" in payload["operator_validation"]["blockers"]

    def test_eval_recall_marks_accumulated_library_report_ready_for_explicit_sync(self, tmp_path, monkeypatch):
        store = _store(tmp_path)
        first, _ = store.add_belief(
            Belief(claim="Power delivery constrains accelerator racks.", confidence=0.84, domain="infra")
        )
        second, _ = store.add_belief(
            Belief(claim="Audit retention shapes governance workflows.", confidence=0.82, domain="governance")
        )
        third, _ = store.add_belief(
            Belief(claim="Cooling headroom limits dense cluster deployment.", confidence=0.83, domain="infra")
        )
        store.upsert_belief_embedding(first.id, [1.0, 0.0, 0.0], model="nomic-embed-text")
        store.upsert_belief_embedding(second.id, [0.0, 1.0, 0.0], model="nomic-embed-text")
        store.upsert_belief_embedding(third.id, [0.0, 0.0, 1.0], model="nomic-embed-text")
        case_root = tmp_path / "case-library"
        cases = _scheduler_cases((first.id, second.id, third.id))
        merge_recall_eval_case_library(
            "Recall Eval Expert",
            cases,
            output_dir=case_root / "benchmarks" / "recall_cases",
        )
        vectors_path = tmp_path / "query-vectors.json"
        basis = ([0.99, 0.01, 0.0], [0.0, 0.99, 0.01], [0.01, 0.0, 0.99])
        vectors_path.write_text(
            json.dumps({case.case_id: basis[index % 3] for index, case in enumerate(cases)}),
            encoding="utf-8",
        )
        monkeypatch.setattr("deepr.experts.beliefs.BeliefStore", lambda name: store)
        monkeypatch.setattr(
            "deepr.experts.profile.ExpertStore",
            lambda: type("S", (), {"load": staticmethod(lambda name: object())})(),
        )
        monkeypatch.setattr("deepr.evals.recall_quality.runtime_data_path", lambda *parts: case_root.joinpath(*parts))

        result = CliRunner().invoke(
            cli,
            [
                "eval",
                "recall",
                "Recall Eval Expert",
                "--query-embeddings-json",
                str(vectors_path),
                "--embedding-model",
                "nomic-embed-text",
                "--json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        validation = payload["operator_validation"]
        assert payload["scheduler_preference"]["eligible"] is True
        assert validation["case_source"] == "accumulated_library"
        assert validation["eligible_for_explicit_sync_preference"] is True
        assert validation["sync_requires_explicit_report"] is True
        assert validation["default_routing_change_allowed"] is False
        assert validation["blockers"] == []

    def test_eval_recall_records_single_operator_case_into_runtime_library(self, tmp_path, monkeypatch):
        store, power, _ = _seeded_store(tmp_path)
        case_root = tmp_path / "case-library"
        monkeypatch.setattr("deepr.experts.beliefs.BeliefStore", lambda name: store)
        monkeypatch.setattr(
            "deepr.experts.profile.ExpertStore",
            lambda: type("S", (), {"load": staticmethod(lambda name: object())})(),
        )
        monkeypatch.setattr("deepr.evals.recall_quality.runtime_data_path", lambda *parts: case_root.joinpath(*parts))

        result = CliRunner().invoke(
            cli,
            [
                "eval",
                "recall",
                "Recall Eval Expert",
                "--case-id",
                "reviewed-consult-context",
                "--query",
                "accelerator power deployment",
                "--relevant-belief-id",
                power.id,
                "--record-cases",
                "--json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["cases"][0]["case_id"] == "reviewed-consult-context"
        assert payload["case_library"]["added_count"] == 1
        library_path = Path(payload["case_library"]["path"])
        library_payload = json.loads(library_path.read_text(encoding="utf-8"))
        assert library_payload["cases"] == [
            {
                "case_id": "reviewed-consult-context",
                "query": "accelerator power deployment",
                "relevant_belief_ids": [power.id],
            }
        ]

    def test_eval_recall_record_cases_requires_case_input(self, tmp_path):
        result = CliRunner().invoke(cli, ["eval", "recall", "Whoever", "--record-cases"])

        assert result.exit_code != 0
        assert "--record-cases requires --cases or --query with --relevant-belief-id" in result.output

    def test_eval_recall_rejects_partial_single_case_input(self, tmp_path):
        result = CliRunner().invoke(cli, ["eval", "recall", "Whoever", "--query", "What changed?"])

        assert result.exit_code != 0
        assert "--relevant-belief-id is required with --query" in result.output

    def test_eval_recall_rejects_cases_file_with_single_case_input(self, tmp_path):
        cases_path = tmp_path / "cases.json"
        cases_path.write_text("[]", encoding="utf-8")

        result = CliRunner().invoke(
            cli,
            ["eval", "recall", "Whoever", "--cases", str(cases_path), "--query", "What changed?"],
        )

        assert result.exit_code != 0
        assert "Use either --cases or --query/--relevant-belief-id" in result.output

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
