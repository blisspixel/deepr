"""Exercise an installed Deepr MCP command through the Agent Plugin profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

EXPECTED_READ_ONLY_TOOLS = {
    "deepr_capabilities",
    "deepr_check_status",
    "deepr_get_expert_info",
    "deepr_get_result",
    "deepr_get_task_progress",
    "deepr_list_experts",
    "deepr_list_recoverable_tasks",
    "deepr_list_skills",
    "deepr_status",
    "deepr_tool_search",
}


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _requests() -> str:
    messages: list[dict[str, Any]] = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "agent-plugin-install-check", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {"_fullList": True}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "deepr_status", "arguments": {}}},
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "deepr_research",
                "arguments": {
                    "prompt": "must remain blocked",
                    "budget": 1,
                    "allow_metered_api": True,
                    "confirm_metered_cost": True,
                    "_approved": True,
                },
            },
        },
    ]
    return "".join(f"{json.dumps(message)}\n" for message in messages)


def _plugin_environment(package_root: Path, data_root: Path) -> dict[str, str]:
    manifest = json.loads((package_root / "mcp.json").read_text(encoding="utf-8"))
    declared = manifest["mcpServers"]["deepr"]["env"]
    environment = {
        name: os.environ[name]
        for name in (
            "COMSPEC",
            "ComSpec",
            "PATH",
            "PATHEXT",
            "SYSTEMROOT",
            "SystemRoot",
            "TEMP",
            "TMP",
            "TMPDIR",
            "WINDIR",
        )
        if name in os.environ
    }
    isolated_home = data_root / "host-home"
    environment.update(
        {
            "HOME": str(isolated_home),
            "USERPROFILE": str(isolated_home),
            "XDG_CACHE_HOME": str(isolated_home / "cache"),
            "XDG_CONFIG_HOME": str(isolated_home / "config"),
            "XDG_DATA_HOME": str(isolated_home / "share"),
        }
    )
    forbidden = data_root.parent / "forbidden-inherited-root"
    for name in (
        "DEEPR_DATA_DIR",
        "DEEPR_EXPERTS_PATH",
        "DEEPR_REPORTS_PATH",
        "DEEPR_COST_DATA_DIR",
        "DEEPR_CAPACITY_DATA_DIR",
        "DEEPR_BUDGET_FILE",
    ):
        environment[name] = str(forbidden / name.lower())
    environment.update(
        {
            name: value.replace("${PLUGIN_ROOT}", str(package_root)).replace("${PLUGIN_DATA}", str(data_root))
            for name, value in declared.items()
        }
    )
    return environment


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--command", type=Path, required=True)
    args = parser.parse_args()

    package_root = args.package_root.resolve(strict=True)
    data_root = args.data_root.resolve(strict=False)
    data_root.mkdir(parents=True, exist_ok=False)
    package_before = _tree_digest(package_root)
    completed = subprocess.run(
        [str(args.command.resolve(strict=True))],
        input=_requests(),
        capture_output=True,
        text=True,
        cwd=data_root,
        env=_plugin_environment(package_root, data_root),
        timeout=45,
        check=False,
    )

    if completed.returncode != 0:
        raise RuntimeError(f"deepr-mcp exited {completed.returncode}: {completed.stderr}")
    responses = [json.loads(line) for line in completed.stdout.splitlines() if line]
    if [response.get("id") for response in responses] != [1, 2, 3, 4, 5]:
        raise RuntimeError("stdout was not a clean five-response JSON-RPC stream")
    initial = {tool["name"] for tool in responses[1]["result"]["tools"]}
    if initial != EXPECTED_READ_ONLY_TOOLS:
        raise RuntimeError("ordinary Agent Plugin discovery did not return the exact read-only surface")
    advertised = {tool["name"] for tool in responses[2]["result"]["tools"]}
    if advertised != EXPECTED_READ_ONLY_TOOLS or advertised != initial:
        raise RuntimeError("full discovery disagreed with the exact read-only surface")
    status = json.loads(responses[3]["result"]["content"][0]["text"])
    if status["security"]["research_mode"] != "read_only":
        raise RuntimeError("installed bridge did not enter read-only mode")
    blocked = json.loads(responses[4]["result"]["content"][0]["text"])
    if blocked.get("error_code") != "TOOL_BLOCKED":
        raise RuntimeError("caller approval bypassed the read-only tool gate")
    if _tree_digest(package_root) != package_before:
        raise RuntimeError("installed MCP startup mutated the Agent Plugin package")
    forbidden = data_root.parent / "forbidden-inherited-root"
    if forbidden.exists():
        raise RuntimeError("hostile inherited storage roots were not overridden")
    created = sorted(path.relative_to(data_root).as_posix() for path in data_root.rglob("*") if path.is_file())
    if not created:
        raise RuntimeError("expected contained runtime audit state was not created")
    print(
        json.dumps(
            {
                "status": "passed",
                "initial_tools": sorted(initial),
                "full_tools": sorted(advertised),
                "created_files": created,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
