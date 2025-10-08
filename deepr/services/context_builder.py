"""
Context Builder Service

Summarizes research reports for use as context in subsequent phases.

Based on research findings (docs/research and documentation/context_chaining_best_practices.md):
- Use running summary memory
- Keep summaries under 2K tokens
- Use structured outputs (bullet lists)
- Summary memory cuts token usage ~70%
"""

from typing import Dict, List
from openai import OpenAI
import os


class ContextBuilder:
    """Builds context from prior research for subsequent phases."""

    def __init__(self, api_key: str = None):
        """Initialize context builder with OpenAI client."""
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))

    async def summarize_research(self, report_content: str, max_tokens: int = 500) -> str:
        """
        Summarize a research report for use as context.

        Uses GPT-4 (cheap, fast) to extract key findings.

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
            model="gpt-4",  # Fast and cheap for summarization
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,  # Lower temp for factual extraction
            max_tokens=max_tokens + 100,  # Allow some buffer
        )

        return response.choices[0].message.content.strip()

    async def build_phase_context(
        self,
        task: Dict,
        completed_tasks: Dict[int, Dict],
    ) -> str:
        """
        Build context string for a task based on dependencies.

        Args:
            task: Current task with 'depends_on' field
            completed_tasks: Dict mapping task ID to task data with 'result'

        Returns:
            Context string to inject into prompt
        """
        depends_on = task.get("depends_on", [])

        if not depends_on:
            return ""

        # Build context from dependencies
        context_parts = [
            "Context from previous research:",
            "",
        ]

        for dep_id in depends_on:
            if dep_id not in completed_tasks:
                continue

            dep_task = completed_tasks[dep_id]
            dep_title = dep_task.get("title", f"Task {dep_id}")
            dep_result = dep_task.get("result", "")

            if not dep_result:
                continue

            # Summarize dependency result
            summary = await self.summarize_research(dep_result, max_tokens=400)

            context_parts.append(f"## From: {dep_title}")
            context_parts.append(summary)
            context_parts.append("")

        context_parts.append("---")
        context_parts.append("")
        context_parts.append("Given the above context, now research:")
        context_parts.append("")

        return "\n".join(context_parts)

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
