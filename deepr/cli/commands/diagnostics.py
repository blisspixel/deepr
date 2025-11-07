"""Diagnostics commands for expert self-awareness and knowledge tracking."""

import click
from pathlib import Path
from datetime import datetime
from deepr.experts.profile import ExpertStore
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

        click.echo(f"\n{'='*70}")
        click.echo(f"  Meta-Cognitive Awareness: {expert_name}")
        click.echo(f"{'='*70}\n")

        # Overall stats
        click.echo(f"Knowledge Gaps Tracked: {stats['total_knowledge_gaps']}")
        click.echo(f"  - Researched: {stats['researched_gaps']}")
        click.echo(f"  - Learned: {stats['learned_gaps']}")
        click.echo(f"  - Learning Rate: {stats['learning_rate']:.1%}")
        click.echo(f"\nDomains Tracked: {stats['domains_tracked']}")
        click.echo(f"  - High Confidence: {stats['high_confidence_domains']}")
        click.echo(f"  - Low Confidence: {stats['low_confidence_domains']}")
        click.echo(f"  - Average Confidence: {stats['average_confidence']:.1%}")
        click.echo(f"\nUncertainty Events: {stats['total_uncertainty_events']}")

        # Show knowledge gaps that need research
        suggestions = meta.suggest_proactive_research(threshold_times_asked=2)
        if suggestions:
            click.echo(f"\n{'='*70}")
            click.echo(f"Suggested Proactive Research (asked {2}+ times):")
            click.echo(f"{'='*70}\n")
            for topic in suggestions[:5]:
                click.echo(f"  - {topic}")

        # Show high confidence domains
        high_conf = meta.get_high_confidence_domains(min_confidence=0.7)
        if high_conf:
            click.echo(f"\n{'='*70}")
            click.echo(f"High Confidence Domains:")
            click.echo(f"{'='*70}\n")
            for conf in sorted(high_conf, key=lambda x: x.confidence, reverse=True)[:5]:
                click.echo(f"  - {conf.domain}: {conf.confidence:.1%} ({conf.evidence_count} sources)")

        # Show low confidence domains
        low_conf = meta.get_low_confidence_domains(max_confidence=0.4)
        if low_conf:
            click.echo(f"\n{'='*70}")
            click.echo(f"Low Confidence Domains (need more research):")
            click.echo(f"{'='*70}\n")
            for conf in sorted(low_conf, key=lambda x: x.confidence)[:5]:
                click.echo(f"  - {conf.domain}: {conf.confidence:.1%} ({conf.evidence_count} sources)")

        click.echo()

    except Exception as e:
        click.echo(f"Error loading metacognition: {e}")


@diagnostics_cli.command(name="temporal")
@click.argument("expert_name")
@click.option("--topic", "-t", help="Show timeline for specific topic")
def show_temporal(expert_name: str, topic: str = None):
    """Show expert's temporal knowledge (when facts were learned, evolution over time).

    Examples:
        deepr diagnostics temporal "AWS Expert"
        deepr diagnostics temporal "AWS Expert" --topic "S3 pricing"
    """
    try:
        # Load temporal tracker
        temporal = TemporalKnowledgeTracker(expert_name)
        stats = temporal.get_statistics()

        click.echo(f"\n{'='*70}")
        click.echo(f"  Temporal Knowledge: {expert_name}")
        click.echo(f"{'='*70}\n")

        # Overall stats
        click.echo(f"Topics Tracked: {stats['total_topics']}")
        click.echo(f"Total Facts: {stats['total_facts']}")
        click.echo(f"  - Current: {stats['current_facts']}")
        click.echo(f"  - Superseded: {stats['superseded_facts']}")
        click.echo(f"Contradictions Resolved: {stats['contradictions_resolved']}")
        click.echo(f"\nKnowledge Age:")
        click.echo(f"  - Average: {stats['average_fact_age_days']:.0f} days")
        click.echo(f"  - Oldest: {stats['oldest_fact_age_days']:.0f} days")
        click.echo(f"Stale Topics: {stats['stale_topics']}")

        # Show specific topic timeline
        if topic:
            click.echo(f"\n{'='*70}")
            click.echo(f"Learning Timeline: {topic}")
            click.echo(f"{'='*70}\n")

            timeline = temporal.get_knowledge_timeline(topic)
            if timeline:
                for event in timeline:
                    date_str = datetime.fromisoformat(event['date']).strftime("%Y-%m-%d")
                    status = "CURRENT" if event['current'] else "SUPERSEDED"
                    click.echo(f"{date_str} [{status}] (age: {event['age_days']}d, conf: {event['confidence']:.1%})")
                    click.echo(f"  {event['fact'][:200]}...")
                    if 'superseded_by' in event:
                        click.echo(f"  > Superseded by: {event['superseded_by']}")
                    click.echo()
            else:
                click.echo(f"No knowledge recorded for topic: {topic}")

        # Show stale knowledge that needs refresh
        stale = temporal.get_stale_knowledge(max_age_days=90)
        if stale:
            click.echo(f"\n{'='*70}")
            click.echo(f"Stale Knowledge (>90 days old, needs refresh):")
            click.echo(f"{'='*70}\n")
            for stale_topic in stale[:10]:
                click.echo(f"  - {stale_topic}")

        click.echo()

    except Exception as e:
        click.echo(f"Error loading temporal knowledge: {e}")


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
