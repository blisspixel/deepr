"""Tests for scoped-key enforcement in the MCP HTTP transport."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepr.mcp.request_context import current_mcp_request_identity
from deepr.mcp.security.scoped_keys import RemoteMCPAuditLog, ScopedMCPKeyStore
from deepr.mcp.security.tool_allowlist import ResearchMode
from deepr.mcp.transport.http import HttpMessage, StreamingHttpTransport


def _request(body: dict, token: str):
    req = MagicMock()
    req.headers = {"Authorization": f"Bearer {token}"}
    req.read = AsyncMock(return_value=json.dumps(body).encode("utf-8"))
    req.query = {}
    req.remote = "127.0.0.1"
    return req


class TestStreamingHttpScopedKeys:
    @pytest.mark.asyncio
    async def test_scoped_key_allows_protocol_handshake_without_confirmation(self, tmp_path):
        store = ScopedMCPKeyStore(tmp_path / "keys.json")
        secret, _record = store.create_key("agent", mode=ResearchMode.STANDARD, secret="secret")
        audit = RemoteMCPAuditLog(tmp_path / "audit.jsonl")
        transport = StreamingHttpTransport(scoped_key_store=store, audit_log=audit)
        handler = AsyncMock(return_value=HttpMessage(id="1", result={"ok": True}))
        transport.on_message(handler)

        for method in ("initialize", "tools/list"):
            response = await transport._handle_post(
                _request(
                    {
                        "jsonrpc": "2.0",
                        "id": method,
                        "method": method,
                        "params": {},
                    },
                    secret,
                )
            )

            assert response.status == 200
            assert json.loads(response.text)["result"] == {"ok": True}

        assert handler.await_count == 2
        assert [call.args[0].method for call in handler.await_args_list] == ["initialize", "tools/list"]

    @pytest.mark.asyncio
    async def test_scoped_key_auth_injects_context_and_audits_success(self, tmp_path):
        store = ScopedMCPKeyStore(tmp_path / "keys.json")
        secret, _record = store.create_key("agent", mode=ResearchMode.UNRESTRICTED, secret="secret")
        audit = RemoteMCPAuditLog(tmp_path / "audit.jsonl")
        transport = StreamingHttpTransport(scoped_key_store=store, audit_log=audit)

        async def handler(message: HttpMessage):
            assert isinstance(message.params, dict)
            assert message.params["_scoped_key"]["key_id"] == "agent"
            identity = current_mcp_request_identity()
            assert identity is not None
            assert identity.authentication == "scoped_key"
            assert identity.scoped_key_id == "agent"
            assert identity.peer_is_loopback is True
            return HttpMessage(id=message.id, result={"ok": True})

        transport.on_message(handler)
        response = await transport._handle_post(
            _request(
                {
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "tools/call",
                    "params": {"name": "deepr_status", "arguments": {"trace_id": "trace-1"}},
                },
                secret,
            )
        )

        assert response.status == 200
        assert json.loads(response.text)["result"] == {"ok": True}
        event = audit.read_recent()[0]
        assert event.key_id == "agent"
        assert event.tool == "deepr_status"
        assert event.outcome == "success"
        assert event.trace_id == "trace-1"
        assert current_mcp_request_identity() is None

    @pytest.mark.asyncio
    async def test_legacy_method_uses_canonical_scoped_authorization(self, tmp_path):
        store = ScopedMCPKeyStore(tmp_path / "keys.json")
        secret, _record = store.create_key(
            "agent",
            mode=ResearchMode.UNRESTRICTED,
            expert_allowlist=["alpha"],
            secret="secret",
        )
        audit = RemoteMCPAuditLog(tmp_path / "audit.jsonl")
        transport = StreamingHttpTransport(scoped_key_store=store, audit_log=audit)
        handler = AsyncMock(return_value=HttpMessage(id="1", result={"ok": True}))
        transport.on_message(handler)

        response = await transport._handle_post(
            _request(
                {
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "get_expert_info",
                    "params": {"expert_name": "beta"},
                },
                secret,
            )
        )

        payload = json.loads(response.text)
        assert payload["error"]["data"]["error_code"] == "EXPERT_SCOPE_DENIED"
        handler.assert_not_awaited()
        event = audit.read_recent()[-1]
        assert event.tool == "deepr_get_expert_info"
        assert event.error_code == "EXPERT_SCOPE_DENIED"

    @pytest.mark.asyncio
    async def test_allowed_legacy_method_dispatches_and_audits_canonical_tool(self, tmp_path):
        store = ScopedMCPKeyStore(tmp_path / "keys.json")
        secret, _record = store.create_key(
            "agent",
            mode=ResearchMode.UNRESTRICTED,
            expert_allowlist=["alpha"],
            secret="secret",
        )
        audit = RemoteMCPAuditLog(tmp_path / "audit.jsonl")
        transport = StreamingHttpTransport(scoped_key_store=store, audit_log=audit)

        async def handler(message: HttpMessage):
            assert message.method == "tools/call"
            assert message.params is not None
            assert message.params["name"] == "deepr_get_expert_info"
            assert message.params["arguments"] == {"expert_name": "alpha"}
            return HttpMessage(id=message.id, result={"ok": True})

        transport.on_message(handler)
        response = await transport._handle_post(
            _request(
                {
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "get_expert_info",
                    "params": {"expert_name": "alpha"},
                },
                secret,
            )
        )

        assert json.loads(response.text)["result"] == {"ok": True}
        assert audit.read_recent()[-1].tool == "deepr_get_expert_info"

    @pytest.mark.asyncio
    async def test_legacy_method_without_params_is_canonicalized_before_rate_limit(self, tmp_path):
        store = ScopedMCPKeyStore(tmp_path / "keys.json")
        secret, _record = store.create_key(
            "agent",
            mode=ResearchMode.UNRESTRICTED,
            rate_limit_per_minute=1,
            secret="secret",
        )
        audit = RemoteMCPAuditLog(tmp_path / "audit.jsonl")
        transport = StreamingHttpTransport(scoped_key_store=store, audit_log=audit)

        async def handler(message: HttpMessage):
            assert message.method == "tools/call"
            assert message.params is not None
            assert message.params["name"] == "deepr_list_experts"
            assert message.params["arguments"] == {}
            return HttpMessage(id=message.id, result={"experts": []})

        transport.on_message(handler)
        body = {"jsonrpc": "2.0", "method": "list_experts"}
        first = await transport._handle_post(_request({**body, "id": "1"}, secret))
        second = await transport._handle_post(_request({**body, "id": "2"}, secret))

        assert json.loads(first.text)["result"] == {"experts": []}
        assert json.loads(second.text)["error"]["data"]["error_code"] == "KEY_RATE_LIMIT_EXCEEDED"
        assert [event.tool for event in audit.read_recent()] == [
            "deepr_list_experts",
            "deepr_list_experts",
        ]

    @pytest.mark.asyncio
    async def test_scoped_key_blocks_outside_expert_before_handler(self, tmp_path):
        store = ScopedMCPKeyStore(tmp_path / "keys.json")
        secret, _record = store.create_key(
            "agent",
            mode=ResearchMode.UNRESTRICTED,
            expert_allowlist=["alpha"],
            secret="secret",
        )
        audit = RemoteMCPAuditLog(tmp_path / "audit.jsonl")
        transport = StreamingHttpTransport(scoped_key_store=store, audit_log=audit)
        handler = AsyncMock(return_value=HttpMessage(id="1", result={"ok": True}))
        transport.on_message(handler)

        response = await transport._handle_post(
            _request(
                {
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "tools/call",
                    "params": {
                        "name": "deepr_query_expert",
                        "arguments": {"expert_name": "beta", "_approved": True},
                    },
                },
                secret,
            )
        )

        assert response.status == 200
        payload = json.loads(response.text)
        assert payload["error"]["data"]["error_code"] == "EXPERT_SCOPE_DENIED"
        handler.assert_not_awaited()
        assert audit.read_recent()[0].error_code == "EXPERT_SCOPE_DENIED"

    @pytest.mark.asyncio
    async def test_scoped_key_constrains_consult_auto_selection_before_handler(self, tmp_path):
        store = ScopedMCPKeyStore(tmp_path / "keys.json")
        secret, _record = store.create_key(
            "agent",
            mode=ResearchMode.UNRESTRICTED,
            expert_allowlist=["alpha"],
            budget_limit_usd=0.0,
            secret="secret",
        )
        audit = RemoteMCPAuditLog(tmp_path / "audit.jsonl")
        transport = StreamingHttpTransport(scoped_key_store=store, audit_log=audit)

        async def handler(message: HttpMessage):
            assert isinstance(message.params, dict)
            assert message.params["arguments"]["experts"] == ["alpha"]
            return HttpMessage(id=message.id, result={"ok": True})

        transport.on_message(handler)
        response = await transport._handle_post(
            _request(
                {
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "tools/call",
                    "params": {
                        "name": "deepr_consult_experts",
                        "arguments": {"question": "q", "synthesis_backend": "local", "budget": 0},
                    },
                },
                secret,
            )
        )

        assert response.status == 200
        assert json.loads(response.text)["result"] == {"ok": True}
        event = audit.read_recent()[0]
        assert event.tool == "deepr_consult_experts"
        assert event.expert_names == ("alpha",)

    @pytest.mark.asyncio
    async def test_scoped_key_blocks_over_budget_before_handler(self, tmp_path):
        store = ScopedMCPKeyStore(tmp_path / "keys.json")
        secret, _record = store.create_key(
            "agent", mode=ResearchMode.UNRESTRICTED, budget_limit_usd=1.0, secret="secret"
        )
        audit = RemoteMCPAuditLog(tmp_path / "audit.jsonl")
        context = store.authenticate(secret)
        assert context is not None
        audit.record_tool_call(
            context,
            tool="deepr_query_expert",
            arguments={"expert_name": "alpha"},
            outcome="success",
            cost_usd=0.75,
        )
        transport = StreamingHttpTransport(scoped_key_store=store, audit_log=audit)
        handler = AsyncMock(return_value=HttpMessage(id="1", result={"ok": True}))
        transport.on_message(handler)

        response = await transport._handle_post(
            _request(
                {
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "tools/call",
                    "params": {
                        "name": "deepr_agentic_research",
                        "arguments": {"goal": "research", "budget": 0.50},
                    },
                },
                secret,
            )
        )

        assert response.status == 200
        payload = json.loads(response.text)
        assert payload["error"]["data"]["error_code"] == "KEY_BUDGET_EXCEEDED"
        assert payload["error"]["data"]["remaining_usd"] == 0.25
        handler.assert_not_awaited()
        assert audit.read_recent()[-1].error_code == "KEY_BUDGET_EXCEEDED"

    @pytest.mark.asyncio
    async def test_scoped_key_injects_remaining_budget_when_omitted(self, tmp_path):
        store = ScopedMCPKeyStore(tmp_path / "keys.json")
        secret, _record = store.create_key(
            "agent", mode=ResearchMode.UNRESTRICTED, budget_limit_usd=1.0, secret="secret"
        )
        audit = RemoteMCPAuditLog(tmp_path / "audit.jsonl")
        context = store.authenticate(secret)
        assert context is not None
        audit.record_tool_call(
            context,
            tool="deepr_query_expert",
            arguments={"expert_name": "alpha"},
            outcome="success",
            cost_usd=0.25,
        )
        transport = StreamingHttpTransport(scoped_key_store=store, audit_log=audit)

        async def handler(message: HttpMessage):
            assert isinstance(message.params, dict)
            arguments = message.params["arguments"]
            assert arguments["budget"] == 0.75
            return HttpMessage(id=message.id, result={"ok": True})

        transport.on_message(handler)
        response = await transport._handle_post(
            _request(
                {
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "tools/call",
                    "params": {
                        "name": "deepr_agentic_research",
                        "arguments": {"goal": "research"},
                    },
                },
                secret,
            )
        )

        assert response.status == 200
        assert json.loads(response.text)["result"] == {"ok": True}

    @pytest.mark.asyncio
    async def test_scoped_key_audit_records_response_cost(self, tmp_path):
        store = ScopedMCPKeyStore(tmp_path / "keys.json")
        secret, _record = store.create_key(
            "agent", mode=ResearchMode.UNRESTRICTED, budget_limit_usd=1.0, secret="secret"
        )
        audit = RemoteMCPAuditLog(tmp_path / "audit.jsonl")
        transport = StreamingHttpTransport(scoped_key_store=store, audit_log=audit)

        async def handler(message: HttpMessage):
            payload = {"answer": "ok", "cost": 0.12}
            return HttpMessage(
                id=message.id,
                result={"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False},
            )

        transport.on_message(handler)
        response = await transport._handle_post(
            _request(
                {
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "tools/call",
                    "params": {
                        "name": "deepr_query_expert",
                        "arguments": {"expert_name": "alpha", "question": "why?", "agentic": True, "budget": 0.50},
                    },
                },
                secret,
            )
        )

        assert response.status == 200
        event = audit.read_recent()[-1]
        assert event.outcome == "success"
        assert event.cost_usd == 0.12
        assert audit.total_cost_for_key("agent") == 0.12

    @pytest.mark.asyncio
    async def test_scoped_key_audit_records_structured_tool_error(self, tmp_path):
        store = ScopedMCPKeyStore(tmp_path / "keys.json")
        secret, _record = store.create_key("agent", mode=ResearchMode.UNRESTRICTED, secret="secret")
        audit = RemoteMCPAuditLog(tmp_path / "audit.jsonl")
        transport = StreamingHttpTransport(scoped_key_store=store, audit_log=audit)

        async def handler(message: HttpMessage):
            payload = {
                "schema_version": "deepr-expert-conversation-error-v1",
                "kind": "deepr.expert.conversation_error",
                "error": {"code": "version_conflict", "safe_message": "Fetch current state."},
            }
            return HttpMessage(
                id=message.id,
                result={
                    "content": [{"type": "text", "text": json.dumps(payload)}],
                    "isError": True,
                },
            )

        transport.on_message(handler)
        response = await transport._handle_post(
            _request(
                {
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "tools/call",
                    "params": {
                        "name": "deepr_get_expert_conversation",
                        "arguments": {"conversation_id": "conv_missing"},
                    },
                },
                secret,
            )
        )

        assert response.status == 200
        event = audit.read_recent()[-1]
        assert event.outcome == "error"
        assert event.error_code == "version_conflict"
        assert event.cost_usd is None

    @pytest.mark.asyncio
    async def test_scoped_key_blocks_over_rate_limit_before_handler(self, tmp_path):
        store = ScopedMCPKeyStore(tmp_path / "keys.json")
        secret, _record = store.create_key(
            "agent",
            mode=ResearchMode.UNRESTRICTED,
            rate_limit_per_minute=1,
            secret="secret",
        )
        audit = RemoteMCPAuditLog(tmp_path / "audit.jsonl")
        transport = StreamingHttpTransport(scoped_key_store=store, audit_log=audit)
        handler = AsyncMock(return_value=HttpMessage(id="1", result={"ok": True}))
        transport.on_message(handler)

        first = await transport._handle_post(
            _request(
                {
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "tools/call",
                    "params": {"name": "deepr_status", "arguments": {"trace_id": "trace-1"}},
                },
                secret,
            )
        )
        second = await transport._handle_post(
            _request(
                {
                    "jsonrpc": "2.0",
                    "id": "2",
                    "method": "tools/call",
                    "params": {"name": "deepr_status", "arguments": {"trace_id": "trace-2"}},
                },
                secret,
            )
        )

        assert first.status == 200
        assert second.status == 200
        payload = json.loads(second.text)
        assert payload["error"]["data"]["error_code"] == "KEY_RATE_LIMIT_EXCEEDED"
        assert payload["error"]["data"]["limit_per_minute"] == 1
        assert payload["error"]["data"]["calls_in_window"] == 1
        assert handler.await_count == 1
        assert audit.read_recent()[-1].error_code == "KEY_RATE_LIMIT_EXCEEDED"

    @pytest.mark.asyncio
    async def test_concurrent_transports_reserve_budget_before_dispatch(self, tmp_path):
        store = ScopedMCPKeyStore(tmp_path / "keys.json")
        secret, _record = store.create_key(
            "agent",
            mode=ResearchMode.UNRESTRICTED,
            budget_limit_usd=0.02,
            secret="secret",
        )
        audit = RemoteMCPAuditLog(tmp_path / "audit.jsonl")
        first_transport = StreamingHttpTransport(scoped_key_store=store, audit_log=audit)
        second_transport = StreamingHttpTransport(scoped_key_store=store, audit_log=audit)
        entered = asyncio.Event()
        release = asyncio.Event()

        async def held_handler(message: HttpMessage):
            entered.set()
            await release.wait()
            return HttpMessage(id=message.id, result={"verdict": "supported"})

        first_transport.on_message(held_handler)
        second_handler = AsyncMock(return_value=HttpMessage(id="2", result={"verdict": "supported"}))
        second_transport.on_message(second_handler)
        body = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "deepr_expert_validate",
                "arguments": {"expert_name": "alpha", "claim": "claim", "_approved": True},
            },
        }

        first_task = asyncio.create_task(first_transport._handle_post(_request({**body, "id": "1"}, secret)))
        await entered.wait()
        second = await second_transport._handle_post(_request({**body, "id": "2"}, secret))

        assert json.loads(second.text)["error"]["data"]["error_code"] == "KEY_BUDGET_EXCEEDED"
        second_handler.assert_not_awaited()
        release.set()
        first = await first_task
        assert json.loads(first.text)["result"] == {"verdict": "supported"}
        assert audit.total_cost_for_key("agent") == 0.02

    @pytest.mark.asyncio
    async def test_concurrent_transports_reserve_rate_slot_before_dispatch(self, tmp_path):
        store = ScopedMCPKeyStore(tmp_path / "keys.json")
        secret, _record = store.create_key(
            "agent",
            mode=ResearchMode.UNRESTRICTED,
            rate_limit_per_minute=1,
            secret="secret",
        )
        audit = RemoteMCPAuditLog(tmp_path / "audit.jsonl")
        first_transport = StreamingHttpTransport(scoped_key_store=store, audit_log=audit)
        second_transport = StreamingHttpTransport(scoped_key_store=store, audit_log=audit)
        entered = asyncio.Event()
        release = asyncio.Event()

        async def held_handler(message: HttpMessage):
            entered.set()
            await release.wait()
            return HttpMessage(id=message.id, result={"ok": True})

        first_transport.on_message(held_handler)
        second_handler = AsyncMock(return_value=HttpMessage(id="2", result={"ok": True}))
        second_transport.on_message(second_handler)
        body = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "deepr_status", "arguments": {}},
        }

        first_task = asyncio.create_task(first_transport._handle_post(_request({**body, "id": "1"}, secret)))
        await entered.wait()
        second = await second_transport._handle_post(_request({**body, "id": "2"}, secret))

        assert json.loads(second.text)["error"]["data"]["error_code"] == "KEY_RATE_LIMIT_EXCEEDED"
        second_handler.assert_not_awaited()
        release.set()
        first = await first_task
        assert json.loads(first.text)["result"] == {"ok": True}

    @pytest.mark.asyncio
    async def test_resource_methods_consume_rate_and_write_method_audit(self, tmp_path):
        store = ScopedMCPKeyStore(tmp_path / "keys.json")
        secret, _record = store.create_key(
            "agent",
            mode=ResearchMode.READ_ONLY,
            rate_limit_per_minute=1,
            secret="secret",
        )
        audit = RemoteMCPAuditLog(tmp_path / "audit.jsonl")
        transport = StreamingHttpTransport(scoped_key_store=store, audit_log=audit)
        handler = AsyncMock(return_value=HttpMessage(id="1", result={"resources": []}))
        transport.on_message(handler)

        first = await transport._handle_post(
            _request(
                {"jsonrpc": "2.0", "id": "1", "method": "resources/list"},
                secret,
            )
        )
        second = await transport._handle_post(
            _request(
                {
                    "jsonrpc": "2.0",
                    "id": "2",
                    "method": "resources/read",
                    "params": {"uri": "deepr://experts/alpha/beliefs"},
                },
                secret,
            )
        )

        assert json.loads(first.text)["result"] == {"resources": []}
        assert json.loads(second.text)["error"]["data"]["error_code"] == "KEY_RATE_LIMIT_EXCEEDED"
        assert handler.await_count == 1
        events = audit.read_recent()
        assert [event.tool for event in events] == ["resources/list", "resources/read"]

    @pytest.mark.asyncio
    async def test_scoped_notification_settles_admission_once(self, tmp_path):
        store = ScopedMCPKeyStore(tmp_path / "keys.json")
        secret, _record = store.create_key("agent", secret="secret")
        audit = RemoteMCPAuditLog(tmp_path / "audit.jsonl")
        transport = StreamingHttpTransport(scoped_key_store=store, audit_log=audit)
        transport.on_message(AsyncMock(return_value=None))

        response = await transport._handle_post(
            _request(
                {"jsonrpc": "2.0", "method": "resources/list", "params": {}},
                secret,
            )
        )

        assert response.status == 204
        assert [event.tool for event in audit.read_recent()] == ["resources/list"]

    @pytest.mark.asyncio
    async def test_handler_failure_conservatively_settles_budget_hold(self, tmp_path):
        store = ScopedMCPKeyStore(tmp_path / "keys.json")
        secret, _record = store.create_key(
            "agent",
            mode=ResearchMode.UNRESTRICTED,
            budget_limit_usd=0.02,
            secret="secret",
        )
        audit = RemoteMCPAuditLog(tmp_path / "audit.jsonl")
        transport = StreamingHttpTransport(scoped_key_store=store, audit_log=audit)
        handler = AsyncMock(side_effect=RuntimeError("handler failed after dispatch"))
        transport.on_message(handler)
        body = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "deepr_expert_validate",
                "arguments": {"expert_name": "alpha", "claim": "claim", "_approved": True},
            },
        }

        first = await transport._handle_post(_request({**body, "id": "1"}, secret))
        second = await transport._handle_post(_request({**body, "id": "2"}, secret))

        assert first.status == 500
        assert json.loads(second.text)["error"]["data"]["error_code"] == "KEY_BUDGET_EXCEEDED"
        assert handler.await_count == 1
        assert audit.total_cost_for_key("agent") == 0.02
        assert audit.read_recent()[0].error_code == "MCP_HANDLER_FAILED"

    @pytest.mark.asyncio
    async def test_public_bind_with_active_scoped_key_succeeds_without_shared_token(self, tmp_path):
        store = ScopedMCPKeyStore(tmp_path / "keys.json")
        store.create_key("agent", secret="secret")
        transport = StreamingHttpTransport(host="0.0.0.0", scoped_key_store=store)

        with (
            patch("deepr.mcp.transport.http.web.Application") as app_cls,
            patch("deepr.mcp.transport.http.web.AppRunner") as runner_cls,
            patch("deepr.mcp.transport.http.web.TCPSite") as site_cls,
        ):
            app = MagicMock(router=MagicMock())
            app_cls.return_value = app
            runner = MagicMock(setup=AsyncMock(), cleanup=AsyncMock())
            runner_cls.return_value = runner
            site = MagicMock(start=AsyncMock())
            site_cls.return_value = site
            await transport.start()
            assert transport.is_running
            await transport.stop()

    @pytest.mark.asyncio
    async def test_public_bind_with_empty_scoped_store_is_refused(self, tmp_path):
        store = ScopedMCPKeyStore(tmp_path / "keys.json")
        transport = StreamingHttpTransport(host="0.0.0.0", scoped_key_store=store)

        with pytest.raises(RuntimeError, match="scoped key"):
            await transport.start()
