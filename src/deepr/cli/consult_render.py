"""Human consultation view of the same retained payload emitted as JSON."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.text import Text

from deepr.cli.colors import ROLE_STYLES
from deepr.cli.companion import CompanionState, companion_allowed, render_companion
from deepr.experts.consult_support import recorded_statement


def _text(console: Console, value: object) -> None:
    console.print(Text(str(value)))


def _section(console: Console, title: str) -> None:
    console.print()
    console.print(Text(title, style=ROLE_STYLES["accent"]))


def _grounds(console: Console, perspectives: list[dict[str, Any]]) -> None:
    _section(console, "Grounds")
    if not perspectives:
        _text(console, "None recorded.")
    for perspective in perspectives:
        _text(console, perspective.get("expert") or "Unnamed expert")
        context = perspective.get("context") or {}
        passages = context.get("passages") or []
        if passages:
            _text(console, f"{len(passages)} retained passages from {len({p['sha256'] for p in passages})} sources.")
            for passage in passages:
                console.print(
                    Text("\n".join("│ " + line for line in passage["text"].splitlines()), style=ROLE_STYLES["quote"])
                )
                _text(console, f"Source: {passage['origin']} ({passage['sha256']})")
        if context.get("orientation"):
            _text(console, context["orientation"])
        if not passages and not context.get("orientation"):
            console.print(Markdown(perspective.get("response") or "None recorded."))
        _text(console, "These are selected stored grounds; answer-level citation review is unassessed.")


def _support(console: Console, perspectives: list[dict[str, Any]]) -> None:
    _section(console, "Support")
    if not perspectives:
        _text(console, "None recorded.")
    for perspective in perspectives:
        context = perspective.get("context") or {}
        _text(console, perspective.get("expert") or "Unnamed expert")
        positions = context.get("positions") or []
        if not positions:
            _text(console, "Position support label: none recorded.")
        for position in positions:
            label = recorded_statement(position.get("confidence")) or "none recorded"
            _text(console, f"{position['question']}: {label} (recorded label, not a probability).")
            if position.get("confidence_basis"):
                _text(console, f"Basis: {position['confidence_basis']}")
        if "findings_anchored" in context:
            _text(
                console,
                f"Findings anchored {context['findings_anchored']} of {context.get('findings_included', 0)} (recorded matches).",
            )
        else:
            _text(console, "Anchored finding counts: none recorded.")
        _text(console, f"Citation coverage: {context.get('coverage') or 'none recorded'}; not an advice-quality score.")
        for support in context.get("support") or []:
            if not support.get("resolved"):
                _text(
                    console,
                    f"Unresolved support for {support.get('question', 'position')}: study binding {support.get('study_binding', 'unknown')}.",
                )


def _currency(console: Console, payload: dict[str, Any]) -> None:
    _section(console, "Currency")
    freshness = (payload.get("context_delivery") or {}).get("freshness")
    if freshness == "stored_context_only":
        _text(console, "Stored context only; nothing checked live for this answer.")
    else:
        _text(console, f"Freshness: {freshness or 'none recorded'}; no live check established.")
    for perspective in payload.get("perspectives") or []:
        date = (perspective.get("context") or {}).get("studied_at") or "none recorded"
        _text(console, f"{perspective.get('expert')}: studied {date}.")
    _text(console, "Study time is an observation date, not proof that advice is current.")


def pushback_rows(payload: dict[str, Any]) -> list[str]:
    """One projection shared by the displayed Pushback section and its pose."""
    rows = []
    for item in payload.get("disagreements") or []:
        rows.append(f"Disagreements: {item}")
    for perspective in payload.get("perspectives") or []:
        context = perspective.get("context") or {}
        name = perspective.get("expert") or "Unnamed expert"
        rows.extend(f"{name}, recorded dissent: {item}" for item in context.get("recorded_dissent") or [])
        rows.extend(f"{name}, unknown: {item}" for item in context.get("unknown") or [])
        rows.extend(f"{name}, open question: {item}" for item in context.get("live") or [])
        for position in context.get("positions") or []:
            if revision := recorded_statement(position.get("would_change_my_mind")):
                rows.append(f"{name}, revision condition: {revision}")
    return list(dict.fromkeys(rows))


def _pushback(console: Console, payload: dict[str, Any]) -> None:
    _section(console, "Pushback")
    rows = pushback_rows(payload)
    for row in rows:
        _text(console, row)
    if not rows:
        _text(console, "None recorded; this is not proof of consensus. Premise challenge is not separately assessed.")
    for item in payload.get("agreements") or []:
        _text(console, f"Agreements: {item}")


def render_consult(payload: dict[str, Any], console: Console) -> None:
    """Never slice the answer or modify the machine-readable artifact."""
    console.print(Text("Position / Synthesis", style="bold"))
    console.print(Markdown(payload.get("answer") or "None recorded."))
    status = payload.get("synthesis_status") or "unknown"
    if status != "completed":
        reason = payload.get("synthesis_stop_reason") or payload.get("synthesis_error_type") or "none recorded"
        _text(console, f"Synthesis is incomplete: {status} ({reason}).")
    perspectives = payload.get("perspectives") or []
    _grounds(console, perspectives)
    _support(console, perspectives)
    _currency(console, payload)
    _pushback(console, payload)
    delivery = payload.get("context_delivery") or {}
    for line in str(delivery.get("user_prompt") or "").splitlines():
        if line.startswith("[") and "context block(s) omitted by the prompt limit:" in line:
            _text(console, line)
    _text(console, "Mode: one-shot stored-context council; experts do not exchange turns")
    capacity = payload.get("capacity") or {}
    route = " ".join(str(capacity[key]) for key in ("synthesis_backend", "model") if capacity.get(key))
    footer = Text(
        f"${payload.get('cost_usd', 0):.4f} {route} | Knowledge writes: none; review-only output.",
        style=ROLE_STYLES["muted"],
    )
    if companion_allowed(console):
        pose: CompanionState = "error"
        if status == "completed" and payload.get("experts_consulted"):
            pose = "skeptical" if pushback_rows(payload) else "success"
        console.print(render_companion(pose, footer, console=console))
    else:
        console.print(footer)
