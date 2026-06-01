"""Tests for deepr.experts.health_check.ExpertHealthChecker.

The health checker is a read-side, cost-$0 audit. These tests assert it:
- composes the existing read-side primitives without any provider call,
- maps each check onto the right severity and the right recommended action,
- rolls findings up into the overall status correctly,
- serializes to a stable dict for MCP/JSON consumers.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from deepr.core.contracts import Claim, ExpertManifest, Gap, Source, TrustClass
from deepr.experts.approval import ApprovalTier
from deepr.experts.beliefs import Belief
from deepr.experts.health_check import (
    ExpertHealthChecker,
    HealthReport,
    _approval_tier_for_cost,
)


def _claim(statement: str, sourced: bool = True, confidence: float = 0.8) -> Claim:
    sources = [Source.create(title="src", trust_class=TrustClass.TERTIARY)] if sourced else []
    return Claim(id=statement[:12], statement=statement, domain="d", confidence=confidence, sources=sources)


def _profile(
    *,
    freshness: dict | None = None,
    claims: list[Claim] | None = None,
    gaps: list[Gap] | None = None,
    documents: int = 0,
) -> MagicMock:
    prof = MagicMock()
    prof.name = "Test Expert"
    prof.domain = "d"
    prof.total_documents = documents
    prof.source_files = []
    prof.research_jobs = []
    prof.get_staleness_details.return_value = freshness or {
        "freshness_status": "fresh",
        "age_days": 1,
        "threshold_days": 90,
        "estimated_refresh_cost": 0.5,
        "refresh_command": "deepr expert refresh Test Expert --budget 0.50",
    }
    prof.get_manifest.return_value = ExpertManifest(
        expert_name="Test Expert",
        domain="d",
        claims=claims if claims is not None else [],
        gaps=gaps if gaps is not None else [],
    )
    return prof


def _run(monkeypatch, profile, beliefs: list[Belief] | None = None) -> HealthReport:
    # _load_beliefs reads the on-disk BeliefStore; stub it so the audit is
    # fully deterministic and never touches the filesystem.
    monkeypatch.setattr("deepr.experts.health_check._load_beliefs", lambda p: beliefs or [])
    return ExpertHealthChecker(profile).run()


def _finding(report: HealthReport, category: str):
    return next(f for f in report.findings if f.category == category)


def _action(report: HealthReport, category: str):
    return next((a for a in report.actions if a.category == category), None)


# --------------------------------------------------------------------------- #
# Approval-tier mapping
# --------------------------------------------------------------------------- #


class TestApprovalTierForCost:
    def test_free_is_auto(self):
        assert _approval_tier_for_cost(0.0) == ApprovalTier.AUTO_APPROVE.value

    def test_modest_is_notify(self):
        assert _approval_tier_for_cost(0.5) == ApprovalTier.NOTIFY.value

    def test_over_a_dollar_is_confirm(self):
        assert _approval_tier_for_cost(1.01) == ApprovalTier.CONFIRM.value


# --------------------------------------------------------------------------- #
# Individual checks
# --------------------------------------------------------------------------- #


class TestFreshness:
    def test_stale_is_warning_with_refresh_action(self, monkeypatch):
        prof = _profile(
            freshness={
                "freshness_status": "stale",
                "age_days": 200,
                "threshold_days": 90,
                "estimated_refresh_cost": 0.5,
                "refresh_command": "deepr expert refresh Test Expert --budget 0.50",
            }
        )
        report = _run(monkeypatch, prof)
        assert _finding(report, "freshness").severity == "warning"
        action = _action(report, "freshness")
        assert action is not None
        assert action.estimated_cost == 0.5
        assert action.approval_tier == ApprovalTier.NOTIFY.value

    def test_incomplete_is_critical(self, monkeypatch):
        prof = _profile(
            freshness={
                "freshness_status": "incomplete",
                "estimated_refresh_cost": 0.5,
                "refresh_command": "deepr expert learn Test Expert --budget 5",
            }
        )
        report = _run(monkeypatch, prof)
        assert _finding(report, "freshness").severity == "critical"
        assert report.status == "critical"

    def test_fresh_emits_no_action(self, monkeypatch):
        report = _run(monkeypatch, _profile())
        assert _finding(report, "freshness").severity == "ok"
        assert _action(report, "freshness") is None


class TestContradictions:
    def test_detects_opposed_beliefs(self, monkeypatch):
        beliefs = [
            Belief(claim="Rust is memory safe by default guaranteed", domain="d", confidence=0.8),
            Belief(claim="Rust is not memory safe by default", domain="d", confidence=0.8),
        ]
        report = _run(monkeypatch, _profile(), beliefs)
        finding = _finding(report, "contradictions")
        assert finding.severity == "warning"
        assert finding.detail["count"] == 1
        action = _action(report, "contradictions")
        assert action is not None
        assert "resolve-conflicts" in action.command

    def test_no_beliefs_is_ok(self, monkeypatch):
        report = _run(monkeypatch, _profile(), [])
        assert _finding(report, "contradictions").severity == "ok"
        assert _action(report, "contradictions") is None


class TestProvenance:
    def test_unsourced_claims_flagged(self, monkeypatch):
        claims = [_claim("X is true", sourced=True), _claim("Y is true", sourced=False)]
        report = _run(monkeypatch, _profile(claims=claims))
        finding = _finding(report, "provenance")
        assert finding.severity == "warning"
        assert finding.detail["unsourced_count"] == 1
        assert finding.detail["total_claims"] == 2
        # Provenance gaps are a review signal, not an automated paid fix.
        assert _action(report, "provenance") is None

    def test_all_sourced_is_ok(self, monkeypatch):
        claims = [_claim("X is true", sourced=True)]
        report = _run(monkeypatch, _profile(claims=claims))
        assert _finding(report, "provenance").severity == "ok"


class TestStaleBeliefs:
    def test_decayed_beliefs_flagged(self, monkeypatch):
        beliefs = [Belief(claim="low confidence belief", domain="d", confidence=0.05)]
        report = _run(monkeypatch, _profile(), beliefs)
        finding = _finding(report, "stale_beliefs")
        assert finding.severity == "warning"
        assert finding.detail["count"] == 1

    def test_confident_beliefs_ok(self, monkeypatch):
        beliefs = [Belief(claim="solid belief", domain="d", confidence=0.95)]
        report = _run(monkeypatch, _profile(), beliefs)
        assert _finding(report, "stale_beliefs").severity == "ok"


class TestGapBacklog:
    def test_large_backlog_is_warning(self, monkeypatch):
        gaps = [Gap.create(topic=f"gap {i}", priority=3) for i in range(6)]
        report = _run(monkeypatch, _profile(gaps=gaps))
        finding = _finding(report, "gaps")
        assert finding.severity == "warning"
        action = _action(report, "gaps")
        assert action is not None
        assert "fill-gaps" in action.command

    def test_small_backlog_is_info(self, monkeypatch):
        gaps = [Gap.create(topic="one gap", priority=3)]
        report = _run(monkeypatch, _profile(gaps=gaps))
        assert _finding(report, "gaps").severity == "info"

    def test_no_gaps_is_ok(self, monkeypatch):
        report = _run(monkeypatch, _profile(gaps=[]))
        assert _finding(report, "gaps").severity == "ok"
        assert _action(report, "gaps") is None


class TestCoverage:
    def test_documents_without_claims_flagged(self, monkeypatch):
        report = _run(monkeypatch, _profile(documents=5, claims=[]))
        finding = _finding(report, "coverage")
        assert finding.severity == "warning"
        action = _action(report, "coverage")
        assert action is not None
        assert "--synthesize" in action.command

    def test_documents_with_claims_ok(self, monkeypatch):
        report = _run(monkeypatch, _profile(documents=5, claims=[_claim("X")]))
        assert _finding(report, "coverage").severity == "ok"


# --------------------------------------------------------------------------- #
# Roll-up + serialization
# --------------------------------------------------------------------------- #


class TestReport:
    def test_clean_expert_is_healthy(self, monkeypatch):
        report = _run(monkeypatch, _profile(claims=[_claim("X")], documents=1), [])
        assert report.status == "healthy"
        # Every check still produces a finding even when all are ok.
        assert {f.category for f in report.findings} == {
            "freshness",
            "contradictions",
            "provenance",
            "stale_beliefs",
            "gaps",
            "coverage",
        }

    def test_findings_sorted_by_severity_desc(self, monkeypatch):
        prof = _profile(
            freshness={
                "freshness_status": "incomplete",
                "estimated_refresh_cost": 0.5,
                "refresh_command": "x",
            },
            claims=[_claim("X")],
            documents=1,
        )
        report = _run(monkeypatch, prof)
        severities = [f.severity for f in report.findings]
        order = {"critical": 3, "warning": 2, "info": 1, "ok": 0}
        assert severities == sorted(severities, key=lambda s: order[s], reverse=True)

    def test_to_dict_is_serializable(self, monkeypatch):
        report = _run(monkeypatch, _profile(claims=[_claim("X")], documents=1), [])
        d = report.to_dict()
        assert d["expert_name"] == "Test Expert"
        assert d["status"] in {"healthy", "needs_attention", "critical"}
        assert isinstance(d["findings"], list) and d["findings"]
        assert all({"category", "severity", "summary", "detail"} <= set(f) for f in d["findings"])
        assert "generated_at" in d


# --------------------------------------------------------------------------- #
# Cost discipline: the audit must never trigger a provider call.
# --------------------------------------------------------------------------- #


class TestNoProviderCall:
    def test_run_makes_no_llm_call(self, monkeypatch):
        # If the audit ever reached the paid LLM contradiction path, this would
        # raise instead of returning a report.
        import deepr.experts.conflict_resolver as cr

        async def _boom(*a, **k):  # pragma: no cover - must never be called
            raise AssertionError("health-check must not make a paid LLM call")

        monkeypatch.setattr(cr.ConflictResolver, "_llm_detect_contradictions", _boom)
        beliefs = [
            Belief(claim="A is not true here", domain="d", confidence=0.8),
            Belief(claim="A is true here indeed", domain="d", confidence=0.8),
        ]
        report = _run(monkeypatch, _profile(), beliefs)
        assert isinstance(report, HealthReport)
