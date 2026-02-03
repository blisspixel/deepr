"""Semantic command interface - intent-based commands for natural workflows.

This package provides natural, intent-based commands that map to the underlying
implementation commands in run.py. Users think in terms of "I want to research X"
not "Should I use focus or docs mode?".

Command mapping:
    deepr research  -> Automatically chooses between run focus/docs based on prompt
    deepr learn     -> Maps to run project (multi-phase learning)
    deepr team      -> Maps to run team (multi-perspective analysis)

All flags from the underlying commands are supported.
"""

from deepr.cli.commands.semantic.research import research, learn, team, check, detect_research_mode
from deepr.cli.commands.semantic.artifacts import make, agentic
from deepr.cli.commands.semantic.experts import (
    expert, make_expert, list_experts, expert_info, delete_expert,
    learn_expert, resume_expert_learning, export_expert, import_expert,
    fill_gaps, refresh_expert, chat_with_expert,
)

__all__ = [
    "research", "learn", "team", "check", "detect_research_mode",
    "make", "agentic",
    "expert", "make_expert", "list_experts", "expert_info", "delete_expert",
    "learn_expert", "resume_expert_learning", "export_expert", "import_expert",
    "fill_gaps", "refresh_expert", "chat_with_expert",
]
