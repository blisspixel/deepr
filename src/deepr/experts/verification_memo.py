"""Memoized claim+source+window verification results (ROADMAP item 7).

A verification decision is safe to reuse verbatim only when every input the
verifier judged against is byte-identical: the claim statement and policy, the
cited evidence excerpts, and the recall context in the prompt packet. The memo
key is therefore a hash of the rendered candidate packet (minus the run-random
candidate id) plus the prompt version and the verifier provider/model. Any
change in evidence, statement, policy, recall context, prompt, or model misses
the memo and re-dispatches the model.

Deterministic code owns the memo: exact-equality lookup, no similarity, no
lexical judgment. The model still owns all fresh semantic judgment. Reused
items drop ``edge_decisions`` because those reference other candidates from
the original prompt run and are only meaningful inside that run.

The store is an append-only JSONL cache; losing or disabling it only means
re-verification at the normal gated cost, so reads fail open.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepr.experts.semantic_model_gate import sha256_text, stable_json

logger = logging.getLogger(__name__)

VERIFICATION_MEMO_SCHEMA_VERSION = "deepr-verification-memo-v1"
DEFAULT_VERIFICATION_MEMO_FILENAME = "verification_memos.jsonl"
DISABLE_ENV_VAR = "DEEPR_DISABLE_VERIFICATION_MEMO"

# Fields the verifier returns per candidate that are safe to replay verbatim.
# edge_decisions are deliberately absent: they reference sibling candidates
# from the original prompt run.
_REPLAYABLE_ITEM_FIELDS = (
    "support_verdict",
    "contradiction_verdict",
    "dedup_verdict",
    "temporal_scope_verdict",
    "confidence",
    "rationale",
    "support_summary",
    "origin",
    "uncertainty",
    "expected_observations",
    "disconfirming_signals",
)


def verification_memo_enabled() -> bool:
    """Whether memo reuse is enabled (escape hatch: DEEPR_DISABLE_VERIFICATION_MEMO=1)."""
    return os.getenv(DISABLE_ENV_VAR, "").strip().lower() not in ("1", "true", "yes")


def verification_memo_key(
    packet: dict[str, Any],
    *,
    prompt_version: str,
    provider: str,
    model: str,
) -> str:
    """Hash the exact judgment inputs for one candidate packet.

    The candidate id is excluded because it is derived from the statement and
    source refs, which the key already covers; excluding it cannot produce a
    false hit because two packets with identical remaining fields carry
    identical judgment inputs.
    """
    keyed = {key: value for key, value in packet.items() if key != "candidate_id"}
    material = stable_json(
        {
            "packet": keyed,
            "prompt_version": prompt_version,
            "provider": provider,
            "model": model,
        }
    )
    return sha256_text(material)


def replayable_verification_item(item: dict[str, Any]) -> dict[str, Any]:
    """Reduce a verifier item to the fields that are safe to replay."""
    return {field: item[field] for field in _REPLAYABLE_ITEM_FIELDS if field in item}


class VerificationMemoStore:
    """Append-only JSONL store of replayable verification decisions."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._records: dict[str, dict[str, Any]] | None = None

    @classmethod
    def for_expert(cls, expert_name: str) -> VerificationMemoStore:
        from deepr.experts.paths import canonical_expert_dir

        return cls(canonical_expert_dir(expert_name) / "sync_artifacts" / DEFAULT_VERIFICATION_MEMO_FILENAME)

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._records is not None:
            return self._records
        records: dict[str, dict[str, Any]] = {}
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(record, dict):
                        continue
                    key = str(record.get("key", "") or "")
                    item = record.get("item")
                    if key and isinstance(item, dict):
                        records[key] = record
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as exc:
            # A cache that cannot be read must not block verification.
            # ValueError covers UnicodeDecodeError from torn or corrupt bytes.
            logger.warning("Verification memo store unreadable (%s); verifying fresh: %s", self.path, exc)
        self._records = records
        return records

    def get(self, key: str) -> dict[str, Any] | None:
        """Return the replayable item for a key, or None on miss."""
        record = self._load().get(key)
        if record is None:
            return None
        return replayable_verification_item(dict(record.get("item", {})))

    def put(
        self,
        key: str,
        item: dict[str, Any],
        *,
        provider: str,
        model: str,
        prompt_version: str,
        artifact_ref: str = "",
    ) -> bool:
        """Append one replayable decision; returns False when the write fails.

        Memo writes are best-effort: a failed append only costs a future
        re-verification, so it logs and returns rather than raising into the
        already-successful verification path.
        """
        record = {
            "schema_version": VERIFICATION_MEMO_SCHEMA_VERSION,
            "key": key,
            "item": replayable_verification_item(item),
            "provider": provider,
            "model": model,
            "prompt_version": prompt_version,
            "artifact_ref": artifact_ref,
            "recorded_at": datetime.now(UTC).isoformat(),
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=True) + "\n")
        except OSError as exc:
            logger.warning("Could not append verification memo (%s): %s", self.path, exc)
            return False
        if self._records is not None:
            self._records[key] = record
        return True


__all__ = [
    "DEFAULT_VERIFICATION_MEMO_FILENAME",
    "DISABLE_ENV_VAR",
    "VERIFICATION_MEMO_SCHEMA_VERSION",
    "VerificationMemoStore",
    "replayable_verification_item",
    "verification_memo_enabled",
    "verification_memo_key",
]
