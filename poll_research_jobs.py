"""Poll deep research jobs and retrieve results when complete."""
import asyncio
import os
import sys
from datetime import datetime
from openai import AsyncOpenAI
from deepr.experts.profile import ExpertStore
from deepr.providers.openai_provider import OpenAIProvider
from deepr.core.research import ResearchOrchestrator
from deepr.storage.local import LocalStorage
from deepr.core.documents import DocumentManager
from deepr.core.reports import ReportGenerator


async def poll_and_retrieve_research(expert_name: str, check_interval: int = 30):
    """Poll research jobs for an expert and retrieve results when complete.

    Args:
        expert_name: Name of the expert
        check_interval: Seconds between status checks
    """
    # Load expert
    store = ExpertStore()
    expert = store.load(expert_name)

    if not expert:
        print(f"Error: Expert '{expert_name}' not found")
        return

    if not expert.research_jobs:
        print(f"Expert '{expert_name}' has no research jobs tracked")
        return

    print(f"=" * 70)
    print(f"  Monitoring Deep Research Jobs for: {expert_name}")
    print(f"=" * 70)
    print(f"Jobs to monitor: {len(expert.research_jobs)}")
    print(f"Check interval: {check_interval}s")
    print()

    # Initialize provider
    provider = OpenAIProvider()

    # Track job statuses
    pending_jobs = set(expert.research_jobs)
    completed_jobs = set()
    failed_jobs = set()

    start_time = datetime.now()

    while pending_jobs:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Checking job statuses...")
        print(f"Pending: {len(pending_jobs)}, Completed: {len(completed_jobs)}, Failed: {len(failed_jobs)}")

        for job_id in list(pending_jobs):
            try:
                response = await provider.get_status(job_id)

                if response.status == "completed":
                    print(f"  ✓ {job_id[:20]}... COMPLETED")
                    pending_jobs.remove(job_id)
                    completed_jobs.add(job_id)

                    # Extract and print summary
                    if response.usage:
                        print(f"    Cost: ${response.usage.cost:.4f}")
                        print(f"    Tokens: {response.usage.total_tokens:,}")

                elif response.status == "failed" or response.status == "cancelled":
                    print(f"  ✗ {job_id[:20]}... FAILED/CANCELLED")
                    print(f"    Error: {response.error}")
                    pending_jobs.remove(job_id)
                    failed_jobs.add(job_id)

                elif response.status in ["in_progress", "queued"]:
                    print(f"  ⋯ {job_id[:20]}... {response.status.upper()}")

                else:
                    print(f"  ? {job_id[:20]}... Unknown status: {response.status}")

            except Exception as e:
                print(f"  ! {job_id[:20]}... Error checking status: {e}")

        if pending_jobs:
            elapsed = (datetime.now() - start_time).total_seconds() / 60
            print(f"\nElapsed time: {elapsed:.1f} minutes")
            print(f"Waiting {check_interval}s before next check...")
            await asyncio.sleep(check_interval)

    # Summary
    print("\n" + "=" * 70)
    print("  Research Jobs Complete")
    print("=" * 70)
    print(f"Total jobs: {len(expert.research_jobs)}")
    print(f"Completed: {len(completed_jobs)}")
    print(f"Failed: {len(failed_jobs)}")
    elapsed_total = (datetime.now() - start_time).total_seconds() / 60
    print(f"Total time: {elapsed_total:.1f} minutes")

    if completed_jobs:
        print("\n" + "=" * 70)
        print("  Retrieving Research Reports")
        print("=" * 70)

        # Initialize orchestrator for report retrieval
        storage = LocalStorage()
        doc_manager = DocumentManager()
        report_gen = ReportGenerator()
        orchestrator = ResearchOrchestrator(
            provider=provider,
            storage=storage,
            document_manager=doc_manager,
            report_generator=report_gen
        )

        total_cost = 0.0

        for job_id in completed_jobs:
            try:
                print(f"\n[{job_id[:20]}...] Retrieving report...")

                # Get job response
                response = await provider.get_status(job_id)

                # Save the report
                await orchestrator.process_completion(
                    job_id=job_id,
                    append_references=True,
                    output_formats=["md", "txt"]
                )

                if response.usage:
                    total_cost += response.usage.cost
                    print(f"  Cost: ${response.usage.cost:.4f}")

                print(f"  ✓ Report saved")

            except Exception as e:
                print(f"  ✗ Error retrieving report: {e}")

        print("\n" + "=" * 70)
        print(f"Total research cost: ${total_cost:.2f}")
        print("=" * 70)
        print(f"\nReports saved to: {storage.base_path}")
        print(f"\nNext steps:")
        print(f"  1. Review reports: deepr jobs list")
        print(f"  2. Chat with expert: deepr expert chat '{expert_name}'")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python poll_research_jobs.py <expert_name> [check_interval_seconds]")
        sys.exit(1)

    expert_name = sys.argv[1]
    check_interval = int(sys.argv[2]) if len(sys.argv) > 2 else 30

    asyncio.run(poll_and_retrieve_research(expert_name, check_interval))
