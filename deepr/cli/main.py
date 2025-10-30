"""
Deepr CLI - Modern command-line interface for research automation.

Command Structure: deepr <verb> <noun> [options]

Examples:
    deepr research submit "Your research prompt"
    deepr research status <job-id>
    deepr queue list
    deepr prep plan "Meeting scenario"
    deepr cost estimate "Research prompt"

Interactive Mode:
    deepr interactive
"""

import click
import asyncio
from typing import Optional
from deepr.branding import print_banner, print_section_header, CHECK, CROSS


@click.group()
@click.version_option(version="2.3.0", prog_name="Deepr")
def cli():
    """
    Deepr - Research automation platform.

    Knowledge is Power. Automate It.
    """
    pass


# Import command groups
from deepr.cli.commands import run, status, budget, cost, interactive, docs, vector, config, analytics, templates, migrate, jobs

# Core commands - new structure
cli.add_command(run.run)
cli.add_command(jobs.jobs)

# Deprecated commands (kept for backward compatibility with warnings)
cli.add_command(status.status)
cli.add_command(status.get)
cli.add_command(status.list_jobs, name="list")
cli.add_command(status.cancel)

# Quick aliases
cli.add_command(run.run_alias)
cli.add_command(status.status_alias)
cli.add_command(status.list_alias)

# Supporting commands
cli.add_command(budget.budget)
cli.add_command(cost.cost)
cli.add_command(interactive.interactive)
cli.add_command(docs.docs)
cli.add_command(vector.vector)
cli.add_command(config.config)
cli.add_command(analytics.analytics)
cli.add_command(templates.templates)
cli.add_command(migrate.migrate)


def main():
    """Entry point for CLI."""
    print_banner("main")
    cli()


if __name__ == "__main__":
    main()
