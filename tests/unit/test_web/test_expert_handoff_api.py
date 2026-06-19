"""Tests for the expert handoff web API route."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("flask")

from flask import Flask, jsonify

from deepr.web.expert_handoff_api import register_expert_handoff_api


def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _decode_name(name: str):
    return name, None


@pytest.fixture
def client():
    app = Flask(__name__)
    register_expert_handoff_api(
        app,
        Path("data") / "experts",
        _decode_name,
        _safe_int,
        1000,
        logging.getLogger(__name__),
    )
    app.config.update(TESTING=True)
    return app.test_client()


def test_handoff_route_returns_versioned_payload(client):
    profile = MagicMock()
    profile.name = "Platform Expert"
    payload = {"schema_version": "deepr-expert-handoff-v1", "expert": {"name": "Platform Expert"}}

    with (
        patch("deepr.web.expert_handoff_api.ExpertStore") as store_type,
        patch("deepr.web.expert_handoff_api.build_expert_handoff") as build_handoff,
    ):
        store_type.return_value.load.return_value = profile
        build_handoff.return_value = payload

        resp = client.get(
            "/api/experts/Platform%20Expert/handoff"
            "?max_claims=500&max_gaps=500&loop_limit=500&include_decisions=true"
        )

    assert resp.status_code == 200
    assert resp.get_json() == {"handoff": payload}
    store_type.return_value.load.assert_called_once_with("Platform Expert")
    build_handoff.assert_called_once_with(
        profile,
        max_claims=100,
        max_gaps=50,
        loop_limit=50,
        include_claims=True,
        include_gaps=True,
        include_decisions=True,
    )


def test_handoff_route_returns_404_for_missing_expert(client):
    with patch("deepr.web.expert_handoff_api.ExpertStore") as store_type:
        store_type.return_value.load.return_value = None

        resp = client.get("/api/experts/Ghost/handoff")

    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Expert not found"}


def test_handoff_route_uses_decode_error():
    app = Flask(__name__)

    def bad_decode(name: str):
        return "", (jsonify({"error": f"bad name: {name}"}), 400)

    register_expert_handoff_api(
        app,
        Path("data") / "experts",
        bad_decode,
        _safe_int,
        1000,
        logging.getLogger(__name__),
    )
    app.config.update(TESTING=True)

    resp = app.test_client().get("/api/experts/bad/handoff")

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "bad name: bad"}
