#!/usr/bin/env python3
"""Block growth of unaudited paid-provider dispatch boundaries.

Provider SDK construction is intentionally concentrated in adapters, bounded
services, read-only diagnostics, and currently gated legacy modules. This AST
ratchet makes every new construction site and raw paid-provider endpoint an
explicit review event instead of a silent money path. Counts may shrink without
updating the baseline; they may never grow or appear in a new file.
"""

from __future__ import annotations

import ast
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SCAN_ROOTS = (_ROOT / "src" / "deepr", _ROOT / "scripts")
_TARGETS = {
    "openai.OpenAI",
    "openai.AsyncOpenAI",
    "openai.AzureOpenAI",
    "openai.AsyncAzureOpenAI",
    "anthropic.Anthropic",
    "anthropic.AsyncAnthropic",
    "AsyncAnthropic",
    "google.genai.Client",
    "xai_sdk.Client",
    "azure.ai.projects.AIProjectClient",
    "azure.ai.agents.AgentsClient",
}
_HTTPX_CLIENT_CONSTRUCTORS = {
    "httpx.Client",
    "httpx.AsyncClient",
}
_FIXED_ENDPOINT_SDK_CONSTRUCTORS = {
    "openai.OpenAI",
    "openai.AsyncOpenAI",
    "anthropic.Anthropic",
    "anthropic.AsyncAnthropic",
    "AsyncAnthropic",
}
_AZURE_ENDPOINT_SDK_CONSTRUCTORS = {
    "openai.AzureOpenAI",
    "openai.AsyncAzureOpenAI",
    "azure.ai.projects.AIProjectClient",
    "azure.ai.agents.AgentsClient",
}
_ENDPOINT_GUARDS = {
    "deepr.providers.dispatch_authority.require_official_paid_client",
    "deepr.providers.dispatch_authority.require_official_paid_endpoint",
}
_PAID_ENDPOINT_FRAGMENTS = (
    "api.anthropic.com",
    "api.openai.com",
    "api.x.ai",
    "generativelanguage.googleapis.com",
    "openai.azure.com",
    "services.ai.azure.com",
)
_METERED_WRAPPERS = {
    "deepr.services.metered_call.execute_reserved_sync_call",
    "deepr.services.metered_call.execute_reserved_async_call",
    "deepr.services.metered_call.execute_reserved_async_stream",
    "deepr.services.metered_call.execute_reserved_fixed_cost_async_call",
    "deepr.experts.chat_metered.execute_metered_chat_provider_call",
    "deepr.experts.chat_metered.execute_metered_chat_provider_stream",
}

# Audited 2026-07-25. A lower count is an improvement. A higher count or new
# path fails until the site has a durable transaction or an explicit gate and
# this review baseline is deliberately amended.
_BASELINE = {
    "scripts/analyze_doc_gaps.py": 0,
    "scripts/testing/check_vector_store.py": 0,
    "src/deepr/backends/local.py": 1,
    "src/deepr/cli/commands/eval.py": 1,
    "src/deepr/cli/commands/providers.py": 3,
    "src/deepr/experts/chat_api_backends.py": 2,
    "src/deepr/experts/chat_research_ops.py": 0,
    "src/deepr/experts/citation_validator.py": 1,
    "src/deepr/experts/claim_extraction.py": 1,
    "src/deepr/experts/claim_verification.py": 1,
    "src/deepr/experts/conflict_resolver.py": 0,
    "src/deepr/experts/consensus.py": 5,
    "src/deepr/experts/consult.py": 1,
    "src/deepr/experts/consult_quality_judges.py": 2,
    "src/deepr/experts/curriculum.py": 1,
    "src/deepr/experts/gap_discovery.py": 1,
    "src/deepr/experts/map_reduce.py": 1,
    "src/deepr/experts/multi_pass.py": 1,
    "src/deepr/experts/reflection.py": 1,
    "src/deepr/experts/report_absorber.py": 1,
    "src/deepr/experts/task_planner.py": 1,
    "src/deepr/providers/anthropic_provider.py": 1,
    "src/deepr/providers/azure_foundry_provider.py": 2,
    "src/deepr/providers/azure_provider.py": 2,
    "src/deepr/providers/gemini_provider.py": 1,
    "src/deepr/providers/grok_provider.py": 1,
    "src/deepr/providers/openai_provider.py": 1,
    "src/deepr/services/context_builder.py": 1,
    "src/deepr/services/context_index.py": 2,
    "src/deepr/services/doc_reviewer.py": 1,
    "src/deepr/services/expert_validator.py": 1,
    "src/deepr/services/prompt_refiner.py": 1,
    "src/deepr/services/research_planner.py": 3,
    "src/deepr/services/research_reviewer.py": 1,
    "src/deepr/services/team_architect.py": 2,
}

# Raw HTTP and configurable-provider endpoint references audited on
# 2026-07-25. This catches paid REST calls that never construct an SDK client.
_ENDPOINT_BASELINE = {
    "scripts/benchmark_models.py": 9,
    "scripts/discover_models.py": 7,
    "scripts/setup_local.py": 0,
    "src/deepr/backends/plan_quota/quota_probes.py": 1,
    "src/deepr/cli/commands/providers.py": 0,
    "src/deepr/config.py": 2,
    "src/deepr/experts/consult_quality_judges.py": 0,
    "src/deepr/mcp/security/network.py": 2,
    "src/deepr/providers/dispatch_authority.py": 6,
    "src/deepr/providers/grok_provider.py": 0,
}
_ACTIVE_SPEND_DEFAULT_NAMES = frozenset(
    {
        "budget",
        "budget_limit",
        "budget_per_operation",
        "budget_per_session",
        "budget_total",
        "daily_limit",
        "default_budget",
        "max_cost",
        "max_cost_per_job",
        "max_daily_cost",
        "max_monthly_cost",
        "max_per_call",
        "max_per_operation",
        "max_weekly_cost",
        "monthly_limit",
        "operation_budget",
    }
)
_MAX_AUDITED_ACTIVE_SPEND_DEFAULT_USD = 5.0

_REQUIRED_SAFETY_FRAGMENTS = {
    "scripts/benchmark_models.py": (
        "api_provider_benchmark_validation",
        "--dry-run and --validate cannot be combined",
    ),
    "scripts/analyze_doc_gaps.py": ("ANALYSIS_EXECUTION_ENABLED = False", "return 2"),
    "scripts/discover_models.py": (
        "LIVE_MODEL_DISCOVERY_ENABLED = False",
        "def require_live_model_discovery()",
    ),
    "src/deepr/agents/contract.py": ("GENERIC_SUBAGENT_EXECUTION_ENABLED = False",),
    "src/deepr/evals/local_compare.py": ("CLI_JUDGE_EXECUTION_ENABLED = False",),
    "src/deepr/experts/heartbeat.py": ("REMOTE_HEARTBEAT_EXECUTION_ENABLED = False",),
    "src/deepr/experts/learner.py": (
        "_MAX_RECONCILIATION_JOBS = 10",
        "_MAX_PROVIDER_STATUS_PASSES = 1",
        "Automatic provider polling stopped",
        "External paper fetch is disabled",
    ),
    "src/deepr/experts/portraits.py": (
        "_require_attested_local_image_capacity()",
        "require_metered_expert_mutation(",
    ),
    "src/deepr/experts/skills/executor.py": (
        "SKILL_TOOL_EXECUTION_DISABLED",
        "return _blocked_result(tool)",
    ),
    "src/deepr/mcp/client/base.py": ("raise MCPClientError(_OUTBOUND_MCP_BLOCK",),
    "src/deepr/mcp/client/pool.py": (
        "_OUTBOUND_MCP_CONNECTION_BLOCK",
        "MCPErrorCode.COST_ACCOUNTING_UNAVAILABLE",
    ),
    "src/deepr/mcp/provider/sampling.py": ("raise SamplingFallbackDisabledError(",),
    "src/deepr/mcp/transport/http.py": (
        "Outbound MCP HTTP clients are disabled",
        "Outbound MCP HTTP requests are disabled",
        "Outbound MCP HTTP subscriptions are disabled",
        "Outbound MCP HTTP streaming is disabled",
    ),
    "src/deepr/services/research_bounds.py": (
        "def require_research_storage_accounting()",
        'code="research_file_storage_unbounded"',
    ),
    "src/deepr/storage/blob.py": ("_require_blob_storage_accounting()",),
    "src/deepr/tools/search_backend.py": ("SearXNG dispatch is disabled",),
    "src/deepr/tools/web_search.py": (
        '_REVIEWED_DDGS_VERSION = "9.14.4"',
        'ddgs_class(proxy=None).text(query, max_results=num_results, backend="duckduckgo")',
    ),
    "src/deepr/webhooks/tunnel.py": ("Ngrok tunnel startup is disabled",),
    "src/deepr/web/app.py": ("external_metadata_cost_unverified",),
    "src/deepr/backends/capacity.py": ("trust_env=False, follow_redirects=False",),
    "src/deepr/backends/plan_quota/quota_probes.py": ("trust_env=False, follow_redirects=False",),
    "src/deepr/providers/dispatch_authority.py": (
        "def require_unproxied_paid_transport()",
        "def require_official_paid_client(",
        "def require_official_paid_endpoint(",
        "def require_exact_provider_model(",
        "def require_no_unaccounted_paid_webhook(",
        "def require_bounded_paid_request_payload(",
        "Generic or injected paid SDK clients are disabled",
        'frozenset({"http_proxy", "https_proxy", "all_proxy"})',
        '"openai_base_url": "openai"',
        '"anthropic_base_url": "anthropic"',
        '"google_gemini_base_url": "gemini"',
        '"azure_openai_endpoint": "azure"',
        '"azure_project_endpoint": "azure-foundry"',
    ),
    "src/deepr/experts/research_cost_gate.py": ("require_unproxied_paid_transport()",),
    "src/deepr/services/metered_call.py": ("require_unproxied_paid_transport()",),
    "src/deepr/security/permissions.py": (
        "0 permits only zero-dollar work",
        "Estimated cost cannot be negative",
        "Empty allowlists deny access",
        "allow_external_requests: bool = False",
    ),
    "src/deepr/mcp/client/profile.py": ("0 permits only $0 calls",),
    "src/deepr/mcp/client/budget_propagator.py": ("Zero never means unlimited",),
    "src/deepr/experts/cost_safety.py": (
        "_ABSOLUTE_TOTAL_SPEND_USD = 5.0",
        "ABSOLUTE_MAX_PER_OPERATION: float = _ABSOLUTE_TOTAL_SPEND_USD",
        "ABSOLUTE_MAX_MONTHLY: float = _ABSOLUTE_TOTAL_SPEND_USD",
    ),
    "src/deepr/core/cost_caps.py": (
        '"per_job": 5.0',
        '"daily": 5.0',
        '"weekly": 5.0',
        '"monthly": 5.0',
        'monthly = min(monthly, _ABSOLUTE_CEILINGS["monthly"])',
    ),
    "src/deepr/experts/skills/definition.py": (
        "_MAX_PER_CALL_USD = 1.0",
        "_MAX_DEFAULT_BUDGET_USD = 5.0",
    ),
    "src/deepr/cli/commands/doctor.py": ("Configured; live metadata request blocked",),
    "src/deepr/cli/commands/keys.py": ("external_metadata_cost_unverified",),
    "src/deepr/cli/commands/providers.py": ("Live provider model discovery is blocked",),
    "scripts/setup_azure.py": (
        "cannot enforce the operator's total dollar ceiling",
        "return 2",
    ),
    "scripts/check_campaign.py": ("EXTERNAL_METADATA_EXECUTION_ENABLED = False", "return 2"),
    "scripts/testing/check_job_status.py": ("EXTERNAL_METADATA_EXECUTION_ENABLED = False", "return 2"),
    "scripts/testing/check_vector_store.py": ("EXTERNAL_METADATA_EXECUTION_ENABLED = False", "return 2"),
    "scripts/testing/run_expert_tests.ps1": ("BLOCKED:", "exit 2"),
    "scripts/testing/run_expert_tests.sh": ("BLOCKED:", "exit 2"),
    "scripts/testing/test_keyboards_cli.bat": ("BLOCKED:", "exit /b 2"),
    "scripts/testing/test_keyboards_cli.sh": ("BLOCKED:", "exit 2"),
    "scripts/destroy_azure.py": ("CLOUD_MUTATION_EXECUTION_ENABLED = False", "return 2"),
    "scripts/monitor_research_jobs.py": ("MONITOR_EXECUTION_ENABLED = False", "return 2"),
    "scripts/Utility_Cancell_Active_Jobs.ps1": ("BLOCKED:", "exit 2"),
    "src/deepr/utils/check_expert_status.py": ("EXTERNAL_METADATA_EXECUTION_ENABLED = False", "return 2"),
    "src/deepr/utils/download_expert_reports.py": (
        "EXTERNAL_METADATA_EXECUTION_ENABLED = False",
        "return 2",
    ),
    "src/deepr/utils/retrieve_expert_reports.py": (
        "EXTERNAL_METADATA_EXECUTION_ENABLED = False",
        "return 2",
    ),
    "src/deepr/utils/integrate_pending_research.py": (
        "EXTERNAL_METADATA_EXECUTION_ENABLED = False",
        "return 2",
    ),
    "deploy/aws/template.yaml": ("BLOCKED:", "ReferenceOnly: true"),
    "deploy/azure/main.bicep": ("BLOCKED:", "targetScope = 'reference-only'"),
    "deploy/gcp/main.tf": ("BLOCKED:", 'required_version = "< 0.0.0"'),
    "deploy/mcp-http/aws-ecs-fargate/template.yaml": ("BLOCKED:", "ReferenceOnly: true"),
    "deploy/mcp-http/azure-container-apps/main.bicep": (
        "BLOCKED:",
        "targetScope = 'reference-only'",
    ),
    "deploy/mcp-http/gcp-cloud-run/main.tf": ("BLOCKED:", 'required_version = "< 0.0.0"'),
    "deploy/mcp-http/cloudflare-worker/worker.mjs": ("BLOCKED:", "No fetch handler"),
    "deploy/mcp-http/cloudflare-worker/wrangler.toml.example": ("BLOCKED:", "no deployable"),
}

_FORBIDDEN_CLOUD_SCRIPT_FRAGMENTS = (
    "aws cloudformation",
    "sam deploy",
    "az group create",
    "az deployment",
    "gcloud services",
    "terraform apply",
    "aws s3 rm",
    "sam delete",
    "az group delete",
    "gcloud config",
    "terraform destroy",
    "curl ",
)
_CLOUD_DEPLOY_SCRIPTS = (
    "deploy/aws/deploy.sh",
    "deploy/aws/destroy.sh",
    "deploy/aws/validate.sh",
    "deploy/azure/deploy.sh",
    "deploy/azure/destroy.sh",
    "deploy/azure/validate.sh",
    "deploy/gcp/deploy.sh",
    "deploy/gcp/destroy.sh",
    "deploy/gcp/validate.sh",
)


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name.split(".")[0]] = item.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for item in node.names:
                aliases[item.asname or item.name] = f"{node.module}.{item.name}"
    return aliases


def _dotted_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = _dotted_name(node.value)
        return f"{owner}.{node.attr}" if owner else None
    return None


def _resolved_call_name(node: ast.Call, aliases: dict[str, str]) -> str | None:
    raw = _dotted_name(node.func)
    if not raw:
        return None
    root, separator, suffix = raw.partition(".")
    imported = aliases.get(root)
    if not imported:
        return raw
    return f"{imported}.{suffix}" if separator else imported


def _dict_keyword_value(node: ast.expr, *names: str) -> ast.expr | None:
    if not isinstance(node, ast.Dict):
        return None
    for key, value in zip(node.keys, node.values, strict=True):
        if isinstance(key, ast.Constant) and isinstance(key.value, str) and key.value in names:
            return value
    return None


def _gemini_sdk_retry_is_disabled(node: ast.Call) -> bool:
    http_options = next((keyword.value for keyword in node.keywords if keyword.arg == "http_options"), None)
    if http_options is None:
        return False
    retry_options = _dict_keyword_value(http_options, "retry_options", "retryOptions")
    if retry_options is None:
        return False
    attempts = _dict_keyword_value(retry_options, "attempts")
    return bool(isinstance(attempts, ast.Constant) and type(attempts.value) is int and attempts.value == 1)


def _literal_false(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is False


def _call_keyword_value(node: ast.Call, name: str) -> ast.expr | None:
    return next((keyword.value for keyword in node.keywords if keyword.arg == name), None)


def _httpx_transport_is_hardened(node: ast.Call) -> bool:
    return _literal_false(_call_keyword_value(node, "trust_env")) and _literal_false(
        _call_keyword_value(node, "follow_redirects")
    )


def _gemini_sdk_transport_is_hardened(node: ast.Call) -> bool:
    http_options = _call_keyword_value(node, "http_options")
    if http_options is None:
        return False
    for option_names in (("client_args", "clientArgs"), ("async_client_args", "asyncClientArgs")):
        client_args = _dict_keyword_value(http_options, *option_names)
        if client_args is None:
            return False
        if not _literal_false(_dict_keyword_value(client_args, "trust_env")):
            return False
        if not _literal_false(_dict_keyword_value(client_args, "follow_redirects")):
            return False
    return True


def _keyword_is_present(node: ast.Call, name: str) -> bool:
    value = _call_keyword_value(node, name)
    return value is not None and not (isinstance(value, ast.Constant) and value.value is None)


def _gemini_sdk_endpoint_is_pinned(node: ast.Call) -> bool:
    mode_is_developer_api = _literal_false(_call_keyword_value(node, "vertexai")) or _literal_false(
        _call_keyword_value(node, "enterprise")
    )
    http_options = _call_keyword_value(node, "http_options")
    return (
        mode_is_developer_api and http_options is not None and _dict_keyword_value(http_options, "base_url") is not None
    )


def _enclosing_function_has_endpoint_guard(tree: ast.AST, target: ast.Call, aliases: dict[str, str]) -> bool:
    candidates: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
            child is target for child in ast.walk(node)
        ):
            candidates.append(node)
    if not candidates:
        return False
    enclosing = min(candidates, key=lambda node: len(list(ast.walk(node))))
    return any(
        isinstance(node, ast.Call) and _resolved_call_name(node, aliases) in _ENDPOINT_GUARDS
        for node in ast.walk(enclosing)
    )


def _constant_money_value(node: ast.expr | None) -> float | None:
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return float(node.value)
    return None


def _active_spend_default_violations(tree: ast.AST, relative: str) -> list[str]:
    """Reject new hard-coded active spend defaults above the release ceiling."""
    violations: list[str] = []

    def check(name: str | None, value_node: ast.expr | None, lineno: int) -> None:
        if not name or name.lower() not in _ACTIVE_SPEND_DEFAULT_NAMES:
            return
        value = _constant_money_value(value_node)
        if value is not None and value > _MAX_AUDITED_ACTIVE_SPEND_DEFAULT_USD:
            violations.append(
                f"{relative}:{lineno}: active spend default {name}=${value:g} exceeds "
                f"${_MAX_AUDITED_ACTIVE_SPEND_DEFAULT_USD:g}"
            )

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            positional = [*node.args.posonlyargs, *node.args.args]
            if node.args.defaults:
                for argument, default in zip(positional[-len(node.args.defaults) :], node.args.defaults, strict=True):
                    check(argument.arg, default, node.lineno)
            for argument, default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True):
                check(argument.arg, default, node.lineno)
        elif isinstance(node, ast.Call):
            for keyword in node.keywords:
                check(keyword.arg, keyword.value, node.lineno)
    return violations


def _scan() -> tuple[Counter[str], Counter[str], list[str], list[str]]:
    constructor_counts: Counter[str] = Counter()
    endpoint_counts: Counter[str] = Counter()
    parse_errors: list[str] = []
    unbounded_metered_calls: list[str] = []
    for scan_root in _SCAN_ROOTS:
        for path in scan_root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            relative = path.relative_to(_ROOT).as_posix()
            if relative == "scripts/check_paid_api_boundaries.py":
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            except (OSError, UnicodeError, SyntaxError) as exc:
                parse_errors.append(f"{relative}: {exc}")
                continue
            aliases = _import_aliases(tree)
            unbounded_metered_calls.extend(_active_spend_default_violations(tree, relative))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    resolved_call = _resolved_call_name(node, aliases)
                    if resolved_call in _TARGETS:
                        constructor_counts[relative] += 1
                    if resolved_call == "google.genai.Client" and not _gemini_sdk_retry_is_disabled(node):
                        unbounded_metered_calls.append(
                            f"{relative}:{getattr(node, 'lineno', '?')}: Gemini client does not pin SDK attempts=1"
                        )
                    if resolved_call == "google.genai.Client" and not _gemini_sdk_transport_is_hardened(node):
                        unbounded_metered_calls.append(
                            f"{relative}:{getattr(node, 'lineno', '?')}: "
                            "Gemini client does not disable proxy inheritance and redirects"
                        )
                    if resolved_call == "google.genai.Client" and not _gemini_sdk_endpoint_is_pinned(node):
                        unbounded_metered_calls.append(
                            f"{relative}:{getattr(node, 'lineno', '?')}: "
                            "Gemini client does not pin Developer API mode and its official endpoint"
                        )
                    if resolved_call in _FIXED_ENDPOINT_SDK_CONSTRUCTORS and not _keyword_is_present(node, "base_url"):
                        unbounded_metered_calls.append(
                            f"{relative}:{getattr(node, 'lineno', '?')}: "
                            "paid SDK client does not pin an explicit reviewed base_url"
                        )
                    if resolved_call in _AZURE_ENDPOINT_SDK_CONSTRUCTORS and not (
                        _keyword_is_present(node, "azure_endpoint")
                        or _keyword_is_present(node, "endpoint")
                        or _keyword_is_present(node, "base_url")
                    ):
                        unbounded_metered_calls.append(
                            f"{relative}:{getattr(node, 'lineno', '?')}: "
                            "Azure SDK client does not pin an explicit reviewed endpoint"
                        )
                    if resolved_call in _HTTPX_CLIENT_CONSTRUCTORS and not _httpx_transport_is_hardened(node):
                        unbounded_metered_calls.append(
                            f"{relative}:{getattr(node, 'lineno', '?')}: "
                            "httpx client must set trust_env=False and follow_redirects=False"
                        )
                    if resolved_call in _METERED_WRAPPERS:
                        if not any(
                            keyword.arg == "max_cost_per_job"
                            and not (isinstance(keyword.value, ast.Constant) and keyword.value.value is None)
                            for keyword in node.keywords
                        ):
                            unbounded_metered_calls.append(
                                f"{relative}:{getattr(node, 'lineno', '?')}: "
                                "metered call lacks explicit max_cost_per_job"
                            )
                        if not any(
                            keyword.arg == "request_envelope"
                            and not (isinstance(keyword.value, ast.Constant) and keyword.value.value is None)
                            for keyword in node.keywords
                        ):
                            unbounded_metered_calls.append(
                                f"{relative}:{getattr(node, 'lineno', '?')}: metered call lacks exact request_envelope"
                            )
                        if resolved_call.startswith("deepr.services.metered_call.") and not (
                            _enclosing_function_has_endpoint_guard(tree, node, aliases)
                        ):
                            unbounded_metered_calls.append(
                                f"{relative}:{getattr(node, 'lineno', '?')}: "
                                "generic metered SDK dispatch lacks an official live-client endpoint guard"
                            )
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    lowered = node.value.lower()
                    endpoint_counts[relative] += sum(fragment in lowered for fragment in _PAID_ENDPOINT_FRAGMENTS)
    return constructor_counts, endpoint_counts, parse_errors, unbounded_metered_calls


def _source_contract_failures() -> list[str]:
    failures: list[str] = []
    for relative, fragments in sorted(_REQUIRED_SAFETY_FRAGMENTS.items()):
        path = _ROOT / relative
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            failures.append(f"{relative}: cannot read required safety boundary: {exc}")
            continue
        for fragment in fragments:
            if fragment not in source:
                failures.append(f"{relative}: required safety boundary is missing: {fragment!r}")

    for relative in _CLOUD_DEPLOY_SCRIPTS:
        path = _ROOT / relative
        try:
            source = path.read_text(encoding="utf-8").lower()
        except (OSError, UnicodeError) as exc:
            failures.append(f"{relative}: cannot read cloud deployment quarantine: {exc}")
            continue
        if "cannot enforce the operator's total dollar ceiling" not in source or "exit 2" not in source:
            failures.append(f"{relative}: cloud deployment does not fail closed on the total cost ceiling")
        for fragment in _FORBIDDEN_CLOUD_SCRIPT_FRAGMENTS:
            if fragment in source:
                failures.append(f"{relative}: forbidden cloud operation remains executable: {fragment!r}")
    return failures


def main() -> int:
    constructor_counts, endpoint_counts, parse_errors, unbounded_metered_calls = _scan()
    failures = [*parse_errors, *unbounded_metered_calls, *_source_contract_failures()]
    for path, count in sorted(constructor_counts.items()):
        baseline = _BASELINE.get(path, 0)
        if count > baseline:
            failures.append(f"{path}: {count} paid-client constructors exceeds audited baseline {baseline}")
    for path, count in sorted(endpoint_counts.items()):
        baseline = _ENDPOINT_BASELINE.get(path, 0)
        if count > baseline:
            failures.append(f"{path}: {count} paid-endpoint references exceeds audited baseline {baseline}")
    improvements = [
        f"{path}: constructors down to {constructor_counts.get(path, 0)} from {baseline}"
        for path, baseline in sorted(_BASELINE.items())
        if constructor_counts.get(path, 0) < baseline
    ]
    improvements.extend(
        f"{path}: endpoint references down to {endpoint_counts.get(path, 0)} from {baseline}"
        for path, baseline in sorted(_ENDPOINT_BASELINE.items())
        if endpoint_counts.get(path, 0) < baseline
    )
    if improvements:
        print("Paid API boundary improved. Tighten the baseline:")
        print("\n".join(f"  {line}" for line in improvements))
    if failures:
        print("Paid API boundary check FAILED:")
        print("\n".join(f"  {line}" for line in failures))
        print("Route the call through the durable transaction or gate it before provider construction.")
        return 1
    print(
        "Paid API boundary OK: "
        f"{sum(constructor_counts.values())} constructor sites and "
        f"{sum(endpoint_counts.values())} raw endpoint references audited; no growth."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
