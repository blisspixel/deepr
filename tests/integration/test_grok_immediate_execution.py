"""Test Grok provider immediate execution."""

import asyncio
import os

from deepr.providers.base import ResearchRequest
from deepr.providers.grok_provider import GrokProvider


async def test_immediate_execution():
    """Test that Grok executes and completes immediately."""

    # Create provider
    provider = GrokProvider(api_key=os.getenv("XAI_API_KEY"))

    # Create request without tools first
    request = ResearchRequest(
        prompt="What is 2+2? Answer in one short sentence.",
        model="grok-4-fast",
        system_message="You are a helpful assistant.",
        tools=None,
        background=False,
    )

    print("Submitting research...")
    job_id = await provider.submit_research(request)
    print(f"Job ID: {job_id}")

    print("\nChecking status immediately...")
    response = await provider.get_status(job_id)

    print(f"Status: {response.status}")
    print(f"Output: {response.output}")
    if response.usage:
        print(f"Cost: ${response.usage.cost:.4f}")
    if response.error:
        print(f"Error: {response.error}")

    return response


if __name__ == "__main__":
    asyncio.run(test_immediate_execution())
