"""Tests for generated expert memory cards."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from deepr.core.contracts import Claim, ExpertManifest, Gap, Source
from deepr.experts.memory_card import (
    EXPERT_MEMORY_CARD_KIND,
    EXPERT_MEMORY_CARD_SCHEMA_VERSION,
    build_expert_memory_card,
    render_expert_memory_card,
    write_expert_memory_card,
)
from deepr.experts.profile import ExpertProfile


def _profile() -> ExpertProfile:
    return ExpertProfile(
        name="Memory Card Expert",
        vector_store_id="vs-memory-card",
        domain="agent memory",
        description="Durable expert memory",
        knowledge_cutoff_date=datetime(2026, 6, 26, tzinfo=UTC),
        last_knowledge_refresh=datetime(2026, 6, 26, tzinfo=UTC),
        installed_skills=["consult-review"],
    )


def _manifest() -> ExpertManifest:
    source = Source.create("Memory design note", extraction_method="manual")
    safe_claim = Claim.create(
        "Expert memory cards should be regenerated from structured state.",
        "agent memory",
        0.91,
        sources=[source],
        grounding_assurance="cross_vendor",
    )
    contested = Claim.create(
        "Markdown files are authoritative expert memory.",
        "agent memory",
        0.2,
        contradicts=[safe_claim.id],
    )
    theory = Claim.create(
        "Regenerated memory cards can help host agents build rapport with an expert.",
        "agent memory",
        0.7,
        tags=["hypothesis", "insight"],
    )
    return ExpertManifest(
        expert_name="Memory Card Expert",
        domain="agent memory",
        claims=[safe_claim, theory, contested],
        gaps=[
            Gap.create(
                "identity update review",
                questions=["How should preferred names be reviewed?"],
                priority=5,
                ev_cost_ratio=8.0,
            )
        ],
    )


def test_build_expert_memory_card_is_read_only_derived_view(tmp_path):
    event_log = tmp_path / "events.jsonl"
    event_log.write_text(
        json.dumps(
            {
                "timestamp": "2026-06-27T12:00:00+00:00",
                "belief_id": "belief_1",
                "change_type": "created",
                "reason": "absorbed source note",
                "new_claim": "Memory cards are derived.",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    payload = build_expert_memory_card(
        _profile(),
        _manifest(),
        focus_limit=3,
        generated_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
        event_log_path=event_log,
    )

    assert payload["schema_version"] == EXPERT_MEMORY_CARD_SCHEMA_VERSION
    assert payload["kind"] == EXPERT_MEMORY_CARD_KIND
    assert payload["contract"]["read_only"] is True
    assert payload["contract"]["cost_usd"] == 0.0
    assert payload["contract"]["authoritative"] is False
    assert payload["contract"]["model_calls"] == 0
    assert payload["artifact"]["filename"] == "EXPERT.md"
    assert payload["expert"]["preferred_name"] == "Memory Card Expert"
    assert payload["expert"]["identity_policy"].startswith("The profile name is authoritative")
    assert payload["memory_layers"]["belief_graph"]["authority"] == "canonical"
    assert payload["memory_layers"]["wiki_card"]["authority"] == "derived"
    assert payload["current_stance"]["belief_count"] == 3
    assert len(payload["beliefs"]) == 3
    assert payload["beliefs"][0]["grounding_assurance"] == "cross_vendor"
    assert payload["perspective"]["position"] == "expertise is a developing perspective, not a fact list"
    assert payload["perspective"]["working_theories"][0]["state_tags"] == ["hypothesis", "insight"]
    assert "metered API calls" in payload["perspective"]["agency_scope"]["requires_explicit_gate"]
    assert payload["perspective"]["self_research_agenda"][0]["topic"] == "identity update review"
    assert payload["gaps"][0]["topic"] == "identity update review"
    assert payload["recent_belief_events"][0]["new_claim"] == "Memory cards are derived."
    assert "hypothesis or original idea" in payload["collaboration"]["host_agent_guidance"][2]


def test_render_expert_memory_card_markdown_has_policy_sections():
    payload = build_expert_memory_card(
        _profile(),
        _manifest(),
        generated_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
    )

    markdown = render_expert_memory_card(payload)

    assert markdown.startswith("---\n")
    assert "# Memory Card Expert" in markdown
    assert "## Current Stance" in markdown
    assert "## Perspective And Agency" in markdown
    assert "## Working Theories And Insights" in markdown
    assert "## Self Research Agenda" in markdown
    assert "## What Would Change My Mind" in markdown
    assert "## Memory Layers" in markdown
    assert "## Update Policy" in markdown
    assert "Canonical memory lives in structured Deepr state." in markdown
    assert "Do not hand-edit it as memory." in markdown


def test_write_expert_memory_card_writes_output_path(tmp_path):
    output_path = tmp_path / "EXPERT.md"

    artifact = write_expert_memory_card(
        _profile(),
        _manifest(),
        output_path=output_path,
        generated_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
    )

    assert artifact.path == output_path
    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8") == artifact.markdown
    assert artifact.payload["artifact"]["filename"] == "EXPERT.md"
