"""Integration tests for validating Gemini and Grok provider implementations."""

import asyncio

import pytest
from dotenv import load_dotenv

load_dotenv()

from deepr.providers.base import ResearchRequest, ToolConfig
from deepr.providers.gemini_provider import GeminiProvider
from deepr.providers.grok_provider import GrokProvider


@pytest.mark.asyncio
@pytest.mark.integration
async def test_gemini_provider_basic():
    """Test Gemini provider with a simple query."""
    provider = GeminiProvider()

    request = ResearchRequest(
        prompt="What are the key features of Python 3.13 released in 2024?",
        model="gemini-2.5-flash",
        system_message="You are a helpful research assistant. Provide concise, accurate information.",
        tools=[ToolConfig(type="web_search_preview")],
        background=False,
    )

    # Submit job
    job_id = await provider.submit_research(request)
    assert job_id is not None
    assert job_id.startswith("gemini-")

    # Wait for completion (up to 2 minutes)
    max_wait = 120
    poll_interval = 2
    elapsed = 0

    while elapsed < max_wait:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        response = await provider.get_status(job_id)

        if response.status == "completed":
            # Validate response structure
            assert response.output is not None
            assert len(response.output) > 0

            # Check for content
            has_content = False
            for block in response.output:
                if block.get("type") == "message":
                    for item in block.get("content", []):
                        if item.get("type") == "output_text":
                            text = item.get("text", "")
                            if text:
                                has_content = True
                                break

            assert has_content, "Response should contain output text"

            # Validate usage stats
            assert response.usage is not None
            assert response.usage.input_tokens > 0
            assert response.usage.output_tokens > 0
            assert response.usage.cost > 0

            return

        elif response.status == "failed":
            pytest.fail(f"Job failed: {response.error}")

    pytest.fail(f"Job timed out after {max_wait}s")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_grok_provider_basic():
    """Test Grok provider with a simple query."""
    provider = GrokProvider()

    request = ResearchRequest(
        prompt="What are the latest developments from xAI in 2024?",
        model="grok-4-fast",
        system_message="You are a helpful research assistant. Provide concise, accurate information.",
        tools=[ToolConfig(type="web_search_preview")],
        background=False,
    )

    # Submit job
    job_id = await provider.submit_research(request)
    assert job_id is not None

    # Wait for completion (up to 2 minutes)
    max_wait = 120
    poll_interval = 2
    elapsed = 0

    while elapsed < max_wait:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        response = await provider.get_status(job_id)

        if response.status == "completed":
            # Validate response structure
            assert response.output is not None
            assert len(response.output) > 0

            # Check for content
            has_content = False
            for block in response.output:
                if block.get("type") == "message":
                    for item in block.get("content", []):
                        if item.get("type") == "output_text":
                            text = item.get("text", "")
                            if text:
                                has_content = True
                                break

            assert has_content, "Response should contain output text"

            # Validate usage stats
            assert response.usage is not None
            assert response.usage.input_tokens > 0
            assert response.usage.output_tokens > 0
            assert response.usage.cost > 0

            return

        elif response.status == "failed":
            pytest.fail(f"Job failed: {response.error}")

    pytest.fail(f"Job timed out after {max_wait}s")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_gemini_cost_tracking():
    """Test that Gemini provider correctly tracks costs."""
    provider = GeminiProvider()

    request = ResearchRequest(
        prompt="What is 2+2?",  # Simple query for predictable cost
        model="gemini-2.5-flash",
        system_message="You are a helpful assistant.",
        tools=[],
        background=False,
    )

    job_id = await provider.submit_research(request)

    # Wait for completion
    max_wait = 60
    poll_interval = 2
    elapsed = 0

    while elapsed < max_wait:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        response = await provider.get_status(job_id)

        if response.status == "completed":
            assert response.usage is not None
            assert response.usage.cost > 0, "Cost should be tracked"
            assert response.usage.cost < 0.10, "Simple query should be very cheap"
            return

        elif response.status == "failed":
            pytest.fail(f"Job failed: {response.error}")

    pytest.fail(f"Job timed out after {max_wait}s")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_grok_cost_tracking():
    """Test that Grok provider correctly tracks costs."""
    provider = GrokProvider()

    request = ResearchRequest(
        prompt="What is 2+2?",  # Simple query for predictable cost
        model="grok-4-fast",
        system_message="You are a helpful assistant.",
        tools=[],
        background=False,
    )

    job_id = await provider.submit_research(request)

    # Wait for completion
    max_wait = 60
    poll_interval = 2
    elapsed = 0

    while elapsed < max_wait:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        response = await provider.get_status(job_id)

        if response.status == "completed":
            assert response.usage is not None
            assert response.usage.cost > 0, "Cost should be tracked"
            assert response.usage.cost < 0.10, "Simple query should be very cheap"
            return

        elif response.status == "failed":
            pytest.fail(f"Job failed: {response.error}")

    pytest.fail(f"Job timed out after {max_wait}s")
