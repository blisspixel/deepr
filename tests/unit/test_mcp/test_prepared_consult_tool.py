"""Prepared MCP admission and error privacy without provider or source I/O."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from deepr.mcp.consult_tool import CONSULT_EXPERTS_INPUT_SCHEMA, consult_experts_tool
from deepr.mcp.request_context import MCPRequestIdentity, bind_mcp_request_identity, reset_mcp_request_identity


def request():
    return {
        "schema_version": "deepr-python-preparation-request-v1",
        "enabled": True,
        "request_id": "prepared_request_0001",
        "environment": {"interpreter_version": "3.12", "platform": "fixture"},
        "packages": [{"name": "fixture", "version": "1.0"}],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("loopback", [True, False])
async def test_unauthenticated_http_refused_before_profile_or_transaction(monkeypatch, loopback):
    load = Mock(side_effect=AssertionError("private profile lookup"))
    transaction = AsyncMock(side_effect=AssertionError("transaction"))
    monkeypatch.setattr("deepr.experts.profile_store.ExpertStore.load", load)
    monkeypatch.setattr("deepr.mcp.consult_tool.execute_consult_transaction", transaction)
    token = bind_mcp_request_identity(MCPRequestIdentity.http_unauthenticated(peer_is_loopback=loopback))
    try:
        result = await consult_experts_tool(question="private", experts=["Alias"], preparation=request())
    finally:
        reset_mcp_request_identity(token)
    assert result["error_code"] == "PREPARATION_REFUSED"
    load.assert_not_called()
    transaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_canonical_alias_owner_admitted_without_migration_and_private_exception_redacted(monkeypatch, tmp_path):
    load = Mock(return_value=SimpleNamespace(name="Canonical"))
    transaction = AsyncMock(side_effect=RuntimeError("PRIVATE_ERROR"))
    monkeypatch.setattr("deepr.experts.profile_store.ExpertStore.load", load)
    monkeypatch.setattr("deepr.mcp.consult_tool.execute_consult_transaction", transaction)
    monkeypatch.setenv("DEEPR_DATA_DIR", str(tmp_path))
    identity = MCPRequestIdentity.http_scoped_key(
        key_id="server-key", expert_allowlist=("Canonical",), peer_is_loopback=True
    )
    token = bind_mcp_request_identity(identity)
    try:
        result = await consult_experts_tool(question="private", experts=["Alias"], preparation=request())
    finally:
        reset_mcp_request_identity(token)
    load.assert_called_once_with("Alias", persist_migration=False)
    kwargs = transaction.call_args.kwargs
    assert kwargs["requested_experts"] == ["Canonical"]
    assert kwargs["preparation"].root == tmp_path / "preparation"
    assert "PRIVATE_ERROR" not in str(result) and result["error_code"] == "PREPARATION_FAILED"


@pytest.mark.asyncio
@pytest.mark.parametrize("patch", [{"owner": "forged"}, {"root": "private"}, {"enabled": False}])
async def test_public_preparation_cannot_forge_internal_authority(monkeypatch, patch):
    load = Mock(side_effect=AssertionError("profile lookup"))
    monkeypatch.setattr("deepr.experts.profile_store.ExpertStore.load", load)
    token = bind_mcp_request_identity(MCPRequestIdentity.local_stdio())
    try:
        result = await consult_experts_tool(question="private", experts=["Alias"], preparation={**request(), **patch})
    finally:
        reset_mcp_request_identity(token)
    assert result["error_code"] == "PREPARATION_REFUSED"
    load.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("preparation", [None, False, [], "private"])
async def test_explicit_invalid_preparation_never_becomes_ordinary_consult(monkeypatch, preparation):
    transaction = AsyncMock()
    monkeypatch.setattr("deepr.mcp.consult_tool.execute_consult_transaction", transaction)
    result = await consult_experts_tool(question="private", experts=["Alias"], preparation=preparation)
    assert result["error_code"] == "PREPARATION_REFUSED"
    transaction.assert_not_awaited()


def test_preparation_schema_has_resolvable_definitions_and_rejects_extra_authority():
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(CONSULT_EXPERTS_INPUT_SCHEMA)
    assert not list(validator.iter_errors({"question": "q", "preparation": request()}))
    assert list(validator.iter_errors({"question": "q", "preparation": {**request(), "owner": "forged"}}))
    assert list(validator.iter_errors({"question": "q", "preparation": {**request(), "enabled": False}}))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "options",
    [{"experts": []}, {"experts": ["A", "B"]}, {"budget": 1}, {"synthesis_backend": "plan", "plan": "fixture"}],
)
async def test_prepared_capacity_and_explicit_roster_refused_before_profile(monkeypatch, options):
    load = Mock(side_effect=AssertionError("profile lookup"))
    monkeypatch.setattr("deepr.experts.profile_store.ExpertStore.load", load)
    token = bind_mcp_request_identity(MCPRequestIdentity.local_stdio())
    try:
        result = await consult_experts_tool(question="private", preparation=request(), **{"experts": ["A"], **options})
    finally:
        reset_mcp_request_identity(token)
    assert result["error_code"] == "PREPARATION_REFUSED"
    load.assert_not_called()


@pytest.mark.asyncio
async def test_canonical_expert_outside_allowlist_never_starts_transaction(monkeypatch):
    monkeypatch.setattr(
        "deepr.experts.profile_store.ExpertStore.load", Mock(return_value=SimpleNamespace(name="Denied"))
    )
    transaction = AsyncMock()
    monkeypatch.setattr("deepr.mcp.consult_tool.execute_consult_transaction", transaction)
    token = bind_mcp_request_identity(
        MCPRequestIdentity.http_scoped_key(key_id="key", expert_allowlist=("Allowed",), peer_is_loopback=True)
    )
    try:
        result = await consult_experts_tool(question="private", experts=["Alias"], preparation=request())
    finally:
        reset_mcp_request_identity(token)
    assert result["error_code"] == "PREPARATION_REFUSED"
    transaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_ordinary_consult_does_not_forward_preparation(monkeypatch):
    transaction = AsyncMock(return_value={"answer": "fixture"})
    monkeypatch.setattr("deepr.mcp.consult_tool.execute_consult_transaction", transaction)
    assert await consult_experts_tool(question="q", experts=["A"]) == {"answer": "fixture"}
    assert "preparation" not in transaction.call_args.kwargs


@pytest.mark.asyncio
async def test_prepared_backend_refusal_has_fixed_private_error(monkeypatch):
    from deepr.experts.consult import ConsultBackendError

    monkeypatch.setattr("deepr.experts.profile_store.ExpertStore.load", Mock(return_value=SimpleNamespace(name="A")))
    monkeypatch.setattr(
        "deepr.mcp.consult_tool.execute_consult_transaction",
        AsyncMock(side_effect=ConsultBackendError("PRIVATE_BACKEND")),
    )
    token = bind_mcp_request_identity(MCPRequestIdentity.local_stdio())
    try:
        result = await consult_experts_tool(question="private", experts=["A"], preparation=request())
    finally:
        reset_mcp_request_identity(token)
    assert result["error_code"] == "PREPARATION_BACKEND_UNAVAILABLE" and "PRIVATE_BACKEND" not in str(result)


@pytest.mark.asyncio
async def test_real_stdio_method_binding_resets_identity_after_failure(monkeypatch):
    from deepr.mcp import protocol_dispatch
    from deepr.mcp.request_context import current_mcp_request_identity

    async def dispatch(server, method, params):
        identity = current_mcp_request_identity()
        assert identity is not None and identity.transport == "stdio" and identity.authenticated
        raise RuntimeError("fixture")

    monkeypatch.setattr(protocol_dispatch, "dispatch_protocol_method", dispatch)
    assert current_mcp_request_identity() is None
    with pytest.raises(RuntimeError, match="fixture"):
        await protocol_dispatch.bind_stdio_method(SimpleNamespace(), "tools/call")({})
    assert current_mcp_request_identity() is None
