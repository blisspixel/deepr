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
    "deepr.experts.chat_metered.execute_metered_chat_provider_call",
    "deepr.experts.chat_metered.execute_metered_chat_provider_stream",
}

# Audited 2026-07-25. A lower count is an improvement. A higher count or new
# path fails until the site has a durable transaction or an explicit gate and
# this review baseline is deliberately amended.
_BASELINE = {
    "scripts/analyze_doc_gaps.py": 1,
    "scripts/testing/check_vector_store.py": 1,
    "src/deepr/backends/local.py": 1,
    "src/deepr/cli/commands/doctor.py": 4,
    "src/deepr/cli/commands/eval.py": 1,
    "src/deepr/cli/commands/providers.py": 3,
    "src/deepr/experts/chat_api_backends.py": 2,
    "src/deepr/experts/chat_research_ops.py": 1,
    "src/deepr/experts/citation_validator.py": 1,
    "src/deepr/experts/claim_extraction.py": 1,
    "src/deepr/experts/claim_verification.py": 1,
    "src/deepr/experts/conflict_resolver.py": 1,
    "src/deepr/experts/consensus.py": 5,
    "src/deepr/experts/consult.py": 1,
    "src/deepr/experts/consult_quality_judges.py": 2,
    "src/deepr/experts/curriculum.py": 1,
    "src/deepr/experts/gap_discovery.py": 1,
    "src/deepr/experts/map_reduce.py": 1,
    "src/deepr/experts/multi_pass.py": 1,
    "src/deepr/experts/portraits.py": 3,
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
    "src/deepr/web/app.py": 1,
}

# Raw HTTP and configurable-provider endpoint references audited on
# 2026-07-25. This catches paid REST calls that never construct an SDK client.
_ENDPOINT_BASELINE = {
    "scripts/benchmark_models.py": 9,
    "scripts/discover_models.py": 7,
    "scripts/setup_local.py": 1,
    "src/deepr/backends/plan_quota/quota_probes.py": 1,
    "src/deepr/cli/commands/doctor.py": 1,
    "src/deepr/cli/commands/keys.py": 4,
    "src/deepr/cli/commands/providers.py": 1,
    "src/deepr/config.py": 2,
    "src/deepr/experts/consult_quality_judges.py": 1,
    "src/deepr/experts/portraits.py": 2,
    "src/deepr/mcp/security/network.py": 2,
    "src/deepr/providers/grok_provider.py": 1,
}


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
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    resolved_call = _resolved_call_name(node, aliases)
                    if resolved_call in _TARGETS:
                        constructor_counts[relative] += 1
                    if resolved_call in _METERED_WRAPPERS and not any(
                        keyword.arg == "max_cost_per_job"
                        and not (isinstance(keyword.value, ast.Constant) and keyword.value.value is None)
                        for keyword in node.keywords
                    ):
                        unbounded_metered_calls.append(
                            f"{relative}:{getattr(node, 'lineno', '?')}: metered call lacks explicit max_cost_per_job"
                        )
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    lowered = node.value.lower()
                    endpoint_counts[relative] += sum(fragment in lowered for fragment in _PAID_ENDPOINT_FRAGMENTS)
    return constructor_counts, endpoint_counts, parse_errors, unbounded_metered_calls


def main() -> int:
    constructor_counts, endpoint_counts, parse_errors, unbounded_metered_calls = _scan()
    failures = [*parse_errors, *unbounded_metered_calls]
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
