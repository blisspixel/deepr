"""Frozen, read-only decision packets over outcome and consultation records."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from deepr.experts.experience import consult_trace_link, index_consult_traces
from deepr.experts.outcomes import ExpertOutcome


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def select_decision_outcomes(
    expert_name: str,
    outcomes: list[ExpertOutcome],
    *,
    outcome_id: str | None = None,
    decision_id: str | None = None,
) -> list[ExpertOutcome]:
    """Select exact caller identities, retaining every observation of that decision."""
    if bool(outcome_id) == bool(decision_id):
        raise ValueError("Select exactly one --outcome-id or --decision-id")
    normalized = " ".join(expert_name.split()).casefold()
    if any(" ".join(item.expert_name.split()).casefold() != normalized for item in outcomes):
        raise ValueError("Outcome expert does not match the requested expert")
    ids = [item.outcome_id for item in outcomes]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate outcome identity; decision review is ambiguous")
    if outcome_id:
        matches = [item for item in outcomes if item.outcome_id == outcome_id]
        if not matches:
            raise ValueError(f"Outcome {outcome_id!r} was not found")
        decision_id = matches[0].decision_id
    selected = [item for item in outcomes if item.decision_id == decision_id]
    if not selected:
        raise ValueError(f"Decision {decision_id!r} was not found")
    return selected


def review_trace_ids(outcomes: list[ExpertOutcome], compare_trace_id: str | None = None) -> set[str]:
    ids = {item.consult_trace_id for item in outcomes if item.consult_trace_id is not None}
    if compare_trace_id:
        ids.add(compare_trace_id)
    if len(ids) > 100:
        raise ValueError("Decision review supports at most 100 distinct consult traces")
    return ids


def _trace_snapshot(
    trace_id: str | None,
    expert_name: str,
    indexed: dict[str, dict[str, Any]],
    duplicates: set[str],
) -> dict[str, Any]:
    link = consult_trace_link(trace_id, expert_name=expert_name, traces_by_id=indexed, duplicate_trace_ids=duplicates)
    if link["status"] != "matched":
        return {"link": link, "record": None, "record_sha256": None, "unavailable": ["consultation record"]}
    record = json.loads(_json(indexed[str(trace_id)]))
    output = record.get("output")
    output = output if isinstance(output, dict) else {}
    delivery = output.get("context_delivery")
    missing = []
    for field in ("answer", "synthesis_status", "synthesis_stop_reason"):
        if not isinstance(output.get(field), str) or not output[field]:
            missing.append(field)
    if not isinstance(delivery, dict) or not delivery:
        missing.append("delivered prompt receipt")
    else:
        missing.extend(
            f"delivery.{field}"
            for field in ("system_prompt", "user_prompt", "user_prompt_sha256")
            if not isinstance(delivery.get(field), str) or not delivery[field]
        )
    if not isinstance(record.get("context_packet"), dict) or not record["context_packet"].get("selected"):
        missing.append("selected source context")
    return {"link": link, "record": record, "record_sha256": _digest(record), "unavailable": missing}


def _recorded_sources(record: dict[str, Any]) -> list[dict[str, str]] | None:
    """Project only source identities explicitly stored in selected context."""
    packet = record.get("context_packet")
    selected = packet.get("selected") if isinstance(packet, dict) else None
    if not isinstance(selected, list) or not selected:
        return None
    sources: dict[str, dict[str, str]] = {}
    for item in selected:
        context = item.get("context") if isinstance(item, dict) else None
        passages = context.get("passages") if isinstance(context, dict) else None
        if not isinstance(passages, list):
            return None
        for passage in passages:
            if not isinstance(passage, dict) or not isinstance(passage.get("sha256"), str):
                return None
            identity = {"sha256": passage["sha256"], "origin": str(passage.get("origin", ""))}
            sources[_json(identity)] = identity
    return [sources[key] for key in sorted(sources)]


def _comparison(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    records = [left["record"], right["record"]]
    if any(record is None for record in records):
        return {"status": "unavailable", "reason": "Both trace identities must match the expert unambiguously"}
    source_sets = [_recorded_sources(record) for record in records]
    identities = [{_json(item) for item in items} if items is not None else None for items in source_sets]
    first, second = identities
    source_delta: dict[str, Any] = {"status": "unavailable"}
    if first is not None and second is not None:
        source_delta = {
            "status": "recorded",
            "added": [json.loads(item) for item in sorted(second - first)],
            "removed": [json.loads(item) for item in sorted(first - second)],
            "unchanged_count": len(first & second),
        }
    deliveries = []
    for record in records:
        output = record.get("output")
        delivery = output.get("context_delivery") if isinstance(output, dict) else None
        deliveries.append(delivery if isinstance(delivery, dict) and delivery else None)
    return {
        "status": "recorded_input_comparison",
        "left_trace_id": left["link"]["trace_id"],
        "right_trace_id": right["link"]["trace_id"],
        "recorded_source_identities": source_delta,
        "context_packet_changed": (
            None
            if any(not isinstance(record.get("context_packet"), dict) for record in records)
            else records[0]["context_packet"] != records[1]["context_packet"]
        ),
        "delivery_receipt_changed": None
        if any(item is None for item in deliveries)
        else deliveries[0] != deliveries[1],
        "same_decision_inferred": False,
        "advice_supersession_inferred": False,
        "interpretation": "Recorded input changes only. Selected sources need not all appear in delivered messages.",
    }


def build_decision_review(
    expert_name: str,
    *,
    outcomes: list[ExpertOutcome],
    traces: list[dict[str, Any]],
    outcome_id: str | None = None,
    decision_id: str | None = None,
    compare_trace_id: str | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Freeze existing records; never fetch current expert knowledge or infer a revision."""
    selected = select_decision_outcomes(expert_name, outcomes, outcome_id=outcome_id, decision_id=decision_id)
    review_trace_ids(selected, compare_trace_id)
    indexed, duplicates = index_consult_traces(traces)
    superseded_by: dict[str, list[str]] = {}
    for item in selected:
        if item.supersedes_outcome_id:
            superseded_by.setdefault(item.supersedes_outcome_id, []).append(item.outcome_id)
    cases: list[dict[str, Any]] = [
        {
            "outcome": item.model_dump(mode="json"),
            "superseded_by": superseded_by.get(item.outcome_id, []),
            "consultation": _trace_snapshot(item.consult_trace_id, expert_name, indexed, duplicates),
        }
        for item in selected
    ]
    comparison = _trace_snapshot(compare_trace_id, expert_name, indexed, duplicates) if compare_trace_id else None
    changes = []
    if comparison is not None:
        for case in cases:
            if outcome_id is None or case["outcome"]["outcome_id"] == outcome_id:
                changes.append(
                    {"outcome_id": case["outcome"]["outcome_id"], **_comparison(case["consultation"], comparison)}
                )
    frozen = {"cases": cases, "comparison": comparison}
    return {
        "schema_version": "deepr-decision-review-v1",
        "kind": "deepr.expert.decision_review",
        "generated_at": (generated_at or datetime.now(UTC)).isoformat(),
        "expert_name": expert_name,
        "decision_id": selected[0].decision_id,
        "selected_outcome_id": outcome_id,
        "contract": {
            "read_only": True,
            "derived_view": True,
            "writes_state": False,
            "cost_usd": 0.0,
            "model_calls": 0,
            "semantic_quality_verdict": False,
            "operator_identity_independently_verified": False,
        },
        "snapshot_sha256": _digest(frozen),
        **frozen,
        "input_changes": changes,
        "review": {"status": "unreviewed", "still_valid": None, "reconsider": None, "unresolved": None},
    }


def _fenced(text: str, language: str = "") -> str:
    # A longer fence preserves arbitrary recorded text as data, including Markdown.
    fence = "```"
    while fence in text:
        fence += "`"
    return f"{fence}{language}\n{text}\n{fence}"


def _render_trace(snapshot: dict[str, Any]) -> list[str]:
    link = snapshot["link"]
    lines = [f"Trace: {link['trace_id'] or 'not linked'}; link status: {link['status']}.", ""]
    record = snapshot["record"]
    if record is None:
        return [*lines, "Original answer and context unavailable.", ""]
    output = record.get("output")
    output = output if isinstance(output, dict) else {}
    lines += [
        f"Recorded: {link['recorded_at'] or 'unknown'}; trace status: {link['trace_status'] or 'unknown'}.",
        f"Answer status: {output.get('synthesis_status') or 'unavailable'}; "
        f"stop reason: {output.get('synthesis_stop_reason') or 'unavailable'}.",
        "",
        "Question:",
        _fenced(link["question"] or "Unavailable"),
        "",
        "Original answer:",
        _fenced(str(output.get("answer") or "Unavailable")),
        "",
        "Recorded environment:",
        _fenced(json.dumps(record.get("capacity"), indent=2, ensure_ascii=True), "json"),
        "",
        "Unavailable evidence: " + (", ".join(snapshot["unavailable"]) or "none of the inspected fields") + ".",
        "",
        "Recorded selected source identities (selection does not prove delivery):",
        _fenced(json.dumps(_recorded_sources(record), indent=2, ensure_ascii=True), "json"),
        "",
        "Recorded delivered prompt receipt:",
        _fenced(json.dumps(output.get("context_delivery") or "Unavailable", indent=2, ensure_ascii=True), "json"),
        "",
        "Full source context, omissions and failures are preserved in the packet receipt below.",
        "",
    ]
    return lines


def render_decision_review(packet: dict[str, Any]) -> str:
    """Render one packet, retaining its complete JSON receipt for exact parity."""
    lines = [
        "# Decision review",
        "",
        f"Generated: {packet['generated_at']}",
        f"Snapshot SHA-256 (canonical JSON): {packet['snapshot_sha256']}",
        "",
        "Expert and exact decision identity:",
        _fenced(f"{packet['expert_name']}\n{packet['decision_id']}"),
        "",
        "Operator observations are attestations, not independently verified outcomes. "
        "A shared decision ID does not establish applicability to every question or environment.",
        "",
    ]
    for index, case in enumerate(packet["cases"], 1):
        outcome = case["outcome"]
        lines += [f"## Observation {index}", "", _fenced(outcome["outcome_id"]), ""]
        lines += _render_trace(case["consultation"])
        lines += [
            "Operator-attested observation:",
            _fenced(outcome["observation"]),
            f"Observed: {outcome['observed_at']}; recorded: {outcome['recorded_at']}; result: {outcome['result']}.",
            "Attested by:",
            _fenced(outcome["attested_by"]),
            "Explicit outcome supersession (does not supersede advice):",
            _fenced(
                json.dumps({"supersedes": outcome["supersedes_outcome_id"], "superseded_by": case["superseded_by"]})
            ),
            "",
        ]
    if packet["comparison"] is not None:
        lines += ["## Explicit comparison consultation", "", *_render_trace(packet["comparison"])]
        lines += ["Recorded input changes only:", _fenced(json.dumps(packet["input_changes"], indent=2), "json"), ""]
    lines += [
        "## Review remains unreviewed",
        "",
        "Still valid: not reviewed. Reconsider: not reviewed. Unresolved: not reviewed.",
        "An accountable reviewer must assess meaning and applicability; this packet makes no quality verdict.",
        "",
        "## Complete frozen packet receipt",
        "",
        _fenced(json.dumps(packet, indent=2, ensure_ascii=True, allow_nan=False), "json"),
        "",
    ]
    return "\n".join(lines)
