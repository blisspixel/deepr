"""Attended local research builds and their durable progress for the dashboard."""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import UTC, datetime
from typing import Any

from flask import jsonify

from deepr.experts.formation import form_expert, read_formation_state
from deepr.experts.loop_lock import expert_verb_lock
from deepr.experts.paths import canonical_expert_dir
from deepr.experts.profile_store import ExpertStore
from deepr.utils.atomic_io import atomic_write_json

logger = logging.getLogger(__name__)
_capacity_slot = threading.BoundedSemaphore(1)


def _record_unavailable(profile: Any, error: Exception) -> None:
    with expert_verb_lock(profile.name, "formation") as acquired:
        if not acquired:
            return
        previous = read_formation_state(profile.name)
        if previous and previous.get("status") in {"research_complete", "incomplete", "interrupted"}:
            return
        _write_capacity_failure(profile, error)


def _write_capacity_failure(profile: Any, error: Exception) -> None:
    atomic_write_json(
        canonical_expert_dir(profile.name) / "formation/current.json",
        {
            "schema_version": "deepr-formation-v1",
            "expert": profile.name,
            "status": "incomplete",
            "stage": "capacity",
            "progress": str(error)[:500],
            "qualification": "not_reviewed",
            "updated_at": datetime.now(UTC).isoformat(),
            "api_cost_usd": 0,
            "model_calls": 0,
        },
        fsync=True,
    )


def start_formation(profile: Any) -> bool:
    """Start at most one dashboard-owned local build; never queue unbounded work."""
    if not _capacity_slot.acquire(blocking=False):
        _record_unavailable(
            profile, ValueError("Another local research build is running. Start this build when capacity is available.")
        )
        return False

    def worker() -> None:
        try:
            from deepr.cli.commands.semantic.study_backend import build_study_backend

            backend = build_study_backend(profile=profile, local=True, model=profile.model)
            asyncio.run(form_expert(profile, backend))
        except Exception as error:
            logger.warning("Local formation could not start for %s: %s", profile.name, error)
            _record_unavailable(profile, error)
        finally:
            _capacity_slot.release()

    thread = threading.Thread(target=worker, daemon=True, name="expert-formation")
    try:
        thread.start()
    except Exception:
        _capacity_slot.release()
        raise
    return True


def register_expert_formation_api(app, decode_expert_name, log) -> None:
    def resolve(name):
        decoded, error = decode_expert_name(name)
        if error:
            return None, error
        profile = ExpertStore().load(decoded)
        if profile is None:
            return None, (jsonify({"error": "Expert not found"}), 404)
        return profile, None

    def status(name):
        profile, error = resolve(name)
        if error:
            return error
        try:
            return jsonify({"formation": read_formation_state(profile.name)})
        except (OSError, ValueError):
            log.warning("Unreadable formation status for %s", profile.name, exc_info=True)
            return jsonify({"error": "Formation record could not be read"}), 500

    def build(name):
        from deepr.experts.expert_layout import hold_current_path

        profile, error = resolve(name)
        if error:
            return error
        if hold_current_path(profile.name).exists():
            return jsonify({"error": "This expert already has a brief; use explicit maintenance"}), 409
        started = start_formation(profile)
        return jsonify({"started": started}), 202 if started else 409

    app.add_url_rule(
        "/api/experts/<name>/formation", endpoint="expert_formation_status", view_func=status, methods=["GET"]
    )
    app.add_url_rule("/api/experts/<name>/build", endpoint="expert_formation_build", view_func=build, methods=["POST"])
