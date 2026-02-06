"""Manually integrate completed research for existing experts."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from deepr.config import load_config
from deepr.experts.learner import AutonomousLearner
from deepr.experts.profile import ExpertStore


async def integrate_expert_research(expert_name: str):
    """Integrate completed research for an existing expert."""
    # Load expert
    store = ExpertStore()
    expert = store.load(expert_name)

    if not expert:
        print(f"ERROR: Expert '{expert_name}' not found")
        return

    if not expert.research_jobs:
        print("Expert has no research jobs")
        return

    print(f"Expert: {expert_name}")
    print(f"Research jobs: {len(expert.research_jobs)}")
    print(f"Current documents: {expert.total_documents}")
    print()

    # Create learner
    config = load_config()
    learner = AutonomousLearner(config)

    # Run polling and integration
    print("Starting integration...")
    await learner._poll_and_integrate_reports(expert=expert, job_ids=expert.research_jobs, callback=None)

    # Reload to show updated counts
    expert = store.load(expert_name)
    print()
    print(f"DONE! Expert now has {expert.total_documents} documents")


if __name__ == "__main__":
    expert_name = sys.argv[1] if len(sys.argv) > 1 else "Agentic Digital Consciousness"
    asyncio.run(integrate_expert_research(expert_name))
