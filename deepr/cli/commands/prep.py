"""Prep commands - plan and execute multi-angle research."""

import click
from typing import Optional
from deepr.branding import print_section_header, CHECK, CROSS


@click.group()
def prep():
    """Plan and execute multi-angle research (uses GPT-5)."""
    pass


@prep.command()
@click.argument("scenario")
@click.option("--topics", "-n", default=5, type=click.IntRange(1, 10),
              help="Number of research topics to generate (1-10)")
@click.option("--context", "-c", default=None,
              help="Additional context for planning")
@click.option("--planner", "-p", default="gpt-5-mini",
              type=click.Choice(["gpt-5", "gpt-5-mini", "gpt-5-nano"]),
              help="GPT-5 model for planning (cheap, fast)")
@click.option("--model", "-m", default="o4-mini-deep-research",
              type=click.Choice(["o4-mini-deep-research", "o3-deep-research"]),
              help="Deep research model for execution")
@click.option("--check-docs", is_flag=True,
              help="Check existing docs before planning (saves money)")
def plan(scenario: str, topics: int, context: Optional[str], planner: str, model: str, check_docs: bool):
    """
    Generate multi-phase research plan with dependencies.

    Uses GPT-5 (cheap, fast) to decompose high-level goal into phased research tasks.
    Shows what research depends on what, lets you review before executing.

    Example:
        deepr prep plan "Analyze electric vehicle market" --topics 5
        deepr prep plan "Build AI code review tool" --topics 7
    """
    print_section_header("Research Planning")

    click.echo(f"\nScenario: {scenario}")
    if context:
        click.echo(f"Context: {context}")
    click.echo(f"\nUsing {planner} to generate {topics} research topics...")
    click.echo(f"Planning cost: ~$0.01 (does NOT execute research yet)")

    try:
        import json
        from pathlib import Path
        from datetime import datetime
        from deepr.services.research_planner import ResearchPlanner

        # Check existing docs if requested
        enhanced_context = context
        if check_docs:
            click.echo("\nChecking existing documentation...")
            from deepr.services.doc_reviewer import DocReviewer

            reviewer = DocReviewer(model=planner)
            doc_analysis = reviewer.check_existing_docs(scenario)

            # Show what we found
            relevant = doc_analysis.get("relevant_docs", [])
            if relevant:
                click.echo(f"\nFound {len(relevant)} relevant docs:")
                for doc in relevant:
                    quality = doc.get("quality", "unknown")
                    click.echo(f"  - {Path(doc['path']).name} ({quality})")

            gaps = doc_analysis.get("gaps", [])
            if gaps:
                click.echo(f"\nGaps to address: {len(gaps)}")
                for gap in gaps[:3]:  # Show first 3
                    click.echo(f"  - {gap}")

            # Generate enhanced context for planner
            enhanced_context = reviewer.generate_enhanced_plan_context(
                scenario=scenario,
                doc_analysis=doc_analysis,
            )

            click.echo(f"\nDoc review cost: ~$0.01")

        # Create planner
        planner_svc = ResearchPlanner(model=planner)

        # Generate plan
        tasks = planner_svc.plan_research(
            scenario=scenario,
            max_tasks=topics,
            context=enhanced_context
        )

        # Group by phase
        phases = {}
        for i, task in enumerate(tasks, 1):
            task['id'] = i
            task['approved'] = True  # Default to approved
            phase = task.get('phase', 1)
            if phase not in phases:
                phases[phase] = []
            phases[phase].append(task)

        click.echo(f"\n{CHECK} Generated {len(tasks)} research tasks in {len(phases)} phases:\n")

        # Display by phase
        avg_cost = 0.50 if "mini" in model else 5.0
        total_cost = 0

        for phase_num in sorted(phases.keys()):
            phase_tasks = phases[phase_num]
            click.echo(f"Phase {phase_num}:")

            if phase_num == 1:
                click.echo("  (Foundation research - can run in parallel)")
            elif phase_num == len(phases):
                click.echo("  (Synthesis - depends on all previous research)")
            else:
                click.echo("  (Analysis - uses previous phase results as context)")

            click.echo()

            for task in phase_tasks:
                deps = task.get('depends_on', [])
                deps_str = f" [needs: {','.join(map(str, deps))}]" if deps else ""

                task_type = task.get('type', 'analysis')
                type_label = f" ({task_type})" if task_type else ""

                click.echo(f"  {task['id']}. {task['title']}{type_label}{deps_str}")
                click.echo(f"     {task['prompt'][:80]}...")

                # Adjust cost estimate based on type
                est_cost = avg_cost * 0.7 if task_type == 'documentation' else avg_cost
                click.echo(f"     Est: ~${est_cost:.2f}, Time: 5-15 min")
                click.echo()
                total_cost += est_cost

        click.echo(f"Total Estimated Cost: ${total_cost:.2f}")
        click.echo(f"Total Estimated Time: {len(tasks) * 10} minutes (if sequential)")
        click.echo()
        click.echo("Note: Phase 2+ tasks will use previous results as context")
        click.echo("      This creates comprehensive, interconnected research")

        # Save plan
        plan_dir = Path(".deepr/plans")
        plan_dir.mkdir(parents=True, exist_ok=True)

        plan_id = scenario.replace(" ", "_").lower()[:50]
        plan_file = plan_dir / f"{plan_id}.json"

        plan_data = {
            "scenario": scenario,
            "context": context,
            "model": model,
            "planner": planner,
            "tasks": tasks,
            "phases": len(phases),
            "created_at": datetime.utcnow().isoformat()
        }

        with open(plan_file, "w") as f:
            json.dump(plan_data, f, indent=2)

        click.echo(f"\nPlan saved: {plan_file}")
        click.echo()
        click.echo("Next steps:")
        click.echo(f"  deepr prep review    # Review and approve/remove tasks")
        click.echo(f"  deepr prep execute   # Execute approved tasks")

    except Exception as e:
        click.echo(f"\n{CROSS} Error: {e}", err=True)
        import traceback
        traceback.print_exc()
        raise click.Abort()


@prep.command()
def review():
    """
    Review and approve/reject tasks from last plan.

    Shows each task and lets you approve, reject, or edit before execution.

    Example:
        deepr prep review
    """
    print_section_header("Review Research Plan")

    try:
        import json
        from pathlib import Path

        # Load last plan
        plan_dir = Path(".deepr/plans")
        plan_files = sorted(plan_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)

        if not plan_files:
            click.echo(f"\n{CROSS} No plan found. Run 'deepr prep plan' first.", err=True)
            raise click.Abort()

        plan_file = plan_files[0]

        with open(plan_file, "r") as f:
            plan_data = json.load(f)

        scenario = plan_data["scenario"]
        tasks = plan_data["tasks"]

        click.echo(f"\nScenario: {scenario}")
        click.echo(f"Tasks: {len(tasks)}\n")

        # Review each task
        approved_count = 0
        for task in tasks:
            task_id = task['id']
            phase = task.get('phase', 1)
            deps = task.get('depends_on', [])

            click.echo(f"\n{'=' * 60}")
            click.echo(f"Task {task_id}: {task['title']}")
            click.echo(f"Phase: {phase}")
            if deps:
                click.echo(f"Depends on: {', '.join(map(str, deps))}")
            click.echo(f"\nPrompt: {task['prompt']}")
            click.echo(f"{'=' * 60}\n")

            # Get user decision
            choice = click.prompt(
                "Action? (a)pprove, (r)eject, (s)kip to end",
                type=click.Choice(['a', 'r', 's'], case_sensitive=False),
                default='a'
            )

            if choice == 'a':
                task['approved'] = True
                approved_count += 1
                click.echo(f"{CHECK} Approved")
            elif choice == 'r':
                task['approved'] = False
                click.echo(f"{CROSS} Rejected")
            elif choice == 's':
                # Keep remaining tasks as approved
                for remaining in tasks[tasks.index(task):]:
                    if 'approved' not in remaining:
                        remaining['approved'] = True
                        approved_count += 1
                break

        # Save updated plan
        with open(plan_file, "w") as f:
            json.dump(plan_data, f, indent=2)

        click.echo(f"\n{CHECK} Review complete!")
        click.echo(f"\nApproved: {approved_count} / {len(tasks)}")
        click.echo(f"\nNext step:")
        click.echo(f"  deepr prep execute    # Execute approved tasks")

    except Exception as e:
        click.echo(f"\n{CROSS} Error: {e}", err=True)
        import traceback
        traceback.print_exc()
        raise click.Abort()


@prep.command()
@click.option("--yes", "-y", is_flag=True,
              help="Skip confirmation")
def execute(yes: bool):
    """
    Execute the last generated research plan with context chaining.

    Runs multi-phase research campaign:
    - Phase 1: Foundation tasks (parallel)
    - Phase 2+: Analysis tasks (with Phase 1 context injected)
    - Final: Synthesis (with all prior research integrated)

    Example:
        deepr prep execute
        deepr prep execute --yes
    """
    print_section_header("Execute Research Campaign")

    try:
        import json
        import asyncio
        from pathlib import Path
        from deepr.config import load_config
        from deepr.queue.local_queue import SQLiteQueue
        from deepr.storage.local_storage import LocalStorage
        from deepr.providers.openai_provider import OpenAIProvider
        from deepr.services.context_builder import ContextBuilder
        from deepr.services.batch_executor import BatchExecutor

        # Load last plan
        plan_dir = Path(".deepr/plans")
        plan_files = sorted(plan_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)

        if not plan_files:
            click.echo(f"\n{CROSS} No plan found. Run 'deepr prep plan' first.", err=True)
            raise click.Abort()

        plan_file = plan_files[0]

        with open(plan_file, "r") as f:
            plan_data = json.load(f)

        scenario = plan_data["scenario"]
        all_tasks = plan_data["tasks"]
        model = plan_data["model"]

        # Filter to approved tasks only
        tasks = [t for t in all_tasks if t.get('approved', True)]

        if not tasks:
            click.echo(f"\n{CROSS} No approved tasks. Run 'deepr prep review' first.", err=True)
            raise click.Abort()

        # Calculate estimated cost
        avg_cost = 0.50 if "mini" in model else 5.0
        estimated_cost = avg_cost * len(tasks)

        # Show plan
        click.echo(f"\nScenario: {scenario}")
        click.echo(f"Tasks: {len(tasks)} across {plan_data['phases']} phases")
        click.echo(f"Model: {model}")
        click.echo(f"\nEstimated Cost: ${estimated_cost:.2f}")
        click.echo(f"Estimated Time: {len(tasks) * 10} minutes")

        # Confirmation
        if not yes:
            click.echo("\nThis will execute the full multi-phase research campaign.")
            click.echo("Phase 2+ tasks will receive context from previous phases.")
            if not click.confirm(f"\nExecute campaign for ~${estimated_cost:.2f}?"):
                click.echo(f"\n{CROSS} Cancelled")
                return

        # Initialize services
        config = load_config()
        queue = SQLiteQueue(config["queue_db_path"])
        storage = LocalStorage(config["storage_path"])
        provider = OpenAIProvider(api_key=config["api_key"])
        context_builder = ContextBuilder(api_key=config["api_key"])
        executor = BatchExecutor(
            queue=queue,
            provider=provider,
            storage=storage,
            context_builder=context_builder,
        )

        # Generate campaign ID
        import uuid
        campaign_id = f"campaign-{uuid.uuid4().hex[:12]}"

        click.echo(f"\n{CHECK} Starting campaign: {campaign_id}")
        click.echo("\nThis will take a while. Each task takes 5-15 minutes.")
        click.echo("Progress will be shown as tasks complete.\n")

        # Execute campaign
        async def run_campaign():
            results = await executor.execute_campaign(
                tasks=tasks,
                campaign_id=campaign_id,
            )
            return results

        results = asyncio.run(run_campaign())

        # Show results
        click.echo(f"\n{CHECK} Campaign completed!")
        click.echo(f"\nTotal Cost: ${results['total_cost']:.2f}")
        click.echo(f"Total Tasks: {len(results['tasks'])}")
        click.echo(f"\nResults saved: .deepr/storage/{campaign_id}/")
        click.echo(f"\nView summary: deepr research result {campaign_id}")

    except Exception as e:
        click.echo(f"\n{CROSS} Error: {e}", err=True)
        import traceback
        traceback.print_exc()
        raise click.Abort()


@prep.command()
@click.argument("batch_id")
def status(batch_id: str):
    """
    Check status of batch research.

    Example:
        deepr prep status batch-abc123
    """
    print_section_header(f"Batch Status: {batch_id}")

    try:
        from deepr.services.queue import get_queue

        queue = get_queue()

        # Get all jobs in batch
        all_jobs = queue.list_jobs(limit=1000)
        batch_jobs = [
            j for j in all_jobs
            if hasattr(j, "metadata") and j.metadata and j.metadata.get("batch_id") == batch_id
        ]

        if not batch_jobs:
            click.echo(f"\n{CROSS} Batch not found: {batch_id}", err=True)
            raise click.Abort()

        # Calculate stats
        scenario = batch_jobs[0].metadata.get("batch_scenario", "Unknown")
        total = len(batch_jobs)
        pending = sum(1 for j in batch_jobs if j.status.value == "pending")
        in_progress = sum(1 for j in batch_jobs if j.status.value == "in_progress")
        completed = sum(1 for j in batch_jobs if j.status.value == "completed")
        failed = sum(1 for j in batch_jobs if j.status.value == "failed")

        total_cost = sum(
            getattr(j, 'actual_cost', None) or getattr(j, 'estimated_cost', 0)
            for j in batch_jobs
        )

        # Display
        click.echo(f"\nScenario: {scenario}")
        click.echo(f"\nProgress:")
        click.echo(f"   Total: {total} tasks")
        click.echo(f"   Pending: {pending}")
        click.echo(f"   In Progress: {in_progress}")
        click.echo(f"   Completed: {completed}")
        click.echo(f"   Failed: {failed}")

        progress = ((completed + failed) / total * 100) if total > 0 else 0
        click.echo(f"\n{progress:.0f}% complete")
        click.echo(f"Total Cost: ${total_cost:.2f}")

        # Show tasks
        if batch_jobs:
            click.echo(f"\nTasks:")
            for job in batch_jobs:
                status_labels = {
                    "pending": "PENDING    ",
                    "in_progress": "IN_PROGRESS",
                    "completed": "COMPLETED  ",
                    "failed": "FAILED     "
                }
                label = status_labels.get(job.status.value, "UNKNOWN    ")

                title = job.metadata.get("task_title", "Unknown")
                click.echo(f"   {label} | {title}")

        if completed > 0:
            click.echo(f"\nView results: deepr research result <job-id>")

    except Exception as e:
        click.echo(f"\n{CROSS} Error: {e}", err=True)
        raise click.Abort()
