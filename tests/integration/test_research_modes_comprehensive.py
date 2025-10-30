"""Comprehensive integration tests for all Deepr research modes.

Tests all four research modes with real API calls:
1. Focus Research - Quick, focused queries
2. Documentation Research - Technical API documentation
3. Multi-Phase Projects - Adaptive research with context chaining
4. Dynamic Teams - Multiple perspectives synthesized

Provider Coverage:
- OpenAI: Full coverage (all 4 modes)
- Gemini: Focus + Docs modes only (no multi-phase/team)
- Grok: Focus mode only (basic capability check)

These tests serve dual purposes:
1. Validate that all research modes work correctly
2. Use Deepr to improve Deepr (dogfooding/learning feedback loop)

Cost Estimate: ~$5-10 per full test run
Run explicitly with: pytest -m "research_modes"
"""

import pytest
import asyncio
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from deepr.providers.openai_provider import OpenAIProvider
from deepr.providers.gemini_provider import GeminiProvider
from deepr.providers.grok_provider import GrokProvider
from deepr.providers.base import ResearchRequest, ToolConfig


def validate_research_output(response, mode_name, min_length=500):
    """Validate that research output meets quality standards."""
    assert response is not None, f"{mode_name}: Response is None"
    assert response.status == "completed", f"{mode_name}: Status is {response.status}"
    assert response.output is not None, f"{mode_name}: No output"

    # Extract text content
    text_content = ""
    for block in response.output:
        if block.get('type') == 'message':
            for item in block.get('content', []):
                if item.get('type') in ['output_text', 'text']:
                    text_content += item.get('text', '')

    assert len(text_content) >= min_length, \
        f"{mode_name}: Output too short ({len(text_content)} chars, expected >={min_length})"

    # Check for citations (research should have sources)
    has_citations = any(marker in text_content.lower()
                       for marker in ['source', 'http', 'www', 'citation', 'reference'])

    # Validate usage stats
    assert response.usage is not None, f"{mode_name}: No usage stats"
    assert response.usage.input_tokens > 0, f"{mode_name}: No input tokens"
    assert response.usage.output_tokens > 0, f"{mode_name}: No output tokens"
    assert response.usage.cost >= 0, f"{mode_name}: Invalid cost"

    return text_content, has_citations


# ==============================================================================
# OpenAI Tests (Full Coverage - All 4 Modes)
# ==============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_api
@pytest.mark.research_modes
async def test_openai_focus_mode_self_improvement():
    """Test Focus mode: Use Deepr to research Deepr improvements.

    Real-world scenario: Quick research on how to improve the project.
    Cost: ~$0.50-1.00
    Duration: 5-10 minutes
    """
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OpenAI API key not set")

    provider = OpenAIProvider()

    # Use Deepr to improve Deepr
    request = ResearchRequest(
        prompt="""What are the latest best practices for Python CLI tools in 2025?
        Focus on: command structure, configuration, error handling, and testing.
        Keep it concise (one page).""",
        model="o4-mini-deep-research",
        system_message="You are a Python development expert. Provide actionable advice with examples.",
        tools=[ToolConfig(type="web_search_preview")],
        background=True
    )

    job_id = await provider.submit_research(request)
    assert job_id is not None

    print(f"\n[Focus Mode] Job submitted: {job_id}")

    # Poll for completion
    max_wait = 600  # 10 minutes
    poll_interval = 10
    elapsed = 0

    while elapsed < max_wait:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        response = await provider.get_status(job_id)
        print(f"  [{elapsed}s] Status: {response.status}")

        if response.status == "completed":
            text_content, has_citations = validate_research_output(
                response, "Focus Mode", min_length=500
            )

            print(f"  Output: {len(text_content)} chars")
            print(f"  Cost: ${response.usage.cost:.4f}")
            print(f"  Has citations: {has_citations}")

            # Save output for review
            output_dir = Path("tests/data/research_outputs")
            output_dir.mkdir(parents=True, exist_ok=True)

            output_file = output_dir / f"focus_cli_best_practices_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            output_file.write_text(text_content)
            print(f"  Saved to: {output_file}")

            assert response.usage.cost < 2.0, "Focus mode should be relatively cheap"
            return

        elif response.status == "failed":
            pytest.fail(f"Focus mode failed: {response.error}")

    pytest.fail(f"Focus mode timed out after {max_wait}s")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_api
@pytest.mark.research_modes
async def test_openai_docs_mode_api_research():
    """Test Documentation mode: Research OpenAI's own API for validation.

    Real-world scenario: Get latest API documentation to validate our implementation.
    Cost: ~$0.50-1.00
    Duration: 5-10 minutes
    """
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OpenAI API key not set")

    provider = OpenAIProvider()

    # Research OpenAI's Deep Research API to validate our usage
    request = ResearchRequest(
        prompt="""OpenAI Deep Research API (Responses API) - October 2025 documentation.

        Focus on:
        - Tool configuration (web_search_preview, code_interpreter, file_search)
        - Parameter requirements for each tool
        - Background job handling
        - Pricing and limits
        - Breaking changes in recent updates

        Provide code examples.""",
        model="o4-mini-deep-research",
        system_message="""You are a technical documentation specialist.
        Emphasize current state, recent changes, and code examples.
        Include pricing and limits. Cite authoritative sources.""",
        tools=[ToolConfig(type="web_search_preview")],
        background=True
    )

    job_id = await provider.submit_research(request)
    print(f"\n[Docs Mode] Job submitted: {job_id}")

    # Poll for completion
    max_wait = 600
    poll_interval = 10
    elapsed = 0

    while elapsed < max_wait:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        response = await provider.get_status(job_id)
        print(f"  [{elapsed}s] Status: {response.status}")

        if response.status == "completed":
            text_content, has_citations = validate_research_output(
                response, "Docs Mode", min_length=1000
            )

            print(f"  Output: {len(text_content)} chars")
            print(f"  Cost: ${response.usage.cost:.4f}")
            print(f"  Has citations: {has_citations}")

            # Check for technical content indicators
            has_code_examples = any(marker in text_content
                                   for marker in ['```', 'python', 'json', 'curl'])
            has_pricing = any(word in text_content.lower()
                            for word in ['price', 'cost', '$', 'limit', 'quota'])

            assert has_code_examples, "Docs mode should include code examples"
            assert has_pricing, "Docs mode should include pricing info"
            assert has_citations, "Docs mode should have citations"

            # Save output
            output_dir = Path("tests/data/research_outputs")
            output_dir.mkdir(parents=True, exist_ok=True)

            output_file = output_dir / f"docs_openai_api_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            output_file.write_text(text_content)
            print(f"  Saved to: {output_file}")

            assert response.usage.cost < 3.0, "Docs mode should be reasonably priced"
            return

        elif response.status == "failed":
            pytest.fail(f"Docs mode failed: {response.error}")

    pytest.fail(f"Docs mode timed out after {max_wait}s")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_api
@pytest.mark.research_modes
@pytest.mark.expensive
async def test_openai_project_mode_multi_phase():
    """Test Project mode: Multi-phase adaptive research.

    Real-world scenario: Complex question requiring multiple rounds of research.
    Cost: ~$2-5
    Duration: 10-20 minutes
    """
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OpenAI API key not set")

    provider = OpenAIProvider()

    # Multi-phase research on improving Deepr's testing strategy
    request = ResearchRequest(
        prompt="""Analyze Deepr's testing strategy and recommend improvements.

        Context: Deepr is a Python CLI tool for autonomous research with multiple AI providers.
        Current issues:
        - Test coverage at 14% overall
        - Unit tests don't catch API parameter bugs
        - Need integration tests with real APIs

        Research phases:
        1. Survey testing best practices for Python CLI tools
        2. Analyze provider API testing strategies (OpenAI, Google, etc.)
        3. Recommend specific improvements for Deepr
        4. Provide implementation priorities

        Be specific with examples and code where relevant.""",
        model="o3-deep-research",  # Use o3 for multi-phase capability
        system_message="""You are a software testing expert.
        Break this into phases, research each thoroughly, then synthesize recommendations.""",
        tools=[ToolConfig(type="web_search_preview")],
        background=True
    )

    job_id = await provider.submit_research(request)
    print(f"\n[Project Mode] Job submitted: {job_id}")

    # Project mode takes longer
    max_wait = 1200  # 20 minutes
    poll_interval = 15
    elapsed = 0

    while elapsed < max_wait:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        response = await provider.get_status(job_id)
        print(f"  [{elapsed}s] Status: {response.status}")

        if response.status == "completed":
            text_content, has_citations = validate_research_output(
                response, "Project Mode", min_length=2000
            )

            print(f"  Output: {len(text_content)} chars")
            print(f"  Cost: ${response.usage.cost:.4f}")

            # Project mode should show multi-phase structure
            has_phases = any(marker in text_content.lower()
                           for marker in ['phase', 'step', 'stage', 'round'])

            assert has_phases, "Project mode should show phased approach"
            assert has_citations, "Project mode should have extensive citations"

            # Save output
            output_dir = Path("tests/data/research_outputs")
            output_dir.mkdir(parents=True, exist_ok=True)

            output_file = output_dir / f"project_testing_strategy_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            output_file.write_text(text_content)
            print(f"  Saved to: {output_file}")

            assert response.usage.cost < 10.0, "Project mode should be under $10"
            return

        elif response.status == "failed":
            pytest.fail(f"Project mode failed: {response.error}")

    pytest.fail(f"Project mode timed out after {max_wait}s")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_api
@pytest.mark.research_modes
@pytest.mark.expensive
async def test_openai_team_mode_diverse_perspectives():
    """Test Team mode: Dynamic research team with diverse perspectives.

    Real-world scenario: Strategic decision requiring multiple viewpoints.
    Cost: ~$3-8
    Duration: 15-30 minutes
    """
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OpenAI API key not set")

    provider = OpenAIProvider()

    # Strategic question for the team
    request = ResearchRequest(
        prompt="""Should Deepr focus on enterprise features or developer tools in 2025?

        Context: Deepr is a research operating system with multi-provider support.
        Current state: Individual developer focused, CLI-first, local-first.

        Assemble an optimal team to analyze this decision. Consider:
        - Market opportunity
        - Technical feasibility
        - Competitive positioning
        - Resource requirements
        - Risk factors

        Each team member should research independently from their perspective,
        then synthesize a balanced recommendation.""",
        model="o3-deep-research",  # Use o3 for team capability
        system_message="""You are a strategic research orchestrator.
        Design an optimal team for this question.
        Each member researches independently to prevent groupthink.
        Synthesize their findings into a balanced recommendation.""",
        tools=[ToolConfig(type="web_search_preview")],
        background=True
    )

    job_id = await provider.submit_research(request)
    print(f"\n[Team Mode] Job submitted: {job_id}")

    # Team mode takes longest
    max_wait = 1800  # 30 minutes
    poll_interval = 20
    elapsed = 0

    while elapsed < max_wait:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        response = await provider.get_status(job_id)
        print(f"  [{elapsed}s] Status: {response.status}")

        if response.status == "completed":
            text_content, has_citations = validate_research_output(
                response, "Team Mode", min_length=3000
            )

            print(f"  Output: {len(text_content)} chars")
            print(f"  Cost: ${response.usage.cost:.4f}")

            # Team mode should show multiple perspectives
            has_team_structure = any(marker in text_content.lower()
                                    for marker in ['team member', 'perspective',
                                                  'analyst', 'expert', 'synthesis'])

            assert has_team_structure, "Team mode should show team structure"
            assert has_citations, "Team mode should have extensive citations"

            # Save output
            output_dir = Path("tests/data/research_outputs")
            output_dir.mkdir(parents=True, exist_ok=True)

            output_file = output_dir / f"team_strategic_decision_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            output_file.write_text(text_content)
            print(f"  Saved to: {output_file}")

            assert response.usage.cost < 15.0, "Team mode should be under $15"
            return

        elif response.status == "failed":
            pytest.fail(f"Team mode failed: {response.error}")

    pytest.fail(f"Team mode timed out after {max_wait}s")


# ==============================================================================
# Gemini Tests (Limited - Focus + Docs Only)
# ==============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_api
@pytest.mark.research_modes
async def test_gemini_focus_mode_capability_check():
    """Test Gemini Focus mode: Basic capability validation.

    Gemini doesn't have multi-phase or team modes, but Focus works well.
    Cost: ~$0.10-0.50
    Duration: 2-5 minutes
    """
    if not os.getenv("GEMINI_API_KEY"):
        pytest.skip("Gemini API key not set")

    provider = GeminiProvider()

    request = ResearchRequest(
        prompt="What are the key features of Google Gemini 2.5 models? Keep it brief (one page).",
        model="gemini-2.5-flash",
        system_message="You are a helpful AI assistant. Provide concise, accurate information.",
        tools=[ToolConfig(type="google_search")],  # Gemini uses google_search not web_search
    )

    job_id = await provider.submit_research(request)
    print(f"\n[Gemini Focus] Job submitted: {job_id}")

    # Gemini is synchronous, so response should be immediate or fast
    response = await provider.get_status(job_id)

    if response.status == "completed":
        text_content, has_citations = validate_research_output(
            response, "Gemini Focus", min_length=300
        )

        print(f"  Output: {len(text_content)} chars")
        print(f"  Cost: ${response.usage.cost:.4f}")

        assert response.usage.cost < 1.0, "Gemini Focus should be cheap"
        return
    else:
        pytest.fail(f"Gemini Focus failed: {response.status}")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_api
@pytest.mark.research_modes
async def test_gemini_docs_mode_api_documentation():
    """Test Gemini Docs mode: Technical documentation research.

    Cost: ~$0.20-0.80
    Duration: 3-8 minutes
    """
    if not os.getenv("GEMINI_API_KEY"):
        pytest.skip("Gemini API key not set")

    provider = GeminiProvider()

    request = ResearchRequest(
        prompt="""Google Gemini API documentation - October 2025.

        Focus on:
        - Available models (Pro, Flash, Flash-Lite)
        - Thinking/reasoning configuration
        - Tool calling capabilities
        - Pricing and context limits

        Include code examples.""",
        model="gemini-2.5-flash",
        system_message="You are a technical documentation specialist. Provide current, accurate API details.",
        tools=[ToolConfig(type="google_search")],
    )

    job_id = await provider.submit_research(request)
    print(f"\n[Gemini Docs] Job submitted: {job_id}")

    response = await provider.get_status(job_id)

    if response.status == "completed":
        text_content, has_citations = validate_research_output(
            response, "Gemini Docs", min_length=500
        )

        print(f"  Output: {len(text_content)} chars")
        print(f"  Cost: ${response.usage.cost:.4f}")

        # Save for comparison with OpenAI docs output
        output_dir = Path("tests/data/research_outputs")
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / f"docs_gemini_api_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        output_file.write_text(text_content)
        print(f"  Saved to: {output_file}")

        assert response.usage.cost < 2.0, "Gemini Docs should be reasonably priced"
        return
    else:
        pytest.fail(f"Gemini Docs failed: {response.status}")


# ==============================================================================
# Grok Tests (Minimal - Focus Only)
# ==============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_api
@pytest.mark.research_modes
async def test_grok_focus_mode_basic():
    """Test Grok Focus mode: Basic capability check.

    Grok has limited deep research capabilities - just validate it works.
    Cost: ~$0.10-0.30
    Duration: 1-3 minutes
    """
    if not os.getenv("GROK_API_KEY"):
        pytest.skip("Grok API key not set")

    provider = GrokProvider()

    request = ResearchRequest(
        prompt="What is xAI Grok and what are its key capabilities? Keep it very brief.",
        model="grok-beta",
        system_message="You are a helpful assistant. Be concise.",
        tools=[ToolConfig(type="x_search")],  # Grok uses X/Twitter search
    )

    job_id = await provider.submit_research(request)
    print(f"\n[Grok Focus] Job submitted: {job_id}")

    response = await provider.get_status(job_id)

    if response.status == "completed":
        text_content, has_citations = validate_research_output(
            response, "Grok Focus", min_length=200
        )

        print(f"  Output: {len(text_content)} chars")
        print(f"  Cost: ${response.usage.cost:.4f}")

        assert response.usage.cost < 1.0, "Grok Focus should be cheap"
        return
    else:
        pytest.fail(f"Grok Focus failed: {response.status}")


# ==============================================================================
# Comparative Tests
# ==============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_api
@pytest.mark.research_modes
@pytest.mark.expensive
async def test_provider_comparison_same_query():
    """Compare all providers on the same query.

    Research question: "Latest Python testing best practices 2025"
    Compares output quality, cost, and speed across providers.

    Cost: ~$1-3
    Duration: 10-20 minutes
    """
    query = "Latest Python testing best practices for 2025. Focus on CLI tools. Be concise (one page)."

    results = {}

    # Test OpenAI
    if os.getenv("OPENAI_API_KEY"):
        provider = OpenAIProvider()
        request = ResearchRequest(
            prompt=query,
            model="o4-mini-deep-research",
            system_message="You are a Python testing expert.",
            tools=[ToolConfig(type="web_search_preview")],
            background=True
        )

        job_id = await provider.submit_research(request)
        print(f"\n[Comparison - OpenAI] Job: {job_id}")

        # Poll for completion (simplified)
        for i in range(60):  # 10 minutes max
            await asyncio.sleep(10)
            response = await provider.get_status(job_id)
            if response.status == "completed":
                results["openai"] = {
                    "output_length": len(str(response.output)),
                    "cost": response.usage.cost,
                    "tokens": response.usage.total_tokens
                }
                print(f"  OpenAI: {results['openai']}")
                break

    # Test Gemini
    if os.getenv("GEMINI_API_KEY"):
        provider = GeminiProvider()
        request = ResearchRequest(
            prompt=query,
            model="gemini-2.5-flash",
            system_message="You are a Python testing expert.",
            tools=[ToolConfig(type="google_search")],
        )

        job_id = await provider.submit_research(request)
        response = await provider.get_status(job_id)

        if response.status == "completed":
            results["gemini"] = {
                "output_length": len(str(response.output)),
                "cost": response.usage.cost,
                "tokens": response.usage.total_tokens
            }
            print(f"  Gemini: {results['gemini']}")

    # Test Grok
    if os.getenv("GROK_API_KEY"):
        provider = GrokProvider()
        request = ResearchRequest(
            prompt=query,
            model="grok-beta",
            system_message="You are a Python testing expert.",
            tools=[ToolConfig(type="x_search")],
        )

        job_id = await provider.submit_research(request)
        response = await provider.get_status(job_id)

        if response.status == "completed":
            results["grok"] = {
                "output_length": len(str(response.output)),
                "cost": response.usage.cost,
                "tokens": response.usage.total_tokens
            }
            print(f"  Grok: {results['grok']}")

    # Validate we got at least one result
    assert len(results) > 0, "No providers available for comparison"

    # Save comparison
    comparison_file = Path("tests/data/research_outputs/provider_comparison.txt")
    comparison_file.parent.mkdir(parents=True, exist_ok=True)

    with open(comparison_file, "w") as f:
        f.write(f"Provider Comparison - {datetime.now()}\n")
        f.write(f"Query: {query}\n\n")
        for provider_name, stats in results.items():
            f.write(f"{provider_name.upper()}:\n")
            f.write(f"  Output: {stats['output_length']} chars\n")
            f.write(f"  Cost: ${stats['cost']:.4f}\n")
            f.write(f"  Tokens: {stats['tokens']}\n\n")

    print(f"\nComparison saved to: {comparison_file}")
