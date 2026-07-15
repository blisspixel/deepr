"""Property-based tests for MCP client config loader.

Feature: mcp-client-agent-interop
- Property 1: Config parsing round-trip preserves all fields
- Property 3: Environment variable resolution
- Property 4: Invalid config produces field-specific errors
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from deepr.mcp.client.config_loader import ConfigLoader, _resolve_env_vars
from deepr.mcp.client.profile import MCPClientProfile

# Strategy for valid profile names (non-empty alphanumeric + hyphens)
profile_names = st.from_regex(r"[a-z][a-z0-9\-]{0,20}", fullmatch=True)

# Strategy for valid commands
commands = st.from_regex(r"[a-z][a-z0-9_]{0,15}", fullmatch=True)

# Strategy for valid transport types
transports = st.sampled_from(["stdio", "sse"])

# Strategy for valid timeout values
timeouts = st.floats(min_value=1.0, max_value=3600.0, allow_nan=False, allow_infinity=False)

# Strategy for valid budget limits
budget_limits = st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)

# Strategy for tool name lists
tool_names = st.lists(st.from_regex(r"[a-z_]{1,15}", fullmatch=True), max_size=5)


# Feature: mcp-client-agent-interop, Property 1: Config parsing round-trip preserves all fields


@settings(max_examples=100)
@given(
    name=profile_names,
    command=commands,
    transport=transports,
    timeout=timeouts,
    budget_limit=budget_limits,
    auto_approve=tool_names,
    require_approval=tool_names,
    progress=st.booleans(),
    enabled=st.booleans(),
)
def test_property_1_config_round_trip(
    name: str,
    command: str,
    transport: str,
    timeout: float,
    budget_limit: float,
    auto_approve: list[str],
    require_approval: list[str],
    progress: bool,
    enabled: bool,
) -> None:
    """For any valid integration profile configuration, serializing to dict and
    parsing back with from_dict SHALL produce an MCPClientProfile with all field
    values identical to the original.

    **Validates: Requirements 1.1**
    """
    original = MCPClientProfile(
        name=name,
        command=command,
        transport=transport,
        timeout=timeout,
        budget_limit=budget_limit,
        auto_approve=auto_approve,
        require_approval=require_approval,
        progress=progress,
        enabled=enabled,
    )

    # Round-trip through dict
    data = original.to_dict()
    restored = MCPClientProfile.from_dict(data)

    assert restored.name == original.name
    assert restored.command == original.command
    assert restored.transport == original.transport
    assert restored.timeout == original.timeout
    assert restored.budget_limit == original.budget_limit
    assert restored.auto_approve == original.auto_approve
    assert restored.require_approval == original.require_approval
    assert restored.progress == original.progress
    assert restored.enabled == original.enabled


# Feature: mcp-client-agent-interop, Property 3: Environment variable resolution


@settings(max_examples=100)
@given(
    var_name=st.from_regex(r"[A-Z][A-Z0-9_]{0,15}", fullmatch=True),
    var_value=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "P")),
        min_size=1,
        max_size=50,
    ),
)
def test_property_3_env_var_resolution(var_name: str, var_value: str) -> None:
    """For any string containing ${VAR_NAME} patterns where the referenced variables
    exist in the process environment, the resolver SHALL substitute each ${VAR_NAME}
    with the corresponding environment value.

    **Validates: Requirements 1.3**
    """
    input_str = f"prefix-${{{var_name}}}-suffix"

    with patch.dict(os.environ, {var_name: var_value}):
        result = _resolve_env_vars(input_str)

    # The resolved string should contain the variable value
    assert var_value in result
    # No unresolved pattern for this variable
    assert f"${{{var_name}}}" not in result
    # Prefix and suffix preserved
    assert result.startswith("prefix-")
    assert result.endswith("-suffix")


@settings(max_examples=100)
@given(
    var_name=st.from_regex(r"[A-Z][A-Z0-9_]{0,15}", fullmatch=True),
)
def test_property_3_missing_env_var_fails_closed(var_name: str) -> None:
    """An undefined environment variable is reported instead of erased silently.

    **Validates: Requirements 1.3**
    """
    input_str = f"${{{var_name}}}"

    # Ensure the variable is NOT in the environment
    env_copy = {k: v for k, v in os.environ.items() if k != var_name}
    with patch.dict(os.environ, env_copy, clear=True):
        with pytest.raises(ValueError, match="undefined environment variable") as exc_info:
            _resolve_env_vars(input_str)

    assert var_name in str(exc_info.value)


# Feature: mcp-client-agent-interop, Property 4: Invalid config produces field-specific errors


@settings(max_examples=100)
@given(
    name=st.one_of(st.just(""), st.just(None)),
    command=commands,
)
def test_property_4_missing_name_produces_error(name: str | None, command: str) -> None:
    """When a profile has a missing or empty name, validate() SHALL return an error
    referencing the 'name' field.

    **Validates: Requirements 1.4**
    """
    raw = {"profiles": [{"name": name, "command": command}]}
    if name is None:
        del raw["profiles"][0]["name"]

    loader = ConfigLoader()
    errors = loader.validate(raw)

    assert len(errors) > 0
    assert any("name" in e for e in errors)


@settings(max_examples=100)
@given(
    name=profile_names,
    command=st.one_of(st.just(""), st.just(None)),
)
def test_property_4_missing_command_produces_error(name: str, command: str | None) -> None:
    """When a profile has a missing or empty command, validate() SHALL return an error
    referencing the 'command' field.

    **Validates: Requirements 1.4**
    """
    raw = {"profiles": [{"name": name, "command": command}]}
    if command is None:
        del raw["profiles"][0]["command"]

    loader = ConfigLoader()
    errors = loader.validate(raw)

    assert len(errors) > 0
    assert any("command" in e for e in errors)


@settings(max_examples=100)
@given(
    name=profile_names,
    command=commands,
    transport=st.text(min_size=1, max_size=10).filter(lambda s: s not in ("stdio", "sse")),
)
def test_property_4_invalid_transport_produces_error(name: str, command: str, transport: str) -> None:
    """When a profile has an invalid transport type, validate() SHALL return an error
    referencing the 'transport' field.

    **Validates: Requirements 1.4**
    """
    raw = {"profiles": [{"name": name, "command": command, "transport": transport}]}

    loader = ConfigLoader()
    errors = loader.validate(raw)

    assert len(errors) > 0
    assert any("transport" in e for e in errors)
