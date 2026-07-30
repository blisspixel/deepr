"""Validation harness for Deepr A2A host contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from ipaddress import IPv4Address, IPv6Address, ip_address
from math import isfinite
from typing import Any, Literal
from urllib.parse import urlsplit

from deepr.a2a.agent_card import AgentCardGenerator, ExpertInfo
from deepr.a2a.constants import (
    A2A_AGENT_CARD_PATH,
    CONSULT_SKILL_NAME,
)
from deepr.a2a.consult_tasks import build_consult_artifact, build_consult_result
from deepr.a2a.models import A2A_TASK_KIND, A2A_TASK_SCHEMA_VERSION, Task, TaskState
from deepr.experts import consult as consult_core
from deepr.mcp.consult_validation import ValidationBackend, build_offline_consult_fixture

A2A_HOST_VALIDATION_SCHEMA_VERSION = "deepr-a2a-host-validation-v1"
A2A_HOST_VALIDATION_KIND = "deepr.a2a.host_validation"

A2AValidationMode = Literal["offline", "http"]
CheckStatus = Literal["passed", "failed", "warning", "skipped"]

DEFAULT_A2A_VALIDATION_QUESTION = (
    "Validate the Deepr A2A expert consult contract for a host agent. Map the "
    "math, uncertainty, dissent, capacity posture, and next action boundary."
)

MAX_HTTP_VALIDATION_TIMEOUT_SECONDS = 300.0
MAX_HTTP_VALIDATION_POLL_ATTEMPTS = 100
MAX_HTTP_VALIDATION_POLL_INTERVAL_SECONDS = 10.0
_OWNED_LOOPBACK_ADDRESSES = {IPv4Address("127.0.0.1"), IPv6Address("::1")}


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class A2AHostValidationCheck:
    """One deterministic A2A validation check."""

    name: str
    status: CheckStatus
    detail: str

    @property
    def ok(self) -> bool:
        return self.status in {"passed", "warning", "skipped"}

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


@dataclass(frozen=True)
class A2AHostValidationReport:
    """Structured result for A2A host validation."""

    mode: A2AValidationMode
    backend: ValidationBackend
    question: str
    requested_experts: tuple[str, ...]
    checks: tuple[A2AHostValidationCheck, ...]
    endpoint: str | None = None
    discovery_path: str | None = None
    plan: str | None = None
    cost_ceiling_usd: float = 0.0
    agent_card_summary: dict[str, Any] = field(default_factory=dict)
    task_summary: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] = field(default_factory=dict)
    generated_at: datetime = field(default_factory=_utc_now)

    @property
    def ok(self) -> bool:
        return bool(self.checks) and all(check.ok for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        failed = [check.name for check in self.checks if check.status == "failed"]
        return {
            "schema_version": A2A_HOST_VALIDATION_SCHEMA_VERSION,
            "kind": A2A_HOST_VALIDATION_KIND,
            "generated_at": self.generated_at.isoformat(),
            "contract": {
                "cost_usd": 0.0,
                "cost_scope": "validation_client_only",
                "remote_task_cost_ceiling_usd": self.cost_ceiling_usd,
                "remote_task_cost_status": "not_submitted",
                "writes_expert_state": False,
                "submits_a2a_task": False,
                "task_submission_attempted": False,
                "calls_metered_api": False,
                "calls_metered_api_scope": "validation_client_only",
                "remote_task_calls_metered_api": None,
                "semantic_verdict": False,
                "checks_form_and_side_effects_only": True,
            },
            "mode": self.mode,
            "endpoint": self.endpoint,
            "discovery_path": self.discovery_path,
            "backend": self.backend,
            "plan": self.plan,
            "requested_experts": list(self.requested_experts),
            "question_hash_source": "question",
            "cost_ceiling_usd": self.cost_ceiling_usd,
            "summary": {
                "ok": self.ok,
                "check_count": len(self.checks),
                "failed_checks": failed,
            },
            "agent_card_summary": self.agent_card_summary,
            "task_summary": self.task_summary,
            "checks": [check.to_dict() for check in self.checks],
            "error": self.error,
        }


def _check(name: str, condition: bool, passed: str, failed: str) -> A2AHostValidationCheck:
    return A2AHostValidationCheck(name, "passed" if condition else "failed", passed if condition else failed)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if isfinite(number) else None


def _safe_json_contains(payload: dict[str, Any], forbidden_values: tuple[str, ...]) -> bool:
    if not forbidden_values:
        return False
    encoded = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True)
    return any(secret and secret in encoded for secret in forbidden_values)


def _trace_id(payload: dict[str, Any]) -> str:
    trace = _as_dict(payload.get("trace"))
    collaboration = _as_dict(payload.get("collaboration"))
    task = _as_dict(collaboration.get("task"))
    return str(trace.get("trace_id") or task.get("consult_trace_id") or "")


def _skill_names(agent_card: dict[str, Any]) -> list[str]:
    return [str(skill.get("name")) for skill in _as_list(agent_card.get("skills")) if isinstance(skill, dict)]


def _consult_skill(agent_card: dict[str, Any]) -> dict[str, Any]:
    for skill in _as_list(agent_card.get("skills")):
        if isinstance(skill, dict) and skill.get("name") == CONSULT_SKILL_NAME:
            return skill
    return {}


def _find_artifact(task: dict[str, Any]) -> dict[str, Any]:
    result = _as_dict(task.get("result"))
    artifact_id = str(result.get("artifact_id") or "")
    for artifact in _as_list(task.get("artifacts")):
        if isinstance(artifact, dict) and artifact.get("artifact_id") == artifact_id:
            return artifact
    return {}


def _backend_provider_ok(capacity: dict[str, Any], backend: ValidationBackend) -> bool:
    provider = str(capacity.get("provider", ""))
    if backend == "local":
        return provider == "local"
    return provider.startswith("plan_quota:")


def _summarize_agent_card(agent_card: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": agent_card.get("name"),
        "version": agent_card.get("version"),
        "url": agent_card.get("url"),
        "skill_count": len(_as_list(agent_card.get("skills"))),
        "has_consult_skill": CONSULT_SKILL_NAME in _skill_names(agent_card),
    }


def _summarize_task(task: dict[str, Any]) -> dict[str, Any]:
    artifact = _find_artifact(task)
    content = _as_dict(artifact.get("content"))
    capacity = _as_dict(_as_dict(task.get("result")).get("capacity")) or _as_dict(content.get("capacity"))
    return {
        "schema_version": task.get("schema_version"),
        "kind": task.get("kind"),
        "state": task.get("state"),
        "skill": task.get("skill"),
        "cost": _finite_number(task.get("cost")),
        "trace_id": task.get("trace_id"),
        "artifact_count": len(_as_list(task.get("artifacts"))),
        "consult_schema_version": content.get("schema_version"),
        "capacity": capacity,
    }


def validate_a2a_host_payload(
    agent_card: dict[str, Any],
    task: dict[str, Any],
    *,
    expected_backend: ValidationBackend,
    cost_ceiling_usd: float = 0.0,
    forbidden_values: tuple[str, ...] = (),
) -> tuple[A2AHostValidationCheck, ...]:
    """Validate A2A discovery and consult task contracts.

    These checks cover deterministic structure and side-effect posture only.
    They do not judge whether the answer is useful.
    """

    checks: list[A2AHostValidationCheck] = []
    skill = _consult_skill(agent_card)
    result = _as_dict(task.get("result"))
    artifact = _find_artifact(task)
    content = _as_dict(artifact.get("content"))
    collaboration = _as_dict(content.get("collaboration"))
    collaboration_contract = _as_dict(collaboration.get("contract"))
    dissent = _as_dict(collaboration.get("dissent_handling"))
    capacity = _as_dict(result.get("capacity")) or _as_dict(content.get("capacity"))
    contract = _as_dict(task.get("contract"))
    validated_ceiling = _finite_number(cost_ceiling_usd)
    ceiling_ok = validated_ceiling is not None and validated_ceiling >= 0
    ceiling_text = f"${validated_ceiling:.4f}" if ceiling_ok else "an invalid ceiling"

    checks.append(
        _check(
            "cost_ceiling",
            ceiling_ok,
            f"cost ceiling is finite and non-negative: {ceiling_text}",
            "cost ceiling must be a finite non-negative number",
        )
    )

    checks.append(
        _check(
            "agent_card_envelope",
            isinstance(agent_card.get("skills"), list) and bool(agent_card.get("name")),
            "Agent Card exposes name and skills",
            "Agent Card is missing name or skills",
        )
    )
    checks.append(
        _check(
            "consult_skill_discovery",
            bool(skill),
            "Agent Card advertises deepr_consult_experts",
            "Agent Card does not advertise deepr_consult_experts",
        )
    )
    checks.append(
        _check(
            "consult_skill_modes",
            "application/json" in _as_list(skill.get("input_modes"))
            and "application/json" in _as_list(skill.get("output_modes")),
            "consult skill advertises JSON input and output modes",
            "consult skill does not advertise JSON input and output modes",
        )
    )
    checks.append(
        _check(
            "task_envelope",
            task.get("schema_version") == A2A_TASK_SCHEMA_VERSION and task.get("kind") == A2A_TASK_KIND,
            "task uses deepr-a2a-task-v1 envelope",
            "task schema_version or kind is wrong",
        )
    )
    checks.append(
        _check(
            "task_completed",
            task.get("state") == TaskState.COMPLETED.value,
            "consult task completed",
            f"consult task did not complete: state={task.get('state')!r}",
        )
    )
    checks.append(
        _check(
            "task_skill",
            task.get("skill") == CONSULT_SKILL_NAME,
            "task uses deepr_consult_experts skill",
            "task skill is not deepr_consult_experts",
        )
    )
    checks.append(
        _check(
            "artifact_linkage",
            bool(artifact) and result.get("artifact_id") == artifact.get("artifact_id"),
            "task result points to an attached artifact",
            "task result artifact_id does not point to an attached artifact",
        )
    )
    checks.append(
        _check(
            "consult_artifact",
            content.get("schema_version") == consult_core.CONSULT_SCHEMA_VERSION
            and content.get("kind") == consult_core.CONSULT_KIND,
            "attached artifact contains deepr-consult-v1",
            "attached artifact does not contain deepr-consult-v1",
        )
    )
    checks.append(
        _check(
            "capacity_backend",
            capacity.get("synthesis_backend") == expected_backend and _backend_provider_ok(capacity, expected_backend),
            f"capacity reports expected {expected_backend} backend",
            f"capacity does not report expected {expected_backend} backend",
        )
    )
    task_cost = _finite_number(task.get("cost"))
    result_cost = _finite_number(result.get("cost_usd"))
    consult_cost = _finite_number(content.get("cost_usd"))
    checks.append(
        _check(
            "no_metered_cost",
            ceiling_ok
            and validated_ceiling is not None
            and task_cost is not None
            and task_cost >= 0
            and task_cost <= validated_ceiling
            and result_cost is not None
            and result_cost >= 0
            and result_cost <= validated_ceiling
            and consult_cost is not None
            and consult_cost >= 0
            and consult_cost <= validated_ceiling
            and capacity.get("live_metered_fallback") is False,
            f"task and artifact cost fields are within ceiling {ceiling_text}",
            f"cost fields are invalid, exceed {ceiling_text}, or metered fallback is enabled",
        )
    )
    checks.append(
        _check(
            "dissent_contract",
            isinstance(result.get("agreements"), list)
            and isinstance(result.get("disagreements"), list)
            and dissent.get("dissent_preserved") is True
            and dissent.get("synthesis_is_not_truth_adjudication") is True,
            "agreement and disagreement fields are explicit and dissent is preserved",
            "dissent handling metadata is missing or unsafe",
        )
    )
    checks.append(
        _check(
            "result_untrusted_boundary",
            contract.get("result_untrusted") is True
            and _as_dict(artifact.get("metadata")).get("result_untrusted") is True,
            "task and artifact mark result content as untrusted",
            "task or artifact does not mark result content as untrusted",
        )
    )
    checks.append(
        _check(
            "host_action_boundary",
            collaboration_contract.get("host_orchestrated") is True
            and collaboration_contract.get("deepr_enacts_downstream_actions") is False
            and collaboration_contract.get("semantic_verdict") is False,
            "Deepr returns guidance through a host-owned action boundary",
            "collaboration metadata blurs host action or semantic-verdict boundaries",
        )
    )
    checks.append(
        _check(
            "secret_redaction",
            not _safe_json_contains({"agent_card": agent_card, "task": task}, forbidden_values),
            "provided auth secret was not echoed in A2A payloads",
            "provided auth secret appeared in A2A payloads",
        )
    )
    return tuple(checks)


def build_offline_a2a_host_fixture(
    *,
    question: str = DEFAULT_A2A_VALIDATION_QUESTION,
    experts: tuple[str, ...] = (),
    backend: ValidationBackend = "local",
    plan: str | None = None,
    model: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build no-model A2A discovery and consult-task fixtures."""

    names = experts or ("A2A Validation Expert",)
    generator = AgentCardGenerator(version="offline-contract-fixture", url="http://127.0.0.1:0")
    for name in names:
        generator.register_expert(ExpertInfo(name=name, description="A2A validation expert", domain="contracts"))
    agent_card = generator.to_dict()

    consult_payload = build_offline_consult_fixture(
        question=question,
        experts=names,
        backend=backend,
        plan=plan,
        model=model,
    )
    artifact = build_consult_artifact(consult_payload)
    trace_id = _trace_id(consult_payload)
    task = Task(
        id="task_a2a_validation_fixture",
        state=TaskState.COMPLETED,
        skill=CONSULT_SKILL_NAME,
        input=question,
        result=build_consult_result(consult_payload, artifact_id=str(artifact["artifact_id"])),
        cost=0.0,
        trace_id=trace_id,
        artifacts=[artifact],
        metadata={"synthesis_backend": backend, "experts": list(names)},
    ).to_dict()
    return agent_card, task


def _report(
    *,
    mode: A2AValidationMode,
    backend: ValidationBackend,
    question: str,
    experts: tuple[str, ...],
    checks: tuple[A2AHostValidationCheck, ...],
    endpoint: str | None = None,
    discovery_path: str | None = None,
    plan: str | None = None,
    agent_card: dict[str, Any] | None = None,
    task: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
    cost_ceiling_usd: float = 0.0,
) -> A2AHostValidationReport:
    return A2AHostValidationReport(
        mode=mode,
        backend=backend,
        question=question,
        requested_experts=experts,
        endpoint=endpoint,
        discovery_path=discovery_path,
        plan=plan,
        cost_ceiling_usd=cost_ceiling_usd,
        checks=checks,
        agent_card_summary=_summarize_agent_card(agent_card) if agent_card else {},
        task_summary=_summarize_task(task) if task else {},
        error=error or {},
    )


def run_offline_a2a_host_validation(
    *,
    question: str = DEFAULT_A2A_VALIDATION_QUESTION,
    experts: tuple[str, ...] = (),
    backend: ValidationBackend = "local",
    plan: str | None = None,
    model: str | None = None,
) -> A2AHostValidationReport:
    """Run deterministic A2A host validation without a model or endpoint."""

    agent_card, task = build_offline_a2a_host_fixture(
        question=question,
        experts=experts,
        backend=backend,
        plan=plan,
        model=model,
    )
    checks = validate_a2a_host_payload(agent_card, task, expected_backend=backend)
    return _report(
        mode="offline",
        backend=backend,
        question=question,
        experts=experts,
        checks=checks,
        discovery_path=A2A_AGENT_CARD_PATH,
        plan=plan,
        agent_card=agent_card,
        task=task,
    )


def _validated_loopback_endpoint(endpoint: Any) -> str:
    if not isinstance(endpoint, str) or not endpoint or endpoint != endpoint.strip():
        raise ValueError("endpoint must be a non-empty URL without surrounding whitespace")
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("endpoint must be a valid loopback URL") from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("endpoint scheme must be http or https")
    if not parsed.netloc or parsed.username is not None or parsed.password is not None:
        raise ValueError("endpoint must not contain credentials and must include a host")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("endpoint must be an origin URL without a path, query, or fragment")
    hostname = parsed.hostname
    if hostname is None:
        raise ValueError("endpoint must include a host")
    try:
        address = ip_address(hostname)
    except ValueError as exc:
        raise ValueError("endpoint host must be the literal loopback address 127.0.0.1 or ::1") from exc
    if address not in _OWNED_LOOPBACK_ADDRESSES:
        raise ValueError("endpoint host must be the literal loopback address 127.0.0.1 or ::1")
    host = f"[{address.compressed}]" if isinstance(address, IPv6Address) else address.compressed
    port_suffix = f":{port}" if port is not None else ""
    return f"{parsed.scheme.lower()}://{host}{port_suffix}"


def _validated_http_bounds(
    timeout_seconds: Any,
    poll_attempts: Any,
    poll_interval_seconds: Any,
) -> tuple[float, int, float]:
    timeout = _finite_number(timeout_seconds)
    if timeout is None or timeout <= 0 or timeout > MAX_HTTP_VALIDATION_TIMEOUT_SECONDS:
        raise ValueError(
            f"timeout_seconds must be finite and greater than 0, up to {MAX_HTTP_VALIDATION_TIMEOUT_SECONDS:g}"
        )
    if isinstance(poll_attempts, bool) or not isinstance(poll_attempts, int):
        raise ValueError("poll_attempts must be an integer")
    if poll_attempts < 0 or poll_attempts > MAX_HTTP_VALIDATION_POLL_ATTEMPTS:
        raise ValueError(f"poll_attempts must be between 0 and {MAX_HTTP_VALIDATION_POLL_ATTEMPTS}")
    interval = _finite_number(poll_interval_seconds)
    if interval is None or interval < 0 or interval > MAX_HTTP_VALIDATION_POLL_INTERVAL_SECONDS:
        raise ValueError(
            f"poll_interval_seconds must be finite and between 0 and {MAX_HTTP_VALIDATION_POLL_INTERVAL_SECONDS:g}"
        )
    if poll_attempts * interval > timeout:
        raise ValueError("poll_attempts * poll_interval_seconds must not exceed timeout_seconds")
    return timeout, poll_attempts, interval


def _failed_report(
    *,
    mode: A2AValidationMode,
    backend: ValidationBackend,
    question: str,
    experts: tuple[str, ...],
    endpoint: str | None,
    plan: str | None,
    check_name: str,
    detail: str,
    error_code: str,
    discovery_path: str | None = None,
    agent_card: dict[str, Any] | None = None,
    cost_ceiling_usd: float = 0.0,
) -> A2AHostValidationReport:
    return _report(
        mode=mode,
        backend=backend,
        question=question,
        experts=experts,
        endpoint=endpoint,
        discovery_path=discovery_path,
        plan=plan,
        agent_card=agent_card,
        cost_ceiling_usd=cost_ceiling_usd,
        checks=(A2AHostValidationCheck(check_name, "failed", detail),),
        error={"error_code": error_code, "message": detail},
    )


async def run_http_a2a_host_validation(
    endpoint: str,
    *,
    auth_token: str | None = None,
    question: str = DEFAULT_A2A_VALIDATION_QUESTION,
    experts: tuple[str, ...] = (),
    backend: ValidationBackend = "local",
    local_model: str | None = None,
    plan: str | None = None,
    plan_model: str | None = None,
    timeout_seconds: float = 60.0,
    poll_attempts: int = 5,
    poll_interval_seconds: float = 0.25,
) -> A2AHostValidationReport:
    """Fail closed before HTTP task submission until cost authority is attestable."""

    try:
        resolved_endpoint = _validated_loopback_endpoint(endpoint)
        _validated_http_bounds(
            timeout_seconds,
            poll_attempts,
            poll_interval_seconds,
        )
    except ValueError as exc:
        return _failed_report(
            mode="http",
            backend=backend,
            question=question,
            experts=experts,
            endpoint=None,
            plan=plan,
            check_name="http_preflight",
            detail=str(exc),
            error_code="INVALID_HTTP_PREFLIGHT",
        )

    if backend not in {"local", "plan"}:
        return _failed_report(
            mode="http",
            backend=backend,
            question=question,
            experts=experts,
            endpoint=resolved_endpoint,
            plan=plan,
            check_name="backend_configuration",
            detail="HTTP validation permits only local or plan capacity",
            error_code="INVALID_BACKEND",
        )
    if backend == "plan" and not plan:
        return _failed_report(
            mode="http",
            backend=backend,
            question=question,
            experts=experts,
            endpoint=resolved_endpoint,
            plan=plan,
            check_name="backend_configuration",
            detail="plan is required when backend is plan",
            error_code="INVALID_BACKEND",
        )
    del auth_token, local_model, plan_model
    detail = (
        "HTTP A2A task submission is blocked until Deepr can verify an independently enforced "
        "cost authority before POST /tasks. A bearer token, Agent Card, requested backend, and "
        "returned zero-cost fields are self-reported and do not prove that the endpoint avoided "
        "metered side effects. Use offline validation instead."
    )
    return _failed_report(
        mode="http",
        backend=backend,
        question=question,
        experts=experts,
        endpoint=resolved_endpoint,
        plan=plan,
        check_name="http_task_cost_authority",
        detail=detail,
        error_code="A2A_HTTP_TASK_VALIDATION_BLOCKED",
    )
