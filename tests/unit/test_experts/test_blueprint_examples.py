"""Validation for the maintained expert blueprint examples."""

from __future__ import annotations

import json
from pathlib import Path

from deepr.experts.blueprint import ExpertBlueprintDraft

EXAMPLE_DIR = Path(__file__).resolve().parents[3] / "examples" / "expert_blueprints"


def test_all_expert_blueprint_examples_are_valid_drafts() -> None:
    paths = sorted(EXAMPLE_DIR.glob("*.json"))

    assert [path.name for path in paths] == [
        "digital-consciousness.json",
        "model-context-protocol.json",
        "temporal-knowledge-graphs.json",
    ]
    for path in paths:
        draft = ExpertBlueprintDraft.model_validate(json.loads(path.read_text(encoding="utf-8")))
        assert len(draft.decision_use_cases) >= 3
        assert len(draft.acceptance_cases) >= 3
        assert draft.source_policy.primary_sources_required is True
