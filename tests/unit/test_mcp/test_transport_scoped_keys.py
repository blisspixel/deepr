"""Tests for scoped-key enforcement in the MCP HTTP transport."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepr.mcp.security.scoped_keys import RemoteMCPAuditLog, ScopedMCPKeyStore
from deepr.mcp.security.tool_allowlist import ResearchMode
from deepr.mcp.transport.http import HttpMessage, StreamingHttpTransport


def _request(body: dict, token: str):
    req = MagicMock()
    req.headers = {"Authorization": f"Bearer {token}"}
    req.read = AsyncMock(return_value=json.dumps(body).encode("utf-8"))
    req.query = {}
    return req


class TestStreamingHttpScopedKeys:
    @pytest.mark.asyncio
    async def test_scoped_key_auth_injects_context_and_audits_success(self, tmp_path):
        store = ScopedMCPKeyStore(tmp_path / "keys.json")
        secret, _record = store.create_key("agent", mode=ResearchMode.UNRESTRICTED, secret="secret")
        audit = RemoteMCPAuditLog(tmp_path / "audit.jsonl")
        transport = StreamingHttpTransport(scoped_key_store=store, audit_log=audit)

        async def handler(message: HttpMessage):
            assert isinstance(message.params, dict)
            assert message.params["_scoped_key"]["key_id"] == "agent"
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
