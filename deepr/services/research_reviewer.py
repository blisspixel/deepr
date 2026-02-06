"""
Research Reviewer Service

Acts as a research team lead who reviews completed research and plans next phases.

Workflow:
1. Read completed research results from previous phase
2. Identify gaps, patterns, key insights
3. Suggest next research questions to fill gaps
4. Generate Phase N+1 research plan
"""

import os

from openai import OpenAI


class ResearchReviewer:
    """
    Reviews completed research and plans next phases.

    Replicates how a human research lead would work:
    - Review what the team found
    - Identify what's missing
    - Assign next round of research tasks
    """

    def __init__(self, model: str = "gpt-5"):
        """
        Initialize research reviewer.

        Args:
            model: GPT-5 model to use for reasoning (gpt-5, gpt-5-mini)
        """
        valid_models = ["gpt-5", "gpt-5-mini", "gpt-5-nano"]
        if model not in valid_models:
            raise ValueError(f"Invalid model: {model}. Must be one of {valid_models}")

        self.model = model
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def review_and_plan_next(
        self,
        scenario: str,
        completed_results: list[dict],
        current_phase: int,
        max_tasks: int = 5,
    ) -> dict:
        """
        Review completed research and plan next phase.

        Args:
            scenario: Original research scenario/goal
            completed_results: List of completed research with titles and results
            current_phase: Current phase number (next will be current + 1)
            max_tasks: Max tasks to generate for next phase

        Returns:
            Dict with next_phase plan or indication that research is complete
        """
        # Build summary of what's been researched so far
        research_summary = self._summarize_completed_research(completed_results)

        system_prompt = """You are a research team lead reviewing your team's findings and deciding what to research next.

Your job:
1. Review what research has been completed
2. Identify gaps, missing information, or areas needing deeper analysis
3. Determine if more research is needed, or if we have enough for final synthesis
4. If more research needed, suggest specific next research tasks

Be strategic:
- Don't repeat research already done
- Each new task should build on previous findings
- Consider what's ACTUALLY needed to answer the original question
- Sometimes less is more - don't over-research

Output format:
{
  "status": "continue" or "ready_for_synthesis",
  "analysis": "Brief analysis of what we learned and what's missing",
  "next_tasks": [
    {
      "title": "Short descriptive title",
      "prompt": "Detailed research prompt",
      "rationale": "Why this research is needed"
    }
  ]
}

If status is "ready_for_synthesis", next_tasks should have ONE synthesis task that integrates all findings.
"""

        user_prompt = f"""Original Scenario: {scenario}

Current Phase: {current_phase}

Completed Research So Far:
{research_summary}

Based on this research, what should we do next? Do we need more research, or are we ready for final synthesis?

Generate up to {max_tasks} next research tasks, or indicate we're ready to synthesize.

Return ONLY valid JSON, no other text."""

        response = self.client.responses.create(
            model=self.model,
            input=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        )

        # Parse response
        import json

        response_text = self._extract_response_text(response)

        try:
            result = json.loads(response_text)
            result["phase"] = current_phase + 1
            return result
        except json.JSONDecodeError:
            # Fallback: assume we're ready for synthesis
            return {
                "status": "ready_for_synthesis",
                "phase": current_phase + 1,
                "analysis": "Unable to parse review. Proceeding to synthesis.",
                "next_tasks": [
                    {
                        "title": "Final synthesis",
                        "prompt": f"Synthesize all previous research to answer: {scenario}",
                        "rationale": "Final integration of findings",
                    }
                ],
            }

    def _summarize_completed_research(self, completed_results: list[dict]) -> str:
        """Create readable summary of completed research."""
        lines = []
        for i, result in enumerate(completed_results, 1):
            title = result.get("title", f"Task {i}")
            content = result.get("result", "")

            # Truncate long results
            if len(content) > 2000:
                content = content[:2000] + "...(truncated)"

            lines.append(f"## Task {i}: {title}")
            lines.append(content)
            lines.append("")

        return "\n".join(lines)

    def _extract_response_text(self, response) -> str:
        """Extract text from GPT-5 response object."""
        # Try different response formats
        if hasattr(response, "output_text"):
            return response.output_text

        if hasattr(response, "output") and response.output:
            for item in response.output:
                if hasattr(item, "type") and item.type == "message":
                    for content in item.content:
                        if hasattr(content, "type") and content.type == "output_text":
                            return content.text

        # Fallback
        return str(response)

    def should_continue(self, review_result: dict) -> bool:
        """Check if more research is needed."""
        return review_result.get("status") == "continue"

    def is_ready_for_synthesis(self, review_result: dict) -> bool:
        """Check if ready for final synthesis."""
        return review_result.get("status") == "ready_for_synthesis"
