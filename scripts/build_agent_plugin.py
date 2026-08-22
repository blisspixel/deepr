"""Validate and build the deterministic Deepr Agent Plugin archive."""

from __future__ import annotations

import argparse
from pathlib import Path

from deepr.skills.agent_plugin import build_agent_plugin


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("packages/deepr-agent-plugin"))
    parser.add_argument("--output", type=Path, default=Path("dist/deepr-agent-plugin-2.50.3.tar.gz"))
    args = parser.parse_args()
    digest = build_agent_plugin(args.source, args.output)
    print(f"{digest}  {args.output.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
