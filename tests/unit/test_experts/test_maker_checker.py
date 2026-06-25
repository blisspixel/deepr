"""Tests for the cross-vendor maker-checker core."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from deepr.experts.maker_checker import (
    CheckAssurance,
    CheckVerdict,
    build_disconfirm_messages,
    check_claim,
    choose_checker_vendor,
    make_grounding_checker,
    parse_verdict,
)


class _FakeClient:
    """OpenAI-shaped chat client returning a canned reply (or raising)."""

    def __init__(self, reply: str | None = None, error: Exception | None = None):
        self._reply = reply
        self._error = error
        self.calls: list[dict] = []

        async def _create(**kwargs):
            self.calls.append(kwargs)
            if self._error:
                raise self._error
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self._reply))])

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=_create))


class TestChooseCheckerVendor:
    def test_prefers_a_different_vendor(self):
        choice = choose_checker_vendor("openai", ["openai", "anthropic"])
        assert choice.vendor == "anthropic"
        assert choice.assurance is CheckAssurance.CROSS_VENDOR

    def test_order_controls_preference(self):
        choice = choose_checker_vendor("openai", ["xai", "anthropic"])
        assert choice.vendor == "xai"  # first different vendor wins

    def test_falls_back_to_same_vendor_fresh_context(self):
        choice = choose_checker_vendor("openai", ["openai"])
        assert choice.vendor == "openai"
        assert choice.assurance is CheckAssurance.SAME_VENDOR_FRESH_CONTEXT

    def test_unverified_when_no_vendor(self):
        choice = choose_checker_vendor("openai", [])
        assert choice.vendor is None
        assert choice.assurance is CheckAssurance.UNVERIFIED


class TestParseVerdict:
    @pytest.mark.parametrize(
        ("reply", "expected"),
        [
            ("SUPPORTED\nThe evidence states it directly.", True),
            ("UNSUPPORTED\nThe evidence never mentions the figure.", False),
            ("UNVERIFIABLE\nNot enough evidence.", None),
            ("supported", True),
            ("unsupported - the number is different", False),
            ("Maybe?", None),  # off-format -> could not verify, never a verdict
            ("", None),
        ],
    )
    def test_first_word_decides(self, reply, expected):
        supported, _reason = parse_verdict(reply)
        assert supported is expected

    def test_reason_is_captured_and_bounded(self):
        _supported, reason = parse_verdict("UNSUPPORTED\n" + "x" * 500)
        assert reason.startswith("x")
        assert len(reason) <= 200


class TestPrompt:
    def test_fresh_context_contains_only_claim_and_evidence(self):
        messages = build_disconfirm_messages("Topic X shipped in 2026", "Topic X shipped in 2026 per the release.")
        user = messages[1]["content"]
        assert "CLAIM:" in user and "EVIDENCE:" in user
        assert "Topic X shipped in 2026" in user
        # The disconfirm/entailment framing is in the system prompt.
        assert "entail" in messages[0]["content"].lower()

    def test_missing_evidence_is_marked(self):
        messages = build_disconfirm_messages("A claim", "")
        assert "(no evidence provided)" in messages[1]["content"]


class TestCheckClaim:
    async def test_supported_claim_passes(self):
        client = _FakeClient(reply="SUPPORTED\nDirectly stated.")
        verdict = await check_claim(
            "X",
            "X is stated.",
            client=client,
            checker_vendor="anthropic",
            assurance=CheckAssurance.CROSS_VENDOR,
            model="claude",
        )
        assert verdict.supported is True
        assert verdict.refuted is False
        assert verdict.assurance is CheckAssurance.CROSS_VENDOR
        assert verdict.checker_vendor == "anthropic"

    async def test_unsupported_claim_is_refuted(self):
        client = _FakeClient(reply="UNSUPPORTED\nThe evidence says $10, the claim says $30.")
        verdict = await check_claim(
            "Price is $30",
            "The price is $10.",
            client=client,
            checker_vendor="anthropic",
            assurance=CheckAssurance.CROSS_VENDOR,
            model="claude",
        )
        assert verdict.supported is False
        assert verdict.refuted is True

    async def test_no_client_is_unverified(self):
        verdict = await check_claim(
            "X", "E", client=None, checker_vendor=None, assurance=CheckAssurance.UNVERIFIED, model="m"
        )
        assert verdict.supported is None
        assert verdict.assurance is CheckAssurance.UNVERIFIED
        assert verdict.refuted is False

    async def test_model_failure_is_could_not_verify_not_a_refutation(self):
        client = _FakeClient(error=RuntimeError("provider down"))
        verdict = await check_claim(
            "X",
            "E",
            client=client,
            checker_vendor="xai",
            assurance=CheckAssurance.CROSS_VENDOR,
            model="grok",
        )
        assert verdict.supported is None  # could not verify
        assert verdict.refuted is False  # a failure is NOT a refutation
        assert verdict.checker_vendor == "xai"

    async def test_passes_model_and_fresh_context_prompt_to_client(self):
        client = _FakeClient(reply="SUPPORTED")
        await check_claim(
            "claim text",
            "evidence text",
            client=client,
            checker_vendor="anthropic",
            assurance=CheckAssurance.CROSS_VENDOR,
            model="claude-x",
        )
        call = client.calls[0]
        assert call["model"] == "claude-x"
        assert any("evidence text" in m["content"] for m in call["messages"])


async def test_make_grounding_checker_adapts_client_to_absorber_seam():
    client = _FakeClient(reply="SUPPORTED\nThe evidence states it.")
    checker = make_grounding_checker(
        client=client,
        checker_vendor="anthropic",
        assurance=CheckAssurance.CROSS_VENDOR,
        model="claude",
    )

    verdict = await checker("claim text", "evidence text")

    assert verdict.supported is True
    assert verdict.checker_vendor == "anthropic"
    assert client.calls[0]["model"] == "claude"


def test_verdict_to_dict_shape():
    v = CheckVerdict(False, CheckAssurance.CROSS_VENDOR, "anthropic", "mismatch")
    assert v.to_dict() == {
        "supported": False,
        "assurance": "cross_vendor",
        "checker_vendor": "anthropic",
        "reason": "mismatch",
    }
