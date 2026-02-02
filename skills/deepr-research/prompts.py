"""
MCP Prompt Primitives for Deepr.

Defines reusable prompt templates that MCP-compliant clients (Claude Desktop,
OpenClaw, etc.) can present in template menus. These pre-fill the context
with optimized instructions for common research workflows.

Usage in server:
    Register via prompts/list and prompts/get JSON-RPC methods.
"""

from typing import Any


# Prompt definitions: name -> {description, arguments, messages}
PROMPTS: dict[str, dict[str, Any]] = {
    "deep_research_task": {
        "name": "deep_research_task",
        "description": (
            "Conduct comprehensive deep research on a topic. "
            "Produces a cited, structured report with executive summary."
        ),
        "arguments": [
            {
                "name": "topic",
                "description": "The topic or question to research",
                "required": True,
            },
            {
                "name": "scope",
                "description": "Scope constraints (e.g., 'last 5 years', 'US market only')",
                "required": False,
            },
        ],
        "messages": lambda args: [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": (
                        f"Please conduct a comprehensive deep research report on: {args['topic']}\n\n"
                        f"{'Scope: ' + args['scope'] if args.get('scope') else ''}\n\n"
                        "Use the deepr_research tool. Focus on empirical data and cite all sources. "
                        "After the research completes, present the findings with:\n"
                        "1. Executive summary\n"
                        "2. Key findings with citations\n"
                        "3. Methodology and sources\n"
                        "4. Cost and time summary"
                    ),
                },
            }
        ],
    },
    "expert_consultation": {
        "name": "expert_consultation",
        "description": (
            "Consult a domain expert for knowledge-based answers. "
            "Expert draws from ingested documents and synthesized knowledge."
        ),
        "arguments": [
            {
                "name": "expert_name",
                "description": "Name of the expert to consult",
                "required": True,
            },
            {
                "name": "question",
                "description": "Question to ask the expert",
                "required": True,
            },
        ],
        "messages": lambda args: [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": (
                        f"I'd like to consult the '{args['expert_name']}' expert.\n\n"
                        f"Question: {args['question']}\n\n"
                        "Use deepr_query_expert to get the answer. If the expert indicates "
                        "low confidence or a knowledge gap, offer to enable agentic mode "
                        "for autonomous research to fill the gap."
                    ),
                },
            }
        ],
    },
    "comparative_analysis": {
        "name": "comparative_analysis",
        "description": (
            "Compare multiple options or approaches with structured analysis. "
            "Produces a decision matrix with pros, cons, and recommendation."
        ),
        "arguments": [
            {
                "name": "options",
                "description": "Comma-separated list of options to compare (e.g., 'PostgreSQL, MongoDB, Redis')",
                "required": True,
            },
            {
                "name": "criteria",
                "description": "Evaluation criteria (e.g., 'performance, cost, scalability')",
                "required": False,
            },
        ],
        "messages": lambda args: [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": (
                        f"Please conduct a comparative analysis of: {args['options']}\n\n"
                        f"{'Evaluation criteria: ' + args['criteria'] if args.get('criteria') else ''}\n\n"
                        "Use deepr_research to investigate each option. Produce a structured "
                        "comparison with:\n"
                        "1. Overview of each option\n"
                        "2. Decision matrix (options x criteria)\n"
                        "3. Pros and cons for each\n"
                        "4. Recommendation with rationale\n"
                        "5. Sources and citations"
                    ),
                },
            }
        ],
    },
}


def list_prompts() -> list[dict]:
    """Return all prompt definitions for prompts/list response."""
    return [
        {
            "name": p["name"],
            "description": p["description"],
            "arguments": p.get("arguments", []),
        }
        for p in PROMPTS.values()
    ]


def get_prompt(name: str, arguments: dict) -> dict:
    """Get a prompt by name with rendered messages for prompts/get response.

    Args:
        name: Prompt name
        arguments: Template arguments to render

    Returns:
        dict with description and messages, or error
    """
    prompt_def = PROMPTS.get(name)
    if not prompt_def:
        return {"error": f"Prompt not found: {name}"}

    messages_fn = prompt_def["messages"]
    try:
        messages = messages_fn(arguments)
    except KeyError as e:
        return {"error": f"Missing required argument: {e}"}

    return {
        "description": prompt_def["description"],
        "messages": messages,
    }
