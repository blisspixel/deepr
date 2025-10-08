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
@click.version_option(version="2.0.0", prog_name="Deepr")
def cli():
    """
    Deepr - Research automation platform.

    Knowledge is Power. Automate It.
    """
    pass


# Import command groups
from deepr.cli.commands import research, queue, prep, cost, interactive, docs

cli.add_command(research.research)
cli.add_command(queue.queue)
cli.add_command(prep.prep)
cli.add_command(cost.cost)
cli.add_command(interactive.interactive)
cli.add_command(docs.docs)


def main():
    """Entry point for CLI."""
    print_banner("main")
    cli()


if __name__ == "__main__":
    main()
