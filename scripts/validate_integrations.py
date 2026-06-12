"""Live drift check: first-party MCP profiles vs the shipped tool surfaces.

Connects to each first-party instrument (recon, distillr, primr) through
Deepr's own MCP client - the same code path expert skills use - lists the
tools the installed server actually ships, and compares them against the
profile's declared approval lists.

Why this exists (2026-06-11): all three integrations had silently drifted.
primr removed batch_analyze/quick_lookup, recon renamed
get_posteriors/explain_dag to get_signals/explain_signal, and distillr
renamed its entire verb surface (query_library -> find_insights,
ingest_* -> papers/learn_topic/site_batch, refresh -> catch_up). Green
mock-based tests cannot catch this class of break - only a live handshake
can. Run after upgrading any sibling tool, or on a schedule.

Usage:
    uv run python scripts/validate_integrations.py            # all installed
    uv run python scripts/validate_integrations.py primr      # one instrument

Exit codes: 0 = no drift, 1 = drift found, 2 = nothing installed.
Cost: $0 (handshake + tools/list only; no tool calls).
"""

from __future__ import annotations

import asyncio
import shutil
import sys

from deepr.mcp.client.base import MCPClient
from deepr.mcp.client.config_loader import (
    DISTILLR_PROFILE_TEMPLATE,
    PRIMR_PROFILE_TEMPLATE,
    RECON_PROFILE_TEMPLATE,
)

TEMPLATES = {
    "recon": RECON_PROFILE_TEMPLATE,
    "distillr": DISTILLR_PROFILE_TEMPLATE,
    "primr": PRIMR_PROFILE_TEMPLATE,
}


async def check_instrument(name: str, template: dict) -> dict | None:
    """Handshake with one instrument; return a drift report or None if absent."""
    command = template["command"]
    if not shutil.which(command):
        print(f"  {name}: SKIP ({command} not on PATH)")
        return None

    client = MCPClient(
        name=name,
        command=command,
        args=list(template.get("args", [])),
        timeout=float(template.get("timeout", 60)),
    )
    try:
        await client.connect()
        live = {t.get("name", "") for t in client.available_tools} - {""}
    finally:
        await client.close()

    declared = set(template.get("auto_approve", [])) | set(template.get("require_approval", []))
    missing = sorted(declared - live)  # profile references tools the server no longer ships
    unlisted = sorted(live - declared)  # server ships tools the profile does not classify

    status = "DRIFT" if missing else ("ok" if not unlisted else "ok (unclassified extras)")
    print(f"  {name}: {status} - {len(live)} live tools, {len(declared)} declared")
    if missing:
        print(f"    BROKEN references (declared but not shipped): {', '.join(missing)}")
    if unlisted:
        print(f"    unclassified (shipped but not in profile - default approval applies): {', '.join(unlisted)}")
    return {"name": name, "missing": missing, "unlisted": unlisted}


async def main() -> int:
    targets = sys.argv[1:] or list(TEMPLATES)
    print("First-party integration drift check (live tools/list handshake, $0):")

    reports = []
    for name in targets:
        if name not in TEMPLATES:
            print(f"  {name}: unknown instrument (expected one of {', '.join(TEMPLATES)})")
            return 2
        report = await check_instrument(name, TEMPLATES[name])
        if report:
            reports.append(report)

    if not reports:
        print("Nothing installed to validate.")
        return 2
    if any(r["missing"] for r in reports):
        print("\nDrift found: update the profile templates in deepr/mcp/client/config_loader.py")
        return 1
    print("\nAll declared tool references exist on the installed servers.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
