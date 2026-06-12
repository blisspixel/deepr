"""Unit tests for MCP client config loader.

Tests transport type validation, missing required fields, env var resolution,
and disabled profile parsing.

Requirements: 1.1, 1.3, 1.4, 1.5
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from deepr.mcp.client.config_loader import ConfigLoader, _resolve_env_vars


@pytest.fixture(autouse=True)
def _no_first_party_autodiscovery():
    """Make load() deterministic across environments.

    ConfigLoader.load() auto-discovers first-party tools (recon, distillr) by
    probing PATH. Without this, count-based assertions break on dev machines
    where those binaries happen to be installed. Tests that exercise discovery
    on purpose re-patch shutil.which inside their own ``with`` block.
    """
    with patch("deepr.mcp.client.config_loader.shutil.which", return_value=None):
        yield


class TestConfigLoaderValidation:
    """Tests for ConfigLoader.validate()."""

    def test_valid_stdio_transport_accepted(self) -> None:
        """stdio transport type is accepted without errors."""
        raw = {"profiles": [{"name": "test", "command": "echo", "transport": "stdio"}]}
        loader = ConfigLoader()
        errors = loader.validate(raw)
        assert errors == []

    def test_valid_sse_transport_accepted(self) -> None:
        """sse transport type is accepted without errors."""
        raw = {"profiles": [{"name": "test", "command": "echo", "transport": "sse"}]}
        loader = ConfigLoader()
        errors = loader.validate(raw)
        assert errors == []

    def test_invalid_transport_rejected(self) -> None:
        """Invalid transport types produce a clear error."""
        raw = {"profiles": [{"name": "test", "command": "echo", "transport": "http"}]}
        loader = ConfigLoader()
        errors = loader.validate(raw)
        assert len(errors) == 1
        assert "transport" in errors[0]
        assert "http" in errors[0]

    def test_missing_name_produces_error(self) -> None:
        """Missing name field produces a descriptive error."""
        raw = {"profiles": [{"command": "echo"}]}
        loader = ConfigLoader()
        errors = loader.validate(raw)
        assert any("name" in e for e in errors)

    def test_empty_name_produces_error(self) -> None:
        """Empty name field produces a descriptive error."""
        raw = {"profiles": [{"name": "", "command": "echo"}]}
        loader = ConfigLoader()
        errors = loader.validate(raw)
        assert any("name" in e for e in errors)

    def test_missing_command_produces_error(self) -> None:
        """Missing command field produces a descriptive error."""
        raw = {"profiles": [{"name": "test"}]}
        loader = ConfigLoader()
        errors = loader.validate(raw)
        assert any("command" in e for e in errors)

    def test_missing_profiles_key_produces_error(self) -> None:
        """Missing 'profiles' key produces a descriptive error."""
        raw = {"servers": []}
        loader = ConfigLoader()
        errors = loader.validate(raw)
        assert any("profiles" in e for e in errors)

    def test_negative_timeout_produces_error(self) -> None:
        """Negative timeout produces a descriptive error."""
        raw = {"profiles": [{"name": "test", "command": "echo", "timeout": -5}]}
        loader = ConfigLoader()
        errors = loader.validate(raw)
        assert any("timeout" in e for e in errors)

    def test_negative_budget_produces_error(self) -> None:
        """Negative budget_limit produces a descriptive error."""
        raw = {"profiles": [{"name": "test", "command": "echo", "budget_limit": -1}]}
        loader = ConfigLoader()
        errors = loader.validate(raw)
        assert any("budget_limit" in e for e in errors)

    def test_default_transport_is_stdio(self) -> None:
        """When transport is not specified, validation passes (defaults to stdio)."""
        raw = {"profiles": [{"name": "test", "command": "echo"}]}
        loader = ConfigLoader()
        errors = loader.validate(raw)
        assert errors == []


class TestEnvVarResolution:
    """Tests for environment variable resolution."""

    def test_existing_var_resolved(self) -> None:
        """Existing environment variables are resolved."""
        with patch.dict(os.environ, {"MY_KEY": "secret123"}):
            result = _resolve_env_vars("${MY_KEY}")
        assert result == "secret123"

    def test_missing_var_raises(self) -> None:
        """Missing environment variables raise ``ValueError`` (round-3 fix).

        The previous silent-empty behaviour produced confusing downstream
        errors — a server spawned with ``API_KEY=""`` returned 401
        instead of a clear "var not set" message.
        """
        env_copy = {k: v for k, v in os.environ.items() if k != "NONEXISTENT_VAR_XYZ"}
        with patch.dict(os.environ, env_copy, clear=True):
            with pytest.raises(ValueError, match="NONEXISTENT_VAR_XYZ"):
                _resolve_env_vars("${NONEXISTENT_VAR_XYZ}")

    def test_multiple_vars_resolved(self) -> None:
        """Multiple variables in one string are all resolved."""
        with patch.dict(os.environ, {"HOST": "localhost", "PORT": "8080"}):
            result = _resolve_env_vars("${HOST}:${PORT}")
        assert result == "localhost:8080"

    def test_no_vars_unchanged(self) -> None:
        """Strings without ${} patterns are returned unchanged."""
        result = _resolve_env_vars("plain text")
        assert result == "plain text"


class TestConfigLoaderLoad:
    """Tests for ConfigLoader.load()."""

    def test_nonexistent_file_returns_empty(self, tmp_path: Path) -> None:
        """Non-existent config file returns empty list.

        Patches the first-party recon auto-discovery so the test does not
        depend on whether the `recon` binary happens to be installed on
        the dev/CI machine.
        """
        with patch("deepr.mcp.client.config_loader.discover_recon_profile", return_value=None):
            loader = ConfigLoader()
            result = loader.load(tmp_path / "missing.yaml")
        assert result == []

    def test_valid_config_loads_profiles(self, tmp_path: Path) -> None:
        """Valid YAML config loads into MCPClientProfile objects."""
        config = textwrap.dedent("""\
            profiles:
              - name: recon
                command: recon
                args: [mcp]
                transport: stdio
                enabled: true
                timeout: 30
                budget_limit: 0
                auto_approve: [domain_lookup]
                require_approval: [delta]
                progress: false
        """)
        config_file = tmp_path / "integrations.yaml"
        config_file.write_text(config)

        loader = ConfigLoader()
        profiles = loader.load(config_file)

        assert len(profiles) == 1
        p = profiles[0]
        assert p.name == "recon"
        assert p.command == "recon"
        assert p.args == ["mcp"]
        assert p.transport == "stdio"
        assert p.enabled is True
        assert p.timeout == 30.0
        assert p.budget_limit == 0.0
        assert p.auto_approve == ["domain_lookup"]
        assert p.require_approval == ["delta"]
        assert p.progress is False

    def test_disabled_profile_parsed_correctly(self, tmp_path: Path) -> None:
        """Disabled profiles are parsed with enabled=False.

        Patches the first-party recon auto-discovery so the test does not
        depend on whether the `recon` binary is installed.
        """
        config = textwrap.dedent("""\
            profiles:
              - name: disabled-server
                command: some-cmd
                enabled: false
        """)
        config_file = tmp_path / "integrations.yaml"
        config_file.write_text(config)

        with patch("deepr.mcp.client.config_loader.discover_recon_profile", return_value=None):
            loader = ConfigLoader()
            profiles = loader.load(config_file)

        assert len(profiles) == 1
        assert profiles[0].enabled is False

    def test_env_vars_resolved_in_env_dict(self, tmp_path: Path) -> None:
        """Environment variables in env dict are resolved during load."""
        config = textwrap.dedent("""\
            profiles:
              - name: test
                command: test-cmd
                env:
                  API_KEY: ${TEST_API_KEY_XYZ}
        """)
        config_file = tmp_path / "integrations.yaml"
        config_file.write_text(config)

        with patch.dict(os.environ, {"TEST_API_KEY_XYZ": "my-secret"}):
            loader = ConfigLoader()
            profiles = loader.load(config_file)

        assert profiles[0].env == {"API_KEY": "my-secret"}

    def test_invalid_config_raises_value_error(self, tmp_path: Path) -> None:
        """Invalid config raises ValueError with descriptive message."""
        config = textwrap.dedent("""\
            profiles:
              - name: ""
                command: ""
        """)
        config_file = tmp_path / "integrations.yaml"
        config_file.write_text(config)

        loader = ConfigLoader()
        with pytest.raises(ValueError, match="Config validation failed"):
            loader.load(config_file)


class TestDistillrFirstParty:
    """First-party distillr profile + auto-discovery (Phase 2b #2)."""

    def test_distillr_profile_template_fields(self) -> None:
        from deepr.mcp.client.config_loader import get_distillr_profile

        profile = get_distillr_profile()
        assert profile.name == "distillr"
        assert profile.command == "distill-mcp"
        assert profile.budget_limit == 2.0  # spends money: per-call cap exists
        assert profile.progress is True
        assert "find_insights" in profile.auto_approve  # free read-side corpus search
        assert "papers" in profile.require_approval

    def test_discover_returns_profile_when_binary_present(self) -> None:
        from deepr.mcp.client.config_loader import discover_distillr_profile

        with patch("deepr.mcp.client.config_loader.shutil.which", return_value="/usr/bin/distill-mcp"):
            profile = discover_distillr_profile()
        assert profile is not None
        assert profile.name == "distillr"

    def test_discover_returns_none_when_binary_absent(self) -> None:
        from deepr.mcp.client.config_loader import discover_distillr_profile

        with patch("deepr.mcp.client.config_loader.shutil.which", return_value=None):
            assert discover_distillr_profile() is None

    def test_load_auto_includes_distillr_when_present(self, tmp_path: Path) -> None:
        def fake_which(name: str) -> str | None:
            return "/usr/bin/distill-mcp" if name == "distill-mcp" else None

        with patch("deepr.mcp.client.config_loader.shutil.which", side_effect=fake_which):
            profiles = ConfigLoader().load(tmp_path / "absent.yaml")
        names = {p.name for p in profiles}
        assert "distillr" in names
        assert "recon" not in names

    def test_user_distillr_profile_not_duplicated(self, tmp_path: Path) -> None:
        config = textwrap.dedent("""\
            profiles:
              - name: distillr
                command: distill-mcp
                budget_limit: 9.0
        """)
        config_file = tmp_path / "integrations.yaml"
        config_file.write_text(config)

        with patch("deepr.mcp.client.config_loader.shutil.which", return_value="/usr/bin/distill-mcp"):
            profiles = ConfigLoader().load(config_file)

        distillr = [p for p in profiles if p.name == "distillr"]
        assert len(distillr) == 1
        assert distillr[0].budget_limit == 9.0  # user wins over auto-discovery


class TestPrimrFirstParty:
    """First-party primr profile + auto-discovery (Phase 2b #3)."""

    def test_primr_profile_template_fields(self) -> None:
        from deepr.mcp.client.config_loader import get_primr_profile

        profile = get_primr_profile()
        assert profile.name == "primr"
        assert profile.command == "primr-mcp"
        assert profile.args == ["--stdio"]
        assert profile.budget_limit == 5.0  # heaviest tool: higher per-call cap
        assert profile.timeout == 3600  # 35-50 min runs
        assert profile.progress is True
        # Only free read-side tools auto-approve; everything that spends needs approval.
        assert {"estimate_run", "check_jobs", "doctor"} <= set(profile.auto_approve)
        assert "research_company" in profile.require_approval
        assert "delegate_to_agent" in profile.require_approval  # paid handoff, never auto

    def test_discover_returns_profile_when_binary_present(self) -> None:
        from deepr.mcp.client.config_loader import discover_primr_profile

        with patch("deepr.mcp.client.config_loader.shutil.which", return_value="/usr/bin/primr-mcp"):
            profile = discover_primr_profile()
        assert profile is not None
        assert profile.name == "primr"

    def test_discover_returns_none_when_binary_absent(self) -> None:
        from deepr.mcp.client.config_loader import discover_primr_profile

        with patch("deepr.mcp.client.config_loader.shutil.which", return_value=None):
            assert discover_primr_profile() is None

    def test_load_auto_includes_primr_when_present(self, tmp_path: Path) -> None:
        def fake_which(name: str) -> str | None:
            return "/usr/bin/primr-mcp" if name == "primr-mcp" else None

        with patch("deepr.mcp.client.config_loader.shutil.which", side_effect=fake_which):
            profiles = ConfigLoader().load(tmp_path / "absent.yaml")
        names = {p.name for p in profiles}
        assert "primr" in names
        assert "recon" not in names and "distillr" not in names
