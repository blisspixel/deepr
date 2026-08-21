"""Exercise the OpenClaw reference through a clean installed Deepr wheel."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any


def _base_environment(data_root: Path) -> dict[str, str]:
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
    host_home = data_root / "host-home"
    environment.update(
        {
            "HOME": str(host_home),
            "USERPROFILE": str(host_home),
            "XDG_CACHE_HOME": str(host_home / "cache"),
            "XDG_CONFIG_HOME": str(host_home / "config"),
            "XDG_DATA_HOME": str(host_home / "share"),
            "DEEPR_HOST_DATA": str(data_root),
        }
    )
    return environment


def _profile_environment(profile: dict[str, Any], data_root: Path) -> dict[str, str]:
    environment = _base_environment(data_root)
    forbidden = data_root.parent / "forbidden-host-profile-root"
    for name in (
        "DEEPR_DATA_DIR",
        "DEEPR_EXPERTS_PATH",
        "DEEPR_REPORTS_PATH",
        "DEEPR_COST_DATA_DIR",
        "DEEPR_CAPACITY_DATA_DIR",
        "DEEPR_BUDGET_FILE",
    ):
        environment[name] = str(forbidden / name.lower())
    declared = profile["config_fragment"]["mcp"]["servers"]["deepr"]["env"]
    environment.update({name: value.replace("${DEEPR_HOST_DATA}", str(data_root)) for name, value in declared.items()})
    return environment


def _requests() -> str:
    messages: tuple[dict[str, Any], ...] = (
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "openclaw-host-profile-check", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "deepr_research",
                "arguments": {"prompt": "must remain blocked", "_approved": True},
            },
        },
    )
    return "".join(f"{json.dumps(message)}\n" for message in messages)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--mcp-command", type=Path, required=True)
    parser.add_argument("--deepr-command", type=Path, required=True)
    args = parser.parse_args()

    fixture_path = args.fixture.resolve(strict=True)
    fixture_bytes = fixture_path.read_bytes()
    profile = json.loads(fixture_bytes)
    data_root = args.data_root.resolve(strict=False)
    data_root.mkdir(parents=True, exist_ok=False)
    base_environment = _base_environment(data_root)

    generated = subprocess.run(
        [str(args.deepr_command.resolve(strict=True)), "mcp", "host-profile", "openclaw"],
        capture_output=True,
        cwd=data_root,
        env=base_environment,
        check=False,
    )
    if generated.returncode != 0:
        raise RuntimeError(f"clean-wheel host-profile generation failed: {generated.stderr.decode(errors='replace')}")
    if generated.stdout != fixture_bytes:
        raise RuntimeError("clean-wheel host-profile bytes differ from the committed fixture")
    if any(path.is_file() for path in data_root.rglob("*")):
        raise RuntimeError("offline profile generation created runtime state")

    completed = subprocess.run(
        [str(args.mcp_command.resolve(strict=True))],
        input=_requests(),
        capture_output=True,
        text=True,
        cwd=data_root,
        env=_profile_environment(profile, data_root),
        timeout=45,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"deepr-mcp exited {completed.returncode}: {completed.stderr}")
    responses = [json.loads(line) for line in completed.stdout.splitlines() if line]
    if [response.get("id") for response in responses] != [1, 2, 3]:
        raise RuntimeError("stdout was not a clean three-response JSON-RPC stream")

    advertised = {tool["name"] for tool in responses[1]["result"]["tools"]}
    expected = set(profile["capabilities"]["initial_advertised_tools"])
    if advertised != expected:
        raise RuntimeError("ordinary tools/list did not advertise the exact host-profile catalog")
    blocked = json.loads(responses[2]["result"]["content"][0]["text"])
    if blocked.get("error_code") != "TOOL_BLOCKED":
        raise RuntimeError("caller approval bypassed the read-only host-profile gate")
    forbidden = data_root.parent / "forbidden-host-profile-root"
    if forbidden.exists():
        raise RuntimeError("hostile inherited storage roots were not overridden")
    created = sorted(path.relative_to(data_root).as_posix() for path in data_root.rglob("*") if path.is_file())
    if not created:
        raise RuntimeError("expected contained runtime audit state was not created")
    print(json.dumps({"status": "passed", "advertised_tools": sorted(advertised), "created_files": created}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
