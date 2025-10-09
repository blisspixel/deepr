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
@click.option("--planner", "-p", default="gpt-5",
              type=click.Choice(["gpt-5", "gpt-5-mini", "gpt-5-nano"]),
              help="GPT-5 model for planning (reasoning model)")
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
        from deepr.storage.local import LocalStorage
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
        # Use reports_path or default to data/reports
        storage_path = config.get("reports_path", "data/reports")
        storage = LocalStorage(storage_path)
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

        # Save campaign_id to plan for continue command
        plan["last_campaign_id"] = campaign_id
        plan["current_phase"] = 1
        with open(plan_file, "w") as f:
            json.dump(plan, f, indent=2)

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


@prep.command()
@click.option("--topics", "-n", default=5, type=click.IntRange(1, 10),
              help="Number of research tasks for next phase")
@click.option("--yes", "-y", is_flag=True,
              help="Auto-execute without confirmation")
def continue_research(topics: int, yes: bool):
    """
    Continue research campaign by planning next phase based on completed results.

    Replicates research team workflow:
    1. Reviews completed research from previous phase
    2. Identifies gaps and what's needed next
    3. Plans Phase N+1 research tasks
    4. Optionally executes immediately

    Example:
        deepr prep plan "..." --topics 4
        deepr prep execute --yes
        # Wait for completion...
        deepr prep continue --topics 3 --yes
        # Continues with Phase 2 based on Phase 1 findings
    """
    print_section_header("Continue Research Campaign")

    try:
        import json
        import asyncio
        from pathlib import Path
        from deepr.config import load_config
        from deepr.storage.local import LocalStorage
        from deepr.queue.local_queue import SQLiteQueue
        from deepr.services.research_reviewer import ResearchReviewer

        # Load last campaign
        plan_dir = Path(".deepr/plans")
        plan_files = sorted(plan_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)

        if not plan_files:
            click.echo(f"\n{CROSS} No previous campaign found. Run 'deepr prep plan' first.", err=True)
            raise click.Abort()

        plan_file = plan_files[0]
        with open(plan_file, "r") as f:
            plan = json.load(f)

        scenario = plan.get("scenario", "Unknown")
        current_phase = plan.get("current_phase", 1)

        click.echo(f"\nScenario: {scenario}")
        click.echo(f"Current Phase: {current_phase}")
        click.echo(f"\nReviewing Phase {current_phase} results with GPT-5...")

        # Get completed results
        config = load_config()
        storage_path = config.get("reports_path", "data/reports")
        storage = LocalStorage(storage_path)
        queue = SQLiteQueue(config["queue_db_path"])

        # Load results from last execution
        completed_results = []
        if "last_campaign_id" in plan:
            campaign_id = plan["last_campaign_id"]
            # Try to load campaign results
            try:
                campaign_data = asyncio.run(storage.get_report(campaign_id, "campaign_results.json"))
                campaign_json = json.loads(campaign_data.decode("utf-8"))

                # Extract completed task results
                for task_id, task_info in campaign_json.get("tasks", {}).items():
                    if task_info.get("status") == "completed":
                        job_id = task_info.get("job_id")
                        try:
                            result_data = asyncio.run(storage.get_report(job_id, "report.md"))
                            completed_results.append({
                                "title": task_info.get("title"),
                                "result": result_data.decode("utf-8")
                            })
                        except:
                            pass
            except:
                click.echo(f"{CROSS} Could not load previous campaign results", err=True)
                raise click.Abort()

        if not completed_results:
            click.echo(f"\n{CROSS} No completed results found from previous phase.", err=True)
            click.echo("Make sure you ran 'deepr prep execute' and tasks completed.", err=True)
            raise click.Abort()

        click.echo(f"Found {len(completed_results)} completed research tasks")

        # Review with GPT-5
        reviewer = ResearchReviewer(model="gpt-5")
        review_result = reviewer.review_and_plan_next(
            scenario=scenario,
            completed_results=completed_results,
            current_phase=current_phase,
            max_tasks=topics
        )

        # Display review
        click.echo(f"\n{CHECK} Review complete\n")
        click.echo(f"Analysis: {review_result.get('analysis', 'No analysis')}\n")

        if review_result.get("status") == "ready_for_synthesis":
            click.echo("Status: Ready for final synthesis")
        else:
            click.echo(f"Status: Continue with Phase {review_result['phase']}")

        # Display next tasks
        next_tasks = review_result.get("next_tasks", [])
        if next_tasks:
            click.echo(f"\nProposed Phase {review_result['phase']} Tasks:")
            for i, task in enumerate(next_tasks, 1):
                click.echo(f"\n{i}. {task['title']}")
                click.echo(f"   Rationale: {task.get('rationale', 'N/A')}")
                click.echo(f"   Prompt: {task['prompt'][:100]}...")

        # Save updated plan
        plan["current_phase"] = review_result["phase"]
        plan["tasks"] = [
            {
                "id": i,
                "phase": review_result["phase"],
                "title": task["title"],
                "prompt": task["prompt"],
                "type": "synthesis" if review_result.get("status") == "ready_for_synthesis" else "analysis"
            }
            for i, task in enumerate(next_tasks, 1)
        ]

        with open(plan_file, "w") as f:
            json.dump(plan, f, indent=2)

        click.echo(f"\n{CHECK} Plan updated: {plan_file.name}")

        # Ask if should execute
        if not yes:
            if not click.confirm(f"\nExecute Phase {review_result['phase']} now?"):
                click.echo(f"\n{CROSS} Cancelled. Run 'deepr prep execute' when ready.")
                return

        # Execute
        click.echo(f"\n{CHECK} Executing Phase {review_result['phase']}...")
        from click.testing import CliRunner
        runner = CliRunner()
        result = runner.invoke(execute, ['--yes'])
        if result.exit_code != 0:
            click.echo(f"\n{CROSS} Execution failed")
            raise click.Abort()

    except Exception as e:
        click.echo(f"\n{CROSS} Error: {e}", err=True)
        import traceback
        traceback.print_exc()
        raise click.Abort()


@prep.command()
@click.argument("scenario")
@click.option("--rounds", "-r", default=3, type=click.IntRange(2, 5),
              help="Number of research rounds (2-5)")
@click.option("--topics-per-round", "-n", default=4,
              help="Tasks per round")
def auto(scenario: str, rounds: int, topics_per_round: int):
    """
    Fully autonomous multi-round research (plan → execute → review → repeat).

    Replicates complete research team workflow:
    - Round 1: Plan foundation → Execute → Review
    - Round 2: Plan analysis → Execute → Review
    - Round 3: Plan synthesis → Execute → Done

    Example:
        deepr prep auto "What should Ford do in EVs for 2026?" --rounds 3

    This will:
    1. Generate Phase 1 (foundation research)
    2. Execute Phase 1 and wait for completion
    3. Review Phase 1 results with GPT-5
    4. Generate Phase 2 (analysis based on Phase 1)
    5. Execute Phase 2 and wait
    6. Review Phase 2 results
    7. Generate Phase 3 (final synthesis)
    8. Execute Phase 3
    9. Done - comprehensive multi-phase research complete
    """
    print_section_header("Autonomous Multi-Round Research")

    click.echo(f"\nScenario: {scenario}")
    click.echo(f"Rounds: {rounds}")
    click.echo(f"Tasks per round: {topics_per_round}")
    click.echo("\nThis will run completely autonomously.")
    click.echo("Each round: plan → execute → wait → review → next round")
    click.echo(f"\nEstimated time: {rounds * 30}-{rounds * 60} minutes")
    click.echo(f"Estimated cost: ${rounds * topics_per_round * 0.50:.2f} - ${rounds * topics_per_round * 1.00:.2f}")

    if not click.confirm("\nProceed with autonomous research?"):
        click.echo(f"\n{CROSS} Cancelled")
        return

    try:
        from click.testing import CliRunner
        runner = CliRunner()

        # Round 1: Initial plan
        click.echo(f"\n{'='*70}")
        click.echo(f"ROUND 1: Foundation Research")
        click.echo(f"{'='*70}\n")

        result = runner.invoke(plan, [scenario, '--topics', str(topics_per_round)])
        if result.exit_code != 0:
            click.echo(f"\n{CROSS} Planning failed")
            raise click.Abort()

        result = runner.invoke(execute, ['--yes'])
        if result.exit_code != 0:
            click.echo(f"\n{CROSS} Execution failed")
            raise click.Abort()

        # Subsequent rounds
        for round_num in range(2, rounds + 1):
            click.echo(f"\n{'='*70}")
            click.echo(f"ROUND {round_num}: {'Synthesis' if round_num == rounds else 'Analysis'}")
            click.echo(f"{'='*70}\n")

            # Review and plan next
            result = runner.invoke(continue_research, ['--topics', str(topics_per_round), '--yes'])
            if result.exit_code != 0:
                click.echo(f"\n{CROSS} Continue failed")
                raise click.Abort()

        click.echo(f"\n{'='*70}")
        click.echo(f"{CHECK} AUTONOMOUS RESEARCH COMPLETE")
        click.echo(f"{'='*70}\n")
        click.echo("View results: deepr prep review")

    except Exception as e:
        click.echo(f"\n{CROSS} Error: {e}", err=True)
        import traceback
        traceback.print_exc()
        raise click.Abort()
