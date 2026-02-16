"""Skill tool execution — runs Python and MCP tools with budget tracking."""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
from typing import Any

from deepr.experts.skills.definition import SkillDefinition, SkillTool

logger = logging.getLogger(__name__)

# Estimated costs by tier (used when actual cost is unknown)
_COST_TIER_ESTIMATES = {
    "free": 0.0,
    "low": 0.01,
    "medium": 0.05,
    "high": 0.20,
}


class MCPClientProxy:
    """Spawns an MCP server subprocess and sends tool calls via JSON-RPC stdio."""

    def __init__(self, command: str, args: list[str], env: dict[str, str]):
        self._command = command
        self._args = args
        self._env = {**os.environ, **self._resolve_env(env)}
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0

    @staticmethod
    def _resolve_env(env: dict[str, str]) -> dict[str, str]:
        """Resolve ${VAR} references in env values from os.environ."""
        resolved = {}
        for key, value in env.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                env_var = value[2:-1]
                resolved[key] = os.environ.get(env_var, "")
            else:
                resolved[key] = str(value)
        return resolved

    async def _ensure_started(self) -> asyncio.subprocess.Process:
        if self._process is None or self._process.returncode is not None:
            self._process = await asyncio.create_subprocess_exec(
                self._command,
                *self._args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._env,
            )
            # Send initialize handshake
            await self._send_jsonrpc(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "deepr-skill", "version": "1.0.0"},
                },
            )
        return self._process

    async def _send_jsonrpc(self, method: str, params: dict) -> dict:
        """Send a JSON-RPC request and read the response."""
        proc = await self._ensure_started() if self._process is None else self._process
        if proc is None or proc.stdin is None or proc.stdout is None:
            return {"error": "MCP process not available"}

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        line = json.dumps(request) + "\n"
        proc.stdin.write(line.encode())
        await proc.stdin.drain()

        # Read response line
        response_line = await proc.stdout.readline()
        if not response_line:
            return {"error": "MCP server closed connection"}

        try:
            return json.loads(response_line)
        except json.JSONDecodeError:
            return {"error": f"Invalid JSON from MCP server: {response_line[:200]}"}

    async def call_tool(self, tool_name: str, arguments: dict, timeout: int = 30) -> dict:
        """Call a tool on the MCP server.

        Args:
            tool_name: Name of the tool on the remote server
            arguments: Tool arguments
            timeout: Timeout in seconds

        Returns:
            dict with 'result' or 'error' key
        """
        try:
            await self._ensure_started()
            response = await asyncio.wait_for(
                self._send_jsonrpc(
                    "tools/call",
                    {
                        "name": tool_name,
                        "arguments": arguments,
                    },
                ),
                timeout=timeout,
            )

            if "error" in response:
                return {"error": response["error"]}

            result = response.get("result", {})
            # MCP tools return content array
            content = result.get("content", [])
            if content and isinstance(content, list):
                text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
                return {"result": "\n".join(text_parts)}
            return {"result": result}

        except asyncio.TimeoutError:
            return {"error": f"MCP tool '{tool_name}' timed out after {timeout}s"}
        except Exception as e:
            return {"error": f"MCP error: {e}"}

    async def close(self):
        """Terminate the MCP server subprocess."""
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()
            self._process = None


class SkillExecutor:
    """Executes skill tools with budget tracking."""

    def __init__(self, skill: SkillDefinition, budget_remaining: float):
        self._skill = skill
        self._budget_remaining = budget_remaining
        self._mcp_proxies: dict[str, MCPClientProxy] = {}
        self._tool_map: dict[str, SkillTool] = {t.name: t for t in skill.tools}

    async def execute_tool(self, tool_name: str, arguments: dict) -> dict[str, Any]:
        """Route to Python or MCP execution. Check budget first.

        Returns:
            dict with 'result' and 'cost', or 'error' and 'cost'
        """
        tool = self._tool_map.get(tool_name)
        if not tool:
            return {"error": f"Unknown tool: {tool_name}", "cost": 0.0}

        # Budget check
        estimated_cost = _COST_TIER_ESTIMATES.get(tool.cost_tier, 0.0)
        if estimated_cost > 0 and estimated_cost > self._budget_remaining:
            return {
                "error": "BUDGET_EXCEEDED",
                "detail": f"Tool costs ~${estimated_cost:.2f} but only ${self._budget_remaining:.2f} remains",
                "cost": 0.0,
            }

        if tool.type == "python":
            result = await self._execute_python(tool, arguments)
        elif tool.type == "mcp":
            result = await self._execute_mcp(tool, arguments)
        else:
            result = {"error": f"Unknown tool type: {tool.type}", "cost": 0.0}

        # Deduct cost from remaining budget
        cost = result.get("cost", 0.0)
        self._budget_remaining -= cost
        return result

    async def _execute_python(self, tool: SkillTool, arguments: dict) -> dict[str, Any]:
        """Import module and call function. Supports sync and async."""
        if not tool.module or not tool.function:
            return {"error": "Python tool missing module/function", "cost": 0.0}

        try:
            # Resolve module relative to skill path
            import sys

            skill_dir = str(self._skill.path)
            if skill_dir not in sys.path:
                sys.path.insert(0, skill_dir)

            mod = importlib.import_module(tool.module)
            func = getattr(mod, tool.function)

            if asyncio.iscoroutinefunction(func):
                result = await func(**arguments)
            else:
                result = func(**arguments)

            return {"result": result, "cost": 0.0}  # Python tools are free

        except Exception as e:
            logger.warning("Python tool %s.%s failed: %s", tool.module, tool.function, e)
            return {"error": str(e), "cost": 0.0}

    async def _execute_mcp(self, tool: SkillTool, arguments: dict) -> dict[str, Any]:
        """Spawn/reuse MCP server, proxy the call, handle timeout."""
        if not tool.server_command:
            return {"error": "MCP tool missing server command", "cost": 0.0}

        proxy_key = f"{tool.server_command}:{' '.join(tool.server_args)}"

        if proxy_key not in self._mcp_proxies:
            self._mcp_proxies[proxy_key] = MCPClientProxy(
                command=tool.server_command,
                args=tool.server_args,
                env=tool.server_env,
            )

        proxy = self._mcp_proxies[proxy_key]
        remote_name = tool.remote_tool_name or tool.name

        result = await proxy.call_tool(remote_name, arguments, timeout=tool.timeout_seconds)

        cost = _COST_TIER_ESTIMATES.get(tool.cost_tier, 0.0)
        result["cost"] = cost
        return result

    async def cleanup(self):
        """Terminate all MCP subprocesses."""
        for proxy in self._mcp_proxies.values():
            await proxy.close()
        self._mcp_proxies.clear()
