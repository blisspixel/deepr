"""Public council requests require explicit paid-capacity authority."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from deepr.web.council_api import handle_expert_council_request


def _jsonify(value):
    return value


def test_council_denies_missing_metered_consent_before_construction():
    factory = MagicMock(side_effect=AssertionError("council must not be constructed"))

    response, status = handle_expert_council_request(
        {"query": "What should Deepr improve?", "budget": 1.0},
        run_async=MagicMock(),
        jsonify_response=_jsonify,
        council_factory=factory,
    )

    assert status == 403
    assert "budget is only a ceiling" in response["error"]
    factory.assert_not_called()


@pytest.mark.parametrize("budget", [0, -1, float("nan"), float("inf"), "invalid"])
def test_council_rejects_invalid_budget_before_construction(budget):
    factory = MagicMock(side_effect=AssertionError("council must not be constructed"))

    response, status = handle_expert_council_request(
        {
            "query": "What should Deepr improve?",
            "budget": budget,
            "allow_metered_api": True,
            "confirm_metered_cost": True,
        },
        run_async=MagicMock(),
        jsonify_response=_jsonify,
        council_factory=factory,
    )

    assert status == 400
    assert response == {"error": "budget must be a finite positive number"}
    factory.assert_not_called()


def test_council_forwards_bounded_authorized_request():
    async def consult(**kwargs):
        return kwargs

    council = SimpleNamespace(consult=MagicMock(side_effect=consult))

    def run_async(awaitable):
        import asyncio

        return asyncio.run(awaitable)

    response = handle_expert_council_request(
        {
            "query": "  What should Deepr improve?  ",
            "budget": 1.0,
            "allow_metered_api": True,
            "confirm_metered_cost": True,
        },
        run_async=run_async,
        jsonify_response=_jsonify,
        council_factory=lambda: council,
    )

    assert response == {"query": "What should Deepr improve?", "budget": 1.0}
