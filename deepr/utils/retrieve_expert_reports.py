"""Utility to retrieve completed research reports for an expert."""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from deepr.experts.profile import ExpertStore
from deepr.providers.openai_provider import OpenAIProvider
from deepr.core.research import ResearchOrchestrator
from deepr.storage.local import LocalStorage
from deepr.core.documents import DocumentManager
from deepr.core.reports import ReportGenerator


async def retrieve_reports(expert_name: str):
    """Retrieve all completed research reports for an expert."""
    # Load expert
    store = ExpertStore()
    expert = store.load(expert_name)

    if not expert or not expert.research_jobs:
        print(f"ERROR: Expert '{expert_name}' not found or has no research jobs")
        return

    print("=" * 70)
    print(f"  Retrieving Research Reports: {expert_name}")
    print("=" * 70)
    print(f"Jobs: {len(expert.research_jobs)}")
    print(f"Vector Store: {expert.vector_store_id}")
    print()

    # Initialize
    provider = OpenAIProvider()
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
    completed = 0
    failed = 0

    for i, job_id in enumerate(expert.research_jobs, 1):
        print(f"{i}/{len(expert.research_jobs)}: {job_id[:20]}...")
        try:
            # Check status
            response = await provider.get_status(job_id)

            if response.status == "completed":
                # Save report
                await orchestrator.process_completion(
                    job_id=job_id,
                    append_references=True,
                    output_formats=["md", "txt"]
                )

                if response.usage:
                    cost = response.usage.cost
                    total_cost += cost
                    print(f"  [OK] Cost: ${cost:.4f}")
                else:
                    print(f"  [OK] Retrieved")

                completed += 1
            elif response.status in ["failed", "cancelled"]:
                print(f"  [FAILED] {response.error}")
                failed += 1
            else:
                print(f"  [SKIP] Status: {response.status}")

        except Exception as e:
            print(f"  [ERROR] {str(e)}")
            failed += 1

    print()
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"Completed: {completed}/{len(expert.research_jobs)}")
    print(f"Failed: {failed}/{len(expert.research_jobs)}")
    print(f"Total cost: ${total_cost:.2f}")
    print(f"Estimated: $10.00")
    if total_cost > 0:
        variance = ((total_cost - 10.0) / 10.0) * 100
        print(f"Variance: {variance:+.1f}%")
    print()
    print(f"Reports saved to: {storage.base_path}")


if __name__ == "__main__":
    expert_name = sys.argv[1] if len(sys.argv) > 1 else "Agentic Digital Consciousness"
    asyncio.run(retrieve_reports(expert_name))
