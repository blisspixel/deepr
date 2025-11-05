"""Semantic command interface - intent-based commands for natural workflows.

This module provides natural, intent-based commands that map to the underlying
implementation commands in run.py. Users think in terms of "I want to research X"
not "Should I use focus or docs mode?".

Command mapping:
    deepr research  -> Automatically chooses between run focus/docs based on prompt
    deepr learn     -> Maps to run project (multi-phase learning)
    deepr team      -> Maps to run team (multi-perspective analysis)

All flags from the underlying commands are supported.
"""

import click
import asyncio
from typing import Optional
from deepr.cli.commands.run import _run_single, _run_campaign, _run_team


def detect_research_mode(prompt: str) -> str:
    """Auto-detect whether this is documentation research or focused research.

    Returns:
        "docs" if prompt seems documentation-oriented, "focus" otherwise
    """
    # Keywords that suggest documentation intent
    doc_keywords = [
        "document", "documentation", "docs", "guide", "tutorial",
        "how to", "explain", "api", "reference", "spec", "specification",
        "architecture", "design doc", "readme", "manual"
    ]

    prompt_lower = prompt.lower()

    # Check if prompt contains documentation-related keywords
    for keyword in doc_keywords:
        if keyword in prompt_lower:
            return "docs"

    # Default to focused research
    return "focus"


@click.command()
@click.argument("query")
@click.option("--model", "-m", default="o4-mini-deep-research", help="Research model to use")
@click.option("--provider", "-p", default="openai",
              type=click.Choice(["openai", "azure", "gemini", "grok"]),
              help="Research provider (openai, azure, gemini, grok)")
@click.option("--no-web", is_flag=True, help="Disable web search")
@click.option("--no-code", is_flag=True, help="Disable code interpreter")
@click.option("--upload", "-u", multiple=True, help="Upload files for context")
@click.option("--limit", "-l", type=float, help="Cost limit in dollars")
@click.option("--yes", "-y", is_flag=True, help="Skip budget confirmation")
@click.option("--mode", type=click.Choice(["focus", "docs", "auto"]), default="auto",
              help="Research mode (auto=detect automatically)")
def research(
    query: str,
    model: str,
    provider: str,
    no_web: bool,
    no_code: bool,
    upload: tuple,
    limit: Optional[float],
    yes: bool,
    mode: str,
):
    """Run research with automatic mode detection.

    Automatically detects whether you need focused research or documentation
    research based on your query. You can override with --mode.

    Examples:
        deepr research "Analyze AI code editor market 2025"
        deepr research "Document the authentication flow" --mode docs
        deepr research "Latest quantum computing trends" -m o3-deep-research
        deepr research "Company analysis" --upload data.csv --limit 5.00
        deepr research "Query" --provider gemini -m gemini-2.5-flash
    """
    # Auto-detect mode if set to auto
    if mode == "auto":
        detected_mode = detect_research_mode(query)
        click.echo(f"[Auto-detected mode: {detected_mode}]")
    else:
        detected_mode = mode

    # Modify query for docs mode to optimize for documentation
    if detected_mode == "docs":
        if not query.lower().startswith("create") and not query.lower().startswith("document"):
            query = f"Create comprehensive documentation for: {query}"

    # Call the underlying _run_single implementation
    asyncio.run(_run_single(query, model, provider, no_web, no_code, upload, limit, yes))


@click.command()
@click.argument("topic")
@click.option("--model", "-m", default="o4-mini-deep-research", help="Research model")
@click.option("--lead", default="gpt-5", help="Lead planner model")
@click.option("--phases", "-p", type=int, default=3, help="Number of learning phases")
@click.option("--yes", "-y", is_flag=True, help="Skip budget confirmation")
def learn(
    topic: str,
    model: str,
    lead: str,
    phases: int,
    yes: bool,
):
    """Learn about a topic through multi-phase research.

    Creates a structured learning path with multiple research phases that build
    on each other. Perfect for deep-diving into new technologies, concepts, or domains.

    Examples:
        deepr learn "Ford EV strategy for 2026"
        deepr learn "Azure Landing Zones" --phases 4
        deepr learn "Rust programming language" -m o3-deep-research
        deepr learn "Machine learning fundamentals"
    """
    click.echo(f"[Learning Mode: Multi-phase research with {phases} phases]")
    asyncio.run(_run_campaign(topic, model, lead, phases, yes))


@click.command()
@click.argument("question")
@click.option("--model", "-m", default="o4-mini-deep-research", help="Research model")
@click.option("--perspectives", "-p", type=int, default=6, help="Number of perspectives")
@click.option("--yes", "-y", is_flag=True, help="Skip budget confirmation")
def team(
    question: str,
    model: str,
    perspectives: int,
    yes: bool,
):
    """Analyze a question from multiple perspectives (dream team).

    Uses Six Thinking Hats methodology to analyze the question from different
    angles simultaneously. Perfect for complex decisions, strategic questions,
    or situations that need diverse viewpoints.

    Examples:
        deepr team "Should we pivot to enterprise?"
        deepr team "Evaluate merger opportunity" --perspectives 8
        deepr team "Technology decision" -m o3-deep-research
    """
    click.echo(f"[Team Mode: {perspectives} perspectives analyzing in parallel]")
    asyncio.run(_run_team(question, model, perspectives, yes))


@click.group()
def expert():
    """Create and interact with domain experts.

    Experts combine knowledge bases with agentic research capabilities.
    They can autonomously research when they encounter knowledge gaps.
    """
    pass


@expert.command(name="make")
@click.argument("name")
@click.option("--files", "-f", multiple=True, type=click.Path(exists=True),
              help="Files to include in expert's knowledge base")
@click.option("--description", "-d", help="Description of expert's domain")
@click.option("--provider", "-p", default="openai",
              type=click.Choice(["openai", "azure", "gemini"]),
              help="AI provider for expert")
@click.option("--learn", is_flag=True, default=False,
              help="Generate and execute autonomous learning curriculum")
@click.option("--budget", type=float, default=None,
              help="Budget limit for autonomous learning (requires --learn)")
@click.option("--topics", type=int, default=15,
              help="Number of topics in learning curriculum (10-20)")
def make_expert(name: str, files: tuple, description: Optional[str], provider: str,
                learn: bool, budget: Optional[float], topics: int):
    """Create a new domain expert with a knowledge base.

    Creates an expert that can answer questions based on provided documents
    and conduct research when needed.

    Examples:
        deepr expert make "Azure Architect" -f docs/*.md
        deepr expert make "Python Expert" -f guides/*.py --description "Python best practices"
        deepr expert make "Security Advisor" -f policies/*.pdf
    """
    import asyncio
    from deepr.experts.profile import ExpertStore, ExpertProfile, get_expert_system_message
    from deepr.config import load_config
    from deepr.providers import create_provider
    from datetime import datetime

    click.echo(f"\n{'='*70}")
    click.echo(f"  Creating Expert: {name}")
    click.echo(f"{'='*70}\n")

    if not files:
        click.echo("Error: No files specified. Use --files to add documents.")
        click.echo("Example: deepr expert make 'My Expert' -f docs/*.md")
        return

    async def create_expert():
        # Load config
        config = load_config()

        # Get provider-specific API key
        if provider == "gemini":
            api_key = config.get("gemini_api_key")
        elif provider == "azure":
            api_key = config.get("azure_api_key")
        else:
            api_key = config.get("api_key")

        provider_instance = create_provider(provider, api_key=api_key)

        # Upload files and create vector store
        click.echo(f"Uploading {len(files)} file(s)...")
        file_ids = []

        for file_path in files:
            basename = os.path.basename(file_path)
            click.echo(f"  Uploading {basename}...")
            file_id = await provider_instance.upload_document(file_path)
            file_ids.append(file_id)
            click.echo(f"  [OK] {basename}")

        # Create vector store
        click.echo(f"\nCreating knowledge base...")
        vector_store = await provider_instance.create_vector_store(
            name=f"expert-{name.lower().replace(' ', '-')}",
            file_ids=file_ids
        )

        # Wait for indexing
        click.echo(f"  Indexing files (this may take a minute)...")
        success = await provider_instance.wait_for_vector_store(vector_store.id, timeout=900)

        if not success:
            click.echo("Error: Indexing timed out")
            return None

        # Create expert profile with programmatic system message
        # Set initial knowledge cutoff to now (will be updated when learning is added)
        now = datetime.utcnow()

        profile = ExpertProfile(
            name=name,
            vector_store_id=vector_store.id,
            description=description,
            domain=description,
            source_files=[str(f) for f in files],
            total_documents=len(files),
            knowledge_cutoff_date=now,  # Initial docs uploaded now
            last_knowledge_refresh=now,
            system_message=get_expert_system_message(
                knowledge_cutoff_date=now,
                domain_velocity="medium"  # Default, can be customized later
            ),
            provider=provider
        )

        # Save profile
        store = ExpertStore()
        store.save(profile)

        return profile

    import os
    profile = asyncio.run(create_expert())

    if not profile:
        return

    click.echo(f"\n[OK] Expert created successfully!")
    click.echo(f"\nExpert: {profile.name}")
    click.echo(f"Knowledge Base ID: {profile.vector_store_id}")
    click.echo(f"Documents: {profile.total_documents}")

    # Check if we should generate autonomous learning curriculum
    if learn:
        click.echo(f"\n{'='*70}")
        click.echo(f"  Autonomous Learning Mode")
        click.echo(f"{'='*70}\n")

        # Validate budget
        if not budget:
            click.echo("Error: --budget is required when using --learn")
            click.echo("Example: deepr expert make 'Expert' -f docs/*.md --learn --budget 10")
            return

        if budget <= 0:
            click.echo("Error: Budget must be positive")
            return

        # Generate curriculum
        async def generate_and_execute_curriculum():
            from deepr.experts.curriculum import CurriculumGenerator
            from deepr.experts.learner import AutonomousLearner
            from deepr.config import load_config

            config = load_config()

            click.echo(f"Generating learning curriculum with GPT-5...")
            click.echo(f"Target topics: {topics}")
            click.echo(f"Budget limit: ${budget:.2f}\n")

            generator = CurriculumGenerator(config)

            try:
                curriculum = await generator.generate_curriculum(
                    expert_name=name,
                    domain=description or name,
                    initial_documents=[os.path.basename(f) for f in files],
                    target_topics=topics,
                    budget_limit=budget
                )

                # Display curriculum for approval
                click.echo(f"\n{'='*70}")
                click.echo(f"  Learning Curriculum ({len(curriculum.topics)} topics)")
                click.echo(f"{'='*70}\n")

                for i, topic in enumerate(curriculum.topics, 1):
                    priority_marker = "*" * topic.priority
                    click.echo(f"{i}. {topic.title} [{priority_marker}]")
                    click.echo(f"   {topic.description}")
                    click.echo(f"   Est: ${topic.estimated_cost:.2f}, {topic.estimated_minutes}min")
                    if topic.dependencies:
                        click.echo(f"   Depends on: {', '.join(topic.dependencies)}")
                    click.echo()

                click.echo(f"Total estimated cost: ${curriculum.total_estimated_cost:.2f}")
                click.echo(f"Total estimated time: {curriculum.total_estimated_minutes} minutes")
                click.echo(f"Budget limit: ${budget:.2f}")

                if curriculum.total_estimated_cost > budget:
                    click.echo(f"\n[WARNING] Estimated cost exceeds budget!")
                    click.echo(f"  Curriculum has been truncated to fit budget")

                # Ask for confirmation
                click.echo(f"\n{'='*70}")
                if not click.confirm("Proceed with autonomous learning?", default=False):
                    click.echo("Learning cancelled.")
                    return None

                # Execute curriculum
                click.echo(f"\n{'='*70}")
                click.echo(f"  Executing Autonomous Learning")
                click.echo(f"{'='*70}\n")

                learner = AutonomousLearner(config)

                progress = await learner.execute_curriculum(
                    expert=profile,
                    curriculum=curriculum,
                    budget_limit=budget,
                    dry_run=False
                )

                return progress

            except Exception as e:
                click.echo(f"\n[ERROR] Failed to generate curriculum: {e}")
                import traceback
                traceback.print_exc()
                return None

        progress = asyncio.run(generate_and_execute_curriculum())

        if progress:
            click.echo(f"\n{'='*70}")
            click.echo(f"  Learning Summary")
            click.echo(f"{'='*70}\n")
            click.echo(f"Completed: {len(progress.completed_topics)} topics")
            click.echo(f"Failed: {len(progress.failed_topics)} topics")
            click.echo(f"Success rate: {progress.success_rate()*100:.1f}%")
            click.echo(f"Total cost: ${progress.total_cost:.2f}")
            click.echo(f"Time elapsed: {(progress.completed_at - progress.started_at).total_seconds()/60:.1f} minutes")

    # Show usage
    click.echo(f"\nUsage:")
    click.echo(f'  deepr chat expert "{profile.name}"')
    click.echo(f'  deepr chat expert "{profile.name}" --agentic --budget 5')


@expert.command(name="list")
def list_experts():
    """List all available experts."""
    from deepr.experts.profile import ExpertStore

    click.echo(f"\n{'='*70}")
    click.echo(f"  Domain Experts")
    click.echo(f"{'='*70}\n")

    store = ExpertStore()
    experts = store.list_all()

    if not experts:
        click.echo("No experts found.")
        click.echo("\nCreate one with:")
        click.echo('  deepr expert make "Expert Name" -f documents/*.md')
        return

    click.echo(f"Found {len(experts)} expert(s):\n")

    for expert in experts:
        click.echo(f"  {expert.name}")
        if expert.description:
            click.echo(f"    {expert.description}")
        click.echo(f"    Documents: {expert.total_documents}")
        click.echo(f"    Conversations: {expert.conversations}")
        if expert.research_triggered > 0:
            click.echo(f"    Research: {expert.research_triggered} jobs (${expert.total_research_cost:.2f})")
        click.echo(f"    Updated: {expert.updated_at.strftime('%Y-%m-%d')}")
        click.echo()

    click.echo("Usage:")
    click.echo('  deepr chat expert "<name>"')


@expert.command(name="info")
@click.argument("name")
def expert_info(name: str):
    """Show detailed information about an expert."""
    import os
    from deepr.experts.profile import ExpertStore

    store = ExpertStore()
    profile = store.load(name)

    if not profile:
        click.echo(f"Error: Expert not found: {name}")
        click.echo("\nList available experts:")
        click.echo("  deepr expert list")
        return

    click.echo(f"\n{'='*70}")
    click.echo(f"  Expert: {profile.name}")
    click.echo(f"{'='*70}\n")

    click.echo(f"Description: {profile.description or 'N/A'}")
    click.echo(f"Provider: {profile.provider}")
    click.echo(f"Model: {profile.model}")
    click.echo(f"\nKnowledge Base:")
    click.echo(f"  Vector Store ID: {profile.vector_store_id}")
    click.echo(f"  Documents: {profile.total_documents}")
    click.echo(f"  Source Files: {len(profile.source_files)}")

    if profile.source_files:
        click.echo("\n  Files:")
        for f in profile.source_files[:10]:
            click.echo(f"    - {os.path.basename(f)}")
        if len(profile.source_files) > 10:
            click.echo(f"    ... and {len(profile.source_files) - 10} more")

    click.echo(f"\nUsage Stats:")
    click.echo(f"  Conversations: {profile.conversations}")
    click.echo(f"  Research Triggered: {profile.research_triggered}")
    click.echo(f"  Total Research Cost: ${profile.total_research_cost:.2f}")

    if profile.research_jobs:
        click.echo(f"  Research Jobs: {len(profile.research_jobs)}")

    click.echo(f"\nCreated: {profile.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    click.echo(f"Updated: {profile.updated_at.strftime('%Y-%m-%d %H:%M:%S')}")


@expert.command(name="delete")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def delete_expert(name: str, yes: bool):
    """Delete an expert and optionally its knowledge base."""
    from deepr.experts.profile import ExpertStore

    store = ExpertStore()
    profile = store.load(name)

    if not profile:
        click.echo(f"Error: Expert not found: {name}")
        return

    click.echo(f"\nExpert: {profile.name}")
    click.echo(f"Knowledge Base: {profile.vector_store_id}")
    click.echo(f"Documents: {profile.total_documents}")

    if not yes:
        click.echo("\nThis will delete the expert profile.")
        click.echo("Knowledge base (vector store) will remain and must be deleted separately.")
        if not click.confirm("\nDelete expert?"):
            click.echo("Cancelled")
            return

    if store.delete(name):
        click.echo(f"\n[OK] Expert deleted: {name}")
        click.echo(f"\nTo delete the knowledge base:")
        click.echo(f"  deepr brain delete {profile.vector_store_id}")
    else:
        click.echo(f"\nError: Failed to delete expert")


if __name__ == "__main__":
    research()
