"""Comprehensive provider validation tests for all supported providers.

Tests all providers (OpenAI, Gemini, Grok, Azure) with:
- Basic query execution
- Cost tracking
- Error handling
- Response format validation
- Tool usage (web search, code interpreter)

Note: These tests require API keys and will make real API calls.
They are designed to be cheap (simple queries) but will incur small costs.
"""

import asyncio
import os

import pytest
from dotenv import load_dotenv

load_dotenv()

from deepr.providers.azure_provider import AzureProvider
from deepr.providers.base import ResearchRequest, ToolConfig
from deepr.providers.gemini_provider import GeminiProvider
from deepr.providers.grok_provider import GrokProvider
from deepr.providers.openai_provider import OpenAIProvider


# Helper function to validate response structure
def validate_research_response(response, provider_name):
    """Validate that a research response has the expected structure."""
    assert response is not None, f"{provider_name}: Response should not be None"
    assert response.id is not None, f"{provider_name}: Response should have an ID"
    assert response.status in ["completed", "in_progress", "failed"], f"{provider_name}: Status should be valid"

    if response.status == "completed":
        assert response.output is not None, f"{provider_name}: Completed response should have output"
        assert len(response.output) > 0, f"{provider_name}: Output should not be empty"

        # Check for content
        has_content = False
        for block in response.output:
            if block.get("type") == "message":
                for item in block.get("content", []):
                    if item.get("type") in ["output_text", "text"]:
                        text = item.get("text", "")
                        if text:
                            has_content = True
                            break

        assert has_content, f"{provider_name}: Response should contain text content"

        # Validate usage stats
        assert response.usage is not None, f"{provider_name}: Should have usage stats"
        assert response.usage.input_tokens > 0, f"{provider_name}: Should have input tokens"
        assert response.usage.output_tokens > 0, f"{provider_name}: Should have output tokens"
        assert response.usage.cost >= 0, f"{provider_name}: Should have cost (>= 0)"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_api
async def test_openai_provider_basic():
    """Test OpenAI provider with simple query."""
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OpenAI API key not set")

    provider = OpenAIProvider()

    request = ResearchRequest(
        prompt="What is 2+2? Provide a one-sentence answer.",
        model="o4-mini-deep-research",
        system_message="You are a helpful assistant.",
        tools=[ToolConfig(type="web_search_preview")],  # Deep research models require at least one tool
        background=False,
    )

    job_id = await provider.submit_research(request)
    assert job_id is not None

    # Poll for completion
    max_wait = 180
    poll_interval = 5
    elapsed = 0

    while elapsed < max_wait:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        response = await provider.get_status(job_id)

        if response.status == "completed":
            validate_research_response(response, "OpenAI")
            assert response.usage.cost < 0.50, "Simple query should be cheap"
            return

        elif response.status == "failed":
            pytest.fail(f"OpenAI job failed: {response.error}")

    pytest.fail(f"OpenAI job timed out after {max_wait}s")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_api
async def test_gemini_provider_basic():
    """Test Gemini provider with simple query."""
    if not os.getenv("GEMINI_API_KEY"):
        pytest.skip("Gemini API key not set")

    provider = GeminiProvider()

    request = ResearchRequest(
        prompt="What is the capital of France? Provide a one-sentence answer.",
        model="gemini-2.5-flash",
        system_message="You are a helpful assistant.",
        tools=[],
        background=False,
    )

    job_id = await provider.submit_research(request)
    assert job_id is not None

    # Gemini completes immediately
    await asyncio.sleep(1)

    response = await provider.get_status(job_id)

    if response.status == "completed":
        validate_research_response(response, "Gemini")
        assert response.usage.cost < 0.10, "Simple query should be very cheap"
    elif response.status == "failed":
        pytest.fail(f"Gemini job failed: {response.error}")
    else:
        pytest.fail(f"Gemini job still {response.status}")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_api
async def test_grok_provider_basic():
    """Test Grok provider with simple query."""
    if not os.getenv("XAI_API_KEY"):
        pytest.skip("xAI API key not set")

    provider = GrokProvider()

    request = ResearchRequest(
        prompt="What is Python? Provide a one-sentence answer.",
        model="grok-4-fast",
        system_message="You are a helpful assistant.",
        tools=[],
        background=False,
    )

    job_id = await provider.submit_research(request)
    assert job_id is not None

    # Grok completes immediately
    await asyncio.sleep(1)

    response = await provider.get_status(job_id)

    if response.status == "completed":
        validate_research_response(response, "Grok")
        assert response.usage.cost < 0.10, "Simple query should be cheap"
    elif response.status == "failed":
        pytest.fail(f"Grok job failed: {response.error}")
    else:
        pytest.fail(f"Grok job still {response.status}")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_api
async def test_azure_provider_basic():
    """Test Azure OpenAI provider with simple query."""
    if not os.getenv("AZURE_OPENAI_KEY"):
        pytest.skip("Azure OpenAI key not set")

    provider = AzureProvider()

    request = ResearchRequest(
        prompt="What is 5+5? Provide a one-sentence answer.",
        model="o4-mini-deep-research",
        system_message="You are a helpful assistant.",
        tools=[ToolConfig(type="web_search_preview")],  # Deep research models require at least one tool
        background=False,
    )

    job_id = await provider.submit_research(request)
    assert job_id is not None

    # Poll for completion
    max_wait = 180
    poll_interval = 5
    elapsed = 0

    while elapsed < max_wait:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        response = await provider.get_status(job_id)

        if response.status == "completed":
            validate_research_response(response, "Azure")
            return

        elif response.status == "failed":
            pytest.fail(f"Azure job failed: {response.error}")

    pytest.fail(f"Azure job timed out after {max_wait}s")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_api
async def test_all_providers_cost_tracking():
    """Test that all providers correctly track costs."""
    providers_to_test = []

    if os.getenv("OPENAI_API_KEY"):
        providers_to_test.append(("OpenAI", OpenAIProvider(), "o4-mini-deep-research", 180))
    if os.getenv("GEMINI_API_KEY"):
        providers_to_test.append(("Gemini", GeminiProvider(), "gemini-2.5-flash", 60))
    if os.getenv("XAI_API_KEY"):
        providers_to_test.append(("Grok", GrokProvider(), "grok-4-fast", 60))

    if not providers_to_test:
        pytest.skip("No API keys configured for testing")

    for provider_name, provider, model, max_wait in providers_to_test:
        # OpenAI deep research models require at least one tool
        tools = [ToolConfig(type="web_search_preview")] if "deep-research" in model else []

        request = ResearchRequest(
            prompt="What is 1+1? One sentence only.",
            model=model,
            system_message="You are a helpful assistant.",
            tools=tools,
            background=False,
        )

        job_id = await provider.submit_research(request)

        # Wait for completion
        poll_interval = 2 if max_wait < 100 else 5
        elapsed = 0

        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            response = await provider.get_status(job_id)

            if response.status == "completed":
                assert response.usage is not None, f"{provider_name}: Should have usage stats"
                assert response.usage.cost >= 0, f"{provider_name}: Should track cost"
                assert response.usage.input_tokens > 0, f"{provider_name}: Should have input tokens"
                assert response.usage.output_tokens > 0, f"{provider_name}: Should have output tokens"
                break

            elif response.status == "failed":
                pytest.fail(f"{provider_name} job failed: {response.error}")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_api
async def test_provider_response_format_consistency():
    """Test that all providers return consistent response formats."""
    providers_to_test = []

    if os.getenv("GEMINI_API_KEY"):
        providers_to_test.append(("Gemini", GeminiProvider(), "gemini-2.5-flash"))
    if os.getenv("XAI_API_KEY"):
        providers_to_test.append(("Grok", GrokProvider(), "grok-4-fast"))

    if not providers_to_test:
        pytest.skip("No immediate-completion providers configured")

    for provider_name, provider, model in providers_to_test:
        request = ResearchRequest(
            prompt="Say 'hello' in one word.",
            model=model,
            system_message="You are a helpful assistant.",
            tools=[],
            background=False,
        )

        job_id = await provider.submit_research(request)
        await asyncio.sleep(1)

        response = await provider.get_status(job_id)

        # Validate response format
        assert response.id == job_id, f"{provider_name}: Response ID should match job ID"
        assert isinstance(response.output, list), f"{provider_name}: Output should be a list"

        if response.status == "completed":
            # Verify output structure
            found_text = False
            for block in response.output:
                assert isinstance(block, dict), f"{provider_name}: Output blocks should be dicts"
                assert "type" in block, f"{provider_name}: Output blocks should have 'type'"

                if block.get("type") == "message":
                    assert "content" in block, f"{provider_name}: Message blocks should have 'content'"
                    for item in block["content"]:
                        if item.get("type") in ["output_text", "text"]:
                            found_text = True

            assert found_text, f"{provider_name}: Should have text output"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_api
async def test_provider_error_handling():
    """Test that providers handle errors gracefully."""
    if not os.getenv("GEMINI_API_KEY"):
        pytest.skip("Gemini API key not set")

    provider = GeminiProvider()

    # Test with invalid model
    request = ResearchRequest(
        prompt="Test query",
        model="invalid-model-that-does-not-exist",
        system_message="You are a helpful assistant.",
        tools=[],
        background=False,
    )

    # Gemini executes immediately, so job_id is returned even for invalid models
    # The error will be in the job status
    job_id = await provider.submit_research(request)
    assert job_id is not None

    # Check that job failed
    await asyncio.sleep(2)  # Give it time to fail
    status = await provider.get_status(job_id)
    assert status.status == "failed", "Invalid model should result in failed job"
    assert status.error is not None, "Failed job should have error message"
