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

    def test_missing_var_resolves_empty(self) -> None:
        """Missing environment variables resolve to empty string."""
        env_copy = {k: v for k, v in os.environ.items() if k != "NONEXISTENT_VAR_XYZ"}
        with patch.dict(os.environ, env_copy, clear=True):
            result = _resolve_env_vars("${NONEXISTENT_VAR_XYZ}")
        assert result == ""

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
        """Non-existent config file returns empty list."""
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
        """Disabled profiles are parsed with enabled=False."""
        config = textwrap.dedent("""\
            profiles:
              - name: disabled-server
                command: some-cmd
                enabled: false
        """)
        config_file = tmp_path / "integrations.yaml"
        config_file.write_text(config)

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
