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

import sys

import click

from deepr import __version__


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version=__version__, prog_name="Deepr")
def cli():
    """
    Deepr - Research automation platform.

    Knowledge is Power. Automate It.
    """
    pass


# Import command groups (after cli group to avoid circular imports)
from deepr.cli.commands import (
    analytics,
    budget,
    config,
    cost,
    costs,
    diagnostics,
    docs,
    doctor,
    interactive,
    jobs,
    mcp,
    migrate,
    providers,
    run,
    search,
    semantic,
    status,
    templates,
    vector,
    web,
)
from deepr.cli.commands import (
    eval as eval_cmd,
)
from deepr.cli.commands import help as help_cmd

# Core commands - new structure
cli.add_command(run.run)
cli.add_command(jobs.jobs)

# Semantic commands - intent-based interface
cli.add_command(semantic.research)
cli.add_command(semantic.learn)
cli.add_command(semantic.team)
cli.add_command(semantic.check)
cli.add_command(semantic.make)
cli.add_command(semantic.agentic)
cli.add_command(semantic.expert)

# Skill management
from deepr.cli.commands.semantic.skills import skill

cli.add_command(skill)

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
cli.add_command(vector.vector, name="knowledge")  # Intuitive alias for vector
cli.add_command(config.config)
cli.add_command(analytics.analytics)
cli.add_command(templates.templates)
cli.add_command(migrate.migrate)
cli.add_command(doctor.doctor)
cli.add_command(diagnostics.diagnostics_cli)
cli.add_command(mcp.mcp)
cli.add_command(help_cmd.help)
cli.add_command(costs.costs)
cli.add_command(providers.providers)
cli.add_command(search.search)
cli.add_command(web.web)
cli.add_command(eval_cmd.evaluate)


def main():
    """Entry point for CLI.

    When invoked with no arguments, launches interactive mode.
    """
    # If no arguments provided (just 'deepr'), launch interactive mode.
    # Route through Click with an explicit subcommand to avoid NoArgsIsHelpError
    # from the root group parser.
    if len(sys.argv) == 1:
        cli.main(args=["interactive"], prog_name="deepr", standalone_mode=False)
    else:
        cli()


if __name__ == "__main__":
    main()
