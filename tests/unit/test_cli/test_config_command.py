"""Tests for CLI config commands."""

from pathlib import Path

from click.testing import CliRunner

from deepr.cli.main import cli


def test_config_set_cli_branding_alias_writes_env_key():
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path(".env").write_text("OPENAI_API_KEY=test-key\n", encoding="utf-8")

        result = runner.invoke(cli, ["config", "set", "cli.branding", "on"])

        assert result.exit_code == 0
        content = Path(".env").read_text(encoding="utf-8")
        assert "DEEPR_BRANDING=on" in content


def test_config_set_cli_animations_validates_and_normalizes_value():
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path(".env").write_text("", encoding="utf-8")

        result = runner.invoke(cli, ["config", "set", "cli.animations", "FULL"])

        assert result.exit_code == 0
        content = Path(".env").read_text(encoding="utf-8")
        assert "DEEPR_ANIMATIONS=full" in content


def test_config_set_rejects_unknown_cli_namespace_key():
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path(".env").write_text("", encoding="utf-8")

        result = runner.invoke(cli, ["config", "set", "cli.unknown", "on"])

        assert result.exit_code != 0
        assert "Unknown CLI config key" in result.output


def test_config_set_rejects_invalid_cli_animations_value():
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path(".env").write_text("", encoding="utf-8")

        result = runner.invoke(cli, ["config", "set", "cli.animations", "fast"])

        assert result.exit_code != 0
        assert "Invalid value 'fast'" in result.output
        assert "Allowed values: full, light, off" in result.output


def test_config_set_updates_existing_key_without_duplicate():
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path(".env").write_text("DEEPR_ANIMATIONS=off\n", encoding="utf-8")

        result = runner.invoke(cli, ["config", "set", "cli.animations", "light"])

        assert result.exit_code == 0
        content = Path(".env").read_text(encoding="utf-8")
        assert "DEEPR_ANIMATIONS=light" in content
        assert content.count("DEEPR_ANIMATIONS=") == 1
