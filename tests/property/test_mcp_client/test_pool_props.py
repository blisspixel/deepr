"""Property-based tests for MCP client pool extensions.

Feature: mcp-client-agent-interop
- Property 2: Disabled profiles are excluded from connection
- Property 14: Broadcast results preserve order and include all outcomes
- Property 15: Concurrency limit enforcement
- Property 30: Tool discovery aggregation
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from hypothesis import given, settings
from hypothesis import strategies as st

from deepr.mcp.client.base import MCPToolResult
from deepr.mcp.client.pool import MCPClientPool
from deepr.mcp.client.profile import MCPClientProfile

# --- Strategies ---

profile_names = st.from_regex(r"[a-z][a-z0-9\-]{1,12}", fullmatch=True)
tool_names = st.from_regex(r"[a-z_]{2,12}", fullmatch=True)


def make_profile(name: str, enabled: bool = True) -> MCPClientProfile:
    """Create a test profile."""
    return MCPClientProfile(name=name, command="echo", args=["test"], enabled=enabled)


# --- Property 2: Disabled profiles are excluded from connection ---


@settings(max_examples=100)
@given(
    enabled_names=st.lists(profile_names, min_size=0, max_size=5, unique=True),
    disabled_names=st.lists(profile_names, min_size=0, max_size=5, unique=True),
)
def test_property_2_disabled_profiles_excluded(
    enabled_names: list[str],
    disabled_names: list[str],
) -> None:
    """For any mix of enabled and disabled profiles, register() SHALL only
    add enabled profiles to the pool. Disabled profiles are never present.

    **Validates: Requirements 1.2**
    """
    # Ensure no overlap between enabled and disabled names
    disabled_names = [n for n in disabled_names if n not in enabled_names]

    pool = MCPClientPool()

    for name in enabled_names:
        pool.register(make_profile(name, enabled=True))

    for name in disabled_names:
        pool.register(make_profile(name, enabled=False))

    # Only enabled profiles should be in the pool
    for name in enabled_names:
        assert name in pool, f"Enabled profile '{name}' should be in pool"

    for name in disabled_names:
        assert name not in pool, f"Disabled profile '{name}' should NOT be in pool"

    assert len(pool) == len(enabled_names)


# --- Property 14: Broadcast results preserve order and include all outcomes ---


@settings(max_examples=100)
@given(
    server_names=st.lists(profile_names, min_size=1, max_size=6, unique=True),
    fail_indices=st.lists(st.integers(min_value=0, max_value=5), max_size=3, unique=True),
)
def test_property_14_broadcast_preserves_order(
    server_names: list[str],
    fail_indices: list[int],
) -> None:
    """For any set of servers and any subset that fail, broadcast_tool() SHALL
    return results in the same order as the input server list, with failed
    servers producing error results in their slot.

    **Validates: Requirements 7.2, 7.3, 7.4**
    """
    pool = MCPClientPool()
    fail_set = {server_names[i] for i in fail_indices if i < len(server_names)}

    for name in server_names:
        pool.register(make_profile(name))
        client = pool._clients[name]
        client._connected = True
        if name in fail_set:
            client.call_tool = AsyncMock(
                return_value=MCPToolResult(error=f"fail-{name}", server_name=name, tool_name="search")
            )
        else:
            client.call_tool = AsyncMock(
                return_value=MCPToolResult(content=f"ok-{name}", server_name=name, tool_name="search")
            )

    results = asyncio.get_event_loop().run_until_complete(
        pool.broadcast_tool("search", {"q": "test"}, server_names=server_names)
    )

    # Results length matches input
    assert len(results) == len(server_names)

    # Order is preserved
    for i, name in enumerate(server_names):
        r = results[i]
        assert r.server_name == name
        if name in fail_set:
            assert not r.ok
        else:
            assert r.ok
            assert r.content == f"ok-{name}"


# --- Property 15: Concurrency limit enforcement ---


@settings(max_examples=100)
@given(
    num_servers=st.integers(min_value=1, max_value=8),
    max_concurrent=st.integers(min_value=1, max_value=4),
)
def test_property_15_concurrency_limit(
    num_servers: int,
    max_concurrent: int,
) -> None:
    """The pool SHALL never exceed max_concurrent parallel dispatches.

    **Validates: Requirements 7.2**
    """
    pool = MCPClientPool(max_concurrent=max_concurrent)
    names = [f"server-{i}" for i in range(num_servers)]
    peak_concurrent = 0
    current_concurrent = 0
    lock = asyncio.Lock()

    async def _tracked_call(tool_name, arguments, timeout, trace_id):
        nonlocal peak_concurrent, current_concurrent
        async with lock:
            current_concurrent += 1
            if current_concurrent > peak_concurrent:
                peak_concurrent = current_concurrent
        await asyncio.sleep(0.01)
        async with lock:
            current_concurrent -= 1
        return MCPToolResult(content="ok", server_name="x", tool_name=tool_name)

    for name in names:
        pool.register(make_profile(name))
        pool._clients[name]._connected = True
        pool._clients[name].call_tool = _tracked_call

    asyncio.get_event_loop().run_until_complete(pool.broadcast_tool("search", {}, server_names=names))

    assert peak_concurrent <= max_concurrent


# --- Property 30: Tool discovery aggregation ---


@settings(max_examples=100)
@given(
    server_tools=st.dictionaries(
        keys=profile_names,
        values=st.lists(tool_names, min_size=0, max_size=4),
        min_size=1,
        max_size=4,
    ),
)
def test_property_30_tool_discovery_aggregation(
    server_tools: dict[str, list[str]],
) -> None:
    """list_all_tools() SHALL return the union of all tools across connected
    servers, each tagged with its server name.

    **Validates: Requirements 14.3**
    """
    from unittest.mock import MagicMock

    pool = MCPClientPool()

    expected_total = 0
    for server_name, tools in server_tools.items():
        pool.register(make_profile(server_name))
        client = pool._clients[server_name]
        client._connected = True
        # Mock the process so client.connected returns True
        mock_proc = MagicMock()
        mock_proc.returncode = None
        client._process = mock_proc
        client._available_tools = [{"name": t, "description": f"desc-{t}", "inputSchema": {}} for t in tools]
        expected_total += len(tools)

    all_tools = pool.list_all_tools()

    assert len(all_tools) == expected_total

    # Each tool is tagged with its server
    for tool_entry in all_tools:
        assert tool_entry["server"] in server_tools
        assert tool_entry["name"] in server_tools[tool_entry["server"]]
