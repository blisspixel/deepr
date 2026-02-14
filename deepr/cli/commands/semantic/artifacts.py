"""Make and agentic command groups - artifact generation and autonomous research."""

import os
from typing import Optional

import click

from deepr.cli.async_runner import run_async_command
from deepr.cli.colors import console, print_error, print_header, print_key_value, print_section_header


@click.group()
def make():
    """Create artifacts from research.

    Generate documentation, strategic analysis, and other artifacts
    from research results.

    COMMANDS:
      deepr make docs "topic"      Generate documentation
      deepr make strategy "topic"  Strategic analysis

    EXAMPLES:
      deepr make docs "Azure Landing Zone guide"
      deepr make docs "API reference" --format html
      deepr make strategy "Cloud migration" --perspective technical
    """
    pass


@make.command(name="docs")
@click.argument("topic")
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["markdown", "html", "pdf"]),
    default="markdown",
    help="Output format (default: markdown)",
)
@click.option(
    "--outline", is_flag=True, default=False, help="Generate only an outline for review before full generation"
)
@click.option(
    "--files", "-F", multiple=True, type=click.Path(exists=True), help="Existing documents to incorporate as context"
)
@click.option(
    "--provider",
    "-p",
    default=None,
    type=click.Choice(["openai", "azure", "gemini", "xai"]),
    help="AI provider (default: openai for deep research)",
)
@click.option("--model", "-m", default=None, help="Model to use (default: o4-mini-deep-research)")
@click.option("--output", "-o", type=click.Path(), default=None, help="Output file path (default: auto-generated)")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def make_docs(
    topic: str,
    output_format: str,
    outline: bool,
    files: tuple,
    provider: Optional[str],
    model: Optional[str],
    output: Optional[str],
    yes: bool,
):
    """Generate structured documentation from research.

    Creates comprehensive documentation with inline citations from research
    sources. Supports multiple output formats and can incorporate existing
    documents as context.

    EXAMPLES:
      # Generate markdown documentation
      deepr make docs "Azure Landing Zone + Fabric integration guide"

      # Generate HTML documentation
      deepr make docs "API reference" --format html

      # Preview outline before full generation
      deepr make docs "Architecture overview" --outline

      # Include existing docs as context
      deepr make docs "Migration guide" --files existing/*.md

      # Specify output file
      deepr make docs "User guide" -o docs/user-guide.md

    NOTE: PDF export requires pandoc or weasyprint to be installed.
    """
    from deepr.cli.validation import validate_prompt, validate_upload_files

    # Validate topic
    try:
        topic = validate_prompt(topic, max_length=10000, field_name="topic")
    except click.UsageError as e:
        click.echo(f"Error: {e}", err=True)
        return

    # Validate files if provided
    if files:
        try:
            files = tuple(str(f) for f in validate_upload_files(files))
        except click.UsageError as e:
            click.echo(f"Error: {e}", err=True)
            return

    run_async_command(_generate_docs(topic, output_format, outline, files, provider, model, output, yes))


async def _generate_docs(
    topic: str,
    output_format: str,
    outline: bool,
    files: tuple,
    provider: Optional[str],
    model: Optional[str],
    output: Optional[str],
    yes: bool,
):
    """Generate documentation with research and citations."""
    import re
    from datetime import datetime
    from pathlib import Path

    from deepr.cli.progress import ProgressFeedback
    from deepr.config import AppConfig
    from deepr.providers import create_provider

    config = AppConfig.from_env()
    progress = ProgressFeedback()

    # Set defaults for provider and model
    if not provider:
        provider = os.getenv("DEEPR_DEEP_RESEARCH_PROVIDER", "openai")
    if not model:
        model = os.getenv("DEEPR_DEEP_RESEARCH_MODEL", "o4-mini-deep-research")

    console.print(f"[dim]Using {provider}/{model}[/dim]")

    # Get API key based on provider
    if provider == "xai":
        api_key = os.getenv("XAI_API_KEY")
    elif provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
    elif provider == "azure":
        api_key = config.provider.azure_api_key
    else:
        api_key = config.provider.openai_api_key

    if not api_key:
        print_error(f"No API key found for provider: {provider}")
        console.print("\nSet the appropriate environment variable:")
        if provider == "xai":
            console.print("  export XAI_API_KEY=your-key")
        elif provider == "gemini":
            console.print("  export GEMINI_API_KEY=your-key")
        elif provider == "azure":
            console.print("  export AZURE_OPENAI_API_KEY=your-key")
        else:
            console.print("  export OPENAI_API_KEY=your-key")
        return

    provider_instance = create_provider(provider, api_key=api_key)

    # Read context files if provided
    context_content = ""
    if files:
        console.print(f"[dim]Reading {len(files)} context files...[/dim]")
        for file_path in files:
            try:
                with open(file_path, encoding="utf-8") as f:
                    content = f.read()
                    context_content += f"\n\n## Context from: {os.path.basename(file_path)}\n\n{content}"
            except Exception as e:
                print_error(f"Failed to read {file_path}: {e}")

    # Build the prompt
    if outline:
        prompt = f"""Create a detailed outline for documentation about: {topic}

The outline should include:
1. Document title
2. Executive summary (2-3 sentences)
3. Main sections with subsections (3-5 levels deep)
4. Key topics to cover in each section
5. Suggested diagrams or visuals
6. Estimated word count per section

Format as markdown with clear hierarchy.
{f"Use this existing content as context:{context_content}" if context_content else ""}
"""
    else:
        prompt = f"""Create comprehensive documentation about: {topic}

Requirements:
1. Start with a clear title and executive summary
2. Organize content into logical sections with clear headings
3. Include inline citations in format [Source: source_name] for all factual claims
4. Add code examples where relevant (with syntax highlighting hints)
5. Include practical examples and use cases
6. Add a "References" section at the end listing all sources
7. Use clear, professional technical writing style
8. Target audience: technical professionals

{f"Incorporate and build upon this existing content:{context_content}" if context_content else ""}

Output format: Well-structured markdown with proper headings, lists, and code blocks.
"""

    # Show what we're doing
    print_header("Documentation Generation")
    print_key_value("Topic", topic)
    print_key_value("Format", output_format)
    print_key_value("Mode", "Outline only" if outline else "Full documentation")
    if files:
        print_key_value("Context files", str(len(files)))

    if not yes and not outline:
        estimated_cost = "$1.00-$3.00" if "deep-research" in model else "$0.10-$0.50"
        console.print(f"\n[dim]Estimated cost: {estimated_cost}[/dim]")
        if not click.confirm("\nProceed with documentation generation?"):
            console.print("Cancelled")
            return

    # Generate documentation
    with progress.operation("Generating documentation..." if not outline else "Generating outline..."):
        try:
            response = await provider_instance.complete(prompt, model=model)
            content = response.choices[0].message.content
            cost = getattr(response, "cost", 0.0) if hasattr(response, "cost") else 0.0
        except Exception as e:
            print_error(f"Generation failed: {e}")
            return

    progress.phase_complete("Generation complete", cost=cost)

    # Determine output path
    if not output:
        # Generate filename from topic
        safe_topic = re.sub(r"[^\w\s-]", "", topic.lower())
        safe_topic = re.sub(r"[-\s]+", "-", safe_topic)[:50]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if outline:
            output = f"outline_{safe_topic}_{timestamp}.md"
        else:
            ext = {"markdown": "md", "html": "html", "pdf": "pdf"}[output_format]
            output = f"docs_{safe_topic}_{timestamp}.{ext}"

    output_path = Path(output)

    # Convert format if needed
    if output_format == "html" and not outline:
        try:
            import markdown

            html_content = markdown.markdown(content, extensions=["tables", "fenced_code", "toc"])
            html_doc = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{topic}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 900px; margin: 0 auto; padding: 2rem; line-height: 1.6; }}
        h1, h2, h3 {{ color: #333; }}
        code {{ background: #f4f4f4; padding: 0.2em 0.4em; border-radius: 3px; }}
        pre {{ background: #f4f4f4; padding: 1rem; border-radius: 5px; overflow-x: auto; }}
        blockquote {{ border-left: 4px solid #ddd; margin: 0; padding-left: 1rem; color: #666; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 0.5rem; text-align: left; }}
        th {{ background: #f4f4f4; }}
    </style>
</head>
<body>
{html_content}
</body>
</html>"""
            content = html_doc
        except ImportError:
            print_error("HTML conversion requires 'markdown' package. Install with: pip install markdown")
            console.print("Saving as markdown instead...")
            output_path = output_path.with_suffix(".md")

    elif output_format == "pdf" and not outline:
        # Try pandoc first, then weasyprint
        try:
            import subprocess
            import tempfile

            with tempfile.NamedTemporaryFile(mode="w", suffix=".md", encoding="utf-8", delete=False) as tmp:
                tmp.write(content)
                temp_md = tmp.name

            try:
                result = subprocess.run(
                    ["pandoc", temp_md, "-o", str(output_path), "--pdf-engine=xelatex"], capture_output=True, text=True
                )

                if result.returncode != 0:
                    raise Exception(f"pandoc failed: {result.stderr}")
            finally:
                os.unlink(temp_md)

            console.print("[dim]PDF generated using pandoc[/dim]")

        except FileNotFoundError:
            print_error("PDF export requires pandoc. Install from: https://pandoc.org/installing.html")
            console.print("Saving as markdown instead...")
            output_path = output_path.with_suffix(".md")
        except Exception as e:
            print_error(f"PDF conversion failed: {e}")
            console.print("Saving as markdown instead...")
            output_path = output_path.with_suffix(".md")

    # Save the output (for markdown or fallback)
    if output_path.suffix in [".md", ".html"]:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

    # Display result
    print_header("Documentation Complete")
    print_key_value("Output", str(output_path))
    print_key_value("Format", output_format)
    print_key_value("Cost", f"${cost:.4f}")

    if outline:
        console.print("\n[dim]Review the outline, then generate full docs with:[/dim]")
        console.print(f'  deepr make docs "{topic}"')
    else:
        # Show preview
        preview_lines = content.split("\n")[:15]
        console.print("\n[dim]Preview:[/dim]")
        for line in preview_lines:
            console.print(f"  {line[:80]}")
        if len(content.split("\n")) > 15:
            console.print("  ...")


@make.command(name="strategy")
@click.argument("topic")
@click.option(
    "--perspective",
    "-p",
    type=click.Choice(["technical", "business", "financial", "all"]),
    default="all",
    help="Analysis perspective (default: all)",
)
@click.option(
    "--horizon",
    "-h",
    "time_horizon",
    type=click.Choice(["3mo", "6mo", "12mo", "3yr"]),
    default="12mo",
    help="Planning timeframe (default: 12mo)",
)
@click.option(
    "--provider",
    "-P",
    default=None,
    type=click.Choice(["openai", "azure", "gemini", "xai"]),
    help="AI provider (default: openai for deep research)",
)
@click.option("--model", "-m", default=None, help="Model to use (default: o4-mini-deep-research)")
@click.option("--output", "-o", type=click.Path(), default=None, help="Output file path (default: auto-generated)")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def make_strategy(
    topic: str,
    perspective: str,
    time_horizon: str,
    provider: Optional[str],
    model: Optional[str],
    output: Optional[str],
    yes: bool,
):
    """Generate strategic analysis from research.

    Creates business-focused strategic synthesis with executive summary,
    key findings, recommendations, risks, and timeline.

    EXAMPLES:
      # Generate strategic analysis
      deepr make strategy "Fabric adoption roadmap for enterprise"

      # Technical perspective only
      deepr make strategy "Cloud migration" --perspective technical

      # Short-term planning (3 months)
      deepr make strategy "Q1 priorities" --horizon 3mo

      # Business perspective with 3-year horizon
      deepr make strategy "Market expansion" -p business -h 3yr
    """
    from deepr.cli.validation import validate_prompt

    # Validate topic
    try:
        topic = validate_prompt(topic, max_length=10000, field_name="topic")
    except click.UsageError as e:
        click.echo(f"Error: {e}", err=True)
        return

    run_async_command(_generate_strategy(topic, perspective, time_horizon, provider, model, output, yes))


async def _generate_strategy(
    topic: str,
    perspective: str,
    time_horizon: str,
    provider: Optional[str],
    model: Optional[str],
    output: Optional[str],
    yes: bool,
):
    """Generate strategic analysis with structured sections."""
    import re
    from datetime import datetime
    from pathlib import Path

    from deepr.cli.progress import ProgressFeedback
    from deepr.config import AppConfig
    from deepr.providers import create_provider

    config = AppConfig.from_env()
    progress = ProgressFeedback()

    # Set defaults for provider and model
    if not provider:
        provider = os.getenv("DEEPR_DEEP_RESEARCH_PROVIDER", "openai")
    if not model:
        model = os.getenv("DEEPR_DEEP_RESEARCH_MODEL", "o4-mini-deep-research")

    console.print(f"[dim]Using {provider}/{model}[/dim]")

    # Get API key based on provider
    if provider == "xai":
        api_key = os.getenv("XAI_API_KEY")
    elif provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
    elif provider == "azure":
        api_key = config.provider.azure_api_key
    else:
        api_key = config.provider.openai_api_key

    if not api_key:
        print_error(f"No API key found for provider: {provider}")
        console.print("\nSet the appropriate environment variable:")
        if provider == "xai":
            console.print("  export XAI_API_KEY=your-key")
        elif provider == "gemini":
            console.print("  export GEMINI_API_KEY=your-key")
        elif provider == "azure":
            console.print("  export AZURE_OPENAI_API_KEY=your-key")
        else:
            console.print("  export OPENAI_API_KEY=your-key")
        return

    provider_instance = create_provider(provider, api_key=api_key)

    # Map time horizon to description
    horizon_desc = {
        "3mo": "3 months (short-term tactical)",
        "6mo": "6 months (medium-term)",
        "12mo": "12 months (annual planning)",
        "3yr": "3 years (long-term strategic)",
    }[time_horizon]

    # Map perspective to focus areas
    perspective_focus = {
        "technical": "Focus on technical architecture, implementation details, technology choices, integration patterns, and technical risks.",
        "business": "Focus on business value, ROI, market positioning, competitive advantage, and organizational impact.",
        "financial": "Focus on cost analysis, budget requirements, financial risks, investment timeline, and expected returns.",
        "all": "Provide a comprehensive analysis covering technical, business, and financial perspectives.",
    }[perspective]

    # Build the prompt
    prompt = f"""Create a strategic analysis for: {topic}

Planning Horizon: {horizon_desc}
Perspective: {perspective_focus}

Structure the analysis with these sections:

## Executive Summary
A concise 2-3 paragraph overview of the strategic recommendation.

## Current State Assessment
Analysis of the current situation, challenges, and opportunities.

## Key Findings
Numbered list of the most important discoveries from research.
Include inline citations [Source: source_name] for factual claims.

## Strategic Recommendations
Prioritized recommendations with rationale for each.
Include implementation considerations.

## Risk Analysis
Identify key risks with likelihood, impact, and mitigation strategies.
Format as a table if appropriate.

## Implementation Timeline
Phase-based timeline aligned with the {time_horizon} horizon.
Include milestones and dependencies.

## Resource Requirements
Budget estimates, team requirements, and technology needs.

## Success Metrics
KPIs and success criteria for measuring progress.

## References
List all sources cited in the analysis.

Use clear, professional business writing. Target audience: executive leadership and senior technical staff.
"""

    # Show what we're doing
    print_header("Strategic Analysis")
    print_key_value("Topic", topic)
    print_key_value("Perspective", perspective)
    print_key_value("Time Horizon", horizon_desc)

    if not yes:
        estimated_cost = "$2.00-$5.00" if "deep-research" in model else "$0.20-$1.00"
        console.print(f"\n[dim]Estimated cost: {estimated_cost}[/dim]")
        if not click.confirm("\nProceed with strategic analysis?"):
            console.print("Cancelled")
            return

    # Generate strategy
    with progress.operation("Generating strategic analysis..."):
        try:
            response = await provider_instance.complete(prompt, model=model)
            content = response.choices[0].message.content
            cost = getattr(response, "cost", 0.0) if hasattr(response, "cost") else 0.0
        except Exception as e:
            print_error(f"Generation failed: {e}")
            return

    progress.phase_complete("Analysis complete", cost=cost)

    # Determine output path
    if not output:
        # Generate filename from topic
        safe_topic = re.sub(r"[^\w\s-]", "", topic.lower())
        safe_topic = re.sub(r"[-\s]+", "-", safe_topic)[:50]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = f"strategy_{safe_topic}_{timestamp}.md"

    output_path = Path(output)

    # Save the output
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    # Display result
    print_header("Strategic Analysis Complete")
    print_key_value("Output", str(output_path))
    print_key_value("Perspective", perspective)
    print_key_value("Horizon", time_horizon)
    print_key_value("Cost", f"${cost:.4f}")

    # Show preview
    preview_lines = content.split("\n")[:20]
    console.print("\n[dim]Preview:[/dim]")
    for line in preview_lines:
        console.print(f"  {line[:80]}")
    if len(content.split("\n")) > 20:
        console.print("  ...")


@click.group()
def agentic():
    """Autonomous multi-step research workflows.

    Execute complex research goals through Plan-Execute-Review cycles
    without manual orchestration.

    COMMANDS:
      deepr agentic research "topic" --goal "goal"  Autonomous research

    EXAMPLES:
      deepr agentic research "Fabric ALZ governance" --goal "produce reference docs"
      deepr agentic research "Cloud migration" --goal "create checklist" --rounds 3
    """
    pass


@agentic.command(name="research")
@click.argument("topic")
@click.option("--goal", "-g", required=True, help="The goal to achieve (e.g., 'produce reference docs + checklist')")
@click.option("--rounds", "-r", type=int, default=3, help="Maximum Plan-Execute-Review cycles (default: 3)")
@click.option("--budget", "-b", type=float, default=10.0, help="Budget limit for entire workflow (default: $10)")
@click.option(
    "--provider",
    "-p",
    default=None,
    type=click.Choice(["openai", "azure", "gemini", "xai"]),
    help="AI provider (default: openai)",
)
@click.option("--model", "-m", default=None, help="Model to use (default: o4-mini-deep-research)")
@click.option(
    "--output", "-o", type=click.Path(), default=None, help="Output directory for results (default: auto-generated)"
)
@click.option("--resume", is_flag=True, default=False, help="Resume from previous interrupted session")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def agentic_research(
    topic: str,
    goal: str,
    rounds: int,
    budget: float,
    provider: Optional[str],
    model: Optional[str],
    output: Optional[str],
    resume: bool,
    yes: bool,
):
    """Execute autonomous multi-step research workflow.

    Runs Plan-Execute-Review cycles to achieve complex research goals.
    Each cycle:
    1. PLAN: Analyze goal and create research plan
    2. EXECUTE: Run research tasks from the plan
    3. REVIEW: Evaluate progress and decide next steps

    Intermediate results are saved automatically, allowing resume if interrupted.

    EXAMPLES:
      # Basic agentic research
      deepr agentic research "Fabric ALZ governance" --goal "produce reference docs"

      # With budget and round limits
      deepr agentic research "Cloud migration" --goal "create checklist" -r 5 -b 20

      # Resume interrupted session
      deepr agentic research "Topic" --goal "Goal" --resume
    """
    from deepr.cli.validation import validate_budget, validate_prompt

    # Validate inputs
    try:
        topic = validate_prompt(topic, max_length=5000, field_name="topic")
        goal = validate_prompt(goal, max_length=2000, field_name="goal")
    except click.UsageError as e:
        click.echo(f"Error: {e}", err=True)
        return

    # Validate budget
    if not yes:
        try:
            budget = validate_budget(budget, min_budget=1.0)
        except (click.UsageError, click.Abort) as e:
            if isinstance(e, click.Abort):
                click.echo("Cancelled")
                return
            click.echo(f"Error: {e}", err=True)
            return

    run_async_command(_run_agentic_research(topic, goal, rounds, budget, provider, model, output, resume, yes))


async def _run_agentic_research(
    topic: str,
    goal: str,
    max_rounds: int,
    budget: float,
    provider: Optional[str],
    model: Optional[str],
    output_dir: Optional[str],
    resume: bool,
    yes: bool,
):
    """Execute autonomous multi-step research with Plan-Execute-Review cycles."""
    import json
    import re
    from datetime import datetime
    from pathlib import Path

    from deepr.cli.progress import ProgressFeedback
    from deepr.config import AppConfig
    from deepr.providers import create_provider

    config = AppConfig.from_env()
    progress = ProgressFeedback()

    # Set defaults for provider and model
    if not provider:
        provider = os.getenv("DEEPR_DEEP_RESEARCH_PROVIDER", "openai")
    if not model:
        model = os.getenv("DEEPR_DEEP_RESEARCH_MODEL", "o4-mini-deep-research")

    console.print(f"[dim]Using {provider}/{model}[/dim]")

    # Get API key based on provider
    if provider == "xai":
        api_key = os.getenv("XAI_API_KEY")
    elif provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
    elif provider == "azure":
        api_key = config.provider.azure_api_key
    else:
        api_key = config.provider.openai_api_key

    if not api_key:
        print_error(f"No API key found for provider: {provider}")
        return

    provider_instance = create_provider(provider, api_key=api_key)

    # Setup output directory
    if not output_dir:
        safe_topic = re.sub(r"[^\w\s-]", "", topic.lower())
        safe_topic = re.sub(r"[-\s]+", "-", safe_topic)[:30]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = f"agentic_{safe_topic}_{timestamp}"

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # State file for resume capability
    state_file = output_path / "agentic_state.json"

    # Initialize or load state
    if resume and state_file.exists():
        with open(state_file, encoding="utf-8") as f:
            state = json.load(f)
        console.print(f"[dim]Resuming from round {state['current_round']}/{state['max_rounds']}[/dim]")
        current_round = state["current_round"]
        total_cost = state["total_cost"]
        completed_tasks = state["completed_tasks"]
        research_results = state["research_results"]
    else:
        state = {
            "topic": topic,
            "goal": goal,
            "max_rounds": max_rounds,
            "budget": budget,
            "current_round": 1,
            "total_cost": 0.0,
            "completed_tasks": [],
            "research_results": [],
            "started_at": datetime.now().isoformat(),
        }
        current_round = 1
        total_cost = 0.0
        completed_tasks = []
        research_results = []

    # Display plan
    print_header("Agentic Research")
    print_key_value("Topic", topic)
    print_key_value("Goal", goal)
    print_key_value("Max Rounds", str(max_rounds))
    print_key_value("Budget", f"${budget:.2f}")
    print_key_value("Output", str(output_path))

    if not yes and not resume:
        console.print("\n[dim]Estimated cost: $3.00-$10.00 depending on complexity[/dim]")
        if not click.confirm("\nProceed with agentic research?"):
            console.print("Cancelled")
            return

    def save_state():
        """Save current state for resume capability."""
        state["current_round"] = current_round
        state["total_cost"] = total_cost
        state["completed_tasks"] = completed_tasks
        state["research_results"] = research_results
        state["updated_at"] = datetime.now().isoformat()
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    try:
        while current_round <= max_rounds and total_cost < budget:
            print_section_header(f"Round {current_round}/{max_rounds}")

            # PHASE 1: PLAN
            console.print("[bold cyan]PLAN[/bold cyan] - Creating research plan...")

            plan_prompt = f"""You are a research planner. Create a research plan for:

Topic: {topic}
Goal: {goal}
Round: {current_round}/{max_rounds}
Budget remaining: ${budget - total_cost:.2f}

Previous completed tasks: {json.dumps(completed_tasks) if completed_tasks else "None"}

Create 2-4 specific research tasks that will help achieve the goal.
Each task should be:
- Specific and actionable
- Achievable in one research query
- Building toward the overall goal

Respond with JSON:
{{
    "tasks": [
        {{"id": 1, "description": "task description", "priority": "high/medium/low"}},
        ...
    ],
    "reasoning": "why these tasks will help achieve the goal"
}}
"""

            with progress.operation("Planning..."):
                try:
                    plan_response = await provider_instance.complete(plan_prompt, model=model)
                    plan_content = plan_response.choices[0].message.content
                    plan_cost = getattr(plan_response, "cost", 0.05) if hasattr(plan_response, "cost") else 0.05
                    total_cost += plan_cost
                except Exception as e:
                    print_error(f"Planning failed: {e}")
                    save_state()
                    return

            # Parse plan
            try:
                plan_json = re.search(r"\{[\s\S]*\}", plan_content)
                if plan_json:
                    plan = json.loads(plan_json.group())
                    tasks = plan.get("tasks", [])
                else:
                    tasks = [{"id": 1, "description": f"Research {topic} to achieve: {goal}", "priority": "high"}]
            except json.JSONDecodeError:
                tasks = [{"id": 1, "description": f"Research {topic} to achieve: {goal}", "priority": "high"}]

            console.print(f"[dim]Plan created ({len(tasks)} tasks, ${plan_cost:.4f})[/dim]")
            for task in tasks:
                console.print(f"  • {task['description'][:60]}...")

            # PHASE 2: EXECUTE
            console.print("\n[bold cyan]EXECUTE[/bold cyan] - Running research tasks...")

            round_results = []
            for task in tasks:
                if total_cost >= budget:
                    console.print("[yellow]Budget exhausted. Pausing...[/yellow]")
                    break

                task_desc = task["description"]
                console.print(f"\n[dim]Task: {task_desc[:50]}...[/dim]")

                with progress.operation("Researching..."):
                    try:
                        research_prompt = f'''Research the following to help achieve the goal "{goal}":

{task_desc}

Provide comprehensive findings with citations [Source: source_name].
'''
                        research_response = await provider_instance.complete(research_prompt, model=model)
                        research_content = research_response.choices[0].message.content
                        research_cost = (
                            getattr(research_response, "cost", 0.5) if hasattr(research_response, "cost") else 0.5
                        )
                        total_cost += research_cost

                        round_results.append({"task": task_desc, "result": research_content, "cost": research_cost})
                        completed_tasks.append(task_desc)

                        console.print(f"[dim]Complete (${research_cost:.4f})[/dim]")

                    except Exception as e:
                        print_error(f"Research failed: {e}")
                        round_results.append({"task": task_desc, "result": f"Error: {e}", "cost": 0})

            research_results.extend(round_results)

            # Save intermediate results
            round_file = output_path / f"round_{current_round}_results.md"
            with open(round_file, "w", encoding="utf-8") as f:
                f.write(f"# Round {current_round} Results\n\n")
                for result in round_results:
                    f.write(f"## Task: {result['task']}\n\n")
                    f.write(result["result"])
                    f.write("\n\n---\n\n")

            # PHASE 3: REVIEW
            console.print("\n[bold cyan]REVIEW[/bold cyan] - Evaluating progress...")

            review_prompt = f"""Review the research progress:

Goal: {goal}
Completed tasks: {len(completed_tasks)}
Budget used: ${total_cost:.2f} of ${budget:.2f}
Rounds completed: {current_round}/{max_rounds}

Latest results summary:
{chr(10).join([f"- {r['task'][:50]}..." for r in round_results])}

Evaluate:
1. How much progress toward the goal? (0-100%)
2. Is the goal achieved?
3. What's missing?

Respond with JSON:
{{
    "progress_percent": 0-100,
    "goal_achieved": true/false,
    "missing": ["what's still needed"],
    "recommendation": "continue/complete"
}}
"""

            with progress.operation("Reviewing..."):
                try:
                    review_response = await provider_instance.complete(review_prompt, model=model)
                    review_content = review_response.choices[0].message.content
                    review_cost = getattr(review_response, "cost", 0.05) if hasattr(review_response, "cost") else 0.05
                    total_cost += review_cost
                except Exception as e:
                    print_error(f"Review failed: {e}")
                    save_state()
                    return

            # Parse review
            try:
                review_json = re.search(r"\{[\s\S]*\}", review_content)
                if review_json:
                    review = json.loads(review_json.group())
                else:
                    review = {"progress_percent": 50, "goal_achieved": False, "recommendation": "continue"}
            except json.JSONDecodeError:
                review = {"progress_percent": 50, "goal_achieved": False, "recommendation": "continue"}

            progress_pct = review.get("progress_percent", 50)
            goal_achieved = review.get("goal_achieved", False)

            console.print(f"[dim]Progress: {progress_pct}% | Cost: ${total_cost:.2f}[/dim]")

            # Save state after each round
            current_round += 1
            save_state()

            # Check if goal achieved
            if goal_achieved or review.get("recommendation") == "complete":
                console.print("\n[green]Goal achieved![/green]")
                break

            # Budget check
            if total_cost >= budget * 0.95:
                console.print(
                    f"\n[yellow]Budget nearly exhausted (${total_cost:.2f}/${budget:.2f}). Pausing...[/yellow]"
                )
                break

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted. Saving state...[/yellow]")
        save_state()
        console.print(f'Resume with: deepr agentic research "{topic}" --goal "{goal}" --resume')
        return

    # Generate final synthesis
    print_section_header("Final Synthesis")

    synthesis_prompt = f"""Synthesize all research results into a final deliverable for:

Goal: {goal}

Research findings:
{chr(10).join([f"- {r['task']}: {r['result'][:200]}..." for r in research_results[:10]])}

Create a comprehensive final document that achieves the stated goal.
Include all relevant findings with citations.
"""

    with progress.operation("Synthesizing final results..."):
        try:
            synthesis_response = await provider_instance.complete(synthesis_prompt, model=model)
            synthesis_content = synthesis_response.choices[0].message.content
            synthesis_cost = getattr(synthesis_response, "cost", 0.5) if hasattr(synthesis_response, "cost") else 0.5
            total_cost += synthesis_cost
        except Exception as e:
            print_error(f"Synthesis failed: {e}")
            synthesis_content = "Synthesis failed. See individual round results."

    # Save final output
    final_file = output_path / "final_output.md"
    with open(final_file, "w", encoding="utf-8") as f:
        f.write(f"# {topic}\n\n")
        f.write(f"**Goal:** {goal}\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("---\n\n")
        f.write(synthesis_content)

    # Update state as complete
    state["completed_at"] = datetime.now().isoformat()
    state["total_cost"] = total_cost
    state["status"] = "complete"
    save_state()

    # Display summary
    print_header("Agentic Research Complete")
    print_key_value("Rounds completed", str(current_round - 1))
    print_key_value("Tasks completed", str(len(completed_tasks)))
    print_key_value("Total cost", f"${total_cost:.4f}")
    print_key_value("Output directory", str(output_path))
    print_key_value("Final output", str(final_file))

    # Show preview
    preview_lines = synthesis_content.split("\n")[:10]
    console.print("\n[dim]Preview:[/dim]")
    for line in preview_lines:
        console.print(f"  {line[:80]}")
    if len(synthesis_content.split("\n")) > 10:
        console.print("  ...")
