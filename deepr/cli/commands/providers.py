"""Provider management CLI commands.

Provides commands for viewing provider status and metrics:
- deepr providers status - Show provider health and metrics
- deepr providers fallbacks - Show fallback history
- deepr providers reset - Reset provider metrics
"""

from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from deepr.observability.provider_router import AutonomousProviderRouter

console = Console()


@click.group()
def providers():
    """Provider management and monitoring."""
    pass


@providers.command()
@click.option("--all", "show_all", is_flag=True, help="Show all providers including unhealthy")
def status(show_all: bool):
    """Show provider health status and metrics."""
    router = AutonomousProviderRouter()
    status_data = router.get_status()

    # Summary panel
    healthy = status_data["healthy_count"]
    unhealthy = status_data["unhealthy_count"]
    total_requests = status_data["total_requests"]
    total_cost = status_data["total_cost"]

    health_color = "green" if unhealthy == 0 else "yellow" if unhealthy < healthy else "red"

    console.print(
        Panel(
            f"[bold]Provider Health Summary[/bold]\n\n"
            f"Healthy: [{health_color}]{healthy}[/{health_color}]\n"
            f"Unhealthy: [{health_color}]{unhealthy}[/{health_color}]\n"
            f"Total Requests: {total_requests:,}\n"
            f"Total Cost: ${total_cost:.2f}",
            title="Provider Status",
        )
    )

    # Provider table
    if not status_data["providers"]:
        console.print("\n[dim]No provider metrics recorded yet[/dim]")
        return

    table = Table(title="Provider Metrics")
    table.add_column("Provider/Model", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Success Rate", justify="right")
    table.add_column("Avg Latency", justify="right")
    table.add_column("Avg Cost", justify="right")
    table.add_column("Requests", justify="right")

    for name, metrics in sorted(status_data["providers"].items()):
        if not show_all and not metrics["healthy"]:
            continue

        status_icon = "[green]●[/green]" if metrics["healthy"] else "[red]●[/red]"
        success_rate = metrics["success_rate"] * 100
        rate_color = "green" if success_rate >= 95 else "yellow" if success_rate >= 80 else "red"

        table.add_row(
            name,
            status_icon,
            f"[{rate_color}]{success_rate:.1f}%[/{rate_color}]",
            f"{metrics['avg_latency_ms']:.0f}ms",
            f"${metrics['avg_cost']:.4f}",
            str(metrics["total_requests"]),
        )

    console.print(table)

    # Show unhealthy providers with errors
    unhealthy_providers = [
        (name, m) for name, m in status_data["providers"].items() if not m["healthy"] and m.get("last_error")
    ]

    if unhealthy_providers:
        console.print("\n[bold red]Unhealthy Providers:[/bold red]")
        for name, metrics in unhealthy_providers:
            console.print(f"  [red]●[/red] {name}: {metrics['last_error']}")

    # Show auto-disabled providers
    disabled = router.get_disabled_providers()
    if disabled:
        console.print("\n[bold yellow]Auto-Disabled Providers:[/bold yellow]")
        for d in disabled:
            console.print(f"  [yellow]○[/yellow] {d['provider']}/{d['model']}: {d['reason']}")


@providers.command()
@click.option("--limit", default=10, help="Number of events to show")
def fallbacks(limit: int):
    """Show fallback history."""
    router = AutonomousProviderRouter()
    status_data = router.get_status()

    events = status_data.get("recent_fallbacks", [])

    if not events:
        console.print("[dim]No fallback events recorded[/dim]")
        return

    table = Table(title=f"Recent Fallback Events (Last {min(limit, len(events))})")
    table.add_column("Time", style="dim")
    table.add_column("Original", style="red")
    table.add_column("Fallback", style="green")
    table.add_column("Reason")
    table.add_column("Success", justify="center")

    for event in events[-limit:]:
        success_icon = "[green]✓[/green]" if event["success"] else "[red]✗[/red]"
        timestamp = event["timestamp"][:16].replace("T", " ")

        table.add_row(
            timestamp,
            f"{event['original_provider']}/{event['original_model']}",
            f"{event['fallback_provider']}/{event['fallback_model']}",
            event["reason"][:40],
            success_icon,
        )

    console.print(table)


@providers.command()
@click.option("--provider", help="Reset specific provider")
@click.option("--model", help="Reset specific model")
@click.option("--all", "reset_all", is_flag=True, help="Reset all metrics")
@click.confirmation_option(prompt="Are you sure you want to reset provider metrics?")
def reset(provider: Optional[str], model: Optional[str], reset_all: bool):
    """Reset provider metrics."""

    router = AutonomousProviderRouter()

    if reset_all:
        router.metrics.clear()
        router.fallback_events.clear()
        router._save()
        console.print("[green]✓ All provider metrics reset[/green]")
    elif provider and model:
        key = (provider, model)
        if key in router.metrics:
            del router.metrics[key]
            router._save()
            console.print(f"[green]✓ Metrics reset for {provider}/{model}[/green]")
        else:
            console.print(f"[yellow]No metrics found for {provider}/{model}[/yellow]")
    else:
        console.print("[red]Specify --provider and --model, or use --all[/red]")


@providers.command()
@click.argument("task_type", default="general")
@click.option("--prefer-cost", is_flag=True, help="Prefer cheaper providers")
@click.option("--prefer-speed", is_flag=True, help="Prefer faster providers")
def recommend(task_type: str, prefer_cost: bool, prefer_speed: bool):
    """Recommend best provider for a task type.

    Task types: research, chat, synthesis, fact_check, quick, general
    """
    router = AutonomousProviderRouter()

    provider, model = router.select_provider(task_type=task_type, prefer_cost=prefer_cost, prefer_speed=prefer_speed)

    console.print(
        Panel(
            f"[bold]Recommended Provider[/bold]\n\n"
            f"Task Type: {task_type}\n"
            f"Provider: [cyan]{provider}[/cyan]\n"
            f"Model: [cyan]{model}[/cyan]\n\n"
            f"Preferences:\n"
            f"  Cost: {'[green]Yes[/green]' if prefer_cost else '[dim]No[/dim]'}\n"
            f"  Speed: {'[green]Yes[/green]' if prefer_speed else '[dim]No[/dim]'}",
            title="Provider Recommendation",
        )
    )

    # Show metrics if available
    key = (provider, model)
    if key in router.metrics:
        metrics = router.metrics[key]
        console.print("\n[dim]Historical metrics:[/dim]")
        console.print(f"  Success rate: {metrics.success_rate * 100:.1f}%")
        console.print(f"  Avg latency: {metrics.rolling_avg_latency:.0f}ms")
        console.print(f"  Avg cost: ${metrics.rolling_avg_cost:.4f}")


@providers.command()
@click.option("--quick", is_flag=True, help="Quick benchmark (1 request per provider)")
@click.option("--provider", "target_provider", help="Benchmark specific provider only")
@click.option("--iterations", "-n", default=3, help="Number of test iterations")
@click.option("--history", is_flag=True, help="Show historical benchmark data instead of running tests")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for scripting")
def benchmark(quick: bool, target_provider: Optional[str], iterations: int, history: bool, json_output: bool):
    """Benchmark provider performance.

    Sends test requests to measure latency and reliability.
    Use --history to see accumulated historical data.

    Examples:
        deepr providers benchmark --quick
        deepr providers benchmark --provider openai
        deepr providers benchmark -n 5
        deepr providers benchmark --history
        deepr providers benchmark --history --json
    """
    import json as json_module

    # Show historical data if requested
    if history:
        router = AutonomousProviderRouter()
        data = router.get_benchmark_data()

        if json_output:
            print(json_module.dumps(data, indent=2))
            return

        if not data["benchmarks"]:
            console.print("[dim]No historical benchmark data available[/dim]")
            return

        # Summary panel
        summary = data["summary"]
        console.print(
            Panel(
                f"[bold]Historical Benchmark Summary[/bold]\n\n"
                f"Total Providers: {summary['total_providers']}\n"
                f"Healthy: [green]{summary['healthy_providers']}[/green]\n"
                f"Unhealthy: [red]{summary['unhealthy_providers']}[/red]\n"
                f"Total Requests: {summary['total_requests']:,}\n"
                f"Total Cost: ${summary['total_cost_usd']:.2f}",
                title="Historical Data",
            )
        )

        # Detailed table
        table = Table(title="Provider Benchmarks (Historical)")
        table.add_column("Provider/Model", style="cyan")
        table.add_column("Success", justify="center")
        table.add_column("Requests", justify="right")
        table.add_column("P50", justify="right")
        table.add_column("P95", justify="right")
        table.add_column("P99", justify="right")
        table.add_column("Avg Cost", justify="right", style="yellow")
        table.add_column("Health", justify="center")

        for b in data["benchmarks"]:
            name = f"{b['provider']}/{b['model']}"
            success_pct = b["success_rate"] * 100
            success_color = "green" if success_pct >= 95 else "yellow" if success_pct >= 80 else "red"
            health_icon = "[green]●[/green]" if b["health"]["is_healthy"] else "[red]●[/red]"

            table.add_row(
                name,
                f"[{success_color}]{success_pct:.1f}%[/{success_color}]",
                str(b["total_requests"]),
                f"{b['latency']['p50_ms']:.0f}ms",
                f"{b['latency']['p95_ms']:.0f}ms",
                f"{b['latency']['p99_ms']:.0f}ms",
                f"${b['cost']['avg_usd']:.4f}",
                health_icon,
            )

        console.print(table)

        # Task type breakdown
        task_types_found = set()
        for b in data["benchmarks"]:
            task_types_found.update(b["task_types"].keys())

        if task_types_found:
            console.print("\n[bold]Success Rate by Task Type[/bold]")
            task_table = Table()
            task_table.add_column("Provider/Model", style="cyan")
            for task_type in sorted(task_types_found):
                task_table.add_column(task_type.capitalize(), justify="center")

            for b in data["benchmarks"]:
                name = f"{b['provider']}/{b['model']}"
                row = [name]
                for task_type in sorted(task_types_found):
                    stats = b["task_types"].get(task_type)
                    if stats:
                        rate = stats["success_rate"] * 100
                        color = "green" if rate >= 95 else "yellow" if rate >= 80 else "red"
                        row.append(f"[{color}]{rate:.0f}%[/{color}]")
                    else:
                        row.append("[dim]-[/dim]")
                task_table.add_row(*row)

            console.print(task_table)

        return
    import time

    from rich.progress import Progress, SpinnerColumn, TextColumn

    if quick:
        iterations = 1

    # Define test providers and a simple prompt
    test_providers = [
        ("openai", "gpt-5-mini"),
        ("gemini", "gemini-2.5-flash"),
        ("xai", "grok-4-fast"),
    ]

    if target_provider:
        test_providers = [(p, m) for p, m in test_providers if p == target_provider]
        if not test_providers:
            console.print(f"[red]Unknown provider: {target_provider}[/red]")
            return

    test_prompt = "What is 2+2? Answer in one word."

    console.print(
        Panel(
            f"[bold]Provider Benchmark[/bold]\n\n"
            f"Iterations: {iterations}\n"
            f"Providers: {len(test_providers)}\n"
            f'Test prompt: "{test_prompt}"',
            title="Benchmark Configuration",
        )
    )

    results = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        for provider, model in test_providers:
            task = progress.add_task(f"Testing {provider}/{model}...", total=None)
            latencies = []
            errors = 0

            for _i in range(iterations):
                start = time.time()
                try:
                    # Use synchronous client for simplicity
                    if provider == "openai":
                        from openai import OpenAI

                        client = OpenAI()
                        client.chat.completions.create(
                            model=model,
                            messages=[{"role": "user", "content": test_prompt}],
                            max_tokens=10,
                        )
                    elif provider == "gemini":
                        from google import genai

                        client = genai.Client()
                        client.models.generate_content(
                            model=model,
                            contents=test_prompt,
                        )
                    elif provider == "xai":
                        from openai import OpenAI

                        client = OpenAI(
                            base_url="https://api.x.ai/v1",
                        )
                        client.chat.completions.create(
                            model=model,
                            messages=[{"role": "user", "content": test_prompt}],
                            max_tokens=10,
                        )
                    else:
                        continue

                    latency = (time.time() - start) * 1000
                    latencies.append(latency)
                except Exception:
                    errors += 1

            progress.remove_task(task)

            if latencies:
                import statistics

                results[f"{provider}/{model}"] = {
                    "success_rate": (iterations - errors) / iterations,
                    "avg_latency": statistics.mean(latencies),
                    "p50_latency": statistics.median(latencies),
                    "p95_latency": sorted(latencies)[int(len(latencies) * 0.95)]
                    if len(latencies) > 1
                    else latencies[0],
                    "min_latency": min(latencies),
                    "max_latency": max(latencies),
                    "errors": errors,
                }
            else:
                results[f"{provider}/{model}"] = {
                    "success_rate": 0,
                    "avg_latency": 0,
                    "errors": errors,
                }

    # Display results
    console.print()

    table = Table(title="Benchmark Results")
    table.add_column("Provider/Model", style="cyan")
    table.add_column("Success", justify="center")
    table.add_column("Avg", justify="right")
    table.add_column("P50", justify="right")
    table.add_column("P95", justify="right")
    table.add_column("Min", justify="right")
    table.add_column("Max", justify="right")

    for name, metrics in sorted(results.items(), key=lambda x: x[1].get("avg_latency", float("inf"))):
        success_pct = metrics["success_rate"] * 100
        success_color = "green" if success_pct >= 95 else "yellow" if success_pct >= 80 else "red"

        if metrics["avg_latency"] > 0:
            table.add_row(
                name,
                f"[{success_color}]{success_pct:.0f}%[/{success_color}]",
                f"{metrics['avg_latency']:.0f}ms",
                f"{metrics.get('p50_latency', 0):.0f}ms",
                f"{metrics.get('p95_latency', 0):.0f}ms",
                f"{metrics.get('min_latency', 0):.0f}ms",
                f"{metrics.get('max_latency', 0):.0f}ms",
            )
        else:
            table.add_row(
                name,
                "[red]0%[/red]",
                "-",
                "-",
                "-",
                "-",
                "-",
            )

    console.print(table)

    # Recommendation
    best = min(
        [(n, m) for n, m in results.items() if m["success_rate"] > 0],
        key=lambda x: x[1]["avg_latency"],
        default=None,
    )
    if best:
        console.print(f"\n[green]Fastest:[/green] {best[0]} ({best[1]['avg_latency']:.0f}ms avg)")


@providers.command()
def list():
    """List all available providers and models."""
    from deepr.providers.registry import MODEL_CAPABILITIES

    table = Table(title="Available Providers & Models")
    table.add_column("Provider", style="cyan")
    table.add_column("Model")
    table.add_column("Specialization")
    table.add_column("Cost/Query", justify="right", style="yellow")
    table.add_column("Latency", justify="right")

    for _key, cap in sorted(MODEL_CAPABILITIES.items()):
        specializations = ", ".join(cap.specializations[:2]) if cap.specializations else "-"
        table.add_row(
            cap.provider,
            cap.model,
            specializations,
            f"${cap.cost_per_query:.2f}",
            f"{cap.latency_ms:,}ms",
        )

    console.print(table)
