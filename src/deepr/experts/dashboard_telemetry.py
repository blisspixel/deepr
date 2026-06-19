"""Structured expert telemetry for dashboard surfaces."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _iso(value: datetime | None) -> str | None:
    value = _aware(value)
    return value.isoformat() if value else None


def _count_since(values: Iterable[Any], field_name: str, cutoff: datetime) -> int:
    count = 0
    for value in values:
        ts = _aware(getattr(value, field_name, None))
        if ts is not None and ts >= cutoff:
            count += 1
    return count


def _gap_summary(gap: Any) -> dict[str, Any]:
    return {
        "id": str(getattr(gap, "id", "")),
        "topic": str(getattr(gap, "topic", "")),
        "priority": int(getattr(gap, "priority", 0) or 0),
        "ev_cost_ratio": float(getattr(gap, "ev_cost_ratio", 0.0) or 0.0),
        "times_asked": int(getattr(gap, "times_asked", 0) or 0),
        "identified_at": _iso(getattr(gap, "identified_at", None)),
    }


def _freshness_summary(profile: Any) -> dict[str, Any]:
    details = profile.get_staleness_details()
    return {
        "is_stale": bool(details.get("is_stale", False)),
        "status": str(details.get("freshness_status", "unknown")),
        "age_days": details.get("age_days"),
        "threshold_days": details.get("threshold_days"),
        "days_until_stale": details.get("days_until_stale"),
        "domain_velocity": str(details.get("domain_velocity", "")),
        "urgency": str(details.get("urgency", "unknown")),
        "urgency_score": float(details.get("urgency_score", 0.0) or 0.0),
        "estimated_refresh_cost": float(details.get("estimated_refresh_cost", 0.0) or 0.0),
        "last_refresh": details.get("last_refresh"),
        "knowledge_cutoff": details.get("knowledge_cutoff"),
        "message": details.get("message"),
        "action_required": details.get("action_required"),
        "refresh_command": details.get("refresh_command"),
    }


def _gap_telemetry(manifest: Any, *, now: datetime) -> dict[str, Any]:
    gaps = list(getattr(manifest, "gaps", []) or [])
    open_gaps = [gap for gap in gaps if not bool(getattr(gap, "filled", False))]
    closed_gaps = [gap for gap in gaps if bool(getattr(gap, "filled", False))]
    cutoff_7d = now - timedelta(days=7)
    cutoff_30d = now - timedelta(days=30)
    opened_30d = _count_since(gaps, "identified_at", cutoff_30d)
    closed_30d = _count_since(closed_gaps, "filled_at", cutoff_30d)
    top_open = sorted(
        open_gaps,
        key=lambda gap: (
            float(getattr(gap, "ev_cost_ratio", 0.0) or 0.0),
            int(getattr(gap, "priority", 0) or 0),
            int(getattr(gap, "times_asked", 0) or 0),
        ),
        reverse=True,
    )[:5]

    return {
        "total": len(gaps),
        "open": len(open_gaps),
        "closed": len(closed_gaps),
        "opened_last_7_days": _count_since(gaps, "identified_at", cutoff_7d),
        "closed_last_7_days": _count_since(closed_gaps, "filled_at", cutoff_7d),
        "opened_last_30_days": opened_30d,
        "closed_last_30_days": closed_30d,
        "net_open_delta_30_days": opened_30d - closed_30d,
        "top_open": [_gap_summary(gap) for gap in top_open],
    }


def _edge_pairs(edges: Iterable[Any]) -> tuple[set[tuple[str, str]], dict[str, set[str]]]:
    pairs: set[tuple[str, str]] = set()
    by_id: dict[str, set[str]] = {}
    for edge in edges:
        if getattr(edge, "edge_type", "") != "contradicts":
            continue
        src_id = str(getattr(edge, "src_id", ""))
        dst_id = str(getattr(edge, "dst_id", ""))
        if not src_id or not dst_id:
            continue
        pairs.add(tuple(sorted((src_id, dst_id))))
        by_id.setdefault(src_id, set()).add(dst_id)
        by_id.setdefault(dst_id, set()).add(src_id)
    return pairs, by_id


def _contested_sample(item: Any, contradiction_ids: set[str]) -> dict[str, Any]:
    return {
        "id": str(getattr(item, "id", "")),
        "domain": str(getattr(item, "domain", "")),
        "updated_at": _iso(getattr(item, "updated_at", None)),
        "contradiction_count": len(contradiction_ids),
    }


def _contested_telemetry(manifest: Any, belief_store: Any) -> dict[str, Any]:
    claims = list(getattr(manifest, "claims", []) or [])
    beliefs = list(getattr(belief_store, "beliefs", {}).values())
    edge_pairs, edge_ids_by_belief = _edge_pairs(getattr(belief_store, "edges", {}).values())
    claim_ids = {str(claim.id) for claim in claims if getattr(claim, "contradicts", None)}
    belief_ids = {
        str(belief.id)
        for belief in beliefs
        if getattr(belief, "contradictions_with", None) or str(belief.id) in edge_ids_by_belief
    }
    edge_ids = {belief_id for pair in edge_pairs for belief_id in pair}
    open_ids = claim_ids | belief_ids | edge_ids

    samples = []
    seen: set[str] = set()
    min_time = datetime.min.replace(tzinfo=UTC)
    for belief in sorted(beliefs, key=lambda item: _aware(getattr(item, "updated_at", None)) or min_time, reverse=True):
        belief_id = str(getattr(belief, "id", ""))
        if belief_id not in open_ids or belief_id in seen:
            continue
        contradiction_ids = set(getattr(belief, "contradictions_with", []) or []) | edge_ids_by_belief.get(
            belief_id, set()
        )
        samples.append(_contested_sample(belief, contradiction_ids))
        seen.add(belief_id)
        if len(samples) >= 5:
            break
    if len(samples) < 5:
        for claim in claims:
            claim_id = str(getattr(claim, "id", ""))
            if claim_id not in open_ids or claim_id in seen:
                continue
            samples.append(_contested_sample(claim, set(getattr(claim, "contradicts", []) or [])))
            seen.add(claim_id)
            if len(samples) >= 5:
                break

    return {
        "open_count": len(open_ids),
        "manifest_claim_count": len(claim_ids),
        "belief_count": len(belief_ids),
        "contradiction_edge_count": len(edge_pairs),
        "sample": samples,
    }


def build_expert_dashboard_telemetry(
    profile: Any,
    *,
    belief_store: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build read-only expert state telemetry for dashboard consumers."""
    from deepr.experts.beliefs import BeliefStore

    resolved_now = _aware(now) or datetime.now(UTC)
    store = belief_store if belief_store is not None else BeliefStore(str(profile.name))
    manifest = profile.get_manifest()
    return {
        "freshness": _freshness_summary(profile),
        "gaps": _gap_telemetry(manifest, now=resolved_now),
        "contested_claims": _contested_telemetry(manifest, store),
    }
