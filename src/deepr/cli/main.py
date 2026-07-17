"""
Deepr CLI - Modern command-line interface for research automation.

Command Structure: deepr <verb> <noun> [options]

Examples:
    deepr research submit "Your research prompt"
    deepr research status <job-id>
    deepr queue list
    deepr prep plan "Meeting scenario"
    deepr costs estimate "Research prompt"

Interactive Mode:
    deepr interactive
"""

import os
import sys
from importlib import import_module
from typing import NamedTuple

import click

from deepr import __version__
from deepr.cli.color_policy import apply_no_color

# The panel-review finding behind this split: 40+ top-level commands buried
# the three verbs most users need. Help shows these first, in this order;
# everything else lands under "Advanced commands". Behavior is unchanged -
# every command works exactly as before, this only shapes --help output.
_CORE_COMMAND_ORDER = ["research", "expert", "costs", "doctor", "web"]
_CORE_COMMANDS = set(_CORE_COMMAND_ORDER)


class _LazyCommandSpec(NamedTuple):
    """Import recipe and root-help metadata for one top-level command."""

    module: str
    attribute: str
    short_help: str
    hidden: bool = False
    load_after: tuple[str, ...] = ()


_COMMAND_SPECS: dict[str, _LazyCommandSpec] = {
    "a2a": _LazyCommandSpec(
        "deepr.cli.commands.a2a",
        "a2a",
        "Agent-to-Agent interoperability tools.",
    ),
    "agentic": _LazyCommandSpec(
        "deepr.cli.commands.semantic",
        "agentic",
        "Autonomous multi-step research workflows.",
    ),
    "analytics": _LazyCommandSpec(
        "deepr.cli.commands.analytics",
        "analytics",
        "View usage analytics and success metrics.",
    ),
    "budget": _LazyCommandSpec(
        "deepr.cli.commands.budget",
        "budget",
        "Manage monthly research budget.",
    ),
    "cancel": _LazyCommandSpec("deepr.cli.commands.status", "cancel", "Cancel a research job.", True),
    "capacity": _LazyCommandSpec(
        "deepr.cli.commands.capacity",
        "capacity",
        "Show available research capacity (local, plan quota,...",
    ),
    "check": _LazyCommandSpec(
        "deepr.cli.commands.semantic",
        "check",
        "Verify a factual claim quickly.",
    ),
    "completion": _LazyCommandSpec(
        "deepr.cli.commands.completion",
        "completion",
        "Output a tab-completion script for SHELL (bash, zsh, or...",
    ),
    "config": _LazyCommandSpec(
        "deepr.cli.commands.config",
        "config",
        "Manage and validate configuration.",
    ),
    "cost": _LazyCommandSpec(
        "deepr.cli.commands.cost",
        "cost",
        "Deprecated alias for costs.",
        True,
    ),
    "costs": _LazyCommandSpec(
        "deepr.cli.commands.costs",
        "costs",
        "Cost tracking and budget management.",
    ),
    "diagnostics": _LazyCommandSpec(
        "deepr.cli.commands.diagnostics",
        "diagnostics_cli",
        "Diagnostics and self-awareness tools for experts.",
    ),
    "docs": _LazyCommandSpec(
        "deepr.cli.commands.docs",
        "docs",
        "Analyze documentation and queue research for gaps.",
    ),
    "doctor": _LazyCommandSpec(
        "deepr.cli.commands.doctor",
        "doctor",
        "Run diagnostics to check Deepr configuration and...",
    ),
    "eval": _LazyCommandSpec(
        "deepr.cli.commands.eval",
        "evaluate",
        "Run model evaluation workflows with cost safety defaults.",
        load_after=(
            "deepr.cli.commands.eval_conversation",
            "deepr.cli.commands.eval_deliberation",
            "deepr.cli.commands.eval_expert_value",
            "deepr.cli.commands.eval_grounding_correctness",
            "deepr.cli.commands.eval_judge_calibration",
            "deepr.cli.commands.eval_recall",
        ),
    ),
    "expert": _LazyCommandSpec(
        "deepr.cli.commands.semantic",
        "expert",
        "Create and interact with domain experts.",
    ),
    "fleet": _LazyCommandSpec(
        "deepr.cli.commands.fleet",
        "fleet",
        "Roster-wide expert fleet health (read-only, $0).",
    ),
    "get": _LazyCommandSpec("deepr.cli.commands.status", "get", "Get a research result.", True),
    "help": _LazyCommandSpec(
        "deepr.cli.commands.help",
        "help",
        "Get help on Deepr commands and concepts.",
    ),
    "init": _LazyCommandSpec(
        "deepr.cli.commands.init",
        "init",
        "Guided first-run setup: detect keys, write .env, set a...",
    ),
    "interactive": _LazyCommandSpec(
        "deepr.cli.commands.interactive",
        "interactive",
        "Start interactive mode for guided research.",
    ),
    "jobs": _LazyCommandSpec(
        "deepr.cli.commands.jobs",
        "jobs",
        "Manage research jobs (list, status, get results, cancel).",
    ),
    "knowledge": _LazyCommandSpec(
        "deepr.cli.commands.vector",
        "vector",
        "Manage knowledge bases (vector stores) for experts and...",
    ),
    "l": _LazyCommandSpec("deepr.cli.commands.status", "list_alias", "List research jobs.", True),
    "learn": _LazyCommandSpec(
        "deepr.cli.commands.semantic",
        "learn",
        "Learn about a topic through multi-phase research.",
    ),
    "list": _LazyCommandSpec("deepr.cli.commands.status", "list_jobs", "List research jobs.", True),
    "make": _LazyCommandSpec(
        "deepr.cli.commands.semantic",
        "make",
        "Create artifacts from research.",
    ),
    "mcp": _LazyCommandSpec(
        "deepr.cli.commands.mcp",
        "mcp",
        "Model Context Protocol server for AI agent integration.",
    ),
    "migrate": _LazyCommandSpec(
        "deepr.cli.commands.migrate",
        "migrate",
        "Migrate and organize legacy reports.",
    ),
    "providers": _LazyCommandSpec(
        "deepr.cli.commands.providers",
        "providers",
        "Provider management and monitoring.",
    ),
    "r": _LazyCommandSpec("deepr.cli.commands.run", "run_alias", "Run one research job.", True),
    "research": _LazyCommandSpec(
        "deepr.cli.commands.semantic",
        "research",
        "Run research with automatic mode detection.",
    ),
    "route": _LazyCommandSpec(
        "deepr.cli.commands.route",
        "route",
        "Inspect deterministic routing decisions before dispatching...",
    ),
    "run": _LazyCommandSpec(
        "deepr.cli.commands.run",
        "run",
        "Run research jobs (single, campaign, or team).",
    ),
    "s": _LazyCommandSpec("deepr.cli.commands.status", "status_alias", "Show research status.", True),
    "search": _LazyCommandSpec(
        "deepr.cli.commands.search",
        "search",
        "Search and discover related research.",
    ),
    "skill": _LazyCommandSpec(
        "deepr.cli.commands.semantic.skills",
        "skill",
        "Manage expert skills - domain-specific capability packages.",
    ),
    "status": _LazyCommandSpec("deepr.cli.commands.status", "status", "Show research status.", True),
    "team": _LazyCommandSpec(
        "deepr.cli.commands.semantic",
        "team",
        "Analyze a question from multiple perspectives (dream team).",
    ),
    "templates": _LazyCommandSpec(
        "deepr.cli.commands.templates",
        "templates",
        "Manage prompt templates.",
    ),
    "upgrade": _LazyCommandSpec(
        "deepr.cli.commands.upgrade",
        "upgrade",
        "Update deepr to the latest released version.",
    ),
    "vector": _LazyCommandSpec(
        "deepr.cli.commands.vector",
        "vector",
        "Manage knowledge bases (vector stores) for experts and...",
    ),
    "web": _LazyCommandSpec(
        "deepr.cli.commands.web",
        "web",
        "Start the Deepr web dashboard.",
    ),
}


def _apply_no_color_option(_ctx: click.Context, _param: click.Option, value: bool) -> bool:
    if value:
        apply_no_color()
    return value


class SectionedGroup(click.Group):
    """Click group with static root help and lazy top-level command imports."""

    def list_commands(self, ctx: click.Context) -> list[str]:
        """List built-in recipes plus commands registered dynamically by callers."""
        return sorted(set(_COMMAND_SPECS) | set(super().list_commands(ctx)))

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        """Import only the command selected by Click."""
        loaded = super().get_command(ctx, cmd_name)
        if loaded is not None:
            return loaded

        spec = _COMMAND_SPECS.get(cmd_name)
        if spec is None:
            return None

        module = import_module(spec.module)
        for module_name in spec.load_after:
            import_module(module_name)
        command = getattr(module, spec.attribute)
        if not isinstance(command, click.Command):
            raise TypeError(f"Lazy command target {spec.module}:{spec.attribute} is not a Click command")
        command.hidden = spec.hidden
        self.commands[cmd_name] = command
        return command

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        visible: list[tuple[str, str]] = []
        for name in self.list_commands(ctx):
            spec = _COMMAND_SPECS.get(name)
            if spec is not None:
                if not spec.hidden:
                    visible.append((name, spec.short_help))
                continue
            command = super().get_command(ctx, name)
            if command is not None and not command.hidden:
                visible.append((name, command.get_short_help_str()))
        if not visible:
            return

        core: dict[str, str] = {}
        advanced: list[tuple[str, str]] = []
        for name, short in visible:
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
@click.option(
    "--no-color",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_apply_no_color_option,
    help="Disable ANSI color output.",
)
@click.version_option(version=__version__, prog_name="Deepr")
def cli():
    """
    Deepr - Research automation platform.

    \b
    Most workflows need three commands:
      deepr research "your question" --budget 2    Run research (budget is a ceiling, not a price)
      deepr expert consult "question" -e "Expert Name" --local
                                                    Consult stored expert state at $0
      deepr costs show                             See exactly what you have spent

    \b
    deepr doctor verifies your setup. Everything else lives under
    Advanced commands below - you will not need most of it on day one.
    """
    return None


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
    if "NO_COLOR" in os.environ:
        apply_no_color()
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
