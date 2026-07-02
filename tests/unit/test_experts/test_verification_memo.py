"""Tests for memoized claim+source+window verification results."""

from __future__ import annotations

import json

from deepr.experts.verification_memo import (
    VERIFICATION_MEMO_SCHEMA_VERSION,
    VerificationMemoStore,
    replayable_verification_item,
    verification_memo_enabled,
    verification_memo_key,
)


def _packet(candidate_id: str = "cand-1", statement: str = "Compiler v2 shipped in June 2026.") -> dict:
    return {
        "candidate_id": candidate_id,
        "statement": statement,
        "claim_kind": "temporal_claim",
        "confidence": 0.86,
        "state_policy": {"requires_external_support": True},
        "model_judgment": {},
        "evidence": [{"note_id": "n1", "window_id": "w1", "excerpt": "Compiler released v2 in June 2026."}],
        "recall_context": {"candidate_count": 0, "candidates": []},
    }


def _item(candidate_id: str = "cand-1") -> dict:
    return {
        "candidate_id": candidate_id,
        "support_verdict": "supported",
        "contradiction_verdict": "none",
        "dedup_verdict": "new",
        "temporal_scope_verdict": "valid",
        "confidence": 0.91,
        "rationale": "The cited source window supports the claim.",
        "edge_decisions": [{"target_candidate_id": "cand-9", "edge_type": "supports"}],
    }


class TestMemoKey:
    def test_key_ignores_run_random_candidate_id(self):
        key_a = verification_memo_key(_packet("cand-1"), prompt_version="v1", provider="local", model="qwen")
        key_b = verification_memo_key(_packet("cand-77"), prompt_version="v1", provider="local", model="qwen")

        assert key_a == key_b

    def test_key_changes_with_statement_prompt_version_and_model(self):
        base = verification_memo_key(_packet(), prompt_version="v1", provider="local", model="qwen")

        assert base != verification_memo_key(
            _packet(statement="Compiler v3 shipped."), prompt_version="v1", provider="local", model="qwen"
        )
        assert base != verification_memo_key(_packet(), prompt_version="v2", provider="local", model="qwen")
        assert base != verification_memo_key(_packet(), prompt_version="v1", provider="local", model="llama")

    def test_key_changes_with_recall_context(self):
        base = verification_memo_key(_packet(), prompt_version="v1", provider="local", model="qwen")
        with_recall = _packet()
        with_recall["recall_context"] = {"candidate_count": 1, "candidates": [{"item_id": "b1", "text": "prior"}]}

        assert base != verification_memo_key(with_recall, prompt_version="v1", provider="local", model="qwen")


class TestReplayableItem:
    def test_edge_decisions_and_candidate_id_are_never_replayed(self):
        replayable = replayable_verification_item(_item())

        assert "edge_decisions" not in replayable
        assert "candidate_id" not in replayable
        assert replayable["support_verdict"] == "supported"
        assert replayable["dedup_verdict"] == "new"


class TestStore:
    def test_put_then_get_round_trips_replayable_fields(self, tmp_path):
        store = VerificationMemoStore(tmp_path / "memos.jsonl")
        key = verification_memo_key(_packet(), prompt_version="v1", provider="local", model="qwen")

        assert store.put(key, _item(), provider="local", model="qwen", prompt_version="v1", artifact_ref="a.json")
        hit = store.get(key)

        assert hit is not None
        assert hit["support_verdict"] == "supported"
        assert "edge_decisions" not in hit
        record = json.loads((tmp_path / "memos.jsonl").read_text(encoding="utf-8").strip())
        assert record["schema_version"] == VERIFICATION_MEMO_SCHEMA_VERSION
        assert record["artifact_ref"] == "a.json"

    def test_invalid_utf8_bytes_fail_open(self, tmp_path):
        path = tmp_path / "torn.jsonl"
        path.write_bytes(b'{"key": "k1", "item": {"support_verdict": "supported"}}\n\xff\xfe torn bytes')
        store = VerificationMemoStore(path)

        # The only contract is no exception: torn bytes must degrade to fresh
        # verification, never abort it. Whether earlier valid lines survive
        # depends on text-buffer chunking, so both outcomes are acceptable.
        first = store.get("k1")
        assert first is None or first == {"support_verdict": "supported"}
        assert store.get("definitely-missing") is None

    def test_missing_store_and_corrupt_lines_fail_open(self, tmp_path):
        missing = VerificationMemoStore(tmp_path / "absent.jsonl")
        assert missing.get("anything") is None

        path = tmp_path / "corrupt.jsonl"
        path.write_text('not json\n{"key": "k1", "item": {"support_verdict": "supported"}}\n', encoding="utf-8")
        store = VerificationMemoStore(path)

        assert store.get("k1") == {"support_verdict": "supported"}
        assert store.get("k2") is None

    def test_fresh_store_reflects_new_puts_without_reload(self, tmp_path):
        store = VerificationMemoStore(tmp_path / "memos.jsonl")
        assert store.get("k") is None
        key = verification_memo_key(_packet(), prompt_version="v1", provider="local", model="qwen")

        store.put(key, _item(), provider="local", model="qwen", prompt_version="v1")

        assert store.get(key) is not None


class TestEnableSwitch:
    def test_disabled_by_env_var(self, monkeypatch):
        monkeypatch.delenv("DEEPR_DISABLE_VERIFICATION_MEMO", raising=False)
        assert verification_memo_enabled() is True

        monkeypatch.setenv("DEEPR_DISABLE_VERIFICATION_MEMO", "1")
        assert verification_memo_enabled() is False
