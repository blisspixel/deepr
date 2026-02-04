"""
Context Builder Service

Summarizes research reports for use as context in subsequent phases.

Based on research findings (docs/research and documentation/context_chaining_best_practices.md):
- Use running summary memory
- Keep summaries under 2K tokens
- Use structured outputs (bullet lists)
- Summary memory cuts token usage ~70%

Includes token budget management and intelligent context pruning.
"""

from typing import Dict, List, Optional, Tuple
from openai import OpenAI
import os

from deepr.core.constants import MAX_CONTEXT_TOKENS, TOKEN_BUDGET_DEFAULT
from deepr.services.context_pruner import ContextPruner, ContextItem, PruningDecision
from deepr.services.token_budget import TokenBudgetAllocator, BudgetPlan


class ContextBuilder:
    """Builds context from prior research for subsequent phases.

    Includes token budget management and intelligent pruning for
    long research sessions.
    """

    def __init__(
        self,
        api_key: str = None,
        token_budget: Optional[int] = None,
        enable_pruning: bool = True,
    ):
        """Initialize context builder with OpenAI client.

        Args:
            api_key: OpenAI API key
            token_budget: Maximum tokens for context (default from constants)
            enable_pruning: Whether to enable intelligent pruning
        """
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.token_budget = token_budget or MAX_CONTEXT_TOKENS
        self.enable_pruning = enable_pruning

        # Initialize pruner
        self.pruner = ContextPruner() if enable_pruning else None

        # Track pruning decisions for explain output
        self.last_pruning_decision: Optional[PruningDecision] = None

    async def summarize_research(self, report_content: str, max_tokens: int = 500) -> str:
        """
        Summarize a research report for use as context.

        Uses GPT-5-mini (fast, cheap reasoning model) to extract key findings.

        Args:
            report_content: Full research report (could be 10+ pages)
            max_tokens: Target summary length in tokens (default: 500)

        Returns:
            Concise summary with key findings
        """
        # Calculate rough target length in words (4 chars = 1 token)
        target_words = max_tokens * 3

        prompt = f"""Summarize the following research report for use as context in a follow-up research task.

Extract:
- Key findings (facts, data points, insights)
- Important entities (companies, people, technologies)
- Main conclusions

Format as bullet list. Be concise but preserve essential information. Target length: {target_words} words.

Research Report:
{report_content[:20000]}
... (report truncated for summarization)

Summary (bullet list, ~{target_words} words):"""

        response = self.client.chat.completions.create(
            model="gpt-5-mini",  # Fast and cheap reasoning model for summarization
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,  # Lower temp for factual extraction
            max_completion_tokens=max_tokens + 100,  # Allow some buffer
        )

        return response.choices[0].message.content.strip()

    async def build_phase_context(
        self,
        task: Dict,
        completed_tasks: Dict[int, Dict],
        token_budget: Optional[int] = None,
        current_query: Optional[str] = None,
    ) -> str:
        """
        Build context string for a task based on dependencies.

        Args:
            task: Current task with 'depends_on' field
            completed_tasks: Dict mapping task ID to task data with 'result'
            token_budget: Optional override for token budget
            current_query: Current query for relevance-based pruning

        Returns:
            Context string to inject into prompt
        """
        depends_on = task.get("depends_on", [])
        budget = token_budget or self.token_budget
        query = current_query or task.get("prompt", "")

        if not depends_on:
            return ""

        # Collect context items for potential pruning
        context_items = []
        from datetime import datetime, timezone

        for dep_id in depends_on:
            if dep_id not in completed_tasks:
                continue

            dep_task = completed_tasks[dep_id]
            dep_title = dep_task.get("title", f"Task {dep_id}")
            dep_result = dep_task.get("result", "")
            dep_phase = dep_task.get("phase", 1)

            if not dep_result:
                continue

            # Create context item for pruning
            item = ContextItem(
                id=f"dep_{dep_id}",
                text=dep_result,
                source=dep_title,
                timestamp=datetime.now(timezone.utc),
                phase=dep_phase,
                importance=0.7,  # Dependency context is important
            )
            context_items.append((dep_id, item))

        # Apply pruning if enabled and needed
        if self.enable_pruning and self.pruner and context_items:
            items_only = [item for _, item in context_items]
            total_tokens = sum(item.tokens for item in items_only)

            if total_tokens > budget:
                pruned_items, self.last_pruning_decision = self.pruner.prune(
                    context_items=items_only,
                    current_query=query,
                    token_budget=budget,
                )

                # Rebuild mapping
                pruned_ids = {item.id for item in pruned_items}
                context_items = [
                    (dep_id, item) for dep_id, item in context_items
                    if item.id in pruned_ids
                ]

        # Build context from (possibly pruned) items
        context_parts = [
            "Context from previous research:",
            "",
        ]

        for dep_id, item in context_items:
            dep_result = item.text

            # Summarize dependency result
            # Use smaller max_tokens if we have many dependencies
            max_summary_tokens = min(400, budget // max(len(context_items), 1))
            summary = await self.summarize_research(dep_result, max_tokens=max_summary_tokens)

            context_parts.append(f"## From: {item.source}")
            context_parts.append(summary)
            context_parts.append("")

        context_parts.append("---")
        context_parts.append("")
        context_parts.append("Given the above context, now research:")
        context_parts.append("")

        return "\n".join(context_parts)

    def get_context_utilization(self) -> Dict:
        """Get context utilization metrics for --explain output.

        Returns:
            Dictionary with utilization metrics
        """
        if not self.last_pruning_decision:
            return {
                "pruning_applied": False,
                "budget": self.token_budget,
            }

        decision = self.last_pruning_decision
        return {
            "pruning_applied": True,
            "original_items": decision.original_count,
            "final_items": decision.pruned_count,
            "original_tokens": decision.original_tokens,
            "final_tokens": decision.final_tokens,
            "budget": decision.budget,
            "tokens_saved": decision.original_tokens - decision.final_tokens,
            "items_removed": len(decision.items_removed),
            "strategy": decision.strategy_used,
        }

    async def build_synthesis_context(
        self,
        all_tasks: Dict[int, Dict],
    ) -> str:
        """
        Build comprehensive context for final synthesis report.

        Summarizes ALL prior research for integration.

        Args:
            all_tasks: Dict mapping task ID to task data with 'result'

        Returns:
            Context string with summaries of all prior research
        """
        context_parts = [
            "Context from complete research campaign:",
            "",
        ]

        for task_id in sorted(all_tasks.keys()):
            task = all_tasks[task_id]
            title = task.get("title", f"Task {task_id}")
            result = task.get("result", "")

            if not result:
                continue

            # Summarize each research report
            summary = await self.summarize_research(result, max_tokens=300)

            context_parts.append(f"## Research {task_id}: {title}")
            context_parts.append(summary)
            context_parts.append("")

        context_parts.append("---")
        context_parts.append("")
        context_parts.append(
            "Based on all the above research, create a comprehensive synthesis:"
        )
        context_parts.append("")

        return "\n".join(context_parts)
