"""Dashboard builds share local admission and preserve an active operation."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask

from deepr.experts.profile import ExpertProfile
from deepr.experts.profile_store import ExpertStore
from deepr.web import expert_creation, expert_formation_api as api


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPR_EXPERTS_PATH", str(tmp_path))
    profile = ExpertProfile(
        name="Local Example", vector_store_id="local-only:example", provider="local", model="fixture"
    )
    ExpertStore().save(profile)
    app = Flask(__name__)
    api.register_expert_formation_api(app, lambda name: (name, None), Mock())
    return app, profile


def test_default_creation_requests_formation_and_profile_only_does_not(tmp_path, monkeypatch):
    app = Flask(__name__)
    start = Mock(return_value=True)
    monkeypatch.setattr(expert_creation, "start_formation", start)
    monkeypatch.setattr("deepr.backends.local.default_local_model", lambda: "fixture")
    with app.app_context():
        response, status = expert_creation.create_local_expert_request({"name": "Build"}, tmp_path, lambda name: None)
        assert status == 201
        assert response.json["expert"]["formation_requested"] is True
        assert start.call_args.args[0].provider == "local"
        _, status = expert_creation.create_local_expert_request(
            {"name": "Empty", "profile_only": True}, tmp_path, lambda name: None
        )
        assert status == 201
        assert start.call_count == 1


def test_status_is_read_only_and_retry_is_explicit(environment, monkeypatch):
    app, profile = environment
    start = Mock(return_value=True)
    monkeypatch.setattr(api, "start_formation", start)
    client = app.test_client()
    assert client.get("/api/experts/Local%20Example/formation").json == {"formation": None}
    start.assert_not_called()
    assert client.post("/api/experts/Local%20Example/build").status_code == 202
    start.assert_called_once()
    assert client.get("/api/experts/Missing/formation").status_code == 404


def test_build_refuses_existing_brief(environment, monkeypatch):
    app, profile = environment
    path = api.canonical_expert_dir(profile.name) / "hold/current.json"
    path.parent.mkdir(parents=True)
    path.write_text("Existing knowledge", encoding="utf-8")
    start = Mock()
    monkeypatch.setattr(api, "start_formation", start)
    assert app.test_client().post("/api/experts/Local%20Example/build").status_code == 409
    start.assert_not_called()


def test_unavailable_owned_capacity_records_failure_without_provider_fallback(environment, monkeypatch):
    _, profile = environment
    captured = []
    monkeypatch.setattr(
        api.threading, "Thread", lambda **kwargs: SimpleNamespace(start=lambda: captured.append(kwargs["target"]))
    )
    backend = Mock(side_effect=ValueError("Owned local capacity unavailable"))
    monkeypatch.setattr("deepr.cli.commands.semantic.study_backend.build_study_backend", backend)
    assert api.start_formation(profile)
    captured[0]()
    state = api.read_formation_state(profile.name)
    assert state["status"] == "incomplete"
    assert state["api_cost_usd"] == 0
    backend.assert_called_once_with(profile=profile, local=True, model="fixture")


def test_busy_build_does_not_overwrite_running_operation(environment):
    _, profile = environment
    from deepr.experts.loop_lock import expert_verb_lock

    path = api.canonical_expert_dir(profile.name) / "formation/current.json"
    path.parent.mkdir(parents=True)
    raw = json.dumps({"schema_version": "deepr-formation-v1", "status": "running", "operation_id": "owned"})
    path.write_text(raw, encoding="utf-8")
    with expert_verb_lock(profile.name, "formation") as acquired:
        assert acquired
        api._record_unavailable(profile, ValueError("Busy"))
    assert path.read_text() == raw


@pytest.mark.parametrize("data", [[], "bad", {"name": "Example", "profile_only": "yes"}])
def test_creation_rejects_malformed_options_before_saving(tmp_path, data):
    with Flask(__name__).app_context():
        _, status = expert_creation.create_local_expert_request(data, tmp_path, lambda name: None)
    assert status == 400
    assert not list(tmp_path.glob("*/profile.json"))


@pytest.mark.parametrize("exception", [ValueError, RuntimeError])
def test_creation_does_not_expose_internal_failure_details(tmp_path, monkeypatch, exception):
    monkeypatch.setattr(
        "deepr.backends.local.default_local_model",
        Mock(side_effect=exception("Private configuration at /operator/private/settings")),
    )
    with Flask(__name__).app_context():
        response, status = expert_creation.create_local_expert_request(
            {"name": "Example", "profile_only": True}, tmp_path, lambda name: None
        )
    assert status == 500
    assert response.json == {"error": "Internal server error"}
    assert not list(tmp_path.glob("*/profile.json"))
