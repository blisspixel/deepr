"""Credential-free owned-Ollama transport for structured consult evals."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from deepr.backends.capacity import (
    select_materialized_local_ollama_model,
    validate_owned_local_ollama_url,
)
from deepr.evals.consult_graph_contract import (
    StructuredConsultContractError,
    position_model_output_schema,
    stable_json_hash,
    synthesis_model_output_schema,
)

STRUCTURED_KEEP_ALIVE = "5m"
PREFLIGHT_REQUEST_TIMEOUT_SECONDS = 5.0
_ALLOWED_OUTPUT_SCHEMA_HASHES = frozenset(
    {
        stable_json_hash(position_model_output_schema()),
        stable_json_hash(synthesis_model_output_schema()),
    }
)


@dataclass(frozen=True)
class LocalTransportResponse:
    content: object
    request_id: str
    stop_reason: str
    reported_input_tokens: int | None
    reported_output_tokens: int | None


class LocalTransportError(RuntimeError):
    def __init__(self, message: str, *, request_id: str = "", status_code: int | None = None) -> None:
        super().__init__(message)
        self.request_id = request_id
        self.status_code = status_code


class OwnedOllamaConsultTransport:
    """Narrow Ollama-native transport with no credential or proxy inheritance."""

    def __init__(self, endpoint: str, *, timeout: float, http_transport: Any | None = None) -> None:
        import httpx

        self.endpoint = validate_owned_local_ollama_url(endpoint)
        self._attested_model = ""
        self._client = httpx.AsyncClient(
            base_url=f"{self.endpoint}/",
            timeout=timeout,
            trust_env=False,
            follow_redirects=False,
            transport=http_transport,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "deepr-local-consult/1",
            },
        )

    async def attest_model(self, model: str | None) -> tuple[str, dict[str, Any]]:
        status = await self._get_json("api/status")
        cloud = status.get("cloud")
        if not isinstance(cloud, Mapping) or cloud.get("disabled") is not True:
            raise StructuredConsultContractError(
                "LOCAL_CLOUD_NOT_DISABLED",
                "Ollama must report cloud.disabled=true before structured local execution",
            )
        status_source = cloud.get("source")
        if status_source not in {"config", "both"}:
            raise StructuredConsultContractError(
                "LOCAL_CLOUD_STATUS_UNKNOWN",
                "Ollama cloud-disable provenance must be stable config",
            )
        inventory = await self._get_json("api/tags")
        entries = inventory.get("models")
        if not isinstance(entries, list):
            raise StructuredConsultContractError("LOCAL_MODEL_PROVENANCE", "Ollama model inventory is malformed")
        selected = select_materialized_model(entries, requested=model)
        selected_model = str(selected["name"])
        details = selected["details"]
        evidence: dict[str, Any] = {
            "attestation_kind": "ollama-owned-local-v1",
            "cloud_disabled": True,
            "cloud_status_source": status_source,
            "model": selected_model,
            "digest": selected["digest"],
            "size_bytes": selected["size"],
            "format": str(details["format"]).lower(),
            "observed_at": _now(),
        }
        evidence["attestation_hash"] = stable_json_hash(evidence)
        self._attested_model = selected_model
        return selected_model, evidence

    async def _get_json(self, path: str) -> Mapping[str, Any]:
        import httpx

        try:
            response = await self._client.get(path, timeout=PREFLIGHT_REQUEST_TIMEOUT_SECONDS)
        except httpx.TimeoutException as exc:
            raise StructuredConsultContractError("LOCAL_PREFLIGHT_TIMEOUT", "local Ollama preflight timed out") from exc
        if response.status_code != 200:
            raise StructuredConsultContractError(
                "LOCAL_PREFLIGHT_ERROR",
                f"local Ollama preflight returned HTTP {response.status_code}",
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise StructuredConsultContractError(
                "LOCAL_PREFLIGHT_ERROR", "local Ollama preflight was not JSON"
            ) from exc
        if not isinstance(payload, Mapping):
            raise StructuredConsultContractError("LOCAL_PREFLIGHT_ERROR", "local Ollama preflight was not an object")
        return payload

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        output_schema: Mapping[str, Any],
    ) -> LocalTransportResponse:
        import httpx

        if model != self._attested_model:
            raise StructuredConsultContractError(
                "LOCAL_MODEL_PROVENANCE",
                "local model is not bound to the current cloud-disabled inventory attestation",
            )
        if stable_json_hash(output_schema) not in _ALLOWED_OUTPUT_SCHEMA_HASHES:
            raise StructuredConsultContractError(
                "OUTPUT_SCHEMA",
                "local structured consult output schema is not an exact shipped contract",
            )
        try:
            response = await self._client.post(
                "api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "format": dict(output_schema),
                    "keep_alive": STRUCTURED_KEEP_ALIVE,
                    "options": {"num_predict": max_tokens},
                },
            )
        except httpx.TimeoutException as exc:
            raise TimeoutError("local Ollama transport timed out") from exc
        request_id = str(response.headers.get("x-request-id", ""))[:256]
        if response.status_code != 200:
            raise LocalTransportError(
                f"local Ollama returned HTTP {response.status_code}",
                request_id=request_id,
                status_code=response.status_code,
            )
        try:
            payload = response.json()
        except ValueError:
            payload = None
        shaped = payload if isinstance(payload, Mapping) else {}
        message = shaped.get("message")
        content = message.get("content") if isinstance(message, Mapping) else None
        return LocalTransportResponse(
            content=content,
            request_id=request_id,
            stop_reason=str(shaped.get("done_reason", "") or "")[:256],
            reported_input_tokens=_mapping_usage_int(shaped, "prompt_eval_count"),
            reported_output_tokens=_mapping_usage_int(shaped, "eval_count"),
        )

    async def close(self) -> None:
        await self._client.aclose()


def select_materialized_model(entries: list[Any], *, requested: str | None) -> Mapping[str, Any]:
    """Select one exact, materialized local GGUF inventory entry."""
    try:
        return select_materialized_local_ollama_model(entries, requested=requested)
    except ValueError as exc:
        raise StructuredConsultContractError("LOCAL_MODEL_PROVENANCE", str(exc)) from exc


def _mapping_usage_int(usage: Mapping[str, Any], field: str) -> int | None:
    value = usage.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise StructuredConsultContractError("INVALID_USAGE", f"provider {field} must be a non-negative integer")
    return value


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
