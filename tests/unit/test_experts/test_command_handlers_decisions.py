"""Regression tests for /why and /decisions command handlers.

These read DecisionRecord fields; a bug had them accessing `.decision`/`.reasoning`
(which do not exist) instead of `.title`/`.rationale`, crashing both commands
with AttributeError whenever a decision had been recorded.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from deepr.core.contracts import DecisionRecord, DecisionType
from deepr.experts.command_handlers import handle_decisions, handle_why


def _session_with_decisions(*records):
    return SimpleNamespace(thought_stream=SimpleNamespace(decision_records=list(records)))


def _decision(title: str, rationale: str, confidence: float = 0.8) -> DecisionRecord:
    return DecisionRecord.create(
        decision_type=DecisionType.ROUTING,
        title=title,
        rationale=rationale,
        confidence=confidence,
    )


class TestHandleWhy:
    @pytest.mark.asyncio
    async def test_empty(self):
        out = await handle_why(_session_with_decisions(), "", {})
        assert "No decisions" in out.output

    @pytest.mark.asyncio
    async def test_renders_last_decision_without_crashing(self):
        session = _session_with_decisions(
            _decision("Chose grok-4.1-fast", "Cheapest model that fits the query", 0.9),
            _decision("Stopped early", "Confidence threshold met", 0.75),
        )
        out = await handle_why(session, "", {})
        # Must surface the LAST decision's title + rationale (regression: used
        # non-existent .decision/.reasoning).
        assert "Stopped early" in out.output
        assert "Confidence threshold met" in out.output
        assert "75%" in out.output


class TestHandleDecisions:
    @pytest.mark.asyncio
    async def test_empty(self):
        out = await handle_decisions(_session_with_decisions(), "", {})
        assert "No decisions" in out.output

    @pytest.mark.asyncio
    async def test_lists_all_decisions_without_crashing(self):
        session = _session_with_decisions(
            _decision("Chose grok-4.1-fast", "cheap", 0.9),
            _decision("Stopped early", "threshold met", 0.75),
        )
        out = await handle_decisions(session, "", {})
        assert "Chose grok-4.1-fast" in out.output
        assert "Stopped early" in out.output
