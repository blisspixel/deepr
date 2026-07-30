"""Test-only adapter harness behind the production authority boundary."""

from __future__ import annotations

from typing import Any

from deepr.providers.dispatch_authority import (
    _mint_paid_dispatch_grant,
    authorized_paid_dispatch,
    research_request_sha256,
)


async def submit_adapter(provider: Any, request: Any) -> str:
    """Exercise an adapter with a sealed test grant and no external accounting."""
    grant = _mint_paid_dispatch_grant(
        provider=provider.provider_key,
        model=request.model,
        reservation_id="unit-test-reservation",
        job_id="unit-test-job",
        request_sha256=research_request_sha256(request),
    )
    with authorized_paid_dispatch(
        grant=grant,
        provider_instance=provider,
        provider_key=provider.provider_key,
        request=request,
    ):
        return await provider.submit_research(request)
