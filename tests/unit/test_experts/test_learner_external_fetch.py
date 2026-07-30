"""Fail-closed regression for unclassified learner network retrieval."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("azure.core")

from deepr.experts.learner import AutonomousLearner


@pytest.mark.asyncio
async def test_direct_paper_fetch_is_blocked_before_http_client_construction() -> None:
    learner = MagicMock()
    source = SimpleNamespace(url="https://example.com/paper.html")

    with patch("httpx.AsyncClient", side_effect=AssertionError("must not construct external client")):
        result = await AutonomousLearner._fetch_paper(learner, source)

    assert result is None
    message = learner._log_progress.call_args.args[0]
    assert "External paper fetch is disabled" in message
    assert "response-size accounting" in message
