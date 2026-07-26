"""Pause/resume spend memory: in-flight paid jobs must never be re-bought.

A daily-limit pause used to save every not-yet-completed topic as
"remaining", including topics whose jobs were already submitted and billing
at the provider; the next --resume rebuilt and re-submitted them as fresh
paid research. In-flight topics are now excluded from remaining and recorded
with their provider job ids for retrieval.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from deepr.experts import learner_persistence


@dataclass
class _Topic:
    title: str
    research_prompt: str = "p"
    research_mode: str = "single"
    research_type: str = "docs"
    estimated_cost: float = 0.5
    estimated_minutes: int = 5


def _save(tmp_path: Path, **kwargs) -> dict:
    store = MagicMock()
    store.get_knowledge_dir.return_value = tmp_path
    with patch.object(learner_persistence, "ExpertStore", return_value=store):
        learner_persistence.save_learning_progress(
            expert_name="Expert",
            completed_topics=kwargs.get("completed", []),
            failed_topics=kwargs.get("failed", []),
            remaining_topics=kwargs.get("topics", []),
            total_cost=1.23,
            started_at=datetime.now(UTC),
            in_flight=kwargs.get("in_flight"),
        )
    return json.loads((tmp_path / "learning_progress.json").read_text(encoding="utf-8"))


def test_in_flight_topics_are_excluded_from_remaining(tmp_path: Path) -> None:
    topics = [_Topic("Submitted A"), _Topic("Submitted B"), _Topic("Never Started")]
    data = _save(
        tmp_path,
        topics=topics,
        in_flight={"Submitted A": "resp_aaa", "Submitted B": "resp_bbb"},
    )

    remaining_titles = [t["title"] for t in data["remaining_topics"]]
    assert remaining_titles == ["Never Started"]
    assert data["in_flight_topics"] == [
        {"title": "Submitted A", "provider_job_id": "resp_aaa"},
        {"title": "Submitted B", "provider_job_id": "resp_bbb"},
    ]


def test_completed_and_failed_still_excluded(tmp_path: Path) -> None:
    topics = [_Topic("Done"), _Topic("Broken"), _Topic("Fresh")]
    data = _save(tmp_path, topics=topics, completed=["Done"], failed=["Broken"])

    assert [t["title"] for t in data["remaining_topics"]] == ["Fresh"]
    assert data["in_flight_topics"] == []
