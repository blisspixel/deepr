"""Read-only capacity evidence is shared and never substitutes for dispatch proof."""

import importlib
import json
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from click.testing import CliRunner

from deepr.backends.capacity import (
    OllamaGenerationReadiness,
    OwnedLocalCapacityRefused,
    detect_capacity,
    observe_local_ollama_generation,
    validate_owned_local_ollama_cloud_status,
)
from deepr.backends.local_capacity import LocalCapacityObservation, LocalCapacityState

MODEL = {
    "name": "fixture:large",
    "model": "fixture:large",
    "size": 100,
    "digest": "a" * 64,
    "details": {"format": "gguf"},
}


@pytest.fixture
def server(monkeypatch):
    original_client = httpx.Client
    requests = []

    def install(status, *, status_code=200, inventory=None, invalid_json=False, connect_error=False):
        def respond(request):
            requests.append(request)
            assert request.method == "GET"
            assert "authorization" not in request.headers
            if connect_error:
                raise httpx.ConnectError("private detail must not appear", request=request)
            if request.url.path == "/api/status":
                return (
                    httpx.Response(status_code, content=b"not JSON")
                    if invalid_json
                    else httpx.Response(status_code, json=status)
                )
            assert request.url.path == "/api/tags"
            return httpx.Response(200, json=inventory if inventory is not None else {"models": [MODEL]})

        def client(**kwargs):
            assert kwargs["trust_env"] is False
            assert kwargs["follow_redirects"] is False
            return original_client(**kwargs, transport=httpx.MockTransport(respond))

        monkeypatch.setattr(httpx, "Client", client)
        return requests

    return install


@pytest.mark.parametrize("source", ["config", "both"])
def test_ready_proof_reads_status_and_exact_materialized_inventory(server, source, monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://invalid-proxy.example")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-sent")
    requests = server({"cloud": {"disabled": True, "source": source}})
    result = observe_local_ollama_generation("http://127.0.0.1:11435")
    assert result.status == "ready"
    assert result.cloud_disabled is True
    assert result.cloud_source == source
    assert result.model == "fixture:large"
    assert [str(item.url) for item in requests] == [
        "http://127.0.0.1:11435/api/status",
        "http://127.0.0.1:11435/api/tags",
    ]


@pytest.mark.parametrize(
    "cloud",
    [
        {"disabled": False, "source": "none"},
        {"disabled": True, "source": "env"},
        {"disabled": "true", "source": "config"},
        {"disabled": True, "source": []},
        {},
    ],
)
def test_refusal_is_typed_and_explains_daemon_config_without_inventory_request(server, cloud):
    requests = server({"cloud": cloud})
    with pytest.raises(OwnedLocalCapacityRefused):
        validate_owned_local_ollama_cloud_status({"cloud": cloud})
    proof = observe_local_ollama_generation()
    assert proof.status == "refused"
    assert "daemon user's" in proof.detail
    assert "/usr/share/ollama/.ollama/server.json" in proof.detail
    assert "preserving existing settings" in proof.detail
    assert "systemctl restart ollama" in proof.detail
    assert "ollama serve" in proof.detail
    assert len(requests) == 1


@pytest.mark.parametrize(
    "options,reason",
    [
        ({"status_code": 404}, "status_unavailable"),
        ({"status_code": 302}, "status_unavailable"),
        ({"invalid_json": True}, "invalid_status"),
        ({"connect_error": True}, "unreachable"),
    ],
)
def test_missing_or_unreadable_status_is_unverified_and_never_followed(server, options, reason):
    requests = server({}, **options)
    result = observe_local_ollama_generation()
    assert result.status == "unverified"
    assert result.reason == reason
    assert "private detail" not in result.detail
    assert len(requests) == 1


@pytest.mark.parametrize("inventory", [{"models": []}, {"models": [dict(MODEL, remote=True)]}, {"models": "bad"}])
def test_cloud_proof_without_materialized_model_is_not_ready(server, inventory):
    server({"cloud": {"disabled": True, "source": "config"}}, inventory=inventory)
    result = observe_local_ollama_generation()
    assert result.status == "refused"
    assert result.reason == "model_unavailable"


@pytest.mark.parametrize(
    "endpoint", ["http://192.168.1.2:11434", "https://garage.example", "http://user:secret@127.0.0.1"]
)
def test_unowned_endpoint_is_refused_before_http_construction(monkeypatch, endpoint):
    client = Mock(side_effect=AssertionError("must not construct transport"))
    monkeypatch.setattr(httpx, "Client", client)
    result = observe_local_ollama_generation(endpoint)
    assert result.status == "refused"
    assert result.reason == "endpoint_not_owned"
    assert "secret" not in result.detail
    client.assert_not_called()


@pytest.mark.parametrize(
    "status,disabled,source", [("refused", False, "none"), ("ready", True, "config"), ("unverified", None, None)]
)
def test_human_json_and_init_agree_on_generation_evidence(monkeypatch, status, disabled, source):
    capacity_module = importlib.import_module("deepr.cli.commands.capacity")
    proof = OllamaGenerationReadiness(
        status, "Bounded diagnostic evidence", cloud_disabled=disabled, cloud_source=source
    )
    sources = detect_capacity(
        ollama_probe=lambda: (True, "one installed model"),
        ollama_generation_probe=lambda: proof,
        which=lambda executable: None,
        env={},
    )
    monkeypatch.setattr(capacity_module, "detect_capacity", lambda: sources)
    monkeypatch.setattr(capacity_module, "summarize_quota_state", lambda: [])
    monkeypatch.setattr(capacity_module, "_print_admissions_summary", lambda: None)
    monkeypatch.setattr(
        capacity_module,
        "probe_local_gpu_occupancy",
        lambda: LocalCapacityObservation(LocalCapacityState.UNKNOWN, "test", "not measured"),
    )
    runner = CliRunner()
    human = runner.invoke(capacity_module.capacity, [])
    machine = runner.invoke(capacity_module.capacity, ["--json"])
    assert human.exit_code == machine.exit_code == 0
    assert f"Local generation: {status}" in human.output
    local = json.loads(machine.output)[0]
    assert local["available"] is True
    assert local["local_generation"] == proof.to_dict()
    assert local["execution_eligible"] is (None if status == "ready" else False)
    monkeypatch.setattr("deepr.backends.capacity.detect_capacity", lambda **kwargs: sources)
    init_module = importlib.import_module("deepr.cli.commands.init")
    with runner.isolated_filesystem():
        initialized = runner.invoke(init_module.init, ["--yes"])
    assert initialized.exit_code == 0
    assert f"Local generation: {status}" in initialized.output


@pytest.mark.asyncio
async def test_offline_doctor_does_not_probe_and_summary_does_not_claim_ready(monkeypatch, capsys):
    doctor = importlib.import_module("deepr.cli.commands.doctor")
    probe = Mock(side_effect=AssertionError("offline mode must not make HTTP requests"))
    monkeypatch.setattr("deepr.backends.capacity.observe_local_ollama_generation", probe)
    checks = await doctor.check_local_ollama(skip_connectivity=True)
    assert checks[0].severity == "info"
    assert "Unverified" in checks[0].message
    doctor.print_checks(checks)
    rendered = capsys.readouterr().out
    assert "All good" not in rendered
    assert "local generation is unverified" in rendered
    probe.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("status,expected", [("refused", "error"), ("ready", "ok"), ("unverified", "error")])
async def test_connected_doctor_distinguishes_refusal_unknown_and_success(monkeypatch, status, expected):
    doctor = importlib.import_module("deepr.cli.commands.doctor")
    proof = OllamaGenerationReadiness(status, "Bounded reason", reason="cloud_enabled")
    monkeypatch.setattr("deepr.backends.capacity.observe_local_ollama_generation", lambda: proof)
    checks = await doctor.check_local_ollama(skip_connectivity=False)
    assert checks[0].severity == expected
    assert status in checks[0].message


def test_doctor_skip_command_makes_no_provider_http_calls(monkeypatch):
    doctor = importlib.import_module("deepr.cli.commands.doctor")
    monkeypatch.setattr(httpx, "Client", Mock(side_effect=AssertionError("unexpected HTTP")))
    monkeypatch.setattr(httpx, "AsyncClient", Mock(side_effect=AssertionError("unexpected HTTP")))
    monkeypatch.setattr(doctor, "load_config", lambda: {})
    for name in ["check_api_keys", "check_filesystem", "check_database", "check_deprecated_models"]:
        monkeypatch.setattr(doctor, name, AsyncMock(return_value=[]))
    for name in [
        "check_storage_locations",
        "check_native_instruments",
        "check_spend_integrity",
        "check_mcp_conformance",
        "check_mcp_host_wiring",
    ]:
        monkeypatch.setattr(doctor, name, lambda: [])
    result = CliRunner().invoke(doctor.doctor, ["--skip-connectivity"])
    assert result.exit_code == 0
    assert "Unverified" in result.output
    assert "All good" not in result.output
