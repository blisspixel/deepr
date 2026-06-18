"""Tests for normalized research-backend profiles."""

from __future__ import annotations

from deepr.backends.capacity import BackendKind, CapacitySource, CostModel
from deepr.backends.research_backend import (
    ResearchBackend,
    backend_from_capacity_source,
    discover_research_backends,
)


class TestResearchBackend:
    def test_capacity_source_normalizes_to_backend(self):
        source = CapacitySource(
            name="Plan CLI (plan)",
            kind=BackendKind.PLAN_QUOTA,
            cost_model=CostModel.CREDIT_POOL,
            available=True,
            detail="installed",
            backend_id="plan",
        )

        backend = backend_from_capacity_source(source)

        assert backend.backend_id == "plan"
        assert backend.name == "Plan CLI (plan)"
        assert backend.requires_quota_ledger is True
        assert backend.allow_paid_fallback is False
        assert backend.is_owned_or_prepaid
        assert not backend.is_metered
        assert backend.metadata["marginal_cost"] == "quota (prepaid)"

    def test_missing_source_backend_id_falls_back_to_slug(self):
        source = CapacitySource(
            name="Local Runner",
            kind=BackendKind.LOCAL,
            cost_model=CostModel.OWNED_HARDWARE,
            available=False,
        )

        backend = backend_from_capacity_source(source)

        assert backend.backend_id == "local-runner"

    def test_metered_backend_is_marked_last_resort(self):
        backend = ResearchBackend(
            backend_id="openai",
            name="OpenAI",
            kind=BackendKind.API_METERED,
            cost_model=CostModel.METERED,
            available=True,
        )

        assert backend.is_metered
        assert not backend.is_owned_or_prepaid
        assert backend.supports_task("sync")

    def test_task_classes_restrict_when_present(self):
        backend = ResearchBackend(
            backend_id="ollama",
            name="Ollama",
            kind=BackendKind.LOCAL,
            cost_model=CostModel.OWNED_HARDWARE,
            available=True,
            task_classes=("sync",),
        )

        assert backend.supports_task("sync")
        assert not backend.supports_task("absorb")

    def test_to_dict_shape(self):
        backend = ResearchBackend(
            backend_id="ollama",
            name="Ollama",
            kind=BackendKind.LOCAL,
            cost_model=CostModel.OWNED_HARDWARE,
            available=False,
            detail="not reachable",
            task_classes=("sync", "absorb"),
        )

        data = backend.to_dict()

        assert data["backend_id"] == "ollama"
        assert data["kind"] == "local"
        assert data["cost_model"] == "owned_hardware"
        assert data["task_classes"] == ["sync", "absorb"]
        assert data["is_metered"] is False


class TestDiscoverResearchBackends:
    def test_discover_wraps_detected_capacity(self):
        backends = discover_research_backends(
            ollama_probe=lambda: (False, "off"),
            which=lambda exe: "/bin/copilot" if exe == "copilot" else None,
            env={"OPENAI_API_KEY": "sk-real"},
        )

        assert any(b.backend_id == "ollama" for b in backends)
        assert any(b.backend_id == "copilot" and b.requires_quota_ledger for b in backends)
        assert any(b.backend_id == "openai" and b.is_metered for b in backends)
