"""Terminal presentation contracts, independent of evidence or routing decisions."""

import ast
import io
import re
from pathlib import Path

import pytest

import deepr.cli.colors as colors

ROOT = Path(__file__).resolve().parents[3]
ROLES = {"text", "accent", "success", "live", "warning", "destructive", "error", "info", "muted", "money", "quote"}
PHYSICAL = re.compile(r"\b(?:bright_\w+|black|red|green|yellow|blue|magenta|cyan|white)\b|rgb\(|#[0-9a-fA-F]{6}\b")
STYLE_LITERAL = re.compile(
    r"(?:(?:bold|dim|italic|underline|reverse|on)\s+)*(?:bright_\w+|black|red|green|yellow|blue|magenta|cyan|white)"
)


def test_theme_exposes_every_semantic_role():
    assert ROLES <= colors.custom_theme.styles.keys()


def test_muted_provenance_uses_terminal_foreground():
    style = colors.console.get_style("dim")
    assert style.dim
    assert style.color is None or style.color.name == "default"


def test_commands_have_one_palette_owner():
    violations = []
    for path in (ROOT / "src/deepr/cli").rglob("*.py"):
        if path.name == "colors.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Console":
                violations.append(f"{path.name}:{node.lineno}: independent console")
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            value = node.value
            tags = re.findall(r"\[/?([^]\n]+)\]", value)
            if (
                STYLE_LITERAL.fullmatch(value)
                or any(PHYSICAL.search(tag) for tag in tags)
                or re.fullmatch(r"#[0-9a-fA-F]{6}", value)
                or "rgb(" in value
            ):
                violations.append(f"{path.name}:{node.lineno}: physical style")
    assert not violations, violations[:20]


def test_guidance_prefixes_and_decorations_are_consistent():
    violations = []
    paths = [
        *(ROOT / "src/deepr/cli").rglob("*.py"),
        ROOT / "src/deepr/experts/thought_stream.py",
        ROOT / "src/deepr/services/batch_auto.py",
    ]
    for path in paths:
        source = path.read_text(encoding="utf-8")
        if "◆" in source or "•" in source:
            violations.append(f"{path.name}: decorative glyph")
        for node in ast.walk(ast.parse(source)):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and re.search(r"\b(?:Run|Then|Check|Inspect|Install with):\s", node.value)
            ):
                violations.append(f"{path.name}:{node.lineno}: guidance prefix")
    assert not violations, violations[:20]


@pytest.mark.parametrize("status", ["ok", "warning", "failed", "skipped", "unverified"])
def test_status_words_are_aligned_and_survive_no_color(monkeypatch, status):
    monkeypatch.setenv("NO_COLOR", "1")
    output = io.StringIO()
    console = colors.make_console(file=output, force_terminal=True, width=100)
    console.print(colors.status_text(status), "a diagnostic")
    visible = re.sub(r"\x1b\[[0-9;]*m", "", output.getvalue())
    assert visible.startswith(status.ljust(len("unverified")) + " ")
    assert not re.search(r"\x1b\[(?:[0-9;]*;)?(?:3[0-7]|9[0-7]|38;|48;)", output.getvalue())


def test_console_does_not_implicitly_color_paths_or_numbers(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    output = io.StringIO()
    console = colors.make_console(file=output, force_terminal=True, width=100)
    console.print("/tmp/example.py 123")
    assert output.getvalue() == "/tmp/example.py 123\n"
    assert console.color_system == "standard"


@pytest.mark.parametrize("force_terminal", [None, False])
def test_nonterminal_output_does_not_gain_palette_escape_sequences(monkeypatch, force_terminal):
    from rich.text import Text

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    output = io.StringIO()
    console = colors.make_console(file=output, force_terminal=force_terminal)
    console.print(Text("recorded state", style=colors.ROLE_STYLES["warning"]))
    assert output.getvalue() == "recorded state\n"


def test_doctor_projects_status_without_modifying_machine_evidence(monkeypatch):
    from deepr.cli.commands.doctor import DiagnosticCheck, diagnostic_report, print_checks

    checks = []
    for name, passed, severity, unverified in [
        ("ready", True, "error", False),
        ("unmeasured", False, "info", True),
        ("optional", False, "info", False),
        ("broken", False, "error", False),
        ("degraded", False, "warning", False),
    ]:
        check = DiagnosticCheck(name, "Fixture")
        check.passed, check.failure_severity, check.unverified = passed, severity, unverified
        check.message = "[magenta]literal input[/magenta]"
        checks.append(check)
    before = diagnostic_report(checks)
    output = io.StringIO()
    monkeypatch.setattr(colors, "console", colors.make_console(file=output, force_terminal=False, width=120))
    print_checks(checks, show_all=True)
    assert diagnostic_report(checks) == before
    for state, name in [
        ("ok", "ready"),
        ("unverified", "unmeasured"),
        ("skipped", "optional"),
        ("failed", "broken"),
        ("warning", "degraded"),
    ]:
        assert state.ljust(len("unverified")) + " " + name + ":" in output.getvalue()
    assert "[magenta]literal input[/magenta]" in output.getvalue()


def test_rich_progress_uses_the_same_explicit_roles():
    console = colors.make_console()
    assert console.get_style("bar.complete") == console.get_style("live")
    assert console.get_style("bar.finished") == console.get_style("success")
    assert console.get_style("status.spinner") == console.get_style("live")


def test_detail_and_next_hints_keep_literal_commands_on_one_line(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    output = io.StringIO()
    console = colors.make_console(file=output, force_terminal=True, width=30)
    command = 'deepr expert consult "a question" --local'
    colors.print_detail("Next: " + command, target=console)
    colors.print_detail("[red]literal provenance[/red]", target=console)
    visible = re.sub(r"\x1b\[[0-9;]*m", "", output.getvalue())
    assert visible.splitlines()[0] == "Next: " + command
    assert "[red]literal provenance[/red]" in visible
    assert "\x1b[36m" in output.getvalue()
