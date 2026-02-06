"""Diagnostics commands for expert self-awareness and knowledge tracking."""

from datetime import datetime
from typing import Optional

import click

from deepr.cli.colors import console, print_header, print_key_value, print_section_header
from deepr.experts.metacognition import MetaCognitionTracker
from deepr.experts.temporal_knowledge import TemporalKnowledgeTracker


@click.group(name="diagnostics")
def diagnostics_cli():
    """Diagnostics and self-awareness tools for experts."""
    pass


@diagnostics_cli.command(name="meta")
@click.argument("expert_name")
def show_metacognition(expert_name: str):
    """Show expert's meta-cognitive awareness (what it knows vs doesn't know).

    Examples:
        deepr diagnostics meta "AWS Expert"
        deepr diagnostics meta "Agentic Digital Consciousness"
    """
    try:
        # Load metacognition tracker
        meta = MetaCognitionTracker(expert_name)
        stats = meta.get_learning_stats()

        print_header(f"Meta-Cognitive Awareness: {expert_name}")

        # Overall stats
        print_key_value("Knowledge Gaps Tracked", str(stats["total_knowledge_gaps"]))
        console.print(f"  [dim]-[/dim] Researched: {stats['researched_gaps']}")
        console.print(f"  [dim]-[/dim] Learned: {stats['learned_gaps']}")
        console.print(f"  [dim]-[/dim] Learning Rate: {stats['learning_rate']:.1%}")
        print_key_value("Domains Tracked", str(stats["domains_tracked"]))
        console.print(f"  [dim]-[/dim] High Confidence: {stats['high_confidence_domains']}")
        console.print(f"  [dim]-[/dim] Low Confidence: {stats['low_confidence_domains']}")
        console.print(f"  [dim]-[/dim] Average Confidence: {stats['average_confidence']:.1%}")
        print_key_value("Uncertainty Events", str(stats["total_uncertainty_events"]))

        # Show knowledge gaps that need research
        suggestions = meta.suggest_proactive_research(threshold_times_asked=2)
        if suggestions:
            print_section_header("Suggested Proactive Research (asked 2+ times)")
            for topic in suggestions[:5]:
                console.print(f"  [dim]-[/dim] {topic}")

        # Show high confidence domains
        high_conf = meta.get_high_confidence_domains(min_confidence=0.7)
        if high_conf:
            print_section_header("High Confidence Domains")
            for conf in sorted(high_conf, key=lambda x: x.confidence, reverse=True)[:5]:
                console.print(f"  [dim]-[/dim] {conf.domain}: {conf.confidence:.1%} ({conf.evidence_count} sources)")

        # Show low confidence domains
        low_conf = meta.get_low_confidence_domains(max_confidence=0.4)
        if low_conf:
            print_section_header("Low Confidence Domains (need more research)")
            for conf in sorted(low_conf, key=lambda x: x.confidence)[:5]:
                console.print(f"  [dim]-[/dim] {conf.domain}: {conf.confidence:.1%} ({conf.evidence_count} sources)")

        console.print()

    except Exception as e:
        console.print(f"[error]Error loading metacognition: {e}[/error]")


@diagnostics_cli.command(name="temporal")
@click.argument("expert_name")
@click.option("--topic", "-t", help="Show timeline for specific topic")
def show_temporal(expert_name: str, topic: Optional[str] = None):
    """Show expert's temporal knowledge (when facts were learned, evolution over time).

    Examples:
        deepr diagnostics temporal "AWS Expert"
        deepr diagnostics temporal "AWS Expert" --topic "S3 pricing"
    """
    try:
        # Load temporal tracker
        temporal = TemporalKnowledgeTracker(expert_name)
        stats = temporal.get_statistics()

        print_header(f"Temporal Knowledge: {expert_name}")

        # Overall stats
        print_key_value("Topics Tracked", str(stats["total_topics"]))
        print_key_value("Total Facts", str(stats["total_facts"]))
        console.print(f"  [dim]-[/dim] Current: {stats['current_facts']}")
        console.print(f"  [dim]-[/dim] Superseded: {stats['superseded_facts']}")
        print_key_value("Contradictions Resolved", str(stats["contradictions_resolved"]))
        console.print("\n[dim]Knowledge Age:[/dim]")
        console.print(f"  [dim]-[/dim] Average: {stats['average_fact_age_days']:.0f} days")
        console.print(f"  [dim]-[/dim] Oldest: {stats['oldest_fact_age_days']:.0f} days")
        print_key_value("Stale Topics", str(stats["stale_topics"]))

        # Show specific topic timeline
        if topic:
            print_section_header(f"Learning Timeline: {topic}")

            timeline = temporal.get_knowledge_timeline(topic)
            if timeline:
                for event in timeline:
                    date_str = datetime.fromisoformat(event["date"]).strftime("%Y-%m-%d")
                    status = "CURRENT" if event["current"] else "SUPERSEDED"
                    console.print(f"{date_str} [{status}] (age: {event['age_days']}d, conf: {event['confidence']:.1%})")
                    console.print(f"  {event['fact'][:200]}...")
                    if "superseded_by" in event:
                        console.print(f"  [dim]Superseded by:[/dim] {event['superseded_by']}")
                    console.print()
            else:
                console.print(f"No knowledge recorded for topic: {topic}")

        # Show stale knowledge that needs refresh
        stale = temporal.get_stale_knowledge(max_age_days=90)
        if stale:
            print_section_header("Stale Knowledge (>90 days old, needs refresh)")
            for stale_topic in stale[:10]:
                console.print(f"  [dim]-[/dim] {stale_topic}")

        console.print()

    except Exception as e:
        console.print(f"[error]Error loading temporal knowledge: {e}[/error]")


@diagnostics_cli.command(name="all")
@click.argument("expert_name")
def show_all_diagnostics(expert_name: str):
    """Show complete diagnostic report for an expert.

    Examples:
        deepr diagnostics all "AWS Expert"
    """
    import click.core

    ctx = click.get_current_context()

    # Call both diagnostic commands
    ctx.invoke(show_metacognition, expert_name=expert_name)
    ctx.invoke(show_temporal, expert_name=expert_name)


if __name__ == "__main__":
    diagnostics_cli()
