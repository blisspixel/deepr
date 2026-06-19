"""Web API route for versioned expert handoff payloads."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request

from deepr.experts.handoff import build_expert_handoff
from deepr.experts.profile_store import ExpertStore


def _bool_arg(value: Any, default: bool) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def register_expert_handoff_api(
    app: Flask,
    experts_dir: Path,
    decode_expert_name: Callable[[str], tuple[str, Any]],
    safe_int: Callable[[Any, int], int],
    max_query_limit: int,
    logger: logging.Logger,
) -> None:
    """Register read-only expert handoff routes."""

    @app.route("/api/experts/<name>/handoff", methods=["GET"])
    def get_expert_handoff(name: str):
        try:
            decoded_name, err = decode_expert_name(name)
            if err:
                return err

            store = ExpertStore(str(experts_dir))
            profile = store.load(decoded_name)
            if not profile:
                return jsonify({"error": "Expert not found"}), 404

            max_payload_limit = min(max_query_limit, 100)
            handoff = build_expert_handoff(
                profile,
                max_claims=min(max(safe_int(request.args.get("max_claims", 10), 10), 0), max_payload_limit),
                max_gaps=min(max(safe_int(request.args.get("max_gaps", 10), 10), 0), 50),
                loop_limit=min(max(safe_int(request.args.get("loop_limit", 5), 5), 1), 50),
                include_claims=_bool_arg(request.args.get("include_claims"), True),
                include_gaps=_bool_arg(request.args.get("include_gaps"), True),
                include_decisions=_bool_arg(request.args.get("include_decisions"), False),
            )
            return jsonify({"handoff": handoff})
        except ImportError:
            return jsonify({"error": "Expert system not available"}), 404
        except Exception as exc:
            logger.error("Error getting handoff for expert %s: %s", name, exc)
            return jsonify({"error": "Internal server error"}), 500
