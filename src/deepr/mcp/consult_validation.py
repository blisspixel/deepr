"""Validation harness for no-metered expert consult over MCP.

The harness checks transport, schema, cost, capacity, and collaboration
contracts. It does not judge answer meaning; semantic quality belongs to a
human or calibrated model review path.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from deepr.experts import consult as consult_core
from deepr.experts.consult_traces import build_consult_trace
from deepr.mcp.consult_tool import consult_experts_tool
from deepr.mcp.transport.http import HttpClient, HttpMessage

MCP_CONSULT_VALIDATION_SCHEMA_VERSION = "deepr-mcp-consult-validation-v1"
MCP_CONSULT_VALIDATION_KIND = "deepr.mcp.consult_validation"

ValidationMode = Literal["offline", "in_process", "http"]
ValidationBackend = Literal["local", "plan"]
CheckStatus = Literal["passed", "failed", "warning", "skipped"]

DEFAULT_VALIDATION_QUESTION = (
    "Validate the Deepr expert consult contract for an external agent. Preserve "
    "uncertainty and dissent, and report the no-metered capacity posture."
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class MCPConsultValidationCheck:
    """One deterministic validation check."""

    name: str
    status: CheckStatus
    detail: str

    @property
    def ok(self) -> bool:
        return self.status in {"passed", "warning", "skipped"}

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


@dataclass(frozen=True)
class MCPConsultValidationReport:
    """Structured result for a consult validation run."""

    mode: ValidationMode
    backend: ValidationBackend
    question: str
    requested_experts: tuple[str, ...]
    checks: tuple[MCPConsultValidationCheck, ...]
    endpoint: str | None = None
    plan: str | None = None
    cost_ceiling_usd: float = 0.0
    consult_summary: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] = field(default_factory=dict)
    generated_at: datetime = field(default_factory=_utc_now)

    @property
    def ok(self) -> bool:
        return bool(self.checks) and all(check.ok for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        failed = [check.name for check in self.checks if check.status == "failed"]
        payload: dict[str, Any] = {
            "schema_version": MCP_CONSULT_VALIDATION_SCHEMA_VERSION,
            "kind": MCP_CONSULT_VALIDATION_KIND,
            "generated_at": self.generated_at.isoformat(),
            "contract": {
                "cost_usd": 0.0,
                "writes_state": False,
                "calls_metered_api": False,
                "semantic_verdict": False,
                "checks_form_and_side_effects_only": True,
            },
            "mode": self.mode,
            "endpoint": self.endpoint,
            "backend": self.backend,
            "plan": self.plan,
            "question_hash_source": "question",
            "requested_experts": list(self.requested_experts),
            "cost_ceiling_usd": self.cost_ceiling_usd,
            "summary": {
                "ok": self.ok,
                "check_count": len(self.checks),
                "failed_checks": failed,
            },
            "consult_summary": self.consult_summary,
            "checks": [check.to_dict() for check in self.checks],
            "error": self.error,
        }
        return payload


def _check(name: str, condition: bool, passed: str, failed: str) -> MCPConsultValidationCheck:
    return MCPConsultValidationCheck(name, "passed" if condition else "failed", passed if condition else failed)


def _warning_check(name: str, condition: bool, passed: str, warning: str) -> MCPConsultValidationCheck:
    return MCPConsultValidationCheck(name, "passed" if condition else "warning", passed if condition else warning)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _float_value(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_json_contains(payload: dict[str, Any], forbidden_values: tuple[str, ...]) -> bool:
    if not forbidden_values:
        return False
    encoded = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True)
    return any(secret and secret in encoded for secret in forbidden_values)


def _summarize_consult(payload: dict[str, Any]) -> dict[str, Any]:
    trace = _as_dict(payload.get("trace"))
    capacity = _as_dict(payload.get("capacity"))
    collaboration = _as_dict(payload.get("collaboration"))
    budget_capacity = _as_dict(collaboration.get("budget_capacity_contract"))
    return {
        "schema_version": payload.get("schema_version"),
        "kind": payload.get("kind"),
        "trace_id": trace.get("trace_id"),
        "trace_status": trace.get("status"),
        "experts_consulted": _as_list(payload.get("experts_consulted")),
        "perspective_count": len(_as_list(payload.get("perspectives"))),
        "agreement_count": len(_as_list(payload.get("agreements"))),
        "disagreement_count": len(_as_list(payload.get("disagreements"))),
        "cost_usd": _float_value(payload.get("cost_usd")),
        "capacity": capacity,
        "metered_fallback_allowed": budget_capacity.get("metered_fallback_allowed"),
    }


def _backend_provider_ok(capacity: dict[str, Any], backend: ValidationBackend) -> bool:
    provider = str(capacity.get("provider", ""))
    if backend == "local":
        return provider == "local"
    return provider.startswith("plan_quota:")


def validate_consult_payload(
    payload: dict[str, Any],
    *,
    expected_backend: ValidationBackend,
    cost_ceiling_usd: float = 0.0,
    forbidden_values: tuple[str, ...] = (),
) -> tuple[MCPConsultValidationCheck, ...]:
    """Validate a consult artifact's machine contract.

    These checks are intentionally deterministic and side-effect oriented. They
    do not score whether the answer is insightful.
    """

    checks: list[MCPConsultValidationCheck] = []
    checks.append(MCPConsultValidationCheck("payload_object", "passed", "consult response is a JSON object"))

    if "error_code" in payload:
        code = str(payload.get("error_code") or "UNKNOWN")
        message = str(payload.get("message") or "")
        checks.append(MCPConsultValidationCheck("tool_result", "failed", f"{code}: {message}"))
        return tuple(checks)
    checks.append(MCPConsultValidationCheck("tool_result", "passed", "consult tool returned an artifact"))

    trace = _as_dict(payload.get("trace"))
    capacity = _as_dict(payload.get("capacity"))
    collaboration = _as_dict(payload.get("collaboration"))
    collaboration_contract = _as_dict(collaboration.get("contract"))
    task = _as_dict(collaboration.get("task"))
    budget_capacity = _as_dict(collaboration.get("budget_capacity_contract"))
    dissent = _as_dict(collaboration.get("dissent_handling"))
    result_artifact = _as_dict(collaboration.get("result_artifact"))

    checks.append(
        _check(
            "consult_envelope",
            payload.get("schema_version") == consult_core.CONSULT_SCHEMA_VERSION
            and payload.get("kind") == consult_core.CONSULT_KIND,
            "consult schema_version and kind match deepr-consult-v1",
            "consult schema_version or kind is wrong",
        )
    )
    checks.append(
        _check(
            "trace_envelope",
            trace.get("schema_version") == "deepr-consult-trace-v1"
            and trace.get("kind") == "deepr.expert.consult_trace",
            "trace ref uses deepr-consult-trace-v1",
            "trace ref is missing or malformed",
        )
    )
    checks.append(
        _check(
            "collaboration_envelope",
            collaboration.get("schema_version") == consult_core.COLLABORATION_SCHEMA_VERSION
            and collaboration.get("kind") == consult_core.COLLABORATION_KIND,
            "collaboration block uses deepr-expert-collaboration-v1",
            "collaboration block is missing or malformed",
        )
    )
    trace_id = str(trace.get("trace_id") or "")
    checks.append(
        _check(
            "trace_linkage",
            bool(trace_id)
            and task.get("consult_trace_id") == trace_id
            and task.get("shared_task_trace_id") == trace_id,
            "consult trace id is linked across trace and collaboration task",
            "consult trace id is missing or not linked across collaboration metadata",
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
    checks.append(
        _check(
            "no_metered_fallback",
            capacity.get("live_metered_fallback") is False and budget_capacity.get("metered_fallback_allowed") is False,
            "live metered fallback is disabled in capacity and collaboration metadata",
            "live metered fallback is not disabled everywhere",
        )
    )
    cost = _float_value(payload.get("cost_usd"))
    contract_cost = _float_value(_as_dict(payload.get("contract")).get("cost_usd"))
    budget_cost = _float_value(budget_capacity.get("actual_cost_usd"))
    checks.append(
        _check(
            "cost_ceiling",
            cost <= cost_ceiling_usd and contract_cost <= cost_ceiling_usd and budget_cost <= cost_ceiling_usd,
            f"cost fields are within ceiling ${cost_ceiling_usd:.4f}",
            f"one or more cost fields exceed ceiling ${cost_ceiling_usd:.4f}",
        )
    )
    perspectives = _as_list(payload.get("perspectives"))
    checks.append(
        _warning_check(
            "perspectives_present",
            bool(perspectives),
            f"{len(perspectives)} perspective(s) returned",
            "no expert perspectives returned; create or select experts before relying on consult",
        )
    )
    checks.append(
        _check(
            "dissent_contract",
            isinstance(payload.get("agreements"), list)
            and isinstance(payload.get("disagreements"), list)
            and dissent.get("dissent_preserved") is True
            and dissent.get("synthesis_is_not_truth_adjudication") is True,
            "agreement and disagreement fields are explicit and dissent is preserved",
            "dissent handling metadata is missing or unsafe",
        )
    )
    checks.append(
        _check(
            "host_action_boundary",
            collaboration_contract.get("host_orchestrated") is True
            and collaboration_contract.get("deepr_enacts_downstream_actions") is False
            and collaboration_contract.get("semantic_verdict") is False,
            "Deepr recommends through a host-owned action boundary",
            "collaboration metadata blurs host action or semantic-verdict boundaries",
        )
    )
    checks.append(
        _check(
            "result_artifact_refs",
            result_artifact.get("schema_version") == consult_core.CONSULT_SCHEMA_VERSION
            and result_artifact.get("answer_field") == "answer"
            and result_artifact.get("perspectives_field") == "perspectives",
            "collaboration metadata names result artifact fields",
            "collaboration metadata does not name result artifact fields",
        )
    )
    checks.append(
        _check(
            "secret_redaction",
            not _safe_json_contains(payload, forbidden_values),
            "provided auth secret was not echoed in the consult artifact",
            "provided auth secret appeared in the consult artifact",
        )
    )
    return tuple(checks)


def _offline_capacity(backend: ValidationBackend, *, plan: str | None, model: str | None) -> dict[str, Any]:
    if backend == "plan":
        provider = f"plan_quota:{plan or 'codex'}"
        resolved_model = model or plan or "codex"
    else:
        provider = "local"
        resolved_model = model or "offline-contract-fixture"
    return {
        "synthesis_backend": backend,
        "provider": provider,
        "model": resolved_model,
        "live_metered_fallback": False,
    }


def build_offline_consult_fixture(
    *,
    question: str = DEFAULT_VALIDATION_QUESTION,
    experts: tuple[str, ...] = (),
    backend: ValidationBackend = "local",
    plan: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Build a no-model consult artifact that exercises the consult contract."""

    names = experts or ("MCP Validation Expert",)
    trace_id = "consult_abcdef123456"
    perspectives = [
        {
            "expert_name": name,
            "domain": "mcp consult validation",
            "response": (
                "Offline contract fixture: validates schema, capacity, trace, dissent, "
                "and host-action boundaries without judging answer meaning."
            ),
            "confidence": 0.9,
            "cost": 0.0,
            "context": {
                "source": "belief_store",
                "selection": "offline_contract_fixture",
                "beliefs_included": 1,
            },
        }
        for name in names
    ]
    result: dict[str, Any] = {
        "perspectives": perspectives,
        "synthesis": "Offline fixture for external-agent consult validation.",
        "agreements": ["The consult contract must preserve no-metered capacity posture."],
        "disagreements": ["Semantic quality is intentionally left to reviewed human or calibrated-model judging."],
        "requested_budget_usd": 0.0,
        "total_cost": 0.0,
        "shared_task_trace_id": trace_id,
        "synthesis_status": "completed",
    }
    capacity = _offline_capacity(backend, plan=plan, model=model)
    payload = consult_core.build_consult_payload(question, result)
    payload["capacity"] = capacity
    trace = build_consult_trace(
        question=question,
        requested_experts=list(experts),
        max_experts=len(names),
        budget=0.0,
        payload=payload,
        result=result,
        capacity=capacity,
        trace_id=trace_id,
    )
    payload["trace"] = {
        "schema_version": trace["schema_version"],
        "kind": trace["kind"],
        "trace_id": trace["trace_id"],
        "status": trace["status"],
        "recorded": False,
        "checks_ran": [check["name"] for check in trace.get("checks", []) if isinstance(check, dict)],
    }
    consult_core.attach_collaboration_runtime(payload, result=result, capacity=capacity, trace=payload["trace"])
    return payload


def _report(
    *,
    mode: ValidationMode,
    backend: ValidationBackend,
    question: str,
    experts: tuple[str, ...],
    checks: tuple[MCPConsultValidationCheck, ...],
    endpoint: str | None = None,
    plan: str | None = None,
    payload: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> MCPConsultValidationReport:
    return MCPConsultValidationReport(
        mode=mode,
        backend=backend,
        question=question,
        requested_experts=experts,
        endpoint=endpoint,
        plan=plan,
        checks=checks,
        consult_summary=_summarize_consult(payload) if payload else {},
        error=error or {},
    )


def run_offline_consult_validation(
    *,
    question: str = DEFAULT_VALIDATION_QUESTION,
    experts: tuple[str, ...] = (),
    backend: ValidationBackend = "local",
    plan: str | None = None,
    model: str | None = None,
) -> MCPConsultValidationReport:
    """Run a deterministic $0 fixture validation without a model or endpoint."""

    payload = build_offline_consult_fixture(
        question=question,
        experts=experts,
        backend=backend,
        plan=plan,
        model=model,
    )
    checks = validate_consult_payload(payload, expected_backend=backend)
    return _report(
        mode="offline", backend=backend, question=question, experts=experts, checks=checks, plan=plan, payload=payload
    )


async def run_in_process_consult_validation(
    *,
    question: str = DEFAULT_VALIDATION_QUESTION,
    experts: tuple[str, ...] = (),
    backend: ValidationBackend = "local",
    local_model: str | None = None,
    plan: str | None = None,
    plan_model: str | None = None,
    timeout_seconds: float = 60.0,
) -> MCPConsultValidationReport:
    """Run a live no-metered consult through the same handler MCP uses."""

    if backend == "plan" and not plan:
        config_error: dict[str, Any] = {
            "error_code": "INVALID_BACKEND",
            "message": "plan is required when backend is plan",
        }
        config_checks = (MCPConsultValidationCheck("backend_configuration", "failed", config_error["message"]),)
        return _report(
            mode="in_process",
            backend=backend,
            question=question,
            experts=experts,
            checks=config_checks,
            plan=plan,
            error=config_error,
        )

    try:
        payload = await asyncio.wait_for(
            consult_experts_tool(
                question=question,
                experts=list(experts) or None,
                max_experts=max(len(experts), 1),
                budget=0.0,
                synthesis_backend=backend,
                local_model=local_model,
                plan=plan,
                plan_model=plan_model,
            ),
            timeout=timeout_seconds,
        )
    except (TimeoutError, OSError, RuntimeError, ValueError) as exc:
        call_error: dict[str, Any] = {"error_code": "CONSULT_VALIDATION_FAILED", "message": str(exc)}
        call_checks = (MCPConsultValidationCheck("live_consult_call", "failed", str(exc)),)
        return _report(
            mode="in_process",
            backend=backend,
            question=question,
            experts=experts,
            checks=call_checks,
            plan=plan,
            error=call_error,
        )

    validation_checks = validate_consult_payload(payload, expected_backend=backend)
    validation_error: dict[str, Any] | None = payload if "error_code" in payload else None
    return _report(
        mode="in_process",
        backend=backend,
        question=question,
        experts=experts,
        checks=validation_checks,
        plan=plan,
        payload=payload,
        error=validation_error,
    )


def _tool_arguments(
    *,
    question: str,
    experts: tuple[str, ...],
    backend: ValidationBackend,
    local_model: str | None,
    plan: str | None,
    plan_model: str | None,
) -> dict[str, Any]:
    args: dict[str, Any] = {
        "_approved": True,
        "question": question,
        "max_experts": max(len(experts), 1),
        "synthesis_backend": backend,
        "budget": 0,
    }
    if experts:
        args["experts"] = list(experts)
    if local_model:
        args["local_model"] = local_model
    if plan:
        args["plan"] = plan
    if plan_model:
        args["plan_model"] = plan_model
    return args


def _parse_tool_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {"error_code": "INVALID_MCP_RESULT", "message": "tools/call result was not an object"}
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    content = result.get("content")
    if not isinstance(content, list) or not content:
        return {"error_code": "INVALID_MCP_RESULT", "message": "tools/call returned no content"}
    first = content[0]
    if not isinstance(first, dict) or not isinstance(first.get("text"), str):
        return {"error_code": "INVALID_MCP_RESULT", "message": "tools/call content did not include text JSON"}
    try:
        payload = json.loads(first["text"])
    except json.JSONDecodeError as exc:
        return {"error_code": "INVALID_MCP_RESULT", "message": f"tools/call text was not JSON: {exc}"}
    if not isinstance(payload, dict):
        return {"error_code": "INVALID_MCP_RESULT", "message": "tools/call JSON payload was not an object"}
    return payload


async def run_http_consult_validation(
    url: str,
    *,
    auth_token: str | None = None,
    question: str = DEFAULT_VALIDATION_QUESTION,
    experts: tuple[str, ...] = (),
    backend: ValidationBackend = "local",
    local_model: str | None = None,
    plan: str | None = None,
    plan_model: str | None = None,
    timeout_seconds: float = 60.0,
) -> MCPConsultValidationReport:
    """Call a remote HTTP MCP endpoint and validate its consult artifact."""

    if backend == "plan" and not plan:
        config_error: dict[str, Any] = {
            "error_code": "INVALID_BACKEND",
            "message": "plan is required when backend is plan",
        }
        config_checks = (MCPConsultValidationCheck("backend_configuration", "failed", config_error["message"]),)
        return _report(
            mode="http",
            backend=backend,
            question=question,
            experts=experts,
            checks=config_checks,
            endpoint=url.rstrip("/"),
            plan=plan,
            error=config_error,
        )

    endpoint = url.rstrip("/")
    client = HttpClient(endpoint, timeout=timeout_seconds, auth_token=auth_token)
    check_results: list[MCPConsultValidationCheck] = []
    payload: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    try:
        await client.connect()
        init = await client.send(HttpMessage(id="consult-validation-init", method="initialize", params={}))
        if init is None:
            detail = "initialize returned no response"
            check_results.append(MCPConsultValidationCheck("mcp_initialize", "failed", detail))
            error = {"error_code": "MCP_INITIALIZE_FAILED", "message": detail}
            return _report(
                mode="http",
                backend=backend,
                question=question,
                experts=experts,
                endpoint=endpoint,
                plan=plan,
                checks=tuple(check_results),
                error=error,
            )
        if init.error:
            detail = str(init.error.get("message", "initialize failed"))
            check_results.append(MCPConsultValidationCheck("mcp_initialize", "failed", detail))
            error = {"error_code": "MCP_INITIALIZE_FAILED", "message": detail}
            return _report(
                mode="http",
                backend=backend,
                question=question,
                experts=experts,
                endpoint=endpoint,
                plan=plan,
                checks=tuple(check_results),
                error=error,
            )
        check_results.append(MCPConsultValidationCheck("mcp_initialize", "passed", "endpoint accepted initialize"))
        response = await client.send(
            HttpMessage(
                id="consult-validation-call",
                method="tools/call",
                params={
                    "name": "deepr_consult_experts",
                    "arguments": _tool_arguments(
                        question=question,
                        experts=experts,
                        backend=backend,
                        local_model=local_model,
                        plan=plan,
                        plan_model=plan_model,
                    ),
                },
            )
        )
        if response is None:
            detail = "tools/call returned no response"
            check_results.append(MCPConsultValidationCheck("mcp_tools_call", "failed", detail))
            error = {"error_code": "MCP_TOOLS_CALL_FAILED", "message": detail}
            return _report(
                mode="http",
                backend=backend,
                question=question,
                experts=experts,
                endpoint=endpoint,
                plan=plan,
                checks=tuple(check_results),
                error=error,
            )
        if response.error:
            detail = str(response.error.get("message", "tools/call failed"))
            check_results.append(MCPConsultValidationCheck("mcp_tools_call", "failed", detail))
            error = {"error_code": "MCP_TOOLS_CALL_FAILED", "message": detail}
            return _report(
                mode="http",
                backend=backend,
                question=question,
                experts=experts,
                endpoint=endpoint,
                plan=plan,
                checks=tuple(check_results),
                error=error,
            )
        payload = _parse_tool_result(response.result)
        check_results.append(
            MCPConsultValidationCheck("mcp_tools_call", "passed", "deepr_consult_experts returned a JSON object")
        )
        check_results.extend(
            validate_consult_payload(
                payload,
                expected_backend=backend,
                forbidden_values=(auth_token,) if auth_token else (),
            )
        )
        if "error_code" in payload:
            error = payload
    except (TimeoutError, OSError, RuntimeError, ValueError) as exc:
        error = {"error_code": "MCP_CONSULT_VALIDATION_FAILED", "message": str(exc)}
        check_results.append(MCPConsultValidationCheck("mcp_consult_validation", "failed", str(exc)))
    finally:
        await client.disconnect()

    return _report(
        mode="http",
        backend=backend,
        question=question,
        experts=experts,
        endpoint=endpoint,
        plan=plan,
        checks=tuple(check_results),
        payload=payload,
        error=error,
    )
