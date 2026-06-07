"""Security regression tests for ExpertValidator input bounds.

The deepr_expert_validate MCP tool is advertised as a cheap "free" tool but
runs a paid LLM call. A caller controls ``model`` and ``max_evidence``; without
bounds, an off-allowlist flagship model or a huge evidence window amplifies
provider spend and third-party disclosure of expert knowledge. These tests pin
the clamping done in ExpertValidator itself (so CLI and MCP both benefit).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from deepr.services.expert_validator import (
    DEFAULT_VALIDATION_MODEL,
    MAX_CLAIM_CHARS,
    MAX_EVIDENCE_CAP,
    ExpertValidator,
    ExpertValidatorError,
)


def _validator(model: str = DEFAULT_VALIDATION_MODEL, max_evidence: int = 8) -> ExpertValidator:
    # Inject a mock client so no API key / openai package is required.
    return ExpertValidator(client=MagicMock(), model=model, max_evidence=max_evidence)


class TestMaxEvidenceClamp:
    def test_oversized_evidence_clamped(self):
        assert _validator(max_evidence=10_000).max_evidence == MAX_EVIDENCE_CAP

    def test_zero_or_negative_floored_to_one(self):
        assert _validator(max_evidence=0).max_evidence == 1
        assert _validator(max_evidence=-5).max_evidence == 1

    def test_in_range_value_preserved(self):
        assert _validator(max_evidence=12).max_evidence == 12

    def test_non_int_falls_back(self):
        assert _validator(max_evidence="lots").max_evidence == 8  # type: ignore[arg-type]


class TestModelAllowlist:
    def test_off_allowlist_model_rejected(self):
        # An expensive flagship override must fall back to the cheap default.
        assert _validator(model="o3-deep-research").model == DEFAULT_VALIDATION_MODEL
        assert _validator(model="gpt-5.2-pro").model == DEFAULT_VALIDATION_MODEL

    def test_allowlisted_override_preserved(self):
        assert _validator(model="gpt-4.1-mini").model == "gpt-4.1-mini"


class TestClaimLengthCap:
    @pytest.mark.asyncio
    async def test_overlong_claim_rejected(self):
        validator = _validator()
        with pytest.raises(ExpertValidatorError):
            await validator.validate(MagicMock(), "x" * (MAX_CLAIM_CHARS + 1))

    @pytest.mark.asyncio
    async def test_empty_claim_rejected(self):
        validator = _validator()
        with pytest.raises(ExpertValidatorError):
            await validator.validate(MagicMock(), "   ")
