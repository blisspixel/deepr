"""Web API route for expert loop-status rollups."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request

from deepr.experts.loop_status_rollup import build_loop_status_rollup
from deepr.experts.profile_store import ExpertStore


def register_expert_loop_status_api(
    app: Flask,
    experts_dir: Path,
    decode_expert_name: Callable[[str], tuple[str, Any]],
    safe_int: Callable[[Any, int], int],
    max_query_limit: int,
    logger: logging.Logger,
) -> None:
    """Register read-only loop-status rollup routes."""

    @app.route("/api/experts/<name>/loop-status", methods=["GET"])
    def get_expert_loop_status_rollup(name: str):
        try:
            decoded_name, err = decode_expert_name(name)
            if err:
                return err

            route_limit = min(max_query_limit, 100)
            limit = min(max(safe_int(request.args.get("limit", 20), 20), 1), route_limit)
            store = ExpertStore(str(experts_dir))
            profile = store.load(decoded_name)
            if not profile:
                return jsonify({"error": "Expert not found"}), 404

            resolved_name = getattr(profile, "name", decoded_name) or decoded_name
            rollup = build_loop_status_rollup(str(resolved_name), limit=limit)
            return jsonify({"loop_status": rollup})
        except ImportError:
            return jsonify({"error": "Expert system not available"}), 404
        except Exception as exc:
            logger.error("Error getting loop status for expert %s: %s", name, exc)
            return jsonify({"error": "Internal server error"}), 500
