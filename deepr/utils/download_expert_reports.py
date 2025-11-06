"""Download and save all reports from an expert's research jobs."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from deepr.experts.profile import ExpertStore
from deepr.providers.openai_provider import OpenAIProvider
from deepr.core.reports import ReportGenerator


async def download_reports(expert_name: str, output_dir: str = "expert_reports"):
    """Download all research reports for an expert."""
    # Load expert
    store = ExpertStore()
    expert = store.load(expert_name)

    if not expert:
        print(f"ERROR: Expert '{expert_name}' not found")
        return

    print(f"Expert: {expert.name}")
    print(f"Research jobs: {len(expert.research_jobs)}")
    print(f"Documents in vector store: {expert.total_documents}")
    print()

    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    # Initialize provider and report generator
    provider = OpenAIProvider()
    report_gen = ReportGenerator()

    # Download each report
    for i, job_id in enumerate(expert.research_jobs, 1):
        print(f"{i}/{len(expert.research_jobs)}: {job_id[:20]}...")

        try:
            # Get report from OpenAI
            response = await provider.get_status(job_id)

            # Extract text
            raw_text = report_gen.extract_text_from_response(response)

            if not raw_text:
                print(f"  [SKIP] No content found")
                continue

            # Save to file
            filename = f"research_{job_id[:12]}.md"
            filepath = output_path / filename
            filepath.write_text(raw_text, encoding='utf-8')

            print(f"  [OK] Saved to {filepath}")
            print(f"       Size: {len(raw_text)} chars")

        except Exception as e:
            print(f"  [ERROR] {str(e)}")

    print()
    print(f"Reports saved to: {output_path.absolute()}")


if __name__ == "__main__":
    expert_name = sys.argv[1] if len(sys.argv) > 1 else "Agentic Digital Consciousness"
    asyncio.run(download_reports(expert_name))
