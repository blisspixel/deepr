"""Unit tests for ExpertValidator (expert-as-guardrail mode).

The validator is a side-effect-free service that asks an LLM to assess a
claim against an expert's accumulated knowledge and returns a structured
PASS / WARN / FAIL verdict with citations and confidence.

These tests inject a fake AsyncOpenAI-shaped client so no network call is
made and no API key is required. The fake client lets us assert on:

- The JSON contract the prompt asks for (verdict shape, claim id round-
  tripping into the result, caveats preservation).
- Defensive parsing (invalid verdict, non-JSON body, ill-formed
  confidence) maps to a clean ExpertValidatorError.
- The validator never mutates the expert profile.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from deepr.core.contracts import Claim, ExpertManifest, Source, TrustClass
from deepr.services.expert_validator import (
    DEFAULT_VALIDATION_MODEL,
    ExpertValidator,
    ExpertValidatorError,
    ValidationResult,
)


@dataclass
class _StubExpert:
    """Minimal stand-in for ExpertProfile, exposing only what the
    validator touches: ``name``, ``domain``, and ``get_manifest()``."""

    name: str
    domain: str
    manifest: ExpertManifest

    def get_manifest(self) -> ExpertManifest:
        return self.manifest


def _make_claim(stmt: str, conf: float, claim_id: str | None = None) -> Claim:
    """Helper: build a Claim with a deterministic id for round-tripping."""
    sources = [Source.create(title="ref1", trust_class=TrustClass.TERTIARY)]
    if claim_id is None:
        return Claim.create(statement=stmt, domain="testing", confidence=conf, sources=sources)
    return Claim(
        id=claim_id,
        statement=stmt,
        domain="testing",
        confidence=conf,
        sources=sources,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _make_expert(claims: list[Claim] | None = None, gaps: list | None = None) -> _StubExpert:
    manifest = ExpertManifest(
        expert_name="Test Expert",
        domain="testing",
        claims=claims or [],
        gaps=gaps or [],
        decisions=[],
        policies={},
    )
    return _StubExpert(name="Test Expert", domain="testing", manifest=manifest)


def _fake_client_returning(body: Any) -> Any:
    """Build a fake AsyncOpenAI-shaped client whose chat.completions.create
    returns an object with ``choices[0].message.content == body``."""
    if not isinstance(body, str):
        body = json.dumps(body)

    response = type(
        "Resp",
        (),
        {
            "choices": [
                type(
                    "Choice",
                    (),
                    {"message": type("Msg", (), {"content": body})()},
                )()
            ]
        },
    )()

    client = type("Client", (), {})()
    client.chat = type("Chat", (), {})()
    client.chat.completions = type("Completions", (), {})()
    client.chat.completions.create = AsyncMock(return_value=response)
    return client


class TestValidationResultShape:
    def test_to_dict_round_trip(self):
        result = ValidationResult(
            expert_name="x",
            claim="y",
            verdict="pass",
            confidence=0.83,
            reasoning="reason",
            supporting=[_make_claim("a", 0.9, claim_id="aaa")],
            contradicting=[],
            caveats=["caveat"],
            model="m",
        )
        d = result.to_dict()
        assert d["verdict"] == "pass"
        assert d["confidence"] == 0.83
        assert d["claim"] == "y"
        assert d["caveats"] == ["caveat"]
        assert len(d["supporting"]) == 1
        assert d["supporting"][0]["id"] == "aaa"


class TestValidate:
    @pytest.mark.asyncio
    async def test_pass_verdict_roundtrips_supporting_claims(self):
        c1 = _make_claim("Python is dynamically typed", 0.95, claim_id="c1")
        c2 = _make_claim("Rust enforces ownership at compile time", 0.95, claim_id="c2")
        expert = _make_expert(claims=[c1, c2])

        client = _fake_client_returning(
            {
                "verdict": "pass",
                "confidence": 0.9,
                "reasoning": "Aligns with c1.",
                "supporting_claim_ids": ["c1"],
                "contradicting_claim_ids": [],
                "caveats": [],
            }
        )
        validator = ExpertValidator(client=client)
        result = await validator.validate(expert, "Python uses dynamic typing")

        assert result.verdict == "pass"
        assert result.confidence == pytest.approx(0.9)
        assert len(result.supporting) == 1
        assert result.supporting[0].id == "c1"
        assert result.contradicting == []
        assert result.model == DEFAULT_VALIDATION_MODEL

    @pytest.mark.asyncio
    async def test_fail_verdict_with_contradiction(self):
        c1 = _make_claim("Rust is memory-safe without GC", 0.95, claim_id="c1")
        expert = _make_expert(claims=[c1])

        client = _fake_client_returning(
            {
                "verdict": "fail",
                "confidence": 0.85,
                "reasoning": "Contradicts c1.",
                "supporting_claim_ids": [],
                "contradicting_claim_ids": ["c1"],
                "caveats": [],
            }
        )
        validator = ExpertValidator(client=client)
        result = await validator.validate(expert, "Rust needs a garbage collector")

        assert result.verdict == "fail"
        assert len(result.contradicting) == 1
        assert result.contradicting[0].id == "c1"

    @pytest.mark.asyncio
    async def test_warn_keeps_caveats(self):
        expert = _make_expert(claims=[])
        client = _fake_client_returning(
            {
                "verdict": "warn",
                "confidence": 0.4,
                "reasoning": "Insufficient evidence.",
                "supporting_claim_ids": [],
                "contradicting_claim_ids": [],
                "caveats": [
                    "Expert has no beliefs about this domain.",
                    "Recommend a research run before acting.",
                ],
            }
        )
        validator = ExpertValidator(client=client)
        result = await validator.validate(expert, "anything")
        assert result.verdict == "warn"
        assert len(result.caveats) == 2
        assert "research run" in result.caveats[1]

    @pytest.mark.asyncio
    async def test_unknown_claim_id_is_dropped(self):
        """If the model hallucinates a claim id that isn't in the evidence
        block, it must NOT appear in the result - citation provenance has
        to be ground-truth."""
        c1 = _make_claim("Real claim", 0.9, claim_id="real")
        expert = _make_expert(claims=[c1])

        client = _fake_client_returning(
            {
                "verdict": "pass",
                "confidence": 0.7,
                "reasoning": "Looks fine.",
                "supporting_claim_ids": ["real", "made_up_id_999"],
                "contradicting_claim_ids": [],
                "caveats": [],
            }
        )
        validator = ExpertValidator(client=client)
        result = await validator.validate(expert, "Something")
        assert {c.id for c in result.supporting} == {"real"}

    @pytest.mark.asyncio
    async def test_empty_claim_rejected(self):
        validator = ExpertValidator(client=_fake_client_returning({}))
        with pytest.raises(ExpertValidatorError, match="non-empty"):
            await validator.validate(_make_expert(), "   ")

    @pytest.mark.asyncio
    async def test_invalid_verdict_raises(self):
        client = _fake_client_returning(
            {
                "verdict": "maybe",  # not allowed
                "confidence": 0.5,
                "reasoning": "?",
                "supporting_claim_ids": [],
                "contradicting_claim_ids": [],
                "caveats": [],
            }
        )
        validator = ExpertValidator(client=client)
        with pytest.raises(ExpertValidatorError, match="invalid verdict"):
            await validator.validate(_make_expert(), "ok")

    @pytest.mark.asyncio
    async def test_non_json_response_raises(self):
        client = _fake_client_returning("this is not json")
        validator = ExpertValidator(client=client)
        with pytest.raises(ExpertValidatorError, match="non-JSON"):
            await validator.validate(_make_expert(), "ok")

    @pytest.mark.asyncio
    async def test_confidence_clamped_to_unit_interval(self):
        client = _fake_client_returning(
            {
                "verdict": "pass",
                "confidence": 2.5,  # out of range
                "reasoning": "?",
                "supporting_claim_ids": [],
                "contradicting_claim_ids": [],
                "caveats": [],
            }
        )
        result = await ExpertValidator(client=client).validate(_make_expert(), "x")
        assert 0.0 <= result.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_max_evidence_bounds_prompt(self):
        """If the expert has 100 claims and max_evidence=2, only the 2
        highest-confidence claims should appear in the evidence block and
        be eligible for citation."""
        many = [_make_claim(f"claim {i}", 0.5 + i / 200.0, claim_id=f"c{i}") for i in range(100)]
        expert = _make_expert(claims=many)
        client = _fake_client_returning(
            {
                "verdict": "pass",
                "confidence": 0.6,
                "reasoning": "ok",
                "supporting_claim_ids": ["c0", "c50", "c99"],
                "contradicting_claim_ids": [],
                "caveats": [],
            }
        )
        validator = ExpertValidator(client=client, max_evidence=2)
        result = await validator.validate(expert, "x")
        # c99 has the highest confidence (0.5 + 99/200), c98 next.
        assert {c.id for c in result.supporting} == {"c99"}

    @pytest.mark.asyncio
    async def test_validator_does_not_mutate_expert(self):
        c1 = _make_claim("c1 statement", 0.9, claim_id="c1")
        expert = _make_expert(claims=[c1])
        before_claims = list(expert.get_manifest().claims)
        client = _fake_client_returning(
            {
                "verdict": "pass",
                "confidence": 0.9,
                "reasoning": "ok",
                "supporting_claim_ids": ["c1"],
                "contradicting_claim_ids": [],
                "caveats": [],
            }
        )
        await ExpertValidator(client=client).validate(expert, "Something")
        after_claims = list(expert.get_manifest().claims)
        assert [c.id for c in before_claims] == [c.id for c in after_claims]
