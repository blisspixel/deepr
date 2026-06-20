"""
Doc Reuse Intelligence - Review existing research before planning new tasks.

WARNING: This is experimental and may hurt research quality.

The Problem:
- GPT-5 sees 500 char preview + filename, can't judge actual depth
- A shallow 2-paragraph doc vs comprehensive 60KB research both get "evaluated"
- False confidence: "We have a doc" != "We have sufficient research"
- Wrong optimization: Saves money but delivers worse results

Safe Use Cases:
- API documentation (version-specific facts)
- Recent competitive research (< 6 months old)
- Pricing/factual data
- NOT for: Deep analysis, strategic research, PhD-level synthesis

Current Status: Disabled by default (--check-docs flag required)

SECURITY: scan_docs() is hardened against symlink traversal and path escape.
Only files that resolve inside the configured docs_path are read. Symlinks
are rejected early. Large files are skipped before preview extraction.

Recommendation: Only use for factual/API docs, never for comprehensive research.
"""

import glob
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

from deepr.utils.prompt_security import sanitize_untrusted_content
from deepr.utils.security import InvalidInputError, PathTraversalError, validate_path

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


class DocReviewer:
    """
    Reviews existing documentation to determine reuse opportunities.

    Workflow:
    1. Scan docs/ directory for relevant files
    2. Use GPT-5 to evaluate relevance and sufficiency
    3. Return: which docs to reuse, which need updates, what gaps remain
    """

    def __init__(
        self, api_key: str | None = None, model: str = "gpt-5", docs_path: str = "docs/research and documentation"
    ):
        """
        Initialize doc reviewer.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env)
            model: Model for evaluation (default: gpt-5)
            docs_path: Path to docs directory
        """
        if OpenAI is None:
            raise ImportError("OpenAI SDK required. Run: pip install openai")

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found")

        self.client = OpenAI(api_key=self.api_key)
        self.model = model
        self.docs_path = docs_path

    def scan_docs(self, pattern: str = "**/*.txt") -> list[dict[str, Any]]:
        """
        Scan docs directory for files matching pattern.

        SECURITY: Rejects symlinks and any path that resolves outside docs_path
        (defends against symlink traversal and directory escape attacks).
        Large files (>2MB) are skipped before any content is read.

        Args:
            pattern: Glob pattern (e.g., "**/*.txt", "**/*.md")

        Returns:
            List of dicts with file metadata (only trusted files)
        """
        docs = []

        search_pattern = os.path.join(self.docs_path, pattern)
        files = glob.glob(search_pattern, recursive=True)

        base = self.docs_path  # for clarity in error messages

        for file_path in files:
            try:
                # Hard defense against symlink attacks and path traversal
                if os.path.islink(file_path):
                    logger.debug("Skipping symlink in docs scan (security): %s", file_path)
                    continue

                # validate_path does realpath resolution + containment check
                try:
                    validated = validate_path(file_path, base, must_exist=True)
                except (PathTraversalError, InvalidInputError, FileNotFoundError) as sec_err:
                    # Intent: one untrusted path during docs scan must not abort the entire batch review; continue with remaining files for partial but safe results.
                    logger.debug("Skipping untrusted path in docs scan (security): %s (%s)", file_path, sec_err)
                    continue

                # Early size guard before reading content (DoS + exfil mitigation)
                stat = os.stat(validated)
                if stat.st_size > 2 * 1024 * 1024:  # 2 MB
                    logger.debug("Skipping large file in docs scan: %s (%d bytes)", file_path, stat.st_size)
                    continue

                modified = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
                size = stat.st_size

                # Read first few lines for preview (now from validated path)
                with open(validated, encoding="utf-8") as f:
                    preview = f.read(500)  # First 500 chars

                docs.append(
                    {
                        "path": str(validated),  # report the safe resolved path
                        "name": os.path.basename(file_path),
                        "modified": modified.isoformat(),
                        "size_bytes": size,
                        "preview": preview,
                    }
                )
            except Exception:
                # Skip unreadable file during directory scan; one bad file must not abort the entire doc review batch.
                continue

        return docs

    def review_docs(self, scenario: str, context: str | None = None, max_docs_to_review: int = 10) -> dict[str, Any]:
        """
        Review existing docs for relevance to scenario.

        Args:
            scenario: Research scenario/question
            context: Additional context about the project
            max_docs_to_review: Max number of docs to analyze

        Returns:
            Dict with:
                - sufficient: List of docs that fully address scenario
                - needs_update: List of docs that are relevant but outdated
                - gaps: List of topics not covered by existing docs
                - recommendations: What new research to queue
        """
        # Scan for existing docs
        all_docs = self.scan_docs()

        if not all_docs:
            return {
                "sufficient": [],
                "needs_update": [],
                "gaps": [scenario],
                "recommendations": [{"action": "research", "topic": scenario, "reason": "No existing docs found"}],
            }

        # Limit to most recent docs
        all_docs.sort(key=lambda d: d["modified"], reverse=True)
        docs_to_review = all_docs[:max_docs_to_review]

        # Build evaluation prompt
        prompt = self._build_evaluation_prompt(scenario, context, docs_to_review)

        # Call GPT-5 for evaluation
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a research strategist evaluating existing documentation for reuse opportunities. Your goal is to save costs by reusing good existing research and only requesting updates or new research where genuinely needed.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )

        # Parse response
        try:
            content = response.choices[0].message.content if response.choices else "{}"
            result = json.loads(content or "{}")
        except (json.JSONDecodeError, IndexError) as e:
            logger.warning("Failed to parse doc review response: %s", e)
            result = {"sufficient": [], "needs_update": [], "gaps": [scenario], "recommendations": []}
        return result

    def _build_evaluation_prompt(self, scenario: str, context: str | None, docs: list[dict[str, Any]]) -> str:
        """Build prompt for GPT-5 to evaluate docs."""

        parts = ["# Research Scenario", f"\n{scenario}\n"]

        if context:
            parts.append(f"\n## Additional Context\n{context}\n")

        parts.append("\n## Existing Documentation\n")

        for i, doc in enumerate(docs, 1):
            preview = sanitize_untrusted_content(
                doc.get("preview", ""),
                source_label=f"doc preview {doc.get('name', f'doc {i}')}",
            )
            parts.append(f"\n### Doc {i}: {doc['name']}")
            parts.append(f"**Path:** {doc['path']}")
            parts.append(f"**Last Modified:** {doc['modified']}")
            parts.append(f"**Preview:**\n{preview.delimited}\n")

        parts.append("\n## Your Task\n")
        parts.append("""
Evaluate which docs are relevant to the scenario. For each doc, determine:

1. **Sufficient** - Fully addresses the scenario, no updates needed
2. **Needs Update** - Relevant but outdated (e.g., references 2024 data when we're in 2025)
3. **Not Relevant** - Doesn't address this scenario

Then identify:
- **Gaps** - Topics the scenario needs that aren't covered by existing docs
- **Recommendations** - Specific research tasks to queue

Return JSON:
```json
{
    "sufficient": [
        {"path": "...", "name": "...", "reason": "why it's sufficient"}
    ],
    "needs_update": [
        {"path": "...", "name": "...", "reason": "why it needs update", "what_to_update": "specific gaps"}
    ],
    "gaps": [
        "topic 1 not covered",
        "topic 2 not covered"
    ],
    "recommendations": [
        {"action": "reuse", "doc": "path/to/doc.txt", "reason": "..."},
        {"action": "update", "doc": "path/to/doc.txt", "topic": "Update X with 2025 data", "reason": "..."},
        {"action": "research", "topic": "New topic Y", "reason": "..."}
    ]
}
```

**Important:**
- Be conservative with "sufficient" - only if doc truly addresses scenario completely
- Flag outdated info (e.g., 2024 data when we're in 2025)
- In recommendations, prefer "reuse" and "update" over "research" (saves money)
- Be specific about what to update (not just "needs update")
""")

        return "".join(parts)

    def generate_tasks_from_review(self, review_result: dict[str, Any], max_tasks: int = 5) -> list[dict[str, Any]]:
        """
        Convert review recommendations into research tasks.

        Args:
            review_result: Output from review_docs()
            max_tasks: Maximum number of tasks to generate

        Returns:
            List of task dicts ready for BatchExecutor
        """
        tasks = []
        task_id = 1

        for rec in review_result.get("recommendations", [])[:max_tasks]:
            action = rec.get("action")

            if action == "reuse":
                # Not a task - just include existing doc as context
                continue

            elif action == "update":
                # Task to update existing research
                doc_name = rec.get("doc", "").split("/")[-1]
                task = {
                    "id": task_id,
                    "title": f"Update: {rec.get('topic', doc_name)}",
                    "prompt": f"Update research: {rec.get('topic')}. Reason: {rec.get('reason')}. Focus on what has changed since the previous research.",
                    "type": "documentation",
                    "reason": rec.get("reason"),
                }
                tasks.append(task)
                task_id += 1

            elif action == "research":
                # New research task
                task = {
                    "id": task_id,
                    "title": rec.get("topic"),
                    "prompt": f"Research: {rec.get('topic')}. {rec.get('reason', '')}",
                    "type": "documentation",
                    "reason": rec.get("reason"),
                }
                tasks.append(task)
                task_id += 1

        return tasks
