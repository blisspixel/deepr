"""Create a local profile and start its bounded research foundation."""

from __future__ import annotations

import logging

from flask import jsonify

from deepr.web.expert_formation_api import start_formation

logger = logging.getLogger(__name__)


def _creation_fields(data, validate_name):
    if not isinstance(data, dict) or not data:
        raise ValueError("JSON object required")
    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("Name required")
    if error := validate_name(name):
        raise ValueError(error)
    for field in ("description", "domain"):
        if not isinstance(data.get(field, ""), str):
            raise ValueError(f"{field} must be a string")
    profile_only = data.get("profile_only", False)
    if not isinstance(profile_only, bool):
        raise ValueError("profile_only must be a boolean")
    return name, data.get("description", "").strip()[:1000], data.get("domain", "").strip()[:200], profile_only


def create_local_expert_request(data, experts_dir, validate_name):
    try:
        name, description, domain, profile_only = _creation_fields(data, validate_name)
    except ValueError:
        return jsonify({"error": "Invalid expert name, description, domain, or profile_only option"}), 400

    try:
        from deepr.backends.local import default_local_model
        from deepr.experts.paths import expert_slug
        from deepr.experts.profile import ExpertProfile
        from deepr.experts.profile_store import ExpertStore

        store = ExpertStore(str(experts_dir))
        if store.exists(name):
            return jsonify({"error": "Expert already exists"}), 409

        profile = ExpertProfile(
            name=name,
            vector_store_id=f"local-only:{expert_slug(name)}",
            description=description,
            domain=domain,
            provider="local",
            model=default_local_model() or "ollama",
            monthly_learning_budget=0.0,
        )
        store.save(profile)
        if not profile_only:
            start_formation(profile)

        return jsonify(
            {
                "expert": {
                    "name": profile.name,
                    "formation_requested": not profile_only,
                    "description": profile.description or "",
                    "document_count": 0,
                    "finding_count": 0,
                    "gap_count": 0,
                    "total_cost": 0,
                    "last_active": profile.updated_at.isoformat(),
                    "created_at": profile.created_at.isoformat(),
                }
            }
        ), 201
    except ImportError:
        return jsonify({"error": "Expert system not available"}), 500
    except Exception as e:
        logger.error(f"Error creating expert: {e}")
        return jsonify({"error": "Internal server error"}), 500
