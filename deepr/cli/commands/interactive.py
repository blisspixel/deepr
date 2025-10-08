"""Interactive mode - guided research workflow."""

import click
from deepr.branding import print_banner, print_section_header, CHECK, CROSS


@click.command()
def interactive():
    """
    Start interactive mode for guided research.

    Example:
        deepr interactive
    """
    print_banner("main")
    print_section_header("Interactive Mode")

    click.echo("\nWelcome to Deepr Interactive Mode!")
    click.echo("   Let's set up your research.\n")

    try:
        # Mode selection
        click.echo("What would you like to do?\n")
        click.echo("1. Submit single research job")
        click.echo("2. Plan multi-angle research (Prep)")
        click.echo("3. View queue status")
        click.echo("4. Exit")

        mode = click.prompt("\nSelect option", type=int, default=1)

        if mode == 1:
            _interactive_single_research()
        elif mode == 2:
            _interactive_prep()
        elif mode == 3:
            _interactive_queue()
        elif mode == 4:
            click.echo(f"\n{CHECK} Goodbye!")
            return
        else:
            click.echo(f"\n{CROSS} Invalid option")

    except (KeyboardInterrupt, click.Abort):
        click.echo(f"\n\n{CROSS} Cancelled")


def _interactive_single_research():
    """Interactive single research submission."""
    print_section_header("Submit Research Job")

    # Get prompt
    click.echo("\nWhat would you like to research?")
    prompt = click.prompt("   Prompt")

    if not prompt or len(prompt) < 10:
        click.echo(f"\n{CROSS} Prompt too short (min 10 characters)")
        return

    # Model selection
    click.echo("\nSelect research model:")
    click.echo("   1. o4-mini (Faster, cheaper)")
    click.echo("   2. o3 (More thorough)")
    model_choice = click.prompt("   Model", type=int, default=1)
    model = "o4-mini-deep-research" if model_choice == 1 else "o3-deep-research"

    # Priority
    click.echo("\nSelect priority:")
    click.echo("   1. High (process first)")
    click.echo("   2. Normal")
    click.echo("   3. Low (cheaper, slower)")
    priority_choice = click.prompt("   Priority", type=int, default=2)
    priority = {1: 1, 2: 3, 3: 5}.get(priority_choice, 3)

    # Web search
    web_search = click.confirm("\nEnable web search?", default=True)

    # Estimate cost
    click.echo(f"\nEstimating cost...")

    from deepr.services.cost_estimation import CostEstimator

    estimate = CostEstimator.estimate_cost(
        prompt=prompt,
        model=model,
        enable_web_search=web_search
    )

    click.echo(f"\nEstimated Cost: ${estimate.expected_cost:.2f}")
    click.echo(f"   Range: ${estimate.min_cost:.2f} - ${estimate.max_cost:.2f}")

    # Confirm
    if not click.confirm(f"\nSubmit job for ~${estimate.expected_cost:.2f}?"):
        click.echo(f"\n{CROSS} Cancelled")
        return

    # Submit
    click.echo(f"\n{CHECK} Submitting job...")

    from deepr.services.queue import get_queue
    from deepr.models.job import Job, JobStatus
    import uuid
    from datetime import datetime

    queue = get_queue()

    job = Job(
        id=str(uuid.uuid4()),
        prompt=prompt,
        model=model,
        priority=priority,
        enable_web_search=web_search,
        status=JobStatus.PENDING,
        estimated_cost=estimate.expected_cost,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    queue.enqueue(job)

    click.echo(f"\n{CHECK} Job submitted!")
    click.echo(f"\nJob ID: {job.id}")
    click.echo(f"\nTrack status: deepr research status {job.id}")


def _interactive_prep():
    """Interactive prep/planning mode."""
    print_section_header("Plan Multi-Angle Research")

    click.echo("\nDescribe your scenario:")
    click.echo("   Example: 'Meeting with Company X about implementing Kubernetes'\n")
    scenario = click.prompt("   Scenario")

    if not scenario or len(scenario) < 10:
        click.echo(f"\n{CROSS} Scenario too short")
        return

    # Context
    if click.confirm("\nAdd additional context?", default=False):
        context = click.prompt("   Context")
    else:
        context = None

    # Max tasks
    max_tasks = click.prompt("\nHow many research tasks to generate?", type=int, default=5)
    max_tasks = max(1, min(10, max_tasks))

    # Planner model
    click.echo("\nSelect planner model (GPT-5):")
    click.echo("   1. gpt-5-nano (Fastest)")
    click.echo("   2. gpt-5-mini (Recommended)")
    click.echo("   3. gpt-5 (Most thorough)")
    planner_choice = click.prompt("   Planner", type=int, default=2)
    planner = {1: "gpt-5-nano", 2: "gpt-5-mini", 3: "gpt-5"}.get(planner_choice, "gpt-5-mini")

    # Research model
    click.echo("\nSelect research model:")
    click.echo("   1. o4-mini (Faster, cheaper)")
    click.echo("   2. o3 (More thorough)")
    model_choice = click.prompt("   Model", type=int, default=1)
    model = "o4-mini-deep-research" if model_choice == 1 else "o3-deep-research"

    # Generate plan
    click.echo(f"\nPlanning research strategy...")

    from deepr.services.research_planner import create_planner
    from deepr.services.cost_estimation import CostEstimator

    planner_svc = create_planner(model=planner)

    tasks = planner_svc.plan_research(
        scenario=scenario,
        max_tasks=max_tasks,
        context=context
    )

    # Show tasks
    click.echo(f"\n{CHECK} Generated {len(tasks)} tasks:\n")

    total_cost = 0.0
    for i, task in enumerate(tasks, 1):
        estimate = CostEstimator.estimate_cost(
            prompt=task["prompt"],
            model=model,
            enable_web_search=True
        )
        task["estimated_cost"] = estimate.expected_cost
        total_cost += estimate.expected_cost

        click.echo(f"{i}. {task['title']}")
        click.echo(f"   Cost: ~${estimate.expected_cost:.2f}\n")

    click.echo(f"Total: ${total_cost:.2f}")

    # Select tasks
    if click.confirm("\nExecute all tasks?", default=True):
        selected_tasks = tasks
    else:
        task_nums = click.prompt("   Enter task numbers (e.g., 1,2,4)")
        indices = [int(t.strip()) - 1 for t in task_nums.split(",")]
        selected_tasks = [tasks[i] for i in indices if 0 <= i < len(tasks)]
        total_cost = sum(t.get("estimated_cost", 0) for t in selected_tasks)

    # Confirm execution
    if not click.confirm(f"\nExecute {len(selected_tasks)} tasks for ~${total_cost:.2f}?"):
        click.echo(f"\n{CROSS} Cancelled")
        return

    # Execute
    click.echo(f"\n{CHECK} Creating batch jobs...")

    from deepr.services.queue import get_queue
    from deepr.models.job import Job, JobStatus
    import uuid
    from datetime import datetime

    queue = get_queue()
    batch_id = f"batch-{uuid.uuid4().hex[:12]}"

    for task in selected_tasks:
        job_id = str(uuid.uuid4())

        job = Job(
            id=job_id,
            prompt=task["prompt"],
            model=model,
            priority=3,
            enable_web_search=True,
            status=JobStatus.PENDING,
            estimated_cost=task.get("estimated_cost"),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            metadata={
                "batch_id": batch_id,
                "batch_scenario": scenario,
                "task_title": task["title"]
            }
        )

        queue.enqueue(job)

    click.echo(f"\n{CHECK} Batch created!")
    click.echo(f"\nBatch ID: {batch_id}")
    click.echo(f"Track progress: deepr prep status {batch_id}")


def _interactive_queue():
    """Interactive queue viewing."""
    print_section_header("Queue Status")

    from deepr.services.queue import get_queue

    queue_svc = get_queue()
    jobs = queue_svc.list_jobs(limit=50)

    if not jobs:
        click.echo(f"\nQueue is empty")
        return

    # Stats
    pending = sum(1 for j in jobs if j.status.value == "pending")
    in_progress = sum(1 for j in jobs if j.status.value == "in_progress")
    completed = sum(1 for j in jobs if j.status.value == "completed")
    failed = sum(1 for j in jobs if j.status.value == "failed")

    click.echo(f"\nQueue Statistics:")
    click.echo(f"   Total: {len(jobs)}")
    click.echo(f"   Pending: {pending}")
    click.echo(f"   In Progress: {in_progress}")
    click.echo(f"   Completed: {completed}")
    click.echo(f"   Failed: {failed}")

    # Recent jobs
    click.echo(f"\nRecent Jobs:")
    for job in jobs[:10]:
        status_labels = {
            "pending": "PENDING    ",
            "in_progress": "IN_PROGRESS",
            "completed": "COMPLETED  ",
            "failed": "FAILED     "
        }
        label = status_labels.get(job.status.value, "UNKNOWN    ")

        click.echo(f"\n   {label} | {job.id[:8]}...")
        click.echo(f"      {job.prompt[:60]}...")
