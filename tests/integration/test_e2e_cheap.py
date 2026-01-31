"""
End-to-end test for Deepr using cheap prompts.

This test validates the entire pipeline:
1. Job submission
2. Queue persistence
3. Provider API call
4. Result storage
5. Cost tracking

Uses minimal prompts to keep costs under $1.
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from deepr.queue import create_queue
from deepr.queue.base import ResearchJob, JobStatus
from deepr.storage import create_storage
from deepr.providers import create_provider
from deepr.providers.base import ToolConfig
from deepr.config import load_config

# Import test prompts
test_dir = Path(__file__).parent
sys.path.insert(0, str(test_dir))
from cheap_test_prompts import CHEAP_PROMPTS, TEST_CONFIG


class E2ETestRunner:
    """End-to-end test runner."""

    def __init__(self, skip_provider=False):
        """Initialize test components."""
        self.config = load_config()

        # Use test database
        self.test_db = "tests/test_queue.db"
        self.test_results = "tests/test_results"

        # Initialize components
        self.queue = create_queue("local", db_path=self.test_db)
        self.storage = create_storage("local", base_path=self.test_results)

        # Only initialize provider if not skipping
        if not skip_provider:
            api_key = self.config.get("api_key") or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OpenAI API key required for provider tests. Use --skip-provider to skip.")
            self.provider = create_provider(
                self.config.get("provider", "openai"),
                api_key=api_key
            )
        else:
            self.provider = None

        self.results = []

    async def test_queue_operations(self):
        """Test basic queue operations."""
        print("\n=== Testing Queue Operations ===")

        # Create test job
        job = ResearchJob(
            id=str(uuid.uuid4()),
            prompt="Test prompt",
            model=TEST_CONFIG["model"],
            status=JobStatus.QUEUED,
            submitted_at=datetime.utcnow(),
            cost_limit=TEST_CONFIG["max_cost_per_job"],
        )

        # Enqueue
        print(f"Enqueuing job {job.id}...")
        job_id = await self.queue.enqueue(job)
        assert job_id == job.id, "Job ID mismatch"
        print(f"[OK] Job enqueued: {job_id}")

        # Get job
        retrieved = await self.queue.get_job(job_id)
        assert retrieved is not None, "Job not found"
        assert retrieved.prompt == job.prompt, "Prompt mismatch"
        print(f"[OK] Job retrieved: {retrieved.id}")

        # List jobs
        jobs = await self.queue.list_jobs(status=JobStatus.QUEUED)
        assert len(jobs) > 0, "No jobs in queue"
        print(f"[OK] Found {len(jobs)} queued jobs")

        # Get stats
        stats = await self.queue.get_queue_stats()
        print(f"[OK] Queue stats: {stats}")

        return True

    async def test_storage_operations(self):
        """Test storage operations."""
        print("\n=== Testing Storage Operations ===")

        job_id = str(uuid.uuid4())
        filename = "test_report.md"
        content = b"# Test Report\n\nThis is a test report."

        # Save report
        print(f"Saving report for job {job_id}...")
        metadata = await self.storage.save_report(
            job_id=job_id,
            filename=filename,
            content=content,
            content_type="text/markdown",
        )
        print(f"[OK] Report saved: {metadata.filename} ({metadata.size_bytes} bytes)")

        # Retrieve report
        retrieved = await self.storage.get_report(job_id, filename)
        assert retrieved == content, "Content mismatch"
        print(f"[OK] Report retrieved: {len(retrieved)} bytes")

        # Check exists
        exists = await self.storage.report_exists(job_id, filename)
        assert exists, "Report should exist"
        print(f"[OK] Report exists check passed")

        # List reports
        reports = await self.storage.list_reports(job_id=job_id)
        assert len(reports) > 0, "No reports found"
        print(f"[OK] Found {len(reports)} reports")

        # Cleanup test report
        await self.storage.delete_report(job_id)
        print(f"[OK] Test report cleaned up")

        return True

    async def test_provider_submission(self):
        """Test provider API submission (COSTS MONEY - uses cheapest prompt)."""
        print("\n=== Testing Provider Submission (COSTS MONEY!) ===")
        print(f"Model: {TEST_CONFIG['model']}")
        print(f"Max cost: ${TEST_CONFIG['max_cost_per_job']}")

        from deepr.providers.base import ResearchRequest

        # Use the cheapest test prompt
        prompt = CHEAP_PROMPTS[0]  # Haiku
        print(f"\nPrompt: {prompt}")

        # Create request with web search tool
        request = ResearchRequest(
            prompt=prompt,
            model=TEST_CONFIG["model"],
            system_message="You are a helpful AI research assistant. Provide concise, accurate responses.",
            tools=[ToolConfig(type="web_search_preview")],
            background=True,  # Submit in background
        )

        # Submit
        print("\nSubmitting to provider...")
        try:
            job_id = await self.provider.submit_research(request)
            print(f"[OK] Job submitted: {job_id}")

            # Poll for completion (with timeout)
            print("Polling for completion (timeout: 60s)...")
            max_polls = 20  # 20 * 3s = 60s
            poll_count = 0

            while poll_count < max_polls:
                await asyncio.sleep(3)
                poll_count += 1

                status = await self.provider.get_status(job_id)
                print(f"  Poll {poll_count}: {status}")

                if status == "completed":
                    print("[OK] Job completed!")

                    # Get result
                    result = await self.provider.get_result(job_id)
                    print(f"\nResult preview:")
                    print(f"  Content length: {len(result.content)} chars")
                    print(f"  Cost: ${result.usage.cost:.4f}")
                    print(f"  Tokens: {result.usage.total_tokens}")

                    return True

                elif status == "failed":
                    print("[FAIL] Job failed!")
                    return False

            print(f"[WARN] Timeout after {max_polls * 3}s")
            return False

        except Exception as e:
            print(f"[FAIL] Error: {e}")
            return False

    async def test_full_pipeline(self):
        """Test complete end-to-end pipeline."""
        print("\n=== Testing Full Pipeline (COSTS MONEY!) ===")

        from deepr.providers.base import ResearchRequest

        # Create job
        job_id = str(uuid.uuid4())
        prompt = CHEAP_PROMPTS[1]  # Cost optimization benefits

        print(f"Job ID: {job_id}")
        print(f"Prompt: {prompt}")

        # 1. Create and enqueue job
        job = ResearchJob(
            id=job_id,
            prompt=prompt,
            model=TEST_CONFIG["model"],
            status=JobStatus.QUEUED,
            submitted_at=datetime.utcnow(),
            cost_limit=TEST_CONFIG["max_cost_per_job"],
        )

        print("\n1. Enqueuing job...")
        await self.queue.enqueue(job)
        print("[OK] Job enqueued")

        # 2. Submit to provider
        print("\n2. Submitting to provider...")
        request = ResearchRequest(
            prompt=prompt,
            model=TEST_CONFIG["model"],
            system_message="You are a helpful AI research assistant. Provide concise, accurate responses.",
            tools=[ToolConfig(type="web_search_preview")],
            background=True,
        )

        provider_job_id = await self.provider.submit_research(request)
        print(f"[OK] Submitted: {provider_job_id}")

        # Update job with provider ID
        await self.queue.update_status(
            job_id=job_id,
            status=JobStatus.PROCESSING,
            provider_job_id=provider_job_id,
        )
        print("[OK] Job status updated to processing")

        # 3. Poll for completion
        print("\n3. Polling for completion...")
        max_polls = 20
        poll_count = 0

        while poll_count < max_polls:
            await asyncio.sleep(3)
            poll_count += 1

            status = await self.provider.get_status(provider_job_id)
            print(f"  Poll {poll_count}: {status}")

            if status == "completed":
                # 4. Get result
                print("\n4. Retrieving result...")
                result = await self.provider.get_result(provider_job_id)
                print(f"[OK] Result retrieved ({len(result.content)} chars)")

                # 5. Save to storage
                print("\n5. Saving to storage...")
                await self.storage.save_report(
                    job_id=job_id,
                    filename="report.md",
                    content=result.content.encode("utf-8"),
                    content_type="text/markdown",
                )
                print("[OK] Report saved")

                # 6. Update queue
                print("\n6. Updating queue...")
                await self.queue.update_results(
                    job_id=job_id,
                    report_paths={"markdown": "report.md"},
                    cost=result.usage.cost,
                    tokens_used=result.usage.total_tokens,
                )
                await self.queue.update_status(job_id, JobStatus.COMPLETED)
                print("[OK] Queue updated")

                # 7. Verify
                print("\n7. Verifying...")
                final_job = await self.queue.get_job(job_id)
                assert final_job.status == JobStatus.COMPLETED
                assert final_job.cost is not None
                print(f"[OK] Final cost: ${final_job.cost:.4f}")
                print(f"[OK] Tokens used: {final_job.tokens_used}")

                return True

            elif status == "failed":
                print("\n[FAIL] Job failed")
                await self.queue.update_status(job_id, JobStatus.FAILED)
                return False

        print(f"\n[WARN] Timeout after {max_polls * 3}s")
        return False

    async def run_all_tests(self, skip_provider=False):
        """Run all tests."""
        print("=" * 60)
        print("Deepr End-to-End Test Suite")
        print("=" * 60)

        results = {}

        # Test 1: Queue operations (free)
        try:
            results["queue"] = await self.test_queue_operations()
        except Exception as e:
            print(f"\n[FAIL] Queue test failed: {e}")
            results["queue"] = False

        # Test 2: Storage operations (free)
        try:
            results["storage"] = await self.test_storage_operations()
        except Exception as e:
            print(f"\n[FAIL] Storage test failed: {e}")
            results["storage"] = False

        if not skip_provider:
            # Test 3: Provider submission (costs money)
            try:
                results["provider"] = await self.test_provider_submission()
            except Exception as e:
                print(f"\n[FAIL] Provider test failed: {e}")
                results["provider"] = False

            # Test 4: Full pipeline (costs money)
            try:
                results["pipeline"] = await self.test_full_pipeline()
            except Exception as e:
                print(f"\n[FAIL] Pipeline test failed: {e}")
                results["pipeline"] = False
        else:
            print("\n[SKIP] Skipping provider tests (--skip-provider flag)")
            results["provider"] = None
            results["pipeline"] = None

        # Summary
        print("\n" + "=" * 60)
        print("Test Summary")
        print("=" * 60)
        for test_name, result in results.items():
            if result is True:
                print(f"[OK] {test_name}: PASSED")
            elif result is False:
                print(f"[FAIL] {test_name}: FAILED")
            else:
                print(f"[SKIP] {test_name}: SKIPPED")

        passed = sum(1 for r in results.values() if r is True)
        failed = sum(1 for r in results.values() if r is False)
        skipped = sum(1 for r in results.values() if r is None)

        print(f"\nTotal: {passed} passed, {failed} failed, {skipped} skipped")

        return failed == 0


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run Deepr end-to-end tests")
    parser.add_argument(
        "--skip-provider",
        action="store_true",
        help="Skip provider tests (no API calls, no cost)",
    )
    args = parser.parse_args()

    runner = E2ETestRunner(skip_provider=args.skip_provider)
    success = await runner.run_all_tests(skip_provider=args.skip_provider)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
