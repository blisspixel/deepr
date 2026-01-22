"""Quick test of Anthropic provider with web search."""

import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

# Check if we need to install duckduckgo-search
try:
    import duckduckgo_search
    print("[OK] duckduckgo-search installed")
except ImportError:
    print("[WARNING] Installing duckduckgo-search for free web search...")
    import subprocess
    subprocess.run(["pip", "install", "duckduckgo-search"], shell=False)

from deepr.providers.anthropic_provider import AnthropicProvider
from deepr.providers.base import ResearchRequest


async def test_anthropic():
    """Test Anthropic provider with a simple poem request."""

    print("\n" + "="*80)
    print("Testing Anthropic Provider with Extended Thinking")
    print("="*80 + "\n")

    # Initialize provider
    provider = AnthropicProvider(
        model="claude-sonnet-4-5",
        thinking_budget=10000,  # 10k tokens for thinking
        web_search_backend="auto"  # Try all backends
    )

    print(f"Model: {provider.model}")
    print(f"Thinking Budget: {provider.thinking_budget} tokens")
    print(f"Web Search: Enabled (backend: auto)\n")

    # Create request (simplified - just needs prompt and model)
    request = ResearchRequest(
        prompt="Write a 10-line poem about news from October 8, 2025",
        model="claude-sonnet-4-5",
        system_message="",
        tools=[],  # Web search handled by provider
    )

    # Manually set web_search_enabled attribute
    request.web_search_enabled = True

    print("Submitting research request...")
    print(f"Query: {request.prompt}\n")

    # Submit (this will be synchronous for Anthropic)
    try:
        job_id = await provider.submit_research(request)
        print(f"[OK] Job completed: {job_id}\n")
        print("="*80)
        print("SUCCESS! Anthropic provider is working with web search!")
        print("="*80)

    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_anthropic())
