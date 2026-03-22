"""Tests for structured audit log."""

import pytest

from deepr.security.audit import AuditEvent, AuditEventType, AuditLog


@pytest.fixture
def audit(tmp_path):
    return AuditLog(log_path=tmp_path / "audit.jsonl")


def _make_event(event_type=AuditEventType.TOOL_EXECUTED, actor="test-user", **kwargs):
    return AuditEvent(event_type=event_type, actor=actor, resource="test-tool", action="test", **kwargs)


class TestAuditEvent:
    def test_to_dict(self):
        ev = _make_event(details={"cost": 0.50})
        d = ev.to_dict()
        assert d["event_type"] == "tool_executed"
        assert d["actor"] == "test-user"
        assert d["details"]["cost"] == 0.50

    def test_roundtrip(self):
        original = _make_event(session_id="s1", trace_id="t1")
        restored = AuditEvent.from_dict(original.to_dict())
        assert restored.event_type == AuditEventType.TOOL_EXECUTED
        assert restored.session_id == "s1"
        assert restored.trace_id == "t1"


class TestAuditLog:
    def test_record_and_query(self, audit):
        audit.record(_make_event())
        audit.record(_make_event(event_type=AuditEventType.PERMISSION_DENIED, outcome="denied"))

        events = audit.query()
        assert len(events) == 2

    def test_query_by_type(self, audit):
        audit.record(_make_event(event_type=AuditEventType.TOOL_EXECUTED))
        audit.record(_make_event(event_type=AuditEventType.PERMISSION_DENIED))
        audit.record(_make_event(event_type=AuditEventType.TOOL_EXECUTED))

        events = audit.query(event_type=AuditEventType.TOOL_EXECUTED)
        assert len(events) == 2

    def test_query_by_actor(self, audit):
        audit.record(_make_event(actor="alice"))
        audit.record(_make_event(actor="bob"))

        events = audit.query(actor="alice")
        assert len(events) == 1

    def test_query_by_outcome(self, audit):
        audit.record(_make_event(outcome="success"))
        audit.record(_make_event(outcome="denied"))
        audit.record(_make_event(outcome="denied"))

        events = audit.query(outcome="denied")
        assert len(events) == 2

    def test_limit(self, audit):
        for _ in range(10):
            audit.record(_make_event())

        events = audit.query(limit=3)
        assert len(events) == 3

    def test_empty_log(self, audit):
        assert audit.query() == []
        assert audit.count_by_type() == {}
        assert audit.recent_denials() == []


class TestAuditAnalytics:
    def test_count_by_type(self, audit):
        audit.record(_make_event(event_type=AuditEventType.TOOL_EXECUTED))
        audit.record(_make_event(event_type=AuditEventType.TOOL_EXECUTED))
        audit.record(_make_event(event_type=AuditEventType.PERMISSION_DENIED))

        counts = audit.count_by_type()
        assert counts["tool_executed"] == 2
        assert counts["permission_denied"] == 1

    def test_recent_denials(self, audit):
        audit.record(_make_event(outcome="success"))
        audit.record(_make_event(event_type=AuditEventType.PERMISSION_DENIED, outcome="denied"))
        audit.record(_make_event(event_type=AuditEventType.BUDGET_EXCEEDED, outcome="denied"))

        denials = audit.recent_denials()
        assert len(denials) == 2
        assert all(d.outcome == "denied" for d in denials)

    def test_health(self, audit):
        audit.record(_make_event())
        h = audit.health()
        assert h["exists"] is True
        assert h["event_count"] == 1


class TestAuditEventTypes:
    def test_all_types_have_values(self):
        """All event types should be string-valued."""
        for evt in AuditEventType:
            assert isinstance(evt.value, str)
            assert len(evt.value) > 0

    def test_key_types_exist(self):
        assert AuditEventType.PERMISSION_DENIED
        assert AuditEventType.TOOL_EXECUTED
        assert AuditEventType.BUDGET_EXCEEDED
        assert AuditEventType.ANOMALY_DETECTED
