"""Tests for the sectioned CLI help (the simple default surface).

Panel-review finding: 40+ flat commands buried the three verbs that matter.
--help now lists five core commands first and everything else under
Advanced; deprecated commands and single-letter aliases are hidden from the
listing but must keep working.
"""

from click.testing import CliRunner

from deepr.cli.main import cli


def _help_output() -> str:
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    return result.output


class TestSectionedHelp:
    def test_core_section_lists_the_five_verbs_first(self):
        out = _help_output()
        core_idx = out.index("Core commands:")
        advanced_idx = out.index("Advanced commands:")
        assert core_idx < advanced_idx

        core_block = out[core_idx:advanced_idx]
        for name in ("research", "expert", "costs", "doctor", "web"):
            assert name in core_block, f"'{name}' missing from core section"

    def test_core_order_is_stable(self):
        out = _help_output()
        core_block = out[out.index("Core commands:") : out.index("Advanced commands:")]
        positions = [core_block.index(n) for n in ("research", "expert", "costs", "doctor", "web")]
        assert positions == sorted(positions)

    def test_deprecated_and_alias_commands_hidden(self):
        out = _help_output()
        advanced_block = out[out.index("Advanced commands:") :]
        for hidden_name in ("get ", "cancel ", "l ", "s ", "r "):
            assert f"\n  {hidden_name}" not in advanced_block, f"hidden command '{hidden_name.strip()}' listed in help"

    def test_hidden_commands_still_execute(self):
        runner = CliRunner()
        # Deprecated and aliased commands stay functional - only unlisted
        for name in ("list", "status", "get", "cancel"):
            result = runner.invoke(cli, [name, "--help"])
            assert result.exit_code == 0, f"hidden command '{name}' broke: {result.output}"

    def test_docstring_teaches_the_budget_ceiling(self):
        out = _help_output()
        assert "budget is a ceiling" in out
