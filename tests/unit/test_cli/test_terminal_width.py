"""Deterministic command snapshots at normal narrow and wide terminal widths."""

import importlib
from pathlib import Path

import pytest
from click.testing import CliRunner

from deepr.backends.capacity import BackendKind, CapacitySource, CostModel
from deepr.backends.local_capacity import LocalCapacityObservation, LocalCapacityState
from deepr.cli import colors
from deepr.cli.main import cli

SNAPSHOTS = Path(__file__).with_name("snapshots") / "terminal-width"


@pytest.fixture
def command_fixtures(monkeypatch):
    capacity = importlib.import_module("deepr.cli.commands.capacity")
    doctor = importlib.import_module("deepr.cli.commands.doctor")
    inventory = importlib.import_module("deepr.cli.commands.capacity_inventory")
    sources = [
        CapacitySource(
            "Ollama",
            BackendKind.LOCAL,
            CostModel.OWNED_HARDWARE,
            True,
            "A materialized local runtime was detected; execution proof remains separate.",
        ),
        CapacitySource(
            "Claude Code",
            BackendKind.PLAN_QUOTA,
            CostModel.CREDIT_POOL,
            True,
            "Installation does not prove confinement, plan authentication or overage posture.",
            "claude",
        ),
        CapacitySource("OpenRouter", BackendKind.API_METERED, CostModel.METERED, False, "[config] No stored key."),
    ]
    monkeypatch.setattr(capacity, "detect_capacity", lambda: sources)
    monkeypatch.setattr(capacity, "summarize_quota_state", lambda: [])
    monkeypatch.setattr(
        capacity,
        "probe_local_gpu_occupancy",
        lambda: LocalCapacityObservation(
            LocalCapacityState.UNKNOWN, "fixture", "GPU occupancy was not observed by this fixture."
        ),
    )
    monkeypatch.setattr("deepr.backends.admission.list_active", lambda: [])
    monkeypatch.setattr(doctor, "load_config", lambda: {})
    ready = doctor.DiagnosticCheck("State directory", "Environment")
    ready.passed, ready.message = True, "Private runtime roots are configured."
    ready.details = ["/fixture/retained/input.txt"]
    metered = doctor.DiagnosticCheck("Metered API capacity", "Capacity")
    metered.failure_severity, metered.message = "info", "No metered keys configured."
    local = doctor.DiagnosticCheck("Local Ollama", "Capacity")
    local.failure_severity, local.unverified = "info", True
    local.message = "Generation not tested in offline mode."
    monkeypatch.setattr(doctor, "check_configuration_sources", lambda: [ready])

    async def api_keys(_):
        return [metered]

    async def ollama(**_):
        return [local]

    async def empty_async(*_, **__):
        return []

    monkeypatch.setattr(doctor, "check_api_keys", api_keys)
    monkeypatch.setattr(doctor, "check_local_ollama", ollama)
    for name in ("check_filesystem", "check_database", "check_deprecated_models", "check_provider_connectivity"):
        monkeypatch.setattr(doctor, name, empty_async)
    for name in (
        "check_storage_locations",
        "check_native_instruments",
        "check_spend_integrity",
        "check_mcp_conformance",
        "check_mcp_host_wiring",
    ):
        monkeypatch.setattr(doctor, name, lambda: [])
    return doctor, inventory


@pytest.mark.parametrize("width", [60, 100])
@pytest.mark.parametrize(
    "name,args", [("help", ["--help"]), ("capacity", ["capacity"]), ("doctor", ["doctor", "--skip-connectivity"])]
)
def test_command_width_snapshots(monkeypatch, command_fixtures, width, name, args):
    console = colors.make_console(force_terminal=False, width=width)
    for module in (colors, *command_fixtures):
        monkeypatch.setattr(module, "console", console)
    result = CliRunner().invoke(cli, args, terminal_width=width, prog_name="deepr")
    assert result.exit_code == 0, result.output
    overflow = [line for line in result.stdout.splitlines() if len(line) > width]
    assert not overflow, overflow
    assert result.stdout == (SNAPSHOTS / f"{name}-{width}.txt").read_text(encoding="utf-8")


def test_consult_examples_keep_one_command_per_line():
    result = CliRunner().invoke(cli, ["expert", "consult", "--help"], terminal_width=100)
    assert result.exit_code == 0
    examples = result.stdout.split("EXAMPLES:", 1)[1]
    assert len([line for line in examples.splitlines() if line.strip().startswith("deepr expert consult")]) == 4


def test_complete_next_command_is_the_documented_width_exception():
    from io import StringIO

    output = StringIO()
    console = colors.make_console(file=output, force_terminal=False, width=60)
    command = 'deepr expert consult "a long question" -e "Long Expert Name" --local'
    colors.print_next(command, target=console)
    assert output.getvalue() == "Next: " + command + "\n"


@pytest.mark.parametrize("width", [60, 100])
@pytest.mark.parametrize("indent", [4, 8])
def test_root_help_normalizes_template_before_inserting_preview(monkeypatch, width, indent):
    import inspect

    original = inspect.cleandoc(cli.help)
    template = "\n".join(" " * indent + line if line else "" for line in original.splitlines())
    monkeypatch.setattr(cli, "help", template)
    result = CliRunner().invoke(cli, ["--help"], terminal_width=width, prog_name="deepr")
    assert result.exit_code == 0, result.output
    assert result.stdout == (SNAPSHOTS / f"help-{width}.txt").read_text(encoding="utf-8")
    assert cli.help == template
