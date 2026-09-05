"""Exercise an installed Deepr MCP command through the Agent Plugin profile."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import tempfile
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
PERSISTENCE_EXPERT_NAME = "Plugin Persistence Fixture"


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _requests(*, modern: bool = False) -> list[dict[str, Any]]:
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
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
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
        {"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": {"name": "deepr_list_experts", "arguments": {}}},
    ]
    if modern:
        messages[0] = {"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {}}
        messages.pop(1)
        for message in messages:
            message["params"]["_meta"] = {
                "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                "io.modelcontextprotocol/clientCapabilities": {},
                "io.modelcontextprotocol/clientInfo": {"name": "agent-plugin-install-check", "version": "1"},
            }
        for request_id, version, capabilities in ((6, "1900-01-01", True), (7, "2026-07-28", False)):
            metadata: dict[str, Any] = {"io.modelcontextprotocol/protocolVersion": version}
            if capabilities:
                metadata["io.modelcontextprotocol/clientCapabilities"] = {}
            messages.append({"jsonrpc": "2.0", "id": request_id, "method": "tools/list", "params": {"_meta": metadata}})
    return messages


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
    environment.update({"PLUGIN_ROOT": str(package_root), "PLUGIN_DATA": str(data_root)})
    return environment


def _plugin_launch(
    package_root: Path, data_root: Path, installed_command: Path
) -> tuple[list[str], Path, dict[str, str]]:
    """Resolve Deepr's declared command through a host-visible executable search."""
    server = json.loads((package_root / "mcp.json").read_text(encoding="utf-8"))["mcpServers"]["deepr"]
    installed_command = installed_command.resolve(strict=True)
    search_path = str(installed_command.parent) + os.pathsep + os.environ.get("PATH", "")
    resolved = shutil.which(server["command"], path=search_path)
    if resolved is None or Path(resolved).resolve(strict=True) != installed_command:
        raise RuntimeError("manifest command did not resolve to the installed wheel's executable")

    def expand(value: str) -> str:
        return value.replace("${PLUGIN_ROOT}", str(package_root)).replace("${PLUGIN_DATA}", str(data_root))

    environment = _plugin_environment(package_root, data_root)
    environment["PATH"] = search_path
    command = [resolved, *(expand(value) for value in server.get("args", []))]
    return command, Path(expand(server.get("cwd", "${PLUGIN_ROOT}"))).resolve(strict=True), environment


async def _exchange(
    launch: tuple[list[str], Path, dict[str, str]], messages: list[dict[str, Any]]
) -> dict[int, dict[str, Any]]:
    command, cwd, environment = launch
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        env=environment,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async def communicate() -> dict[int, dict[str, Any]]:
        assert process.stdin is not None and process.stdout is not None
        responses: dict[int, dict[str, Any]] = {}
        for message in messages:
            process.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
            await process.stdin.drain()
            if "id" in message:
                # Await initialize before sending initialized or any legacy work.
                response = json.loads(await process.stdout.readline())
                if response.get("id") != message["id"]:
                    raise RuntimeError("stdout was not a clean response stream for the outstanding request")
                responses[message["id"]] = response
        process.stdin.close()
        stdout, stderr = await process.communicate()
        if process.returncode != 0 or stdout.strip():
            raise RuntimeError(f"unclean MCP exit {process.returncode}: {stderr.decode(errors='replace')}")
        return responses

    try:
        return await asyncio.wait_for(communicate(), timeout=45)
    finally:
        if process.returncode is None:
            process.kill()
            await process.communicate()


def _check_responses(responses: dict[int, dict[str, Any]], *, modern: bool, version: str) -> set[str]:
    if modern:
        discovery = responses[1]["result"]
        if "2026-07-28" not in discovery["supportedVersions"] or "tools" not in discovery["capabilities"]:
            raise RuntimeError("modern discovery did not advertise the supported protocol and tools")
        for response_id in (1, 2, 3, 4, 5, 8):
            result = responses[response_id]["result"]
            info = result["_meta"]["io.modelcontextprotocol/serverInfo"]
            if result["resultType"] != "complete" or info != {"name": "deepr-research", "version": version}:
                raise RuntimeError("modern result omitted its completion or installed server identity")
        for response_id in (1, 2, 3):
            result = responses[response_id]["result"]
            if result["cacheScope"] != "public" or not isinstance(result["ttlMs"], int) or result["ttlMs"] <= 0:
                raise RuntimeError("modern discovery omitted its cache metadata")
        if responses[6]["error"]["code"] != -32022 or responses[7]["error"]["code"] != -32602:
            raise RuntimeError("modern negotiation inherited or accepted invalid per-request metadata")
    elif responses[1]["result"]["protocolVersion"] != "2025-06-18":
        raise RuntimeError("legacy initialization did not negotiate the requested supported version")
    initial = {tool["name"] for tool in responses[2]["result"]["tools"]}
    if initial != EXPECTED_READ_ONLY_TOOLS:
        raise RuntimeError("ordinary Agent Plugin discovery did not return the exact read-only surface")
    advertised = {tool["name"] for tool in responses[3]["result"]["tools"]}
    if advertised != EXPECTED_READ_ONLY_TOOLS or advertised != initial:
        raise RuntimeError("full discovery disagreed with the exact read-only surface")
    status = json.loads(responses[4]["result"]["content"][0]["text"])
    if status["security"]["research_mode"] != "read_only":
        raise RuntimeError("installed bridge did not enter read-only mode")
    blocked = json.loads(responses[5]["result"]["content"][0]["text"])
    if not responses[5]["result"].get("isError") or blocked.get("error_code") != "TOOL_BLOCKED":
        raise RuntimeError("caller approval bypassed the read-only tool gate")
    experts = json.loads(responses[8]["result"]["content"][0]["text"])
    if [expert["name"] for expert in experts] != [PERSISTENCE_EXPERT_NAME]:
        raise RuntimeError("the explicitly provisioned expert was lost or an ambient expert root was exposed")
    return initial


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--command", type=Path, required=True, help="Installed executable to put on the host's PATH")
    args = parser.parse_args()

    package_root = args.package_root.resolve(strict=True)
    data_root = args.data_root.resolve(strict=False)
    data_root.mkdir(parents=True, exist_ok=False)
    package_before = _tree_digest(package_root)
    version = json.loads((package_root / "plugin.json").read_text(encoding="utf-8"))["version"]
    from deepr.experts.profile import ExpertProfile, ExpertStore

    expert_root = data_root / "deepr" / "experts"
    ExpertStore(base_path=str(expert_root)).save(
        ExpertProfile(
            name=PERSISTENCE_EXPERT_NAME,
            vector_store_id="",
            description="Offline installation fixture; no research or model calls.",
        )
    )
    expert_before = _tree_digest(expert_root)
    responses = asyncio.run(_exchange(_plugin_launch(package_root, data_root, args.command), _requests()))
    initial = _check_responses(responses, modern=False, version=version)
    with tempfile.TemporaryDirectory(prefix="deepr plugin update ", dir=data_root.parent) as directory:
        updated_root = Path(directory) / "deepr-research"
        shutil.copytree(package_root, updated_root)
        responses = asyncio.run(
            _exchange(_plugin_launch(updated_root, data_root, args.command), _requests(modern=True))
        )
        _check_responses(responses, modern=True, version=version)
        if _tree_digest(updated_root) != package_before:
            raise RuntimeError("updated package changed during installed MCP startup")
    if _tree_digest(expert_root) != expert_before:
        raise RuntimeError("persisted expert data changed across read-only launches and package replacement")
    if _tree_digest(package_root) != package_before:
        raise RuntimeError("installed MCP startup mutated the Agent Plugin package")
    forbidden = data_root.parent / "forbidden-inherited-root"
    if forbidden.exists():
        raise RuntimeError("hostile inherited storage roots were not overridden")
    created = sorted(path.relative_to(data_root).as_posix() for path in data_root.rglob("*") if path.is_file())
    if not any(path.startswith("deepr/") for path in created):
        raise RuntimeError("expected contained runtime audit state was not created")
    print(
        json.dumps(
            {
                "status": "passed",
                "initial_tools": sorted(initial),
                "full_tools": sorted(initial),
                "protocols": ["2025-06-18", "2026-07-28"],
                "data_preserved_across_package_replacement": True,
                "created_files": created,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
