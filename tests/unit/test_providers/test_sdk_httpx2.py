"""SDK major migration contracts through real clients and offline transports."""

import json

import httpx
import httpx2
import pytest
from anthropic import Anthropic
from openai import APIStatusError

from deepr.providers.anthropic_provider import AnthropicProvider
from deepr.providers.openai_provider import OpenAIProvider


@pytest.mark.asyncio
async def test_openai_major_serializes_responses_and_parses_usage_without_network():
    requests = []

    def reply(request):
        requests.append(request)
        return httpx2.Response(
            200,
            json={
                "id": "resp_offline",
                "object": "response",
                "created_at": 0,
                "model": "gpt-5.6-sol",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "id": "msg_offline",
                        "status": "completed",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "Reviewed answer", "annotations": []}],
                    }
                ],
                "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
            },
        )

    provider = OpenAIProvider(api_key="test-key")
    transport = provider.client._client
    await transport._transport.aclose()
    transport._transport = httpx2.MockTransport(reply)
    try:
        response = await provider.client.responses.create(
            model="gpt-5.6-sol",
            input=[{"role": "user", "content": "Question"}],
            max_output_tokens=100,
            tools=[],
        )
        assert response.output_text == "Reviewed answer"
        assert response.usage.input_tokens == 10
        assert response.usage.output_tokens == 2
        assert len(requests) == 1
        assert str(requests[0].url) == "https://api.openai.com/v1/responses"
        payload = json.loads(requests[0].content)
        assert payload["model"] == "gpt-5.6-sol"
        assert payload["max_output_tokens"] == 100
        assert payload["tools"] == []
        assert transport.trust_env is False
        assert transport.follow_redirects is False
        assert provider.client.max_retries == 0
    finally:
        await provider.client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [302, 429])
async def test_openai_major_does_not_follow_redirects_or_retry_error_responses(status):
    requests = []

    def reply(request):
        requests.append(request)
        return httpx2.Response(
            status,
            headers={"Location": "https://other.invalid/v1/responses", "Retry-After": "0"},
            json={"error": {"message": "offline failure", "type": "rate_limit_error"}},
        )

    provider = OpenAIProvider(api_key="test-key")
    transport = provider.client._client
    await transport._transport.aclose()
    transport._transport = httpx2.MockTransport(reply)
    try:
        with pytest.raises(APIStatusError) as failure:
            await provider.client.responses.create(model="gpt-5.6-sol", input="Question", max_output_tokens=100)
        assert failure.value.status_code == status
        assert len(requests) == 1
        assert requests[0].url.host == "api.openai.com"
    finally:
        await provider.client.close()


def test_anthropic_major_serializes_messages_and_preserves_cache_usage():
    requests = []

    def reply(request):
        requests.append(request)
        return httpx2.Response(
            200,
            json={
                "id": "msg_offline",
                "type": "message",
                "role": "assistant",
                "model": "claude-opus-5",
                "content": [{"type": "text", "text": "Reviewed answer"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 2,
                    "cache_creation_input_tokens": 4,
                    "cache_read_input_tokens": 5,
                },
            },
        )

    provider = AnthropicProvider(api_key="test-key")
    transport = provider.client._client
    transport._transport.close()
    transport._transport = httpx2.MockTransport(reply)
    try:
        response = provider.client.messages.create(
            model="claude-opus-5",
            max_tokens=100,
            messages=[{"role": "user", "content": "Question"}],
            thinking={"type": "adaptive"},
        )
        assert response.content[0].text == "Reviewed answer"
        assert response.usage.cache_creation_input_tokens == 4
        assert response.usage.cache_read_input_tokens == 5
        assert len(requests) == 1
        assert str(requests[0].url) == "https://api.anthropic.com/v1/messages"
        payload = json.loads(requests[0].content)
        assert payload["max_tokens"] == 100
        assert payload["thinking"] == {"type": "adaptive"}
        assert "temperature" not in payload
        assert transport.trust_env is False
        assert transport.follow_redirects is False
        assert provider.client.max_retries == 0
    finally:
        provider.client.close()


def test_anthropic_major_rejects_legacy_httpx_custom_client():
    with httpx.Client(trust_env=False, follow_redirects=False) as transport:
        with pytest.raises(TypeError, match="http_client"):
            Anthropic(api_key="test-key", http_client=transport)
