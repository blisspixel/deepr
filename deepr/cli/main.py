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

# The panel-review finding behind this split: 40+ top-level commands buried
# the three verbs most users need. Help shows these first, in this order;
# everything else lands under "Advanced commands". Behavior is unchanged -
# every command works exactly as before, this only shapes --help output.
_CORE_COMMAND_ORDER = ["research", "expert", "costs", "doctor", "web"]
_CORE_COMMANDS = set(_CORE_COMMAND_ORDER)


class SectionedGroup(click.Group):
    """Click group whose help lists core commands first, the rest as Advanced."""

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        visible: list[tuple[str, click.Command]] = []
        for name in self.list_commands(ctx):
            cmd = self.get_command(ctx, name)
            if cmd is None or cmd.hidden:
                continue
            visible.append((name, cmd))
        if not visible:
            return

        limit = formatter.width - 6 - max(len(name) for name, _ in visible)

        core: dict[str, str] = {}
        advanced: list[tuple[str, str]] = []
        for name, cmd in visible:
            short = cmd.get_short_help_str(limit)
            if name in _CORE_COMMANDS:
                core[name] = short
            else:
                advanced.append((name, short))

        if core:
            with formatter.section("Core commands"):
                formatter.write_dl([(name, core[name]) for name in _CORE_COMMAND_ORDER if name in core])
        if advanced:
            with formatter.section("Advanced commands"):
                formatter.write_dl(sorted(advanced))


@click.group(cls=SectionedGroup, context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version=__version__, prog_name="Deepr")
def cli():
    """
    Deepr - Research automation platform.

    \b
    Most workflows need three commands:
      deepr research "your question" --budget 2    Run research (budget is a ceiling, not a price)
      deepr expert chat "Expert Name"              Consult a persistent domain expert
      deepr costs show                             See exactly what you have spent

    \b
    deepr doctor verifies your setup. Everything else lives under
    Advanced commands below - you will not need most of it on day one.
    """
    pass


# Import command groups (after cli group to avoid circular imports)
from deepr.cli.commands import (
    analytics,
    budget,
    completion,
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
    upgrade,
    vector,
    web,
)
from deepr.cli.commands import (
    capacity as capacity_cmd,
)
from deepr.cli.commands import (
    eval as eval_cmd,
)
from deepr.cli.commands import help as help_cmd
from deepr.cli.commands import (
    init as init_cmd,
)

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

# Deprecated commands (kept for backward compatibility with warnings).
# Hidden from --help so the listing stays navigable; they still execute.
for _legacy in (status.status, status.get, status.list_jobs, status.cancel):
    _legacy.hidden = True
cli.add_command(status.status)
cli.add_command(status.get)
cli.add_command(status.list_jobs, name="list")
cli.add_command(status.cancel)

# Quick single-letter aliases - functional but hidden from --help
for _alias in (run.run_alias, status.status_alias, status.list_alias):
    _alias.hidden = True
cli.add_command(run.run_alias)
cli.add_command(status.status_alias)
cli.add_command(status.list_alias)

# Supporting commands
cli.add_command(budget.budget)
cli.add_command(capacity_cmd.capacity)
cli.add_command(cost.cost)
cli.add_command(interactive.interactive)
cli.add_command(docs.docs)
cli.add_command(vector.vector)
cli.add_command(vector.vector, name="knowledge")  # Intuitive alias for vector
cli.add_command(config.config)
cli.add_command(analytics.analytics)
cli.add_command(templates.templates)
cli.add_command(migrate.migrate)
cli.add_command(completion.completion)
cli.add_command(upgrade.upgrade)
cli.add_command(doctor.doctor)
cli.add_command(init_cmd.init)
cli.add_command(diagnostics.diagnostics_cli)
cli.add_command(mcp.mcp)
cli.add_command(help_cmd.help)
cli.add_command(costs.costs)
cli.add_command(providers.providers)
cli.add_command(search.search)
cli.add_command(web.web)
cli.add_command(eval_cmd.evaluate)


def _ensure_utf8_console() -> None:
    """Reconfigure stdout/stderr to UTF-8 on Windows.

    Windows consoles default to cp1252; any CLI output containing arrows,
    box-drawing, or other non-Latin-1 characters (help text, rich tables,
    cost timelines) crashes with UnicodeEncodeError (live finding
    2026-06-11: `deepr research -h` crashed on a cp1252 console).
    errors="replace" keeps output flowing even on truly limited codepages.
    """
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            reconfigure = getattr(stream, "reconfigure", None)
            if reconfigure is not None:
                try:
                    reconfigure(encoding="utf-8", errors="replace")
                except (ValueError, OSError):
                    pass  # non-reconfigurable stream (e.g. closed/redirected)


def main():
    """Entry point for CLI.

    When invoked with no arguments on an interactive terminal, launches
    interactive mode. With no arguments and a non-interactive stdin (a
    script, CI, or an AI agent driving the CLI), prints help and exits 0
    instead - clig.dev: only start interactive elements when stdin is a
    TTY, never block or surprise a non-interactive caller.
    """
    _ensure_utf8_console()
    # Route the no-args case through Click with an explicit subcommand to
    # avoid NoArgsIsHelpError from the root group parser.
    if len(sys.argv) == 1:
        stdin = sys.stdin
        is_tty = bool(stdin) and hasattr(stdin, "isatty") and stdin.isatty()
        if is_tty:
            cli.main(args=["interactive"], prog_name="deepr", standalone_mode=False)
        else:
            cli.main(args=["--help"], prog_name="deepr", standalone_mode=False)
    else:
        cli()


if __name__ == "__main__":
    main()
