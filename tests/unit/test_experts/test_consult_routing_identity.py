"""An optional ranking must use one attested embedding space across calls."""

import asyncio
from types import SimpleNamespace

import pytest

from deepr.experts import consult_routing as routing
from deepr.experts.semantic_model_gate import _mark_zero_dollar_client
from deepr.experts.study_contracts import StudyFinding


@pytest.fixture
def local_router(monkeypatch):
    state = SimpleNamespace(
        digests=iter(["a" * 64] * 20),
        calls=[],
        dimensions=iter([2] * 20),
        usage=None,
        clock=None,
        client_constructions=0,
    )

    async def get(url, timeout):
        if url.endswith("/api/status"):
            return {"cloud": {"disabled": True, "source": "config"}}
        if state.clock is not None:
            state.clock[0] += 1
        return {
            "models": [
                {
                    "name": "fixture:latest",
                    "model": "fixture:latest",
                    "size": 1000,
                    "digest": next(state.digests),
                    "details": {"format": "gguf"},
                }
            ]
        }

    async def create(**kwargs):
        state.calls.append(kwargs)
        if state.clock is not None:
            state.clock[0] += 2
        size = next(state.dimensions)
        return SimpleNamespace(
            data=[SimpleNamespace(index=i, embedding=[1.0] * size) for i in range(len(kwargs["input"]))],
            usage=state.usage,
        )

    client = _mark_zero_dollar_client(
        SimpleNamespace(embeddings=SimpleNamespace(create=create)), capacity_source="local"
    )

    def make_client(*args, **kwargs):
        state.client_constructions += 1
        return client

    monkeypatch.setattr("deepr.backends.local.ollama_chat_client", make_client)
    monkeypatch.setattr("deepr.experts.investigation.ollama_backend._get_json", get)
    state.router = routing.local_finding_router("fixture:latest")
    state.findings = [
        StudyFinding(lens="synopsis", axis="interrogation", kind="notes", title="evidence", finding_id="f1")
    ]
    return state


def test_tag_change_between_query_and_documents_refuses_before_second_dispatch(local_router):
    state = local_router
    state.digests = iter(["a" * 64, "b" * 64])
    ranking, note = asyncio.run(routing.route_findings(state.router, "question", state.findings))
    assert ranking is None
    assert "lexical overlap only" in note
    assert len(state.calls) == 1


def test_tag_change_between_attempts_does_not_repin_the_run(local_router):
    state = local_router
    state.digests = iter(["a" * 64, "a" * 64, "b" * 64, "b" * 64])
    assert asyncio.run(routing.route_findings(state.router, "question", state.findings))[0] == ["f1"]
    ranking, note = asyncio.run(routing.route_findings(state.router, "question", state.findings))
    assert ranking is None
    assert "lexical overlap only" in note
    assert len(state.calls) == 2


def test_receipts_bind_the_pinned_profile_dimensions_and_canonical_ledger(local_router):
    from deepr.observability.cost_ledger import CostLedger

    state = local_router
    state.usage = SimpleNamespace(prompt_tokens=7)
    ranking, note, receipt = asyncio.run(routing.route_findings_recorded(state.router, "question", state.findings))
    assert ranking == ["f1"] and "embedding similarity" in note
    assert receipt["status"] == "success"
    assert receipt["effective"] == receipt["configured"] == "lexical+local-embedding:fixture:latest"
    assert receipt["identity"] == {"model": "fixture:latest", "profile": "none", "digest": "a" * 64, "dimensions": 2}
    assert [call["role"] for call in receipt["calls"]] == ["query", "document"]
    events = CostLedger().get_events(source="local.native_ollama")
    for call in receipt["calls"]:
        matched = [e for e in events if e.metadata["attempt_id"] == call["attempt_id"]]
        assert [e.metadata["status"] for e in matched] == ["requested", "dispatching", "returned"]
        assert matched[-1].tokens_input == call["tokens_input"] == 7
        assert call["accounting"] == "recorded" and call["cost_usd"] == 0.0
        assert call["model_digest"] == "a" * 64 and call["dimensions"] == 2
        assert call["ledger_path"] == str(CostLedger().ledger_path.resolve())
    assert "question" not in str(receipt) and "evidence" not in str(receipt)


def test_digest_refusal_retains_both_calls_and_observed_identity(local_router):
    state = local_router
    state.digests = iter(["a" * 64, "b" * 64])
    ranking, _, receipt = asyncio.run(routing.route_findings_recorded(state.router, "question", state.findings))
    assert ranking is None and receipt["status"] == "fallback" and receipt["effective"] == "lexical"
    assert receipt["reason"] == "model_identity_changed"
    assert receipt["identity"]["digest"] == "a" * 64
    assert [c["status"] for c in receipt["calls"]] == ["returned", "refused"]
    assert [c["model_digest"] for c in receipt["calls"]] == ["a" * 64, "b" * 64]
    assert all(c["tokens_input"] is None for c in receipt["calls"])


def test_dimension_change_refuses_the_ranking_and_retains_the_failed_call(local_router):
    state = local_router
    state.dimensions = iter([2, 3])
    ranking, _, receipt = asyncio.run(routing.route_findings_recorded(state.router, "question", state.findings))
    assert ranking is None and receipt["status"] == "fallback"
    assert receipt["identity"]["dimensions"] == 2
    assert [call["status"] for call in receipt["calls"]] == ["returned", "failed"]
    assert receipt["calls"][1]["response_dimensions"] == [3]
    assert len(state.calls) == 2


def test_transport_failure_after_query_keeps_failed_work_with_unknown_usage(local_router, monkeypatch):
    state = local_router
    from deepr.backends import local

    real_factory = local.make_local_embedder

    def factory(*args, **kwargs):
        if kwargs["role"] == "document":

            async def broken(**request):
                state.calls.append(request)
                raise ConnectionError("private transport detail")

            sealed = _mark_zero_dollar_client(
                SimpleNamespace(embeddings=SimpleNamespace(create=broken)), capacity_source="local"
            )
            kwargs["client"] = sealed
        return real_factory(*args, **kwargs)

    monkeypatch.setattr(local, "make_local_embedder", factory)
    ranking, _, receipt = asyncio.run(routing.route_findings_recorded(state.router, "question", state.findings))
    assert ranking is None
    assert [c["status"] for c in receipt["calls"]] == ["returned", "failed"]
    assert all(c["accounting"] == "recorded" and c["tokens_input"] is None for c in receipt["calls"])
    assert "private transport detail" not in str(receipt)


def test_ledger_unavailability_is_visible_without_transport(local_router, monkeypatch):
    from deepr.observability.cost_ledger import CostLedger

    def blocked(*args, **kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(CostLedger, "record_event", blocked)
    state = local_router
    ranking, _, receipt = asyncio.run(routing.route_findings_recorded(state.router, "question", state.findings))
    assert ranking is None and receipt["status"] == "fallback"
    assert len(receipt["calls"]) == 1 and receipt["calls"][0]["accounting"] == "unsettled"
    assert receipt["calls"][0]["status"] == "refused"
    assert state.calls == []


def test_profile_mismatch_is_refused_before_dispatch(local_router):
    from deepr.backends.embedding_profiles import EmbeddingIdentity
    from deepr.backends.local import make_local_embedder

    with pytest.raises(ValueError, match="model/profile"):
        make_local_embedder("fixture:latest", identity=EmbeddingIdentity("fixture:latest", "nomic-v1"))
    assert local_router.calls == []


def test_diagnostic_accounts_for_routing_delay_fallback_and_actual_routes(local_router, monkeypatch, tmp_path):
    from deepr.evals import correction_survival as cs

    state = local_router
    state.clock = [0.0]
    state.digests = iter(["a" * 64, "a" * 64, "b" * 64])
    monkeypatch.setattr(cs.time, "perf_counter", lambda: state.clock[0])
    arm_packet = cs._arm_packet

    def assemble(*args, **kwargs):
        state.clock[0] += 1
        return arm_packet(*args, **kwargs)

    async def completion(prompt):
        state.clock[0] += 3
        return cs.MOCK_ANSWER

    monkeypatch.setattr(cs, "_arm_packet", assemble)
    run_dir = tmp_path / "timed-run"
    run = asyncio.run(
        cs.run_diagnostic(run_dir, cases=cs.CASES[:2], finding_router=state.router, completion=completion)
    )
    production = [a for a in run["attempts"] if a["arm"] == "production"]
    assert [a["finding_routing"]["status"] for a in production] == ["success", "fallback"]
    assert [a["answer_elapsed_ms"] for a in production] == [3000.0, 3000.0]
    assert [a["routing_elapsed_ms"] for a in production] == [6000.0, 1000.0]
    assert [a["total_elapsed_ms"] for a in production] == [10000.0, 5000.0]
    assert all(a["elapsed_ms"] == a["answer_elapsed_ms"] for a in run["attempts"])
    assert cs.load_run(run_dir)["attempts"] == run["attempts"]
    assert all(c["model_digest"] == "a" * 64 for c in production[0]["finding_routing"]["calls"])
    assert production[1]["finding_routing"]["identity"]["digest"] == "a" * 64
    assert production[1]["finding_routing"]["calls"][0]["model_digest"] == "b" * 64
    report = cs.build_report(run)
    stats = report["arms"]["production"]
    assert stats["answer_elapsed_ms"] == 6000.0
    assert stats["routing_elapsed_ms"] == 7000.0
    assert stats["total_elapsed_ms"] == 15000.0
    assert stats["routing"]["effective_counts"] == {"lexical+local-embedding:fixture:latest": 1, "lexical": 1}
    assert stats["routing"]["status_counts"] == {"success": 1, "fallback": 1}
    assert stats["routing"]["embedding_calls"] == stats["routing"]["embedding_usage_unknown_calls"] == 3
    assert stats["routing"]["unsettled_calls"] == 0
    for arm in ("oracle_packet", "fresh_sources"):
        assert report["arms"][arm]["routing"]["effective_counts"] == {"not_used_by_arm": 2}
        assert report["arms"][arm]["routing_elapsed_ms"] == 0
        assert report["arms"][arm]["total_elapsed_ms"] == 8000
    rendered = cs.render_report(report)
    assert "configured finding routing:" in rendered and "'fallback': 1" in rendered
    assert report["paid_calls"] == 0 and report["reviewed_obligations"] == 0
    fallback_prompt = (run_dir / "attempts" / production[1]["attempt_id"] / "prompt.json").read_text()
    assert "lexical overlap only" in fallback_prompt


def test_unused_router_makes_no_calls_and_does_not_claim_embedding_use(local_router):
    state = local_router
    ranking, _, receipt = asyncio.run(routing.route_findings_recorded(state.router, " ", state.findings))
    assert ranking == [] and receipt["status"] == "unused" and receipt["effective"] == "lexical"
    assert receipt["calls"] == [] and state.calls == []
    assert state.client_constructions == 0


def test_rankings_reuse_the_local_transport_client(local_router):
    state = local_router
    for _ in range(2):
        ranking, _ = asyncio.run(routing.route_findings(state.router, "question", state.findings))
        assert ranking == ["f1"]
    assert len(state.calls) == 4 and state.client_constructions == 1


def test_terminal_accounting_failure_cannot_be_reported_as_a_success(local_router, monkeypatch):
    from deepr.observability.cost_ledger import CostLedger

    record = CostLedger.record_event

    def fail_terminal(self, **kwargs):
        if kwargs["operation"] == "native_local_embedding_terminal":
            raise OSError("terminal receipt unavailable")
        return record(self, **kwargs)

    monkeypatch.setattr(CostLedger, "record_event", fail_terminal)
    state = local_router
    ranking, _, receipt = asyncio.run(routing.route_findings_recorded(state.router, "question", state.findings))
    assert ranking is None and receipt["status"] == "fallback"
    assert len(state.calls) == 1
    assert receipt["calls"][0]["status"] == "unsettled"
    assert receipt["calls"][0]["accounting"] == "unsettled"
    assert receipt["reason"] == "LocalAttemptAccountingError"


def test_embedding_cancellation_keeps_its_receipt_and_propagates(local_router, monkeypatch):
    from deepr.backends import local

    state = local_router

    async def cancelled(**kwargs):
        raise asyncio.CancelledError()

    client = _mark_zero_dollar_client(
        SimpleNamespace(embeddings=SimpleNamespace(create=cancelled)), capacity_source="local"
    )
    monkeypatch.setattr(local, "ollama_chat_client", lambda *a, **k: client)
    calls = []
    embed = local.make_local_embedder("fixture:latest", attempt_receipts=calls)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(embed(["question"]))
    assert calls[0]["status"] == "cancelled" and calls[0]["accounting"] == "recorded"
    assert state.calls == []
