"""Embedding input contracts and incompatible-index regression checks."""

from types import SimpleNamespace

import pytest

from deepr.backends.local import make_local_embedder
from deepr.experts.belief_vector_index import BeliefVectorIndex
from deepr.experts.semantic_model_gate import _mark_zero_dollar_client


def proof_for(model):
    async def get(url, timeout):
        if url.endswith("/api/status"):
            return {"cloud": {"disabled": True, "source": "config"}}
        return {
            "models": [
                {"name": model, "model": model, "size": 1000000, "digest": "a" * 64, "details": {"format": "gguf"}}
            ]
        }

    return get


@pytest.mark.asyncio
async def test_nomic_query_and_document_inputs_are_distinct():
    inputs = []

    async def create(**kwargs):
        inputs.append(kwargs["input"])
        return SimpleNamespace(data=[SimpleNamespace(index=0, embedding=[1.0, 2.0])])

    client = _mark_zero_dollar_client(
        SimpleNamespace(embeddings=SimpleNamespace(create=create)), capacity_source="local"
    )
    for role in ["query", "document"]:
        embed = make_local_embedder(
            "nomic-embed-text", client=client, profile="auto", role=role, get_json=proof_for("nomic-embed-text")
        )
        await embed(["same text"])
    assert inputs == [["search_query: same text"], ["search_document: same text"]]


def test_profile_change_requires_reembedding_and_changes_state_identity(tmp_path):
    index = BeliefVectorIndex(tmp_path / "vectors.json")
    belief = SimpleNamespace(id="one", claim="A retained statement", domain="test")
    index.upsert_belief(belief, [1.0, 2.0], model="nomic-embed-text")
    before = index.stats([belief], model="nomic-embed-text")
    assert index.missing_or_stale_ids([belief], model="nomic-embed-text", profile="nomic-v1") == ["one"]
    index.upsert_belief(belief, [1.0, 2.0], model="nomic-embed-text", profile="nomic-v1")
    after = index.stats([belief], model="nomic-embed-text", profile="nomic-v1")
    assert after["state_digest"] != before["state_digest"]
    assert index.vectors_for([belief], model="nomic-embed-text") == {}


def test_query_dimensions_cannot_mix_with_document_dimensions(tmp_path):
    index = BeliefVectorIndex(tmp_path / "vectors.json")
    belief = SimpleNamespace(id="one", claim="A retained statement")
    index.upsert_belief(belief, [1.0, 2.0], model="model")
    assert index.vectors_for([belief], model="model", dimensions=3) == {}


@pytest.mark.parametrize(
    ("model", "selected", "expected"),
    [
        ("nomic-embed-text:v1.5", "auto", "nomic-v1"),
        ("embeddinggemma-2:270m", "auto", "embeddinggemma-fact-checking-v1"),
        ("unrecognized-model", "auto", "none"),
        ("nomic-embed-text", "none", "none"),
    ],
)
def test_profile_selection_is_explicit_and_unknown_models_stay_raw(model, selected, expected):
    from deepr.backends.embedding_profiles import resolve_embedding_profile

    assert resolve_embedding_profile(model, selected).name == expected


@pytest.mark.parametrize("size", [128, 256, 512, 768])
def test_gemma_roles_and_dimensions_preserve_the_published_contract(size):
    import math

    from deepr.backends.embedding_profiles import resolve_embedding_profile

    spec = resolve_embedding_profile("embeddinggemma-2:270m", "auto", size)
    assert spec.prepare("claim", "query") == "task: fact checking | query: claim"
    assert spec.prepare("evidence", "document") == "title: none | text: evidence"
    vector = spec.vector([float(value + 1) for value in range(768)])
    assert len(vector) == size and math.hypot(*vector) == pytest.approx(1)
    assert vector[1] / vector[0] == pytest.approx(2)


@pytest.mark.parametrize("values", [[], [0.0, 0.0], [float("nan"), 1.0], [float("inf"), 1.0], [True, 1.0], [1e308] * 4])
def test_invalid_vectors_refuse_instead_of_yielding_a_rank(values):
    from deepr.backends.embedding_profiles import resolve_embedding_profile

    with pytest.raises(ValueError):
        resolve_embedding_profile("unknown").vector(values)


@pytest.mark.parametrize(
    ("model", "profile", "dims"),
    [
        ("unknown", "nomic-v1", None),
        ("nomic-embed-text", "auto", 0),
        ("embeddinggemma-2:270m", "auto", 300),
        ("embeddinggemma-2:270m", "auto", True),
    ],
)
def test_invalid_profiles_refuse_before_client_construction(model, profile, dims, monkeypatch):
    def never(*args, **kwargs):
        raise AssertionError("must not construct client")

    monkeypatch.setattr("deepr.backends.local.ollama_chat_client", never)
    with pytest.raises(ValueError):
        make_local_embedder(model, profile=profile, dimensions=dims)


@pytest.mark.asyncio
async def test_embedding_accounting_records_shape_failure_without_private_input():
    import json
    import os
    from pathlib import Path

    async def create(**kwargs):
        return SimpleNamespace(
            data=[SimpleNamespace(index=0, embedding=[1.0, 0.0]), SimpleNamespace(index=0, embedding=[1.0, 0.0])]
        )

    client = _mark_zero_dollar_client(
        SimpleNamespace(embeddings=SimpleNamespace(create=create)), capacity_source="local"
    )
    embed = make_local_embedder("nomic-embed-text", client=client, get_json=proof_for("nomic-embed-text"))
    with pytest.raises(ValueError, match="permutation"):
        await embed(["PRIVATE ONE", "PRIVATE TWO"])
    text = (Path(os.environ["DEEPR_COST_DATA_DIR"]) / "cost_ledger.jsonl").read_text()
    events = [json.loads(line) for line in text.splitlines()]
    assert [e["metadata"]["status"] for e in events] == ["requested", "dispatching", "failed"]
    assert all(e["metadata"]["kind"] == "embedding" and e["cost_usd"] == 0 for e in events)
    assert "PRIVATE" not in text


@pytest.mark.asyncio
async def test_cloud_refusal_and_ledger_failure_precede_embedding_dispatch(monkeypatch):
    from deepr.observability.cost_ledger import CostLedger
    from deepr.observability.local_attempts import LocalAttemptAccountingError

    calls = []

    async def create(**kwargs):
        calls.append(kwargs)
        raise AssertionError("must not dispatch")

    async def get(url, timeout):
        return {"cloud": {"disabled": False}}

    client = _mark_zero_dollar_client(
        SimpleNamespace(embeddings=SimpleNamespace(create=create)), capacity_source="local"
    )
    embed = make_local_embedder("nomic-embed-text", client=client, get_json=get)
    with pytest.raises(ValueError):
        await embed(["private"])

    def blocked(*args, **kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(CostLedger, "record_event", blocked)
    with pytest.raises(LocalAttemptAccountingError):
        await embed(["private"])
    assert calls == []


def test_unprofiled_legacy_vectors_are_raw_only(tmp_path):
    import json

    path = tmp_path / "vectors.json"
    index = BeliefVectorIndex(path)
    belief = SimpleNamespace(id="one", claim="Retained evidence")
    index.upsert_belief(belief, [1.0, 0.0], model="nomic-embed-text")
    data = json.loads(path.read_text())
    del data["records"]["one"]["profile"]
    path.write_text(json.dumps(data))
    loaded = BeliefVectorIndex(path)
    assert loaded.vectors_for([belief], model="nomic-embed-text") == {"one": (1.0, 0.0)}
    assert loaded.vectors_for([belief], model="nomic-embed-text", profile="nomic-v1") == {}


@pytest.mark.asyncio
async def test_profile_refresh_writes_only_derived_vectors(tmp_path):
    from deepr.experts.belief_embedding_refresh import refresh_missing_belief_embeddings
    from deepr.experts.beliefs import Belief, BeliefStore

    store = BeliefStore("Fixture", storage_dir=tmp_path / "beliefs")
    belief, _ = store.add_belief(Belief(claim="Unchanged canonical claim", confidence=0.5))
    store.upsert_belief_embedding(belief.id, [1.0, 0.0], model="nomic-embed-text")
    before = (store.storage_dir / "beliefs.json").read_bytes()

    async def embed(claims):
        return [(0.0, 1.0) for _ in claims]

    result = await refresh_missing_belief_embeddings(
        store, embed, model="nomic-embed-text", profile="nomic-v1", dimensions=2
    )
    assert result.indexed_count == 1
    assert (
        store.missing_belief_embedding_ids(
            embedding_model="nomic-embed-text", embedding_profile="nomic-v1", dimensions=2
        )
        == []
    )
    assert store.missing_belief_embedding_ids(embedding_model="nomic-embed-text") == [belief.id]
    assert (store.storage_dir / "beliefs.json").read_bytes() == before


def test_mixed_legacy_dimensions_cannot_qualify_complete_coverage(tmp_path):
    from deepr.experts.beliefs import Belief, BeliefStore

    store = BeliefStore("Fixture", storage_dir=tmp_path / "beliefs")
    first, _ = store.add_belief(Belief(claim="First retained document", confidence=0.5), dedup=False)
    second, _ = store.add_belief(Belief(claim="Second retained document", confidence=0.5), dedup=False)
    store.upsert_belief_embedding(first.id, [1.0, 0.0], model="model")
    store.upsert_belief_embedding(second.id, [1.0, 0.0, 0.0], model="model")
    stats = store.belief_embedding_stats(embedding_model="model")
    assert stats["dimensions"] == [2, 3]
    assert stats["current_vector_count"] == 0 and stats["missing_or_stale_count"] == 2
    assert set(store.missing_belief_embedding_ids(embedding_model="model")) == {first.id, second.id}


@pytest.mark.asyncio
async def test_mixed_batch_never_partially_replaces_an_index(tmp_path):
    from deepr.experts.belief_embedding_refresh import refresh_missing_belief_embeddings
    from deepr.experts.beliefs import Belief, BeliefStore

    store = BeliefStore("Fixture", storage_dir=tmp_path / "beliefs")
    for claim in ["First retained document", "Second retained document"]:
        store.add_belief(Belief(claim=claim, confidence=0.5), dedup=False)
    result = await refresh_missing_belief_embeddings(store, lambda texts: [[1.0, 0.0], [1.0, 0.0, 0.0]], model="model")
    assert result.status == "blocked" and result.indexed_count == 0
    assert not (store.storage_dir / "belief_vectors.json").exists()


def test_declared_dimensions_must_match_persisted_vector_bytes(tmp_path):
    import json

    path = tmp_path / "vectors.json"
    index = BeliefVectorIndex(path)
    belief = SimpleNamespace(id="one", claim="Retained document")
    index.upsert_belief(belief, [1.0, 0.0], model="model")
    data = json.loads(path.read_text())
    data["records"]["one"]["dimensions"] = 3
    path.write_text(json.dumps(data))
    loaded = BeliefVectorIndex(path)
    assert loaded.vectors_for([belief], model="model") == {}
    assert loaded.missing_or_stale_ids([belief], model="model", dimensions=2) == ["one"]
