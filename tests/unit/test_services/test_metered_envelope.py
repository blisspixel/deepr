"""Conservative paid chat envelope calculations."""

import pytest

from deepr.services.metered_envelope import (
    MeteredEnvelopeError,
    bounded_chat_envelope,
    bounded_embedding_envelope,
)


def test_envelope_cost_never_exceeds_budget() -> None:
    envelope = bounded_chat_envelope(
        provider="openai",
        model="gpt-5-mini",
        prompt_parts=("system", "x" * 10_000),
        budget_usd=0.02,
        maximum_output_tokens=1_200,
        minimum_output_tokens=128,
    )

    assert envelope.input_tokens >= 10_000
    assert 128 <= envelope.output_tokens <= 1_200
    assert envelope.cost_usd <= 0.02


def test_envelope_rejects_unknown_pricing() -> None:
    with pytest.raises(MeteredEnvelopeError, match="No trusted token pricing"):
        bounded_chat_envelope(
            provider="openai",
            model="unknown-paid-model",
            prompt_parts=("prompt",),
            budget_usd=1.0,
            maximum_output_tokens=100,
        )


def test_envelope_rejects_budget_below_prompt_and_minimum_output() -> None:
    with pytest.raises(MeteredEnvelopeError, match="cannot cover"):
        bounded_chat_envelope(
            provider="openai",
            model="gpt-5-mini",
            prompt_parts=("x" * 10_000,),
            budget_usd=0.000001,
            maximum_output_tokens=1_200,
            minimum_output_tokens=128,
        )


def test_chat_envelope_rejects_prompt_outside_registered_context_window() -> None:
    with pytest.raises(MeteredEnvelopeError, match="context window"):
        bounded_chat_envelope(
            provider="openai",
            model="gpt-5-mini",
            prompt_parts=("x" * 400_000,),
            budget_usd=1.0,
            maximum_output_tokens=100,
        )


def test_chat_envelope_rejects_provider_model_mismatch() -> None:
    with pytest.raises(MeteredEnvelopeError, match="registry assigns it to 'openai'"):
        bounded_chat_envelope(
            provider="xai",
            model="gpt-5-mini",
            prompt_parts=("prompt",),
            budget_usd=1.0,
            maximum_output_tokens=100,
        )


def test_chat_envelope_accepts_azure_openai_model_contract() -> None:
    envelope = bounded_chat_envelope(
        provider="azure",
        model="gpt-5-mini",
        prompt_parts=("prompt",),
        budget_usd=1.0,
        maximum_output_tokens=100,
    )

    assert envelope.output_tokens == 100


def test_embedding_envelope_uses_trusted_input_only_pricing() -> None:
    envelope = bounded_embedding_envelope(
        model="text-embedding-3-small",
        inputs=("bounded text",),
    )

    assert envelope.input_tokens == 20
    assert envelope.output_tokens == 0
    assert envelope.cost_usd == pytest.approx(20 * 0.02 / 1_000_000)


def test_embedding_envelope_rejects_unknown_pricing() -> None:
    with pytest.raises(MeteredEnvelopeError, match="No trusted input-only token pricing"):
        bounded_embedding_envelope(model="unknown-embedding", inputs=("text",))
