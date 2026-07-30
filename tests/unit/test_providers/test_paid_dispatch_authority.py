"""Fail-closed boundaries for provider-backed spend."""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest

from deepr.core.costs import CostEstimate
from deepr.experts.research_cost_gate import (
    ResearchCostReservation,
    mark_research_provider_work,
    reserve_research_cost,
)
from deepr.experts.research_reservation_store import ResearchReservationStore, ResearchReservationStoreError
from deepr.providers.anthropic_provider import AnthropicProvider
from deepr.providers.azure_foundry_provider import AzureFoundryProvider
from deepr.providers.azure_provider import AzureProvider
from deepr.providers.base import (
    DeepResearchProvider,
    ResearchRequest,
    ResearchResponse,
    VectorStore,
)
from deepr.providers.dispatch_authority import (
    PaidDispatchAuthorityError,
    authorized_paid_dispatch,
    research_request_sha256,
)
from deepr.providers.gemini_provider import GeminiProvider
from deepr.providers.grok_provider import GrokProvider
from deepr.providers.openai_provider import OpenAIProvider
from deepr.services.research_bounds import ResearchRequestBoundsError
from deepr.services.research_submission import submit_reserved_provider_research


class _RecordingProvider(DeepResearchProvider):
    provider_key = "openai"
    _paid_endpoint = "https://api.openai.com/v1"

    def __init__(self) -> None:
        self.submissions: list[ResearchRequest] = []
        self.storage_calls = 0

    async def _submit_research_impl(self, request: ResearchRequest) -> str:
        self.submissions.append(request)
        return "provider-job"

    async def get_status(self, job_id: str) -> ResearchResponse:
        return ResearchResponse(id=job_id, status="completed")

    async def cancel_job(self, job_id: str) -> bool:
        return True

    async def _upload_document_accounted(self, file_path: str, purpose: str = "assistants") -> str:
        self.storage_calls += 1
        return "file-id"

    async def delete_document(self, file_id: str) -> bool:
        return True

    async def _create_vector_store_accounted(self, name: str, file_ids: list[str]) -> VectorStore:
        self.storage_calls += 1
        return VectorStore(id="store-id", name=name, file_ids=file_ids)

    async def wait_for_vector_store(
        self,
        vector_store_id: str,
        timeout: int = 900,
        poll_interval: float = 2.0,
    ) -> bool:
        return True

    async def list_vector_stores(self, limit: int = 100) -> list[VectorStore]:
        return []

    async def delete_vector_store(self, vector_store_id: str) -> bool:
        return True

    def get_model_name(self, model_key: str) -> str:
        return model_key


_ADAPTERS = (
    OpenAIProvider,
    AnthropicProvider,
    AzureProvider,
    GeminiProvider,
    GrokProvider,
    AzureFoundryProvider,
)


@pytest.mark.parametrize("adapter", _ADAPTERS)
def test_every_adapter_inherits_protected_cost_boundaries(adapter: type[DeepResearchProvider]) -> None:
    assert adapter.submit_research is DeepResearchProvider.submit_research
    assert adapter.upload_document is DeepResearchProvider.upload_document
    assert adapter.create_vector_store is DeepResearchProvider.create_vector_store
    assert adapter._submit_research_authorized is DeepResearchProvider._submit_research_authorized
    assert "_submit_research_impl" in adapter.__dict__
    assert "_upload_document_accounted" in adapter.__dict__
    assert "_create_vector_store_accounted" in adapter.__dict__


def test_provider_subclass_cannot_replace_cost_boundary() -> None:
    with pytest.raises(TypeError, match="protected cost boundaries"):

        class _UnsafeProvider(_RecordingProvider):
            async def submit_research(self, request: ResearchRequest) -> str:
                return "unsafe"


@pytest.mark.asyncio
async def test_direct_paid_dispatch_is_blocked_before_adapter_call() -> None:
    provider = _RecordingProvider()
    request = ResearchRequest(prompt="question", model="model", system_message="system")

    with pytest.raises(PaidDispatchAuthorityError, match="durable reservation"):
        await provider.submit_research(request)

    assert provider.submissions == []


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter", _ADAPTERS)
async def test_direct_public_call_is_blocked_for_every_adapter(adapter: type[DeepResearchProvider]) -> None:
    provider = object.__new__(adapter)
    request = ResearchRequest(prompt="question", model="model", system_message="system")

    with pytest.raises(PaidDispatchAuthorityError, match="durable reservation"):
        await provider.submit_research(request)

    with pytest.raises(PaidDispatchAuthorityError, match="durable reservation"):
        await provider._submit_research_impl(request)

    with pytest.raises(ResearchRequestBoundsError) as upload_error:
        await provider._upload_document_accounted("document.pdf")
    with pytest.raises(ResearchRequestBoundsError) as store_error:
        await provider._create_vector_store_accounted("store", ["file-id"])

    assert upload_error.value.code == "research_file_storage_unbounded"
    assert store_error.value.code == "research_file_storage_unbounded"
    assert not hasattr(adapter._submit_research_impl, "__wrapped__")
    assert not hasattr(adapter._upload_document_accounted, "__wrapped__")
    assert not hasattr(adapter._create_vector_store_accounted, "__wrapped__")


@pytest.mark.asyncio
async def test_direct_adapter_execution_boundary_is_also_blocked() -> None:
    provider = _RecordingProvider()
    request = ResearchRequest(prompt="question", model="model", system_message="system")

    with pytest.raises(PaidDispatchAuthorityError, match="durable reservation"):
        await provider._submit_research_authorized(request)

    assert provider.submissions == []


def test_caller_supplied_strings_cannot_forge_paid_dispatch_grant() -> None:
    provider = _RecordingProvider()
    request = ResearchRequest(prompt="question", model="model", system_message="system")

    with pytest.raises(PaidDispatchAuthorityError, match="not minted"):
        with authorized_paid_dispatch(
            grant={"provider": "openai", "reservation_id": "reservation-1", "job_id": "job-1"},
            provider_instance=provider,
            provider_key="openai",
            request=request,
        ):
            pass


@pytest.mark.asyncio
async def test_durable_grant_is_request_bound_and_one_use() -> None:
    provider = _RecordingProvider()
    request = ResearchRequest(prompt="question", model="model", system_message="system")
    reservation = ResearchCostReservation(
        job_id="job-1",
        provider="openai",
        model=request.model,
        estimated_cost=1.0,
        reservation_id="reservation-1",
        manager=MagicMock(),
        dispatch_binding_id="a" * 64,
    )
    store = MagicMock()
    with patch("deepr.experts.research_cost_gate.ResearchReservationStore", return_value=store):
        grant = mark_research_provider_work(reservation, request)

    store.mark_provider_work_may_have_run.assert_called_once_with(
        "reservation-1",
        provider="openai",
        model="model",
        job_id="job-1",
        reserved_cost=1.0,
        dispatch_binding_id="a" * 64,
        request_envelope_sha256=research_request_sha256(request),
    )

    with authorized_paid_dispatch(
        grant=grant,
        provider_instance=provider,
        provider_key=provider.provider_key,
        request=request,
    ):
        request.prompt = "mutated"
        with pytest.raises(PaidDispatchAuthorityError, match="changed"):
            await provider.submit_research(request)

    with pytest.raises(PaidDispatchAuthorityError, match="already been consumed"):
        with authorized_paid_dispatch(
            grant=grant,
            provider_instance=provider,
            provider_key=provider.provider_key,
            request=request,
        ):
            pass
    assert provider.submissions == []


@pytest.mark.parametrize("proxy_name", ["HTTP_PROXY", "https_proxy", "ALL_PROXY"])
def test_paid_dispatch_mark_refuses_unaccounted_proxy_environment(monkeypatch, proxy_name: str) -> None:
    provider = _RecordingProvider()
    request = ResearchRequest(prompt="question", model="model", system_message="system")
    reservation = ResearchCostReservation(
        job_id="proxy-job",
        provider="openai",
        model=request.model,
        estimated_cost=1.0,
        reservation_id="proxy-reservation",
        manager=MagicMock(),
        dispatch_binding_id="a" * 64,
    )
    monkeypatch.setenv(proxy_name, "http://metered-proxy.invalid")

    with (
        patch("deepr.experts.research_cost_gate.ResearchReservationStore") as store,
        pytest.raises(PaidDispatchAuthorityError, match="unaccounted proxy"),
    ):
        mark_research_provider_work(reservation, request)

    store.assert_not_called()


def _bounded_reservation(request: ResearchRequest) -> ResearchCostReservation:
    return reserve_research_cost(
        job_id="bound-job",
        provider="openai",
        model=request.model,
        estimate=CostEstimate(
            min_cost=0.05,
            expected_cost=0.10,
            max_cost=0.20,
            model=request.model,
            reasoning="test bound request",
        ),
        max_cost_per_job=1.0,
        max_daily_cost=5.0,
        max_weekly_cost=10.0,
        max_monthly_cost=20.0,
        request=request,
    )


@pytest.mark.parametrize("forged_field", ["provider", "model", "job", "ceiling", "binding"])
def test_forged_handle_cannot_borrow_an_active_reservation(forged_field: str) -> None:
    request = ResearchRequest(prompt="bounded", model="model", system_message="system")
    reservation = _bounded_reservation(request)
    forged_request = request
    if forged_field == "provider":
        forged = replace(reservation, provider="anthropic")
    elif forged_field == "model":
        forged = replace(reservation, model="other-model")
        forged_request = replace(request, model="other-model")
    elif forged_field == "job":
        forged = replace(reservation, job_id="other-job")
    elif forged_field == "ceiling":
        forged = replace(reservation, estimated_cost=5.0)
    else:
        forged = replace(reservation, dispatch_binding_id="f" * 64)

    with pytest.raises(ResearchReservationStoreError, match="does not match"):
        mark_research_provider_work(forged, forged_request)

    active = ResearchReservationStore().active_reservations()
    assert len(active) == 1
    assert active[0].reservation_id == reservation.reservation_id
    assert active[0].provider_work_may_have_run is False


def test_changed_request_cannot_use_a_prebound_reservation() -> None:
    request = ResearchRequest(prompt="bounded", model="model", system_message="system")
    reservation = _bounded_reservation(request)
    changed_request = replace(request, prompt="different paid work")

    with pytest.raises(ResearchReservationStoreError, match="does not match"):
        mark_research_provider_work(reservation, changed_request)

    assert ResearchReservationStore().active_reservations()[0].provider_work_may_have_run is False


def test_exact_request_digest_is_committed_before_grant_is_returned() -> None:
    request = ResearchRequest(prompt="bounded", model="model", system_message="system")
    reservation = _bounded_reservation(request)
    assert reservation.dispatch_binding_id not in repr(reservation)

    grant = mark_research_provider_work(reservation, request)

    assert grant is not None
    assert reservation.request_envelope_sha256 == research_request_sha256(request)
    store = ResearchReservationStore()
    with sqlite3.connect(store.path) as connection:
        row = connection.execute(
            "SELECT provider, model, job_id, reserved_cost, request_envelope_sha256, "
            "provider_work_may_have_run FROM research_cost_reservations WHERE reservation_id = ?",
            (reservation.reservation_id,),
        ).fetchone()
    assert row == (
        "openai",
        request.model,
        reservation.job_id,
        reservation.estimated_cost,
        research_request_sha256(request),
        1,
    )

    with pytest.raises(ResearchReservationStoreError, match="does not match"):
        mark_research_provider_work(reservation, request)


@pytest.mark.asyncio
async def test_hosted_storage_mutations_fail_before_adapter_call() -> None:
    provider = _RecordingProvider()

    with pytest.raises(ResearchRequestBoundsError) as upload_error:
        await provider.upload_document("document.pdf")
    with pytest.raises(ResearchRequestBoundsError) as store_error:
        await provider.create_vector_store("store", ["file-id"])

    assert upload_error.value.code == "research_file_storage_unbounded"
    assert store_error.value.code == "research_file_storage_unbounded"
    assert provider.storage_calls == 0


@pytest.mark.asyncio
async def test_cleanup_operations_remain_available_without_paid_authority() -> None:
    provider = _RecordingProvider()

    assert await provider.cancel_job("job") is True
    assert await provider.delete_document("file") is True
    assert await provider.delete_vector_store("store") is True


@pytest.mark.asyncio
async def test_reserved_service_freezes_request_before_mark_and_mints_after_mark() -> None:
    provider = _RecordingProvider()
    request = ResearchRequest(
        prompt="original",
        model="o4-mini-deep-research",
        system_message="system",
        metadata={"nested": {"value": "original"}},
    )
    reservation = ResearchCostReservation(
        job_id="job-1",
        provider="openai",
        model=request.model,
        estimated_cost=100.0,
        reservation_id="reservation-1",
        manager=MagicMock(),
        dispatch_binding_id="b" * 64,
    )
    mark_started = threading.Event()
    release_mark = threading.Event()

    def durable_mark(_reservation_id: str, **_identity: object) -> None:
        assert provider.submissions == []
        mark_started.set()
        assert release_mark.wait(timeout=2)

    store = MagicMock()
    store.mark_provider_work_may_have_run.side_effect = durable_mark
    with patch("deepr.experts.research_cost_gate.ResearchReservationStore", return_value=store):
        task = asyncio.create_task(
            submit_reserved_provider_research(
                provider=provider,
                request=request,
                reservation=reservation,
                source="test",
            )
        )
        assert await asyncio.to_thread(mark_started.wait, 2)
        request.prompt = "mutated"
        request.metadata["nested"]["value"] = "mutated"
        release_mark.set()
        assert await task == "provider-job"

    submitted = provider.submissions[0]
    assert submitted is not request
    assert submitted.prompt == "original"
    assert submitted.metadata == {"nested": {"value": "original"}}
    store.mark_provider_work_may_have_run.assert_called_once_with(
        "reservation-1",
        provider="openai",
        model=request.model,
        job_id="job-1",
        reserved_cost=100.0,
        dispatch_binding_id="b" * 64,
        request_envelope_sha256=research_request_sha256(submitted),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("adapter", "wrong_provider"),
    [
        (OpenAIProvider, "anthropic"),
        (AnthropicProvider, "openai"),
        (AzureProvider, "openai"),
        (GeminiProvider, "openai"),
        (GrokProvider, "openai"),
        (AzureFoundryProvider, "azure"),
    ],
)
async def test_reservation_cannot_authorize_another_adapter(
    adapter: type[DeepResearchProvider],
    wrong_provider: str,
) -> None:
    provider = object.__new__(adapter)
    request = ResearchRequest(prompt="question", model="model", system_message="system")
    reservation = ResearchCostReservation(
        job_id="job-1",
        provider=wrong_provider,
        model=request.model,
        estimated_cost=100.0,
        reservation_id="reservation-1",
        manager=MagicMock(),
    )

    with (
        patch("deepr.services.research_submission.mark_research_provider_work") as mark,
        patch("deepr.services.research_submission.refund_research_cost") as refund,
        pytest.raises(ResearchRequestBoundsError) as raised,
    ):
        await submit_reserved_provider_research(
            provider=provider,
            request=request,
            reservation=reservation,
            source="test",
        )

    assert raised.value.code == "research_reservation_provider_mismatch"
    mark.assert_not_called()
    refund.assert_called_once_with(reservation)
