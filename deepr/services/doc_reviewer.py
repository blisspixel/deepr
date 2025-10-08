"""
Doc Reviewer Service

Uses GPT-5 to intelligently check existing documentation and determine:
1. Is existing research relevant to the current scenario?
2. Is it sufficient, or do we need updated/deeper research?
3. What gaps exist that should be addressed?

This avoids redundant research and saves money by reusing existing work.
"""

import os
from pathlib import Path
from typing import List, Dict, Optional
from openai import OpenAI


class DocReviewer:
    """
    Reviews existing documentation to avoid redundant research.

    Uses GPT-5 to evaluate whether existing docs are:
    - Relevant to the scenario
    - Sufficiently comprehensive
    - Up-to-date

    Returns guidance on what can be reused vs what needs new research.
    """

    def __init__(self, model: str = "gpt-5-mini"):
        """
        Initialize doc reviewer.

        Args:
            model: GPT-5 model to use for evaluation (cheap, fast)
        """
        self.model = model
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def check_existing_docs(
        self,
        scenario: str,
        docs_dir: str = "docs/research and documentation",
    ) -> Dict[str, any]:
        """
        Check existing docs for relevance to scenario.

        Args:
            scenario: The research scenario to evaluate against
            docs_dir: Directory to scan for existing research

        Returns:
            Dict with:
            - relevant_docs: List of docs that can be reused
            - gaps: List of gaps that need new research
            - recommendations: Specific guidance for planner
        """
        # Scan for existing research files
        docs_path = Path(docs_dir)
        if not docs_path.exists():
            return {
                "relevant_docs": [],
                "gaps": ["No existing documentation found"],
                "recommendations": "Generate full research plan"
            }

        # Find all markdown and text files
        existing_docs = []
        for ext in ["*.md", "*.txt"]:
            existing_docs.extend(docs_path.glob(ext))

        if not existing_docs:
            return {
                "relevant_docs": [],
                "gaps": ["No existing documentation found"],
                "recommendations": "Generate full research plan"
            }

        # Read doc titles/summaries (first 200 chars)
        doc_summaries = []
        for doc in existing_docs[:20]:  # Limit to 20 most recent
            try:
                with open(doc, "r", encoding="utf-8") as f:
                    content = f.read(500)  # Read first 500 chars
                    doc_summaries.append({
                        "path": str(doc),
                        "preview": content[:200]
                    })
            except Exception:
                continue

        if not doc_summaries:
            return {
                "relevant_docs": [],
                "gaps": ["No readable documentation found"],
                "recommendations": "Generate full research plan"
            }

        # Use GPT-5 to evaluate relevance
        system_prompt = """You are a research evaluation expert. Your job is to analyze existing documentation and determine:

1. Which docs are RELEVANT to the current scenario
2. Whether existing docs are SUFFICIENT or if new research is needed
3. What GAPS exist that require new research

Be cost-conscious:
- If existing docs are good enough, recommend reusing them
- If docs are outdated (e.g., 2024 data when we need 2025), recommend updating
- If docs miss key angles, identify specific gaps to research

Return your analysis as JSON:
{
  "relevant_docs": [
    {"path": "...", "reason": "Why it's relevant", "quality": "sufficient|outdated|insufficient"}
  ],
  "gaps": ["Specific gap 1", "Specific gap 2"],
  "recommendations": "Brief guidance for planner (1-2 sentences)"
}"""

        user_prompt = f"""Scenario: {scenario}

Existing documentation:
"""
        for doc in doc_summaries:
            user_prompt += f"\n- {doc['path']}\n  Preview: {doc['preview'][:150]}...\n"

        user_prompt += """

Please analyze whether these docs are relevant and sufficient for the scenario, or if new research is needed. Return ONLY JSON, no other text."""

        try:
            response = self.client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
            )

            # Extract response text
            response_text = ""
            if hasattr(response, 'output_text'):
                response_text = response.output_text
            elif hasattr(response, 'output') and response.output:
                for item in response.output:
                    if hasattr(item, 'type') and item.type == 'message':
                        for content in item.content:
                            if hasattr(content, 'type') and content.type == 'output_text':
                                response_text = content.text
                                break

            # Parse JSON
            import json
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            analysis = json.loads(response_text)
            return analysis

        except Exception as e:
            print(f"Error evaluating docs: {e}")
            return {
                "relevant_docs": [],
                "gaps": [f"Could not evaluate existing docs: {e}"],
                "recommendations": "Proceed with full research plan"
            }

    def generate_enhanced_plan_context(
        self,
        scenario: str,
        doc_analysis: Dict,
    ) -> str:
        """
        Generate context for the planner based on doc analysis.

        This tells the planner:
        - What existing docs to reference
        - What gaps to focus on
        - How to avoid redundant research

        Args:
            scenario: The research scenario
            doc_analysis: Output from check_existing_docs()

        Returns:
            Context string to pass to ResearchPlanner
        """
        context_parts = []

        # Add relevant docs
        relevant = doc_analysis.get("relevant_docs", [])
        if relevant:
            context_parts.append("EXISTING RESEARCH AVAILABLE:")
            for doc in relevant:
                quality = doc.get("quality", "unknown")
                context_parts.append(f"- {doc['path']} ({quality}): {doc['reason']}")

        # Add gaps
        gaps = doc_analysis.get("gaps", [])
        if gaps:
            context_parts.append("\nGAPS TO ADDRESS:")
            for gap in gaps:
                context_parts.append(f"- {gap}")

        # Add recommendations
        recs = doc_analysis.get("recommendations", "")
        if recs:
            context_parts.append(f"\nGUIDANCE: {recs}")

        context_parts.append("\nFocus research on gaps and updates. Avoid duplicating existing sufficient docs.")

        return "\n".join(context_parts)


def create_doc_reviewer(model: str = "gpt-5-mini") -> DocReviewer:
    """
    Factory function to create a doc reviewer.

    Args:
        model: GPT-5 model to use

    Returns:
        Configured DocReviewer instance
    """
    return DocReviewer(model=model)
