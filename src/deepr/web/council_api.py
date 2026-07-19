"""Fail-closed HTTP boundary for metered stored-context councils."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Mapping
from typing import Any

from deepr.security.metered_consent import metered_api_consent_error

logger = logging.getLogger(__name__)


def handle_expert_council_request(
    data: object,
    *,
    run_async: Callable[[Any], Any],
    jsonify_response: Callable[[Any], Any],
    council_factory: Callable[[], Any] | None = None,
) -> Any:
    """Validate authority and bounds before constructing a metered council."""
    if not isinstance(data, Mapping) or not str(data.get("query", "")).strip():
        return jsonify_response({"error": "query required"}), 400
    if denial := metered_api_consent_error(data):
        return jsonify_response({"error": denial}), 403

    from deepr.experts.cost_safety import CostSafetyManager
    from deepr.experts.council import ExpertCouncil

    try:
        raw_budget = float(data.get("budget", 2.0))
    except (TypeError, ValueError):
        return jsonify_response({"error": "budget must be a finite positive number"}), 400
    if not math.isfinite(raw_budget) or raw_budget <= 0:
        return jsonify_response({"error": "budget must be a finite positive number"}), 400
    budget = min(raw_budget, CostSafetyManager.ABSOLUTE_MAX_PER_OPERATION)

    try:
        council = (council_factory or ExpertCouncil)()
        result = run_async(council.consult(query=str(data["query"]).strip(), budget=budget))
        return jsonify_response(result)
    except Exception as exc:
        logger.error("Council request failed (%s)", type(exc).__name__)
        return jsonify_response({"error": "Internal server error"}), 500


__all__ = ["handle_expert_council_request"]
