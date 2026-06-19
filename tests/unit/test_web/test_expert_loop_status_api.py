"""Tests for the expert loop-status web API route."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("flask")

from flask import Flask, jsonify

from deepr.web.expert_loop_status_api import register_expert_loop_status_api


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
    register_expert_loop_status_api(
        app,
        Path("data") / "experts",
        _decode_name,
        _safe_int,
        1000,
        logging.getLogger(__name__),
    )
    app.config.update(TESTING=True)
    return app.test_client()


def test_loop_status_route_returns_rollup(client):
    profile = MagicMock()
    profile.name = "Platform Expert"

    with (
        patch("deepr.web.expert_loop_status_api.ExpertStore") as store_type,
        patch("deepr.web.expert_loop_status_api.build_loop_status_rollup") as build_rollup,
    ):
        store_type.return_value.load.return_value = profile
        build_rollup.return_value = {"expert_name": "Platform Expert", "count": 1}

        resp = client.get("/api/experts/Platform%20Expert/loop-status?limit=200")

    assert resp.status_code == 200
    assert resp.get_json() == {"loop_status": {"expert_name": "Platform Expert", "count": 1}}
    store_type.return_value.load.assert_called_once_with("Platform Expert")
    build_rollup.assert_called_once_with("Platform Expert", limit=100)


def test_loop_status_route_returns_404_for_missing_expert(client):
    with patch("deepr.web.expert_loop_status_api.ExpertStore") as store_type:
        store_type.return_value.load.return_value = None

        resp = client.get("/api/experts/Ghost/loop-status")

    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Expert not found"}


def test_loop_status_route_uses_decode_error():
    app = Flask(__name__)

    def bad_decode(name: str):
        return "", (jsonify({"error": f"bad name: {name}"}), 400)

    register_expert_loop_status_api(
        app,
        Path("data") / "experts",
        bad_decode,
        _safe_int,
        1000,
        logging.getLogger(__name__),
    )
    app.config.update(TESTING=True)

    resp = app.test_client().get("/api/experts/bad/loop-status")

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "bad name: bad"}
