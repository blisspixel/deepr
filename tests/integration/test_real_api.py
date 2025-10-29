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
from pathlib import Path
from datetime import datetime
from deepr.providers import create_provider
from deepr.providers.base import ResearchRequest, ToolConfig
from deepr.storage import create_storage
from deepr.queue import create_queue
from deepr.core.costs import CostEstimator


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

        # Estimate cost
        prompt = "What is 2+2? Answer in exactly one sentence."
        estimate = CostEstimator.estimate_cost(
            prompt=prompt,
            model="o4-mini-deep-research",
            enable_web_search=True
        )

        # Submit research
        request = ResearchRequest(
            prompt=prompt,
            model="o4-mini-deep-research",
            system_message="You are concise. Answer in one sentence only.",
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

        prompt = """As of October 2025, what are the top 3 AI code editors?
        Include: (1) Brief description, (2) Key features, (3) Pricing.
        Keep response under 500 words."""

        estimate = CostEstimator.estimate_cost(
            prompt=prompt,
            model="o4-mini-deep-research",
            enable_web_search=True
        )

        request = ResearchRequest(
            prompt=prompt,
            model="o4-mini-deep-research",
            system_message="You are a helpful research assistant.",
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

        # Research with file context
        prompt = "Based on the uploaded document, what is the product's pricing model?"

        request = ResearchRequest(
            prompt=prompt,
            model="o4-mini-deep-research",
            system_message="You are a helpful research assistant.",
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
    async def test_cost_estimation_accuracy(self, provider, test_results_dir):
        """
        Test: Compare estimated costs to actual costs
        Expected cost: ~$0.05
        Purpose: Validate CostEstimator accuracy for future improvements
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
