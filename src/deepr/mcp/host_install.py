"""Local coding-host MCP wiring (Claude Code, Cursor-style stdio hosts).

Pure helpers: no network, no model, no spend. Writes config files and optional
host CLI registration only when the operator asks.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

HOST_INSTALL_SCHEMA = "deepr-mcp-host-install-v1"
HOST_BRIEF_SCHEMA = "deepr-mcp-host-brief-v1"
DEFAULT_SERVER_NAME = "deepr"
DEFAULT_SYNTHESIS_BACKEND = "local"
DEFAULT_BUDGET = 0
DEFAULT_MAX_ELAPSED_SECONDS = 600


@dataclass(frozen=True)
class HostMcpServerSpec:
    """stdio MCP server block for Claude Code / Cursor-style hosts."""

    name: str
    command: str
    args: list[str]
    env: dict[str, str]

    def as_mcp_json_block(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "args": list(self.args),
            "env": dict(self.env),
        }

    def as_claude_mcp_add_argv(self) -> list[str]:
        """``claude mcp add`` argv for local scope stdio registration."""
        argv = ["mcp", "add", self.name, "-s", "local"]
        for key, value in self.env.items():
            argv.extend(["-e", f"{key}={value}"])
        argv.append("--")
        argv.append(self.command)
        argv.extend(self.args)
        return argv


@dataclass
class HostInstallPlan:
    """What install-host would write / run."""

    schema_version: str = HOST_INSTALL_SCHEMA
    kind: str = "deepr.mcp.host_install"
    server_name: str = DEFAULT_SERVER_NAME
    data_dir: str = ""
    deepr_command: str = ""
    project_dir: str = ""
    mcp_json_path: str = ""
    mcp_json: dict[str, Any] = field(default_factory=dict)
    claude_cli: str | None = None
    claude_add_argv: list[str] = field(default_factory=list)
    restart_required: bool = True
    notes: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    network_opened: bool = False
    model_called: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_deepr_command(*, explicit: str | None = None) -> str:
    """Prefer an absolute path so host child processes do not depend on PATH."""
    if explicit:
        return str(Path(explicit).expanduser().resolve())
    which = shutil.which("deepr")
    if which:
        return str(Path(which).resolve())
    # Editable / same interpreter fallback
    return sys.executable


def resolve_data_dir(*, explicit: str | None = None) -> str:
    if explicit:
        return str(Path(explicit).expanduser().resolve())
    env = os.environ.get("DEEPR_DATA_DIR")
    if env:
        return str(Path(env).expanduser().resolve())
    # Match portable expert home (same root as experts_root parent).
    try:
        from deepr.config import default_data_dir, experts_root

        root = experts_root().parent
        if root.exists() or os.environ.get("DEEPR_DATA_DIR"):
            return str(root.resolve())
        return str(default_data_dir().resolve())
    except Exception:
        return str((Path.home() / ".deepr").resolve())


def build_server_spec(
    *,
    name: str = DEFAULT_SERVER_NAME,
    deepr_command: str | None = None,
    data_dir: str | None = None,
    use_python_module: bool | None = None,
) -> HostMcpServerSpec:
    command = resolve_deepr_command(explicit=deepr_command)
    resolved_data = resolve_data_dir(explicit=data_dir)
    # If command is a Python interpreter, run module entrypoint.
    if use_python_module is None:
        use_python_module = Path(command).name.lower().startswith("python")
    if use_python_module:
        args = ["-m", "deepr.mcp.server"]
        cmd = command
    else:
        args = ["mcp", "serve"]
        cmd = command
    env = {
        "DEEPR_DATA_DIR": resolved_data,
        "DEEPR_LOG_LEVEL": "INFO",
    }
    return HostMcpServerSpec(name=name, command=cmd, args=args, env=env)


def build_mcp_json_document(spec: HostMcpServerSpec) -> dict[str, Any]:
    return {"mcpServers": {spec.name: spec.as_mcp_json_block()}}


def plan_host_install(
    *,
    project_dir: str | Path,
    server_name: str = DEFAULT_SERVER_NAME,
    deepr_command: str | None = None,
    data_dir: str | None = None,
    use_python_module: bool | None = None,
) -> HostInstallPlan:
    project = Path(project_dir).expanduser().resolve()
    spec = build_server_spec(
        name=server_name,
        deepr_command=deepr_command,
        data_dir=data_dir,
        use_python_module=use_python_module,
    )
    mcp_path = project / ".mcp.json"
    claude = shutil.which("claude")
    notes = [
        "MCP hosts load tools at session start. Restart Claude Code / the host after install.",
        "Approve project .mcp.json / trust dialog if the host prompts.",
        "Read-only tools are $0. Consults: synthesis_backend=local budget=0.",
        "Set host tool timeout >= 600s for local 32b consults.",
        'CLI fallback: deepr expert consult "..." --local --budget 0 -y',
    ]
    if not claude:
        notes.append("claude CLI not on PATH; wrote .mcp.json only. Run: claude mcp add ... after install.")
    return HostInstallPlan(
        data_dir=spec.env["DEEPR_DATA_DIR"],
        deepr_command=spec.command,
        project_dir=str(project),
        mcp_json_path=str(mcp_path),
        mcp_json=build_mcp_json_document(spec),
        claude_cli=claude,
        claude_add_argv=spec.as_claude_mcp_add_argv(),
        notes=notes,
        server_name=spec.name,
    )


def write_mcp_json(plan: HostInstallPlan, *, merge: bool = True) -> Path:
    path = Path(plan.mcp_json_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = dict(plan.mcp_json)
    if merge and path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
        if isinstance(existing, dict):
            servers = existing.get("mcpServers")
            if not isinstance(servers, dict):
                servers = {}
            incoming = document.get("mcpServers") or {}
            if isinstance(incoming, dict):
                servers = {**servers, **incoming}
            existing["mcpServers"] = servers
            document = existing
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path


def run_claude_mcp_add(plan: HostInstallPlan, *, timeout_seconds: float = 60.0) -> dict[str, Any]:
    """Register via Claude Code CLI when available. No-op structure if missing."""
    if not plan.claude_cli:
        return {
            "attempted": False,
            "ok": False,
            "error": "claude_cli_not_found",
            "cost_usd": 0.0,
        }
    argv = [plan.claude_cli, *plan.claude_add_argv]
    try:
        completed = subprocess.run(  # noqa: S603 - fixed claude path + planned argv only
            argv,
            cwd=plan.project_dir,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "attempted": True,
            "ok": False,
            "error": type(exc).__name__,
            "detail": str(exc)[:200],
            "argv": argv,
            "cost_usd": 0.0,
        }
    return {
        "attempted": True,
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": (completed.stdout or "")[:2000],
        "stderr": (completed.stderr or "")[:2000],
        "argv": argv,
        "cost_usd": 0.0,
    }


def build_host_brief(
    *,
    experts: list[str] | None = None,
    synthesis_backend: str = DEFAULT_SYNTHESIS_BACKEND,
    budget: float = DEFAULT_BUDGET,
    max_elapsed_seconds: float = DEFAULT_MAX_ELAPSED_SECONDS,
    data_dir: str | None = None,
    server_name: str = DEFAULT_SERVER_NAME,
) -> str:
    """Copy-paste instructions for a coding agent with Deepr MCP stdio access."""
    resolved_data = resolve_data_dir(explicit=data_dir)
    expert_lines = (
        "\n".join(f"- {name}" for name in experts) if experts else "- (call deepr_list_experts and pick relevant names)"
    )
    expert_arg = json.dumps(list(experts)) if experts else "null  # or omit; host may auto-select with max_experts"
    return f"""# Deepr host brief (stdio MCP, $0 local)

schema_version: {HOST_BRIEF_SCHEMA}
server_name: {server_name}
data_dir: {resolved_data}
cost_posture: local synthesis only; budget={budget}; no metered research unless operator asks

## Restart rule

MCP tools load at host session start. If tools are missing mid-session, restart
the host (Claude Code / Cursor / Desktop) after `deepr mcp install-host`.
Do not invent expert answers when tools are absent. Use CLI fallback instead.

## Operator install (once per project)

```text
deepr mcp install-host --project .
deepr mcp conformance --json
# restart host session, then verify tools exist
```

## Experts in scope

{expert_lines}

## Hard rules

1. synthesis_backend="{synthesis_backend}" (or backend="{synthesis_backend}" on query)
2. budget={budget}
3. max_elapsed_seconds={max_elapsed_seconds} for consults (local large models are slow)
4. Prefer read-only first: deepr_list_experts, deepr_get_expert_info, deepr_expert_handoff
5. Do not call metered research, absorb, learn, or mutate beliefs unless the operator asks
6. Experts advise; the host agent writes code. Agent is not the live control loop
7. Documents: 0 does NOT mean empty. Use claim_count / Claims. Absorb --file fills
   the belief store without vector-store documents. knowledge_empty=false when claims>0.
   health-check and handoff are the ground truth for inventory.

## Tool flow

1. deepr_list_experts
2. deepr_expert_handoff(expert_name=..., max_claims=8) for each relevant expert
3. deepr_consult_experts with:
   - question: <design question>
   - experts: {expert_arg}
   - max_experts: 4
   - synthesis_backend: "{synthesis_backend}"
   - budget: {budget}
   - max_elapsed_seconds: {max_elapsed_seconds}
4. Expect schema_version deepr-consult-v1, cost_usd=0, capacity.live_metered_fallback=false

## CLI fallback (when MCP tools missing)

```text
deepr expert consult "<question>" --local --budget 0 -y --json
# add -e "Expert Name" for each expert
```

If experts are missing: set DEEPR_DATA_DIR={resolved_data} and re-run deepr expert list.
"""


def probe_project_mcp_json(project_dir: str | Path, *, server_name: str = DEFAULT_SERVER_NAME) -> dict[str, Any]:
    """Read-only doctor probe for project .mcp.json deepr entry."""
    path = Path(project_dir).expanduser().resolve() / ".mcp.json"
    if not path.exists():
        return {
            "present": False,
            "path": str(path),
            "has_server": False,
            "detail": "missing .mcp.json; run: deepr mcp install-host --project .",
            "cost_usd": 0.0,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "present": True,
            "path": str(path),
            "has_server": False,
            "detail": f"unreadable .mcp.json: {type(exc).__name__}",
            "cost_usd": 0.0,
        }
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    has = isinstance(servers, dict) and server_name in servers
    return {
        "present": True,
        "path": str(path),
        "has_server": has,
        "server_names": list(servers.keys()) if isinstance(servers, dict) else [],
        "detail": "ok" if has else f".mcp.json has no server named {server_name}",
        "cost_usd": 0.0,
    }
