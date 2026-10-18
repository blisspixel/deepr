"""Human-readable rendering for the read-only capacity inventory."""

from __future__ import annotations

from collections.abc import Iterable

from rich.table import Table
from rich.text import Text

from deepr.backends.capacity import BackendKind, CapacitySource
from deepr.backends.local_capacity import LocalCapacityObservation
from deepr.backends.plan_quota.adapters import get_adapter_by_executable
from deepr.backends.quota_ledger import QuotaState
from deepr.cli.colors import console, print_next, status_text

GROUP_ORDER = (
    (BackendKind.LOCAL, "Local runtime (detection only)"),
    (BackendKind.PLAN_QUOTA, "Plan CLIs (installation only)"),
    (BackendKind.API_METERED, "Metered API credentials (configuration only)"),
)


def print_sources(sources: Iterable[CapacitySource]) -> None:
    """Render source evidence without converting presence into eligibility."""
    inventory = list(sources)
    console.print("Capacity sources detected (execution eligibility is workflow-specific)\n")
    narrow = console.width < 100
    for kind, heading in GROUP_ORDER:
        group = [source for source in inventory if source.kind == kind]
        if not group:
            continue
        console.print(Text(heading))
        table = Table(box=None, show_header=False, padding=(0, 1), pad_edge=False)
        table.add_column(width=10)
        table.add_column(max_width=20)
        table.add_column(max_width=14)
        table.add_column(max_width=16)
        table.add_column(ratio=1)
        for source in group:
            evidence = "unverified" if source.available else "skipped"
            present, absent = {
                BackendKind.LOCAL: ("detected", "not detected"),
                BackendKind.PLAN_QUOTA: ("installed", "not installed"),
                BackendKind.API_METERED: ("configured", "not configured"),
            }[kind]
            status = present if source.available else absent
            detail = source.detail
            if source.local_generation is not None:
                proof = source.local_generation
                cloud = f"disabled={proof.cloud_disabled}, source={proof.cloud_source or 'unknown'}"
                detail += f"\nLocal generation: {proof.status} ({cloud}). {proof.detail}"
            if narrow:
                summary = Text("  ")
                summary.append_text(status_text(evidence))
                summary.append(f" {source.name}: {status}; {source.marginal_cost}")
                console.print(summary)
                console.print(Text("    " + detail))
            else:
                table.add_row(
                    status_text(evidence), Text(source.name), Text(status), Text(source.marginal_cost), Text(detail)
                )
        if not narrow:
            console.print(table)
        console.print()
    _print_guidance(inventory)


def _print_guidance(inventory: list[CapacitySource]) -> None:
    """Give complete safe commands from inventory presence, without granting eligibility."""
    console.print("Inventory only: detection, installation, or credential presence does not prove execution.")
    available_kinds = {source.kind for source in inventory if source.available}
    hints = []
    if BackendKind.LOCAL in available_kinds:
        hints.append("deepr capacity next --task-class sync")
    plan_sources = [source for source in inventory if source.available and source.kind == BackendKind.PLAN_QUOTA]
    if any(get_adapter_by_executable(source.backend_id) for source in plan_sources):
        hints.append("deepr capacity fleet")
    unadapted = [source.name for source in plan_sources if not get_adapter_by_executable(source.backend_id)]
    if unadapted:
        console.print(Text(f"Inventory only, no registered adapter: {', '.join(unadapted)}."))
    if BackendKind.API_METERED in available_kinds:
        hints.append('deepr research "your question" --auto --preview')
    if not available_kinds:
        console.print("No source is currently present.")
    for index, command in enumerate(hints or ["deepr init"]):
        print_next(command, also=index > 0)


def _print_local_probe(result: dict[str, object]) -> None:
    """Print a human-readable local probe verdict."""
    if result["ok"]:
        console.print(
            f"Local probe: ok - {result['model']} replied {result['reply']!r} in {result['latency_ms']}ms (cost $0)\n",
            markup=False,
        )
    else:
        console.print(f"Local probe: failed - {result['error']}\n", markup=False)


def _print_local_capacity(observation: LocalCapacityObservation) -> None:
    console.print("")
    console.print(f"Local GPU capacity: {observation.state.value} - {observation.detail}", markup=False)


def _print_quota_summary(quota_states: list[QuotaState]) -> None:
    """Show latest observed quota state from the local append-only ledger."""
    console.print("")
    if not quota_states:
        console.print("No plan quota observations recorded yet.")
        return

    console.print("Observed quota state (local ledger):")
    for state in quota_states:
        event = state.latest_event
        mark = "warning" if state.exhausted or state.quarantined else "unverified"
        status = "quarantined" if state.quarantined else "exhausted" if state.exhausted else event.event_type.value
        remaining = _format_remaining(event.units_remaining, event.unit_name)
        confidence = event.remaining_confidence.value
        reset = f", resets {event.reset_at.isoformat()}" if event.reset_at else ""
        detail = f" - {event.detail}" if event.detail else ""
        console.print(
            "  ",
            status_text(mark),
            f" {state.key}: {status}; {remaining} ({confidence}){reset}{detail}",
            sep="",
            markup=False,
        )


def _format_remaining(units_remaining: float | None, unit_name: str) -> str:
    if units_remaining is None:
        return "remaining unknown"
    return f"{units_remaining:g} {unit_name} remaining"


def _print_admissions_summary() -> None:
    """List models/CLIs admitted for the automatic owned-capacity-first path."""
    from deepr.backends.admission import list_active
    from deepr.backends.waterfall import PLAN_ADMISSION_PREFIX

    admitted = list_active()
    local = [a for a in admitted if not a.model.startswith(PLAN_ADMISSION_PREFIX)]
    plan = [a for a in admitted if a.model.startswith(PLAN_ADMISSION_PREFIX)]

    console.print("")
    if local:
        console.print("Local models admitted for automatic owned-capacity-first maintenance:")
        for a in local:
            exp = a.expires_at.strftime("%Y-%m-%d") if a.expires_at else "never"
            console.print(
                "  ", status_text("ok"), f" {a.model} for {a.task_class} (expires {exp})", sep="", markup=False
            )
    else:
        console.print("No local models admitted yet. Review quality before automatic local maintenance.")
        print_next("deepr capacity admit --help", also=True)

    if plan:
        console.print("")
        console.print("Plan-quota CLIs with recorded routing intent (quota observation still required):")
        for a in plan:
            exp = a.expires_at.strftime("%Y-%m-%d") if a.expires_at else "never"
            console.print(
                f"  [+] {a.model.removeprefix(PLAN_ADMISSION_PREFIX)} for {a.task_class} (expires {exp})", markup=False
            )
