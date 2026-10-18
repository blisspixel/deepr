"""`deepr expert validate-export` - $0 form-only export validation.

Registered on the `expert` group; experts.py imports this module at its
bottom for the registration side effect.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from deepr.cli.colors import console, print_error, print_header, print_key_value
from deepr.cli.commands.semantic.experts import expert


@expert.command(name="validate-export")
@click.argument("path", type=click.Path(path_type=Path))
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def expert_validate_export(path: Path, json_output: bool) -> None:
    """Validate an exported derived view before it ships (cost $0).

    Checks a handoff payload (.json), an OKF bundle directory, or a SKILL.md
    export for required provenance, schema version, trust metadata, and
    artifact-class markers. Every check is form-only; nothing here judges
    whether the content is true. Exits non-zero when any check fails so
    scripted export pipelines can gate on it.
    """
    from deepr.experts.export_validation import validate_export

    report = validate_export(path)

    if json_output:
        click.echo(json.dumps(report, indent=2))
    else:
        print_header(f"Export validation: {path.name}")
        print_key_value("Artifact class", report["artifact_class"])
        print_key_value("Status", report["status"])
        print_key_value("Checks", f"{report['check_count'] - report['failed_count']}/{report['check_count']} passed")
        for check in report["checks"]:
            marker = "[success]pass[/success]" if check["status"] == "pass" else "[error]fail[/error]"
            console.print(f"  {marker}  {check['check']}  [muted]{check['detail']}[/muted]")
        console.print("[muted]Form-only validation; content truth stays with calibrated review paths.[/muted]")

    if report["status"] != "valid":
        if not json_output:
            print_error("Export failed validation.")
        sys.exit(1)
