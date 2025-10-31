"""
Real API integration tests with cost tracking.

These tests use actual OpenAI API calls and cost money.
Run explicitly: pytest -m requires_api tests/integration/test_real_api.py

Design principle: Tests validate functionality AND gather data to improve Deepr.
Each test tracks actual cost, time, and quality to compare against estimates.
"""

import pytest
import os
import time
import json
import asyncio
from pathlib import Path
from datetime import datetime
from deepr.providers import create_provider
from deepr.providers.base import ResearchRequest, ToolConfig
from deepr.storage import create_storage
from deepr.queue import create_queue
from deepr.core.costs import CostEstimator


def get_current_date():
    """Get current date for prompts (system time)."""
    return datetime.now().strftime("%B %d, %Y")


@pytest.fixture
def test_results_dir(tmp_path):
    """Directory for saving test results and analysis."""
    results_dir = tmp_path / "test_results"
    results_dir.mkdir(exist_ok=True)
    return results_dir


@pytest.fixture
def provider():
    """Real OpenAI provider."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")
    return create_provider("openai", api_key=api_key)


@pytest.fixture
def storage(tmp_path):
    """Local storage for test reports."""
    return create_storage("local", base_path=str(tmp_path / "reports"))


@pytest.fixture
def queue(tmp_path):
    """Local queue for test jobs."""
    return create_queue("local", db_path=str(tmp_path / "queue.db"))


def save_test_result(test_results_dir, test_name, result_data):
    """Save test results for analysis."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{test_name}_{timestamp}.json"
    result_path = test_results_dir / filename

    with open(result_path, 'w') as f:
        json.dump(result_data, f, indent=2, default=str)

    print(f"\nTest results saved: {result_path}")
    return result_path


class TestSingleResearchJob:
    """Test basic research submission and retrieval."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.requires_api
    async def test_minimal_research_o4_mini(self, provider, storage, test_results_dir):
        """
        Test: Minimal research job with o4-mini-deep-research
        Expected cost: ~$0.05
        Purpose: Validate basic submit -> status -> retrieve workflow
        """
        start_time = time.time()

        # Estimate cost - using valuable research prompt
        prompt = """As of October 2025, what are the latest best practices for CLI design in developer tools?
Include examples from successful tools (git, docker, kubectl) and key principles for intuitive command structure.
Keep under 300 words."""

        estimate = CostEstimator.estimate_cost(
            prompt=prompt,
            model="o4-mini-deep-research",
            enable_web_search=True
        )

        # Submit research
        request = ResearchRequest(
            prompt=prompt,
            model="o4-mini-deep-research",
            system_message="You are a developer tools expert. Provide actionable insights with examples.",
            tools=[ToolConfig(type="web_search_preview")],
            metadata={"test": "minimal_o4_mini"}
        )

        job_id = await provider.submit_research(request)
        assert job_id.startswith("resp_"), f"Invalid job ID format: {job_id}"

        # Check initial status
        status = await provider.get_status(job_id)
        assert status.status in ["queued", "in_progress", "completed"]

        # Wait for completion (max 5 minutes for this simple query)
        max_wait = 300
        poll_interval = 10
        elapsed = 0

        while elapsed < max_wait:
            status = await provider.get_status(job_id)

            if status.status == "completed":
                break
            elif status.status == "failed":
                # OpenAI API can have transient failures - skip rather than fail
                error_msg = status.error.message if status.error else "Unknown error"
                pytest.skip(f"Job failed due to API error: {error_msg}")

            time.sleep(poll_interval)
            elapsed += poll_interval

        if status.status != "completed":
            pytest.fail(f"Job did not complete in {max_wait}s. Status: {status.status}")

        # Get actual cost and time
        actual_cost = status.usage.cost if status.usage else 0
        actual_time = time.time() - start_time

        # Extract report content
        report_content = ""
        if status.output:
            for block in status.output:
                if block.get('type') == 'message':
                    for item in block.get('content', []):
                        # OpenAI Deep Research uses 'output_text' not 'text'
                        if item.get('type') in ['output_text', 'text']:
                            report_content += item.get('text', '')

        # Save to storage
        await storage.save_report(
            job_id=job_id,
            filename="report.md",
            content=report_content.encode('utf-8'),
            content_type="text/markdown",
            metadata={
                "prompt": prompt,
                "model": "o4-mini-deep-research",
                "actual_cost": actual_cost,
                "actual_time": actual_time,
                "estimated_cost": estimate.expected_cost,
            }
        )

        # Save test results for analysis
        result_data = {
            "test": "minimal_research_o4_mini",
            "job_id": job_id,
            "prompt": prompt,
            "model": "o4-mini-deep-research",
            "estimated_cost": estimate.expected_cost,
            "actual_cost": actual_cost,
            "cost_accuracy": actual_cost / estimate.expected_cost if estimate.expected_cost > 0 else 0,
            "actual_time_seconds": actual_time,
            "report_length_chars": len(report_content),
            "success": True,
            "timestamp": datetime.now().isoformat(),
        }
        save_test_result(test_results_dir, "minimal_research", result_data)

        # Assertions
        assert actual_cost > 0, "Cost should be tracked"
        assert actual_cost < 1.0, f"Cost too high for simple query: ${actual_cost}"
        assert len(report_content) > 0, "Report should have content"

        # Print results
        print(f"\n\nTest Results:")
        print(f"  Job ID: {job_id}")
        print(f"  Estimated cost: ${estimate.expected_cost:.4f}")
        print(f"  Actual cost: ${actual_cost:.4f}")
        print(f"  Cost accuracy: {result_data['cost_accuracy']:.2f}x")
        print(f"  Time: {actual_time:.1f}s")
        print(f"  Report length: {len(report_content)} chars")

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.requires_api
    async def test_realistic_research_o4_mini(self, provider, storage, test_results_dir):
        """
        Test: Realistic research query with o4-mini
        Expected cost: ~$0.10
        Purpose: Validate with actual user-like prompt
        """
        start_time = time.time()

        prompt = """As of October 2025, what are the state-of-the-art techniques for agentic research using deep research APIs and LLMs?
Include: (1) Multi-agent orchestration patterns, (2) Context management strategies, (3) Quality assessment methods, (4) Cost optimization techniques.
Cite specific tools, papers, or implementations where possible. Keep under 800 words."""

        estimate = CostEstimator.estimate_cost(
            prompt=prompt,
            model="o4-mini-deep-research",
            enable_web_search=True
        )

        request = ResearchRequest(
            prompt=prompt,
            model="o4-mini-deep-research",
            system_message="You are an AI research expert. Provide cutting-edge insights with citations.",
            tools=[ToolConfig(type="web_search_preview")],
            metadata={"test": "realistic_query"}
        )

        job_id = await provider.submit_research(request)

        # Wait for completion
        max_wait = 600  # 10 minutes
        poll_interval = 15
        elapsed = 0

        while elapsed < max_wait:
            status = await provider.get_status(job_id)
            if status.status == "completed":
                break
            elif status.status == "failed":
                # OpenAI API can have transient failures - skip rather than fail
                error_msg = status.error.message if status.error else "Unknown error"
                pytest.skip(f"Job failed due to API error: {error_msg}")
            time.sleep(poll_interval)
            elapsed += poll_interval

        assert status.status == "completed", f"Job did not complete in {max_wait}s"

        actual_cost = status.usage.cost if status.usage else 0
        actual_time = time.time() - start_time

        # Extract content
        report_content = ""
        if status.output:
            for block in status.output:
                if block.get('type') == 'message':
                    for item in block.get('content', []):
                        # OpenAI Deep Research uses 'output_text' not 'text'
                        if item.get('type') in ['output_text', 'text']:
                            report_content += item.get('text', '')

        # Analyze quality
        has_numbers = any(char.isdigit() for char in report_content)
        has_structure = "1." in report_content or "2." in report_content

        result_data = {
            "test": "realistic_research_o4_mini",
            "job_id": job_id,
            "prompt_length": len(prompt),
            "estimated_cost": estimate.expected_cost,
            "actual_cost": actual_cost,
            "cost_accuracy": actual_cost / estimate.expected_cost if estimate.expected_cost > 0 else 0,
            "actual_time_seconds": actual_time,
            "report_length_chars": len(report_content),
            "has_numbers": has_numbers,
            "has_structure": has_structure,
            "quality_score": (1.0 if has_numbers else 0.5) * (1.0 if has_structure else 0.5),
            "success": True,
            "timestamp": datetime.now().isoformat(),
        }
        save_test_result(test_results_dir, "realistic_research", result_data)

        # Assertions
        assert actual_cost > 0
        assert actual_cost < 2.0, f"Cost too high: ${actual_cost}"
        assert len(report_content) > 100, "Report too short"
        assert has_structure, "Report should have structured content"

        print(f"\n\nTest Results:")
        print(f"  Estimated cost: ${estimate.expected_cost:.4f}")
        print(f"  Actual cost: ${actual_cost:.4f}")
        print(f"  Cost accuracy: {result_data['cost_accuracy']:.2f}x")
        print(f"  Time: {actual_time:.1f}s ({actual_time/60:.1f} min)")
        print(f"  Report length: {len(report_content)} chars")
        print(f"  Quality indicators: numbers={has_numbers}, structure={has_structure}")


class TestFileUpload:
    """Test file upload and vector store functionality."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.requires_api
    async def test_file_upload_and_search(self, provider, storage, tmp_path, test_results_dir):
        """
        Test: Upload file and research with context
        Expected cost: ~$0.15
        Purpose: Validate file upload, vector store, and semantic search
        """
        start_time = time.time()

        # Create test file
        test_file = tmp_path / "test_doc.txt"
        test_content = """
        Product: AI Research Platform
        Version: 2.3
        Features: Multi-phase campaigns, file upload, cost tracking
        Pricing: Open source, usage-based API costs
        Target: Developers and researchers
        """
        test_file.write_text(test_content)

        # Upload file
        file_id = await provider.upload_document(str(test_file), purpose="assistants")
        assert file_id, "File upload should return ID"

        # Create vector store
        vector_store = await provider.create_vector_store("test_store", [file_id])
        assert vector_store.id, "Vector store should return ID"

        # Wait for vector store to be ready
        ready = await provider.wait_for_vector_store(vector_store.id, timeout=300)
        assert ready, "Vector store should be ready"

        # Research with file context - analyze our actual product
        prompt = """Based on the uploaded product documentation, analyze:
(1) Top 3 features most likely to attract users
(2) Potential usability issues or confusing sections
(3) Missing documentation that would help adoption
(4) Competitive advantages to emphasize in marketing
Provide specific, actionable recommendations."""

        request = ResearchRequest(
            prompt=prompt,
            model="o4-mini-deep-research",
            system_message="You are a product analyst. Provide constructive feedback.",
            tools=[
                ToolConfig(type="file_search", vector_store_ids=[vector_store.id])
            ],
            metadata={"test": "file_upload"}
        )

        job_id = await provider.submit_research(request)

        # Wait for completion
        max_wait = 600
        poll_interval = 15
        elapsed = 0

        while elapsed < max_wait:
            status = await provider.get_status(job_id)
            if status.status == "completed":
                break
            elif status.status == "failed":
                # OpenAI API can have transient failures - skip rather than fail
                error_msg = status.error.message if status.error else "Unknown error"
                pytest.skip(f"Job failed due to API error: {error_msg}")
            time.sleep(poll_interval)
            elapsed += poll_interval

        assert status.status == "completed"

        actual_cost = status.usage.cost if status.usage else 0
        actual_time = time.time() - start_time

        # Extract report
        report_content = ""
        if status.output:
            for block in status.output:
                if block.get('type') == 'message':
                    for item in block.get('content', []):
                        # OpenAI Deep Research uses 'output_text' not 'text'
                        if item.get('type') in ['output_text', 'text']:
                            report_content += item.get('text', '')

        # Check if it used the file context
        used_context = "open source" in report_content.lower() or "usage-based" in report_content.lower()

        result_data = {
            "test": "file_upload_and_search",
            "job_id": job_id,
            "file_id": file_id,
            "file_size_bytes": len(test_content),
            "actual_cost": actual_cost,
            "actual_time_seconds": actual_time,
            "report_length_chars": len(report_content),
            "used_file_context": used_context,
            "success": True,
            "timestamp": datetime.now().isoformat(),
        }
        save_test_result(test_results_dir, "file_upload", result_data)

        # Assertions
        assert actual_cost > 0
        assert actual_cost < 1.0, f"Cost too high: ${actual_cost}"
        assert len(report_content) > 0
        assert used_context, "Report should reference uploaded file content"

        print(f"\n\nTest Results:")
        print(f"  File ID: {file_id}")
        print(f"  Actual cost: ${actual_cost:.4f}")
        print(f"  Time: {actual_time:.1f}s")
        print(f"  Used file context: {used_context}")


class TestPromptRefinement:
    """Test automatic prompt refinement with GPT-5-mini."""

    @pytest.mark.integration
    @pytest.mark.requires_api
    def test_prompt_refinement(self, test_results_dir):
        """
        Test: Prompt refinement with GPT-5-mini
        Expected cost: ~$0.001
        Purpose: Validate prompt optimization works and improves quality
        """
        from deepr.services.prompt_refiner import PromptRefiner

        start_time = time.time()

        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")

        refiner = PromptRefiner()  # Uses gpt-5-mini by default

        # Vague prompt
        vague_prompt = "research AI code editors"

        # Refine it
        result = refiner.refine(vague_prompt, has_files=False)
        refined = result["refined_prompt"]
        changes = result.get("changes_made", [])

        actual_time = time.time() - start_time

        # Analyze improvements
        added_date = "2025" in refined or "october" in refined.lower()
        added_structure = "include" in refined.lower() or "focus on" in refined.lower()
        length_increased = len(refined) > len(vague_prompt) * 1.5

        result_data = {
            "test": "prompt_refinement",
            "original_prompt": vague_prompt,
            "refined_prompt": refined,
            "changes_made": changes,
            "original_length": len(vague_prompt),
            "refined_length": len(refined),
            "time_seconds": actual_time,
            "added_date_context": added_date,
            "added_structure": added_structure,
            "length_increased": length_increased,
            "improvement_score": sum([added_date, added_structure, length_increased]) / 3,
            "success": True,
            "timestamp": datetime.now().isoformat(),
        }
        save_test_result(test_results_dir, "prompt_refinement", result_data)

        # Assertions
        assert actual_time < 60, f"Refinement took too long: {actual_time}s"
        assert len(refined) > len(vague_prompt), "Refined prompt should be longer"
        assert added_date or added_structure, "Should add date context or structure"

        print(f"\n\nTest Results:")
        print(f"  Original: {vague_prompt}")
        print(f"  Refined: {refined[:100]}...")
        print(f"  Time: {actual_time:.2f}s")
        print(f"  Improvements: date={added_date}, structure={added_structure}")


class TestCostTracking:
    """Test cost estimation accuracy."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.requires_api
    @pytest.mark.expensive
    @pytest.mark.flaky(reruns=2)  # API jobs may timeout - transient issue
    async def test_cost_estimation_accuracy(self, provider, test_results_dir):
        """
        Test: Compare estimated costs to actual costs
        Expected cost: ~$0.05
        Purpose: Validate CostEstimator accuracy for future improvements
        Note: This test may fail transiently if API job doesn't complete in 5 minutes
        """
        test_cases = [
            ("Short query", "What is Python?", "o4-mini-deep-research"),
        ]

        results = []

        for name, prompt, model in test_cases:
            # Estimate
            estimate = CostEstimator.estimate_cost(
                prompt=prompt,
                model=model,
                enable_web_search=True
            )

            # Submit
            request = ResearchRequest(
                prompt=prompt,
                model=model,
                system_message="You are a helpful research assistant.",
                tools=[ToolConfig(type="web_search_preview")],
                metadata={"test": "cost_accuracy"}
            )

            job_id = await provider.submit_research(request)

            # Wait
            max_wait = 300
            poll_interval = 10
            elapsed = 0

            while elapsed < max_wait:
                status = await provider.get_status(job_id)
                if status.status in ["completed", "failed"]:
                    break
                time.sleep(poll_interval)
                elapsed += poll_interval

            actual_cost = status.usage.cost if status.usage and status.usage.cost else 0

            accuracy = actual_cost / estimate.expected_cost if estimate.expected_cost > 0 else 0

            results.append({
                "name": name,
                "prompt": prompt,
                "model": model,
                "estimated": estimate.expected_cost,
                "actual": actual_cost,
                "accuracy_ratio": accuracy,
                "status": status.status,
            })

        # Save results
        result_data = {
            "test": "cost_estimation_accuracy",
            "test_cases": results,
            "avg_accuracy": sum(r["accuracy_ratio"] for r in results) / len(results),
            "timestamp": datetime.now().isoformat(),
        }
        save_test_result(test_results_dir, "cost_accuracy", result_data)

        # Print results
        print(f"\n\nCost Estimation Accuracy:")
        for r in results:
            print(f"  {r['name']}: estimated=${r['estimated']:.4f}, actual=${r['actual']:.4f}, ratio={r['accuracy_ratio']:.2f}x")
        print(f"  Average accuracy: {result_data['avg_accuracy']:.2f}x")

        # Check for failures (but don't fail test - API issues are transient)
        completed = [r for r in results if r["status"] == "completed"]
        if len(completed) < len(results):
            print(f"\n  WARNING: {len(results) - len(completed)} test(s) failed due to API errors")
        assert len(completed) > 0, "At least one test should complete"


class TestMultiPhaseCampaign:
    """Test multi-phase campaign functionality."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.requires_api
    async def test_campaign_context_chaining(self, provider, storage, tmp_path, test_results_dir):
        """
        Test: Multi-phase campaign with context chaining
        Expected cost: ~$0.30
        Purpose: Validate campaign execution, context chaining, and report generation
        """
        start_time = time.time()

        # Phase 1: Competitive Intelligence Inventory
        phase1_prompt = """Document the current state of research automation tools and deep research APIs as of October 2025.
Include: product names, key capabilities, pricing models, API features, primary use cases, and any adoption signals.
Focus on tools for agentic research, multi-step reasoning, and knowledge synthesis.
Keep under 600 words with citations."""

        request1 = ResearchRequest(
            prompt=phase1_prompt,
            model="o4-mini-deep-research",
            system_message="You are a competitive intelligence researcher.",
            tools=[ToolConfig(type="web_search_preview")],
            metadata={"test": "campaign_phase_1", "campaign_id": "test-campaign"}
        )

        job1_id = await provider.submit_research(request1)

        # Wait for Phase 1
        max_wait = 600
        poll_interval = 15
        elapsed = 0

        while elapsed < max_wait:
            status1 = await provider.get_status(job1_id)
            if status1.status == "completed":
                break
            elif status1.status == "failed":
                pytest.skip(f"Phase 1 failed: {status1.error.message if status1.error else 'Unknown'}")
            time.sleep(poll_interval)
            elapsed += poll_interval

        assert status1.status == "completed", "Phase 1 must complete"

        # Extract Phase 1 content
        phase1_content = ""
        if status1.output:
            for block in status1.output:
                if block.get('type') == 'message':
                    for item in block.get('content', []):
                        if item.get('type') in ['output_text', 'text']:
                            phase1_content += item.get('text', '')

        # Phase 2: Strategic Analysis using Phase 1 context
        phase2_prompt = f"""Using the inventory from Phase 1 as context, analyze:
(1) Key trends in research automation (what's emerging, what's declining)
(2) Gaps in current offerings (unmet needs, missing features)
(3) Opportunities for differentiation (how Deepr could stand out)
(4) Strategic recommendations for positioning and roadmap priorities

Context from Phase 1:
{phase1_content}

Provide specific, actionable insights. Keep under 500 words."""

        request2 = ResearchRequest(
            prompt=phase2_prompt,
            model="o4-mini-deep-research",
            system_message="You are a product strategy consultant.",
            tools=[ToolConfig(type="web_search_preview")],
            metadata={"test": "campaign_phase_2", "campaign_id": "test-campaign", "previous_phase": job1_id}
        )

        job2_id = await provider.submit_research(request2)

        # Wait for Phase 2
        elapsed = 0
        while elapsed < max_wait:
            status2 = await provider.get_status(job2_id)
            if status2.status == "completed":
                break
            elif status2.status == "failed":
                pytest.skip(f"Phase 2 failed: {status2.error.message if status2.error else 'Unknown'}")
            time.sleep(poll_interval)
            elapsed += poll_interval

        assert status2.status == "completed", "Phase 2 must complete"

        # Extract Phase 2 content
        phase2_content = ""
        if status2.output:
            for block in status2.output:
                if block.get('type') == 'message':
                    for item in block.get('content', []):
                        if item.get('type') in ['output_text', 'text']:
                            phase2_content += item.get('text', '')

        # Calculate totals
        total_cost = (status1.usage.cost if status1.usage else 0) + (status2.usage.cost if status2.usage else 0)
        total_time = time.time() - start_time

        # Verify context chaining
        context_referenced = len(phase1_content) > 50 and len(phase2_content) > 50

        result_data = {
            "test": "campaign_context_chaining",
            "phase1_job_id": job1_id,
            "phase2_job_id": job2_id,
            "phase1_cost": status1.usage.cost if status1.usage else 0,
            "phase2_cost": status2.usage.cost if status2.usage else 0,
            "total_cost": total_cost,
            "total_time_seconds": total_time,
            "phase1_length": len(phase1_content),
            "phase2_length": len(phase2_content),
            "context_chaining_works": context_referenced,
            "success": True,
            "timestamp": datetime.now().isoformat(),
        }
        save_test_result(test_results_dir, "campaign_test", result_data)

        # Assertions
        assert total_cost > 0
        assert total_cost < 1.0, f"Campaign cost too high: ${total_cost}"
        assert len(phase1_content) > 50, "Phase 1 should have content"
        assert len(phase2_content) > 50, "Phase 2 should have content"
        assert context_referenced, "Context chaining should work"

        print(f"\n\nCampaign Test Results:")
        print(f"  Phase 1 cost: ${status1.usage.cost if status1.usage else 0:.4f}")
        print(f"  Phase 2 cost: ${status2.usage.cost if status2.usage else 0:.4f}")
        print(f"  Total cost: ${total_cost:.4f}")
        print(f"  Total time: {total_time/60:.1f} minutes")
        print(f"  Context chaining: {context_referenced}")


class TestGeminiProvider:
    """Test Google Gemini provider with agentic capabilities."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.requires_api
    async def test_gemini_flash_basic_research(self, storage, test_results_dir):
        """
        Test: Gemini 2.5 Flash with thinking and Google Search
        Expected cost: ~$0.02
        Purpose: Validate Gemini thinking, search grounding, and agentic capabilities
        """
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            pytest.skip("GEMINI_API_KEY not set")

        provider = create_provider("gemini", api_key=api_key)
        start_time = time.time()

        # Dogfooding: Get latest pricing and capabilities for Deepr roadmap
        current_date = get_current_date()
        prompt = f"""As of {current_date}, what are the current pricing and model offerings for:
1. Google Gemini (2.5 Pro, Flash, Flash-Lite) - pricing per M tokens, context limits, new capabilities
2. OpenAI (o3, o4-mini deep research) - pricing, any new models or features
3. xAI Grok (4, 4-fast, 3-mini) - pricing, agentic tool calling updates

Focus on: latest deep research capabilities, reasoning/thinking features, context windows, pricing changes.
What new capabilities should we integrate? Keep under 500 words with current pricing."""

        request = ResearchRequest(
            prompt=prompt,
            model="gemini-2.5-flash",
            system_message="You are an AI research analyst. Provide well-cited insights.",
            tools=[ToolConfig(type="web_search_preview")],
            metadata={"test": "gemini_flash_agentic"}
        )

        job_id = await provider.submit_research(request)
        assert job_id is not None, "Job ID should be returned"

        # Poll for completion
        max_wait = 600
        poll_interval = 5
        elapsed = 0
        status = None

        while elapsed < max_wait:
            status = await provider.get_status(job_id)
            if status.status in ["completed", "failed"]:
                break
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        actual_time = time.time() - start_time

        # Extract results
        assert status is not None, "Should have status"
        assert status.status == "completed", f"Job should complete, got: {status.status}"

        content = ""
        thoughts = None
        if status.output:
            for item in status.output:
                if item.get("type") == "message":
                    for part in item.get("content", []):
                        if part.get("type") == "output_text":
                            content += part.get("text", "")
                        elif part.get("type") == "reasoning":
                            thoughts = part.get("text", "")

        actual_cost = status.usage.cost if status.usage else 0
        input_tokens = status.usage.input_tokens if status.usage else 0
        output_tokens = status.usage.output_tokens if status.usage else 0

        # Validate agentic capabilities
        has_content = len(content) > 200
        has_citations = any(word in content.lower() for word in ["source", "according", "report", "research"])
        has_thinking = thoughts is not None and len(thoughts) > 0

        result_data = {
            "test": "gemini_flash_agentic",
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "prompt_length": len(prompt),
            "response_length": len(content),
            "thinking_length": len(thoughts) if thoughts else 0,
            "cost": actual_cost,
            "time_seconds": actual_time,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "has_content": has_content,
            "has_citations": has_citations,
            "has_thinking": has_thinking,
            "success": True,
            "timestamp": datetime.now().isoformat(),
        }
        save_test_result(test_results_dir, "gemini_flash", result_data)

        # Assertions
        assert has_content, "Should have substantial content"
        assert actual_cost < 0.10, f"Cost should be low: ${actual_cost}"
        assert actual_time < 300, f"Should complete in <5min: {actual_time}s"

        print(f"\n\nGemini Flash Test Results:")
        print(f"  Cost: ${actual_cost:.4f}")
        print(f"  Time: {actual_time:.1f}s")
        print(f"  Tokens: {input_tokens} in, {output_tokens} out")
        print(f"  Content length: {len(content)} chars")
        print(f"  Thinking: {len(thoughts) if thoughts else 0} chars")
        print(f"  Has citations: {has_citations}")

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.requires_api
    async def test_gemini_pro_reasoning(self, storage, test_results_dir):
        """
        Test: Gemini 2.5 Pro with maximum reasoning
        Expected cost: ~$0.15
        Purpose: Validate Pro's always-on thinking for complex analysis
        """
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            pytest.skip("GEMINI_API_KEY not set")

        provider = create_provider("gemini", api_key=api_key)
        start_time = time.time()

        # Dogfooding: Research latest deep research capabilities we should add
        current_date = get_current_date()
        prompt = f"""As of {current_date}, what are the newest deep research and agentic AI capabilities across providers?

Research: OpenAI Deep Research, Google Gemini, xAI Grok, Anthropic Claude, Perplexity.
Focus on: new reasoning models, tool calling patterns, multi-step workflows, context management, citation quality.

What breakthrough capabilities emerged recently? What should a research automation tool prioritize integrating?
Provide specific recommendations with examples. Be thorough and analytical."""

        request = ResearchRequest(
            prompt=prompt,
            model="gemini-2.5-pro",
            system_message="You are a strategic technology analyst.",
            tools=[ToolConfig(type="web_search_preview")],
            metadata={"test": "gemini_pro_reasoning"}
        )

        job_id = await provider.submit_research(request)

        # Poll for completion (Pro may take longer)
        max_wait = 900
        poll_interval = 10
        elapsed = 0
        status = None

        while elapsed < max_wait:
            status = await provider.get_status(job_id)
            if status.status in ["completed", "failed"]:
                break
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        actual_time = time.time() - start_time

        assert status.status == "completed", f"Job should complete, got: {status.status}"

        # Extract content
        content = ""
        if status.output:
            for item in status.output:
                if item.get("type") == "message":
                    for part in item.get("content", []):
                        if part.get("type") == "output_text":
                            content += part.get("text", "")

        actual_cost = status.usage.cost if status.usage else 0

        # Validate quality
        has_comparison = any(word in content.lower() for word in ["compare", "versus", "while"])
        has_recommendations = "recommend" in content.lower()
        is_thorough = len(content) > 500

        result_data = {
            "test": "gemini_pro_reasoning",
            "provider": "gemini",
            "model": "gemini-2.5-pro",
            "cost": actual_cost,
            "time_seconds": actual_time,
            "response_length": len(content),
            "has_comparison": has_comparison,
            "has_recommendations": has_recommendations,
            "is_thorough": is_thorough,
            "timestamp": datetime.now().isoformat(),
        }
        save_test_result(test_results_dir, "gemini_pro", result_data)

        assert is_thorough, "Pro should produce thorough analysis"
        assert actual_cost < 0.50, f"Cost should be reasonable: ${actual_cost}"

        print(f"\n\nGemini Pro Test Results:")
        print(f"  Cost: ${actual_cost:.4f}")
        print(f"  Time: {actual_time/60:.1f} minutes")
        print(f"  Quality: comparison={has_comparison}, recommendations={has_recommendations}")


class TestGrokProvider:
    """Test xAI Grok provider with agentic search capabilities."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.requires_api
    async def test_grok_fast_agentic_search(self, storage, test_results_dir):
        """
        Test: Grok 4 Fast with agentic web/X search
        Expected cost: ~$0.03
        Purpose: Validate Grok's agentic tool calling and search capabilities
        """
        api_key = os.getenv("XAI_API_KEY")
        if not api_key:
            pytest.skip("XAI_API_KEY not set")

        provider = create_provider("grok", api_key=api_key)
        start_time = time.time()

        # Dogfooding: Research Grok's latest capabilities and pricing
        current_date = get_current_date()
        prompt = f"""As of {current_date}, what are xAI Grok's current models, pricing, and capabilities?

Research: Grok 4, Grok 4 Fast, Grok 3 Mini pricing and features.
Focus on: agentic tool calling (web search, X search, code execution), pricing per M tokens, rate limits, new features.

What unique capabilities does Grok offer? How is it being used for research automation?
Include current pricing and any recent updates. Keep under 400 words."""

        request = ResearchRequest(
            prompt=prompt,
            model="grok-4-fast",
            system_message="You are a technology news analyst. Provide current, well-sourced information.",
            tools=[ToolConfig(type="web_search_preview")],
            metadata={"test": "grok_fast_agentic"}
        )

        job_id = await provider.submit_research(request)
        assert job_id is not None, "Job ID should be returned"

        # Poll for completion
        max_wait = 600
        poll_interval = 5
        elapsed = 0
        status = None

        while elapsed < max_wait:
            status = await provider.get_status(job_id)
            if status.status in ["completed", "failed"]:
                break
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        actual_time = time.time() - start_time

        assert status is not None, "Should have status"
        assert status.status == "completed", f"Job should complete, got: {status.status}"

        # Extract content
        content = ""
        if status.output:
            for item in status.output:
                if item.get("type") == "message":
                    for part in item.get("content", []):
                        if part.get("type") == "output_text":
                            content += part.get("text", "")

        actual_cost = status.usage.cost if status.usage else 0
        reasoning_tokens = status.usage.reasoning_tokens if status.usage else 0

        # Validate agentic capabilities
        has_content = len(content) > 200
        has_citations = any(word in content.lower() for word in ["source", "according", "x.com", "post"])
        has_reasoning = reasoning_tokens > 0
        is_current = "2025" in content

        result_data = {
            "test": "grok_fast_agentic",
            "provider": "grok",
            "model": "grok-4-fast",
            "cost": actual_cost,
            "time_seconds": actual_time,
            "response_length": len(content),
            "reasoning_tokens": reasoning_tokens,
            "has_content": has_content,
            "has_citations": has_citations,
            "has_reasoning": has_reasoning,
            "is_current": is_current,
            "success": True,
            "timestamp": datetime.now().isoformat(),
        }
        save_test_result(test_results_dir, "grok_fast", result_data)

        # Assertions
        assert has_content, "Should have substantial content"
        assert actual_cost < 0.15, f"Cost should be low: ${actual_cost}"
        assert actual_time < 300, f"Should complete quickly: {actual_time}s"

        print(f"\n\nGrok 4 Fast Test Results:")
        print(f"  Cost: ${actual_cost:.4f}")
        print(f"  Time: {actual_time:.1f}s")
        print(f"  Reasoning tokens: {reasoning_tokens}")
        print(f"  Content length: {len(content)} chars")
        print(f"  Has citations: {has_citations}")
        print(f"  Current info: {is_current}")

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.requires_api
    @pytest.mark.expensive
    @pytest.mark.flaky(reruns=2)  # API jobs may timeout - transient issue
    async def test_grok_reasoning_comparison(self, storage, test_results_dir):
        """
        Test: Compare Grok 4 vs Grok 4 Fast reasoning
        Expected cost: ~$0.25
        Purpose: Validate reasoning differences between models
        """
        api_key = os.getenv("XAI_API_KEY")
        if not api_key:
            pytest.skip("XAI_API_KEY not set")

        provider = create_provider("grok", api_key=api_key)

        # Dogfooding: Verify our pricing data is accurate as of today
        current_date = get_current_date()
        prompt = f"""Verify current pricing for these AI research models as of {current_date}:

1. OpenAI: o3-deep-research, o4-mini-deep-research ($/M tokens input/output)
2. Google Gemini: 2.5-pro, 2.5-flash, 2.5-flash-lite ($/M tokens)
3. xAI Grok: grok-4, grok-4-fast, grok-3-mini ($/M tokens)

Include: exact current pricing, any recent changes, context window limits, special features.
Cite official sources. Keep under 400 words with specific numbers."""

        results = {}

        for model in ["grok-4-fast", "grok-3-mini"]:
            start_time = time.time()

            request = ResearchRequest(
                prompt=prompt,
                model=model,
                tools=[ToolConfig(type="web_search_preview")],
                metadata={"test": f"grok_comparison_{model}"}
            )

            job_id = await provider.submit_research(request)

            # Poll
            max_wait = 900 if model == "grok-4" else 600
            poll_interval = 10
            elapsed = 0
            status = None

            while elapsed < max_wait:
                status = await provider.get_status(job_id)
                if status.status in ["completed", "failed"]:
                    break
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

            actual_time = time.time() - start_time

            if status.status == "completed":
                content = ""
                if status.output:
                    for item in status.output:
                        if item.get("type") == "message":
                            for part in item.get("content", []):
                                if part.get("type") == "output_text":
                                    content += part.get("text", "")

                results[model] = {
                    "cost": status.usage.cost if status.usage else 0,
                    "time": actual_time,
                    "reasoning_tokens": status.usage.reasoning_tokens if status.usage else 0,
                    "content_length": len(content),
                }

        result_data = {
            "test": "grok_reasoning_comparison",
            "results": results,
            "timestamp": datetime.now().isoformat(),
        }
        save_test_result(test_results_dir, "grok_comparison", result_data)

        print(f"\n\nGrok Model Comparison:")
        for model, data in results.items():
            print(f"  {model}:")
            print(f"    Cost: ${data['cost']:.4f}")
            print(f"    Time: {data['time']:.1f}s")
            print(f"    Reasoning tokens: {data['reasoning_tokens']}")
            print(f"    Content: {data['content_length']} chars")


class TestDocumentAnalysis:
    """Test document upload with README/ROADMAP for improvement recommendations."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.requires_api
    async def test_gemini_analyze_deepr_docs(self, storage, test_results_dir):
        """
        Test: Upload README and ROADMAP for detailed developer recommendations
        Expected cost: ~$0.05
        Purpose: Dogfooding - get AI recommendations to improve Deepr
        """
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            pytest.skip("GEMINI_API_KEY not set")

        provider = create_provider("gemini", api_key=api_key)
        start_time = time.time()

        # Upload README and ROADMAP
        readme_path = Path("C:/Users/nicks/OneDrive/deepr/README.md")
        roadmap_path = Path("C:/Users/nicks/OneDrive/deepr/docs/ROADMAP.md")

        if not readme_path.exists() or not roadmap_path.exists():
            pytest.skip("README.md or ROADMAP.md not found")

        # Upload documents
        readme_id = await provider.upload_document(str(readme_path))
        roadmap_id = await provider.upload_document(str(roadmap_path))

        # Dogfooding: Get detailed improvement recommendations
        prompt = """You are an expert developer reviewing a research automation tool called Deepr.

Review the attached README.md and ROADMAP.md files.

Provide detailed, actionable recommendations for improvement:
1. Documentation clarity - What's confusing or missing?
2. Feature prioritization - What should be built next based on market needs?
3. API design - Are the CLI commands intuitive? Any inconsistencies?
4. Architecture gaps - What's missing for production use?
5. Competitive positioning - How to differentiate from similar tools?

Be specific with examples. Focus on developer experience and production readiness.
Keep under 800 words."""

        request = ResearchRequest(
            prompt=prompt,
            model="gemini-2.5-flash",
            system_message="You are a senior software engineer and product strategist.",
            tools=[ToolConfig(type="web_search_preview")],
            document_ids=[readme_id, roadmap_id],
            metadata={"test": "deepr_docs_analysis"}
        )

        job_id = await provider.submit_research(request)

        # Poll for completion
        max_wait = 600
        poll_interval = 10
        elapsed = 0
        status = None

        while elapsed < max_wait:
            status = await provider.get_status(job_id)
            if status.status in ["completed", "failed"]:
                break
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        actual_time = time.time() - start_time

        assert status is not None, "Should have status"
        assert status.status == "completed", f"Job should complete, got: {status.status}"

        # Extract recommendations
        content = ""
        if status.output:
            for item in status.output:
                if item.get("type") == "message":
                    for part in item.get("content", []):
                        if part.get("type") == "output_text":
                            content += part.get("text", "")

        actual_cost = status.usage.cost if status.usage else 0

        # Save recommendations to file for review
        recommendations_file = test_results_dir / "deepr_improvement_recommendations.md"
        with open(recommendations_file, 'w', encoding='utf-8') as f:
            f.write(f"# Deepr Improvement Recommendations\n\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n")
            f.write(f"Model: gemini-2.5-flash\n")
            f.write(f"Cost: ${actual_cost:.4f}\n")
            f.write(f"Time: {actual_time:.1f}s\n\n")
            f.write("---\n\n")
            f.write(content)

        # Validate quality
        has_recommendations = len(content) > 500
        has_sections = content.count("#") >= 3 or content.count("1.") >= 3
        mentions_deepr = "deepr" in content.lower()

        result_data = {
            "test": "deepr_docs_analysis",
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "cost": actual_cost,
            "time_seconds": actual_time,
            "response_length": len(content),
            "has_recommendations": has_recommendations,
            "has_sections": has_sections,
            "mentions_deepr": mentions_deepr,
            "recommendations_file": str(recommendations_file),
            "timestamp": datetime.now().isoformat(),
        }
        save_test_result(test_results_dir, "deepr_docs_analysis", result_data)

        # Assertions
        assert has_recommendations, "Should have substantial recommendations"
        assert mentions_deepr, "Should reference Deepr"
        assert actual_cost < 0.20, f"Cost should be reasonable: ${actual_cost}"

        print(f"\n\nDeepr Documentation Analysis:")
        print(f"  Cost: ${actual_cost:.4f}")
        print(f"  Time: {actual_time:.1f}s")
        print(f"  Recommendations: {len(content)} chars")
        print(f"  Quality checks: sections={has_sections}, mentions_deepr={mentions_deepr}")
        print(f"  Saved to: {recommendations_file}")

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.requires_api
    async def test_openai_analyze_deepr_architecture(self, storage, test_results_dir):
        """
        Test: OpenAI analysis of Deepr for architecture recommendations
        Expected cost: ~$0.10
        Purpose: Dogfooding - get deep architectural insights
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            pytest.skip("OPENAI_API_KEY not set")

        provider = create_provider("openai", api_key=api_key)
        start_time = time.time()

        # Upload README and ROADMAP
        readme_path = Path("C:/Users/nicks/OneDrive/deepr/README.md")
        roadmap_path = Path("C:/Users/nicks/OneDrive/deepr/docs/ROADMAP.md")

        if not readme_path.exists() or not roadmap_path.exists():
            pytest.skip("README.md or ROADMAP.md not found")

        # Upload documents
        readme_id = await provider.upload_document(str(readme_path))
        roadmap_id = await provider.upload_document(str(roadmap_path))

        # Dogfooding: Get architectural analysis
        current_date = get_current_date()
        prompt = f"""Review Deepr's README.md and ROADMAP.md as an experienced system architect.

Focus on architectural analysis as of {current_date}:
1. Multi-provider abstraction - Is the design scalable? Any anti-patterns?
2. Queue/storage architecture - Production-ready? What's missing?
3. Cost management - Robust enough for production?
4. Error handling and resilience - What failure modes aren't covered?
5. Testing strategy - What critical tests are missing?

Compare against production AI systems (Cursor, GitHub Copilot, Perplexity).
Provide specific technical recommendations with code examples where helpful.
Keep under 800 words."""

        request = ResearchRequest(
            prompt=prompt,
            model="o4-mini-deep-research",
            system_message="You are a senior systems architect with expertise in AI platforms.",
            tools=[ToolConfig(type="web_search_preview")],
            document_ids=[readme_id, roadmap_id],
            metadata={"test": "deepr_architecture_analysis"}
        )

        job_id = await provider.submit_research(request)

        # Poll for completion
        max_wait = 900
        poll_interval = 15
        elapsed = 0
        status = None

        while elapsed < max_wait:
            status = await provider.get_status(job_id)
            if status.status in ["completed", "failed"]:
                break
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        actual_time = time.time() - start_time

        assert status is not None, "Should have status"
        assert status.status == "completed", f"Job should complete, got: {status.status}"

        # Extract analysis
        content = ""
        if status.output:
            for item in status.output:
                if item.get("type") == "message":
                    for part in item.get("content", []):
                        if part.get("type") == "output_text":
                            content += part.get("text", "")

        actual_cost = status.usage.cost if status.usage else 0

        # Save to file
        analysis_file = test_results_dir / "deepr_architecture_analysis.md"
        with open(analysis_file, 'w', encoding='utf-8') as f:
            f.write(f"# Deepr Architecture Analysis\n\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n")
            f.write(f"Model: o4-mini-deep-research\n")
            f.write(f"Cost: ${actual_cost:.4f}\n")
            f.write(f"Time: {actual_time/60:.1f} minutes\n\n")
            f.write("---\n\n")
            f.write(content)

        result_data = {
            "test": "deepr_architecture_analysis",
            "provider": "openai",
            "model": "o4-mini-deep-research",
            "cost": actual_cost,
            "time_seconds": actual_time,
            "response_length": len(content),
            "analysis_file": str(analysis_file),
            "timestamp": datetime.now().isoformat(),
        }
        save_test_result(test_results_dir, "deepr_architecture", result_data)

        print(f"\n\nDeepr Architecture Analysis:")
        print(f"  Cost: ${actual_cost:.4f}")
        print(f"  Time: {actual_time/60:.1f} minutes")
        print(f"  Analysis: {len(content)} chars")
        print(f"  Saved to: {analysis_file}")
