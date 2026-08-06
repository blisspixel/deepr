"""Plan Distillr (and Learny) deepen steps for an expert - $0, no network.

Emits operator-run commands. Does not invoke Distill or spend capacity.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

DEEPEN_PLAN_SCHEMA = "deepr-expert-deepen-plan-v1"
DEEPEN_PLAN_KIND = "deepr.expert.deepen_plan"


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:64] or "topic"


@dataclass
class ExpertDeepenPlan:
    """Recipe to deepen an expert via Distill corpus + Deepr absorb."""

    schema_version: str = DEEPEN_PLAN_SCHEMA
    kind: str = DEEPEN_PLAN_KIND
    expert_name: str = ""
    domain: str = ""
    topic_slug: str = ""
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    distill_on_path: bool = False
    learny_on_path: bool = False
    capacity_notes: list[str] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    absorb_examples: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    limitations: list[str] = field(
        default_factory=lambda: [
            "Plan only - does not run Distill, Learny, or absorb.",
            "Distill plan-quota CLIs are not live providers; use cost-mode no-metered + local analysis for $0 API.",
            "Learny conference pipelines are typically metered unless you supply an export from a prior run.",
            "Absorb remains the only path that writes Deepr beliefs.",
        ]
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        lines = [
            f"# Deepen plan: {self.expert_name}",
            "",
            f"Domain: {self.domain}",
            f"Topic slug: `{self.topic_slug}`",
            f"Generated: {self.generated_at}",
            "",
            "## Capacity",
            "",
        ]
        for note in self.capacity_notes:
            lines.append(f"- {note}")
        lines += ["", "## Steps", ""]
        for i, step in enumerate(self.steps, 1):
            lines.append(f"### {i}. {step.get('title', 'step')}")
            lines.append("")
            lines.append(step.get("why", ""))
            lines.append("")
            cmd = step.get("command")
            if cmd:
                lines.append("```text")
                lines.append(cmd)
                lines.append("```")
                lines.append("")
        if self.absorb_examples:
            lines += ["## Absorb into this expert", ""]
            for ex in self.absorb_examples:
                lines.append(f"- `{ex}`")
            lines.append("")
        lines += ["## Limitations", ""]
        for lim in self.limitations:
            lines.append(f"- {lim}")
        lines.append("")
        return "\n".join(lines)


def build_deepen_plan(
    *,
    expert_name: str,
    domain: str,
    query: str | None = None,
) -> ExpertDeepenPlan:
    """Build a Distill/Learny deepen recipe for one expert."""
    focus = (query or domain or expert_name).strip()
    slug = _slug(focus)
    distill = shutil.which("distill") is not None
    learny = shutil.which("learny") is not None

    capacity = [
        "Deepr absorb/sync/consult: prefer --local for $0 API; Claude plan only when paid-overage-off proven.",
        "Distill analysis: use --cost-mode no-metered with local Ollama/LM Studio for $0 API (still fetches public sources).",
        "Distill plan-quota CLIs (Claude/Codex/Grok/Antigravity): not live providers yet.",
        "Learny: use existing export if you have one; live attend/analyze is typically Gemini-metered.",
    ]
    if distill:
        capacity.append(f"distill binary found: {shutil.which('distill')}")
    else:
        capacity.append("distill not on PATH - install: uv tool install distillr")
    if learny:
        capacity.append(f"learny binary found: {shutil.which('learny')}")
    else:
        capacity.append("learny not on PATH - optional for event-scale corpora")

    steps: list[dict[str, Any]] = [
        {
            "id": "distill_preview_papers",
            "title": "Preview academic shortlist (no ingest)",
            "why": "Confirm arXiv relevance before writing corpus files.",
            "command": (f'distill --cost-mode no-metered papers "{focus}" --topic {slug} --limit 5 --preview'),
        },
        {
            "id": "distill_papers_local",
            "title": "Ingest papers with local analysis",
            "why": "Build receipted insights under library/ for multi-source depth.",
            "command": (f'distill --cost-mode no-metered papers "{focus}" --topic {slug} --limit 10'),
        },
        {
            "id": "distill_official_site",
            "title": "Capture official / trusted docs site",
            "why": "Secondary-trust domain mechanics from first-party documentation.",
            "command": (f"distill --cost-mode no-metered site <OFFICIAL_DOCS_URL> --topic {slug}"),
        },
        {
            "id": "distill_latest",
            "title": "Latest news / release notes pulse",
            "why": "Catch version and service changes models do not know yet.",
            "command": (f'distill --cost-mode no-metered latest "{focus}" --topic {slug}'),
        },
        {
            "id": "learny_optional",
            "title": "Optional: Learny event corpus (if conference-scale)",
            "why": "Long-form learnings across hundreds of sessions; usually metered unless you already exported.",
            "command": ('learny attend "<EVENT>" --limit 20   # or learny export --format bundle from a prior run'),
        },
        {
            "id": "absorb_secondary",
            "title": "Absorb Distill Markdown into Deepr expert",
            "why": "Only absorb writes beliefs; use secondary for official/corpus insights.",
            "command": (
                f'deepr expert absorb "{expert_name}" --file <path-to-insight.md> --local --trust-class secondary -y'
            ),
        },
        {
            "id": "regenerate_views",
            "title": "Regenerate wiki digest and score quality",
            "why": "Derived views and structural scorecard after depth lands.",
            "command": (
                f'deepr expert digest "{expert_name}" && '
                f'deepr expert quality "{expert_name}" && '
                f'deepr expert improve "{expert_name}" --local'
            ),
        },
    ]

    absorb_examples = [
        (f'deepr expert absorb "{expert_name}" --file library/{slug}/_Insights.md --local --trust-class secondary -y'),
        (f'deepr expert absorb "{expert_name}" --file library/{slug}/synthesis.md --local --trust-class secondary -y'),
        (f'deepr expert absorb "{expert_name}" --file <learny-export-or-report.md> --local --trust-class secondary -y'),
    ]

    return ExpertDeepenPlan(
        expert_name=expert_name,
        domain=domain,
        topic_slug=slug,
        distill_on_path=distill,
        learny_on_path=learny,
        capacity_notes=capacity,
        steps=steps,
        absorb_examples=absorb_examples,
    )


def deepen_plan_json(plan: ExpertDeepenPlan) -> str:
    return json.dumps(plan.to_dict(), indent=2, sort_keys=True)
