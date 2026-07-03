"""Tests for bounded second-checker grounding escalation."""

from __future__ import annotations

import pytest

from deepr.experts.grounding_escalation import (
    GroundingDisposition,
    GroundingEscalator,
    choose_independent_vendor,
    combine_grounding_verdicts,
    is_weak_verdict,
)
from deepr.experts.maker_checker import CheckAssurance, CheckVerdict


def _verdict(supported, *, vendor="openai", assurance=CheckAssurance.CROSS_VENDOR, reason=""):
    return CheckVerdict(supported, assurance, vendor, reason)


class TestIsWeakVerdict:
    def test_clean_support_is_not_weak(self):
        assert is_weak_verdict(_verdict(True)) is False

    def test_refutation_is_weak(self):
        assert is_weak_verdict(_verdict(False)) is True

    def test_could_not_verify_after_a_real_check_is_weak(self):
        assert is_weak_verdict(_verdict(None, assurance=CheckAssurance.CROSS_VENDOR)) is True

    def test_no_checker_available_is_not_weak(self):
        # UNVERIFIED means no checker ran; escalating adds nothing.
        unverified = CheckVerdict(None, CheckAssurance.UNVERIFIED, None, "")
        assert is_weak_verdict(unverified) is False

    def test_high_risk_forces_escalation_even_on_support(self):
        assert is_weak_verdict(_verdict(True), high_risk=True) is True


class TestChooseIndependentVendor:
    def test_returns_third_vendor_distinct_from_maker_and_first_checker(self):
        assert choose_independent_vendor("openai", "xai", ["openai", "xai", "gemini"]) == "gemini"

    def test_order_is_the_tie_break(self):
        assert choose_independent_vendor("openai", "xai", ["gemini", "anthropic"]) == "gemini"

    def test_none_when_only_maker_and_first_checker_available(self):
        assert choose_independent_vendor("openai", "xai", ["openai", "xai"]) is None

    def test_none_on_empty_and_skips_blank_vendors(self):
        assert choose_independent_vendor("openai", "xai", []) is None
        assert choose_independent_vendor("openai", "xai", ["", "openai"]) is None


class TestCombineGroundingVerdicts:
    def test_both_support_clears(self):
        disposition, verdict = combine_grounding_verdicts(
            _verdict(True, vendor="openai"), _verdict(True, vendor="gemini")
        )
        assert disposition is GroundingDisposition.ESCALATED_CLEARED
        assert verdict.supported is True
        assert verdict.checker_vendor == "gemini"

    def test_both_refute_holds_with_two_vendor_reason(self):
        disposition, verdict = combine_grounding_verdicts(
            _verdict(False, vendor="openai"), _verdict(False, vendor="gemini")
        )
        assert disposition is GroundingDisposition.ESCALATED_HELD
        assert verdict.supported is False
        assert "openai" in verdict.reason and "gemini" in verdict.reason

    def test_disagreement_is_contested_and_conservative(self):
        disposition, verdict = combine_grounding_verdicts(
            _verdict(False, vendor="openai"), _verdict(True, vendor="gemini")
        )
        assert disposition is GroundingDisposition.ESCALATED_CONTESTED
        assert verdict.supported is None  # neither trusted nor hard-refuted

    def test_second_could_not_verify_is_contested(self):
        disposition, verdict = combine_grounding_verdicts(
            _verdict(False, vendor="openai"), _verdict(None, vendor="gemini")
        )
        assert disposition is GroundingDisposition.ESCALATED_CONTESTED
        assert verdict.supported is None


class _RecordingChecker:
    def __init__(self, supported, vendor):
        self.calls: list[tuple[str, str]] = []
        self._verdict = CheckVerdict(supported, CheckAssurance.CROSS_VENDOR, vendor, "")

    async def __call__(self, claim, evidence):
        self.calls.append((claim, evidence))
        return self._verdict


class TestGroundingEscalator:
    @pytest.mark.asyncio
    async def test_clean_verdict_never_builds_a_second_checker(self):
        built: list[str] = []

        def factory(vendor):
            built.append(vendor)
            return _RecordingChecker(True, vendor)

        escalator = GroundingEscalator("openai", ["openai", "xai", "gemini"], factory)
        result = await escalator.escalate("c", "e", _verdict(True, vendor="xai"))

        assert result.disposition is GroundingDisposition.NOT_ESCALATED
        assert result.second is None
        assert built == []  # cost bound: healthy claims pay for one check only

    @pytest.mark.asyncio
    async def test_weak_verdict_escalates_to_an_independent_vendor(self):
        second = _RecordingChecker(True, "gemini")
        escalator = GroundingEscalator("openai", ["openai", "xai", "gemini"], lambda vendor: second)

        result = await escalator.escalate("c", "e", _verdict(False, vendor="xai"))

        assert result.second_checker_vendor == "gemini"
        assert second.calls == [("c", "e")]
        assert result.disposition is GroundingDisposition.ESCALATED_CONTESTED  # refute then support

    @pytest.mark.asyncio
    async def test_double_refutation_holds(self):
        escalator = GroundingEscalator(
            "openai", ["openai", "xai", "gemini"], lambda vendor: _RecordingChecker(False, "gemini")
        )

        result = await escalator.escalate("c", "e", _verdict(False, vendor="xai"))

        assert result.disposition is GroundingDisposition.ESCALATED_HELD
        assert result.held is True
        assert result.verdict.supported is False

    @pytest.mark.asyncio
    async def test_no_independent_vendor_returns_first_verdict_unchanged(self):
        escalator = GroundingEscalator("openai", ["openai", "xai"], lambda vendor: _RecordingChecker(True, vendor))

        first = _verdict(False, vendor="xai")
        result = await escalator.escalate("c", "e", first)

        assert result.disposition is GroundingDisposition.NO_INDEPENDENT_VENDOR
        assert result.verdict is first

    @pytest.mark.asyncio
    async def test_gated_off_factory_returns_first_verdict_unchanged(self):
        first = _verdict(False, vendor="xai")
        escalator = GroundingEscalator("openai", ["openai", "xai", "gemini"], lambda vendor: None)

        result = await escalator.escalate("c", "e", first)

        assert result.disposition is GroundingDisposition.NO_INDEPENDENT_VENDOR
        assert result.verdict is first
