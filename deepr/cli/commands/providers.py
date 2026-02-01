"""Provider management CLI commands.

Provides commands for viewing provider status and metrics:
- deepr providers status - Show provider health and metrics
- deepr providers fallbacks - Show fallback history
- deepr providers reset - Reset provider metrics
"""

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from typing import Optional

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
    
    console.print(Panel(
        f"[bold]Provider Health Summary[/bold]\n\n"
        f"Healthy: [{health_color}]{healthy}[/{health_color}]\n"
        f"Unhealthy: [{health_color}]{unhealthy}[/{health_color}]\n"
        f"Total Requests: {total_requests:,}\n"
        f"Total Cost: ${total_cost:.2f}",
        title="Provider Status"
    ))
    
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
            str(metrics["total_requests"])
        )
    
    console.print(table)
    
    # Show unhealthy providers with errors
    unhealthy_providers = [
        (name, m) for name, m in status_data["providers"].items()
        if not m["healthy"] and m.get("last_error")
    ]
    
    if unhealthy_providers:
        console.print("\n[bold red]Unhealthy Providers:[/bold red]")
        for name, metrics in unhealthy_providers:
            console.print(f"  [red]●[/red] {name}: {metrics['last_error']}")


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
            success_icon
        )
    
    console.print(table)


@providers.command()
@click.option("--provider", help="Reset specific provider")
@click.option("--model", help="Reset specific model")
@click.option("--all", "reset_all", is_flag=True, help="Reset all metrics")
@click.confirmation_option(prompt="Are you sure you want to reset provider metrics?")
def reset(provider: Optional[str], model: Optional[str], reset_all: bool):
    """Reset provider metrics."""
    from pathlib import Path
    
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
    
    provider, model = router.select_provider(
        task_type=task_type,
        prefer_cost=prefer_cost,
        prefer_speed=prefer_speed
    )
    
    console.print(Panel(
        f"[bold]Recommended Provider[/bold]\n\n"
        f"Task Type: {task_type}\n"
        f"Provider: [cyan]{provider}[/cyan]\n"
        f"Model: [cyan]{model}[/cyan]\n\n"
        f"Preferences:\n"
        f"  Cost: {'[green]Yes[/green]' if prefer_cost else '[dim]No[/dim]'}\n"
        f"  Speed: {'[green]Yes[/green]' if prefer_speed else '[dim]No[/dim]'}",
        title="Provider Recommendation"
    ))
    
    # Show metrics if available
    key = (provider, model)
    if key in router.metrics:
        metrics = router.metrics[key]
        console.print(f"\n[dim]Historical metrics:[/dim]")
        console.print(f"  Success rate: {metrics.success_rate*100:.1f}%")
        console.print(f"  Avg latency: {metrics.rolling_avg_latency:.0f}ms")
        console.print(f"  Avg cost: ${metrics.rolling_avg_cost:.4f}")
