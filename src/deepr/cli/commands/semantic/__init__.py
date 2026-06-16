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

from deepr.cli.commands.semantic.artifacts import agentic, make
from deepr.cli.commands.semantic.experts import (
    chat_with_expert,
    delete_expert,
    expert,
    expert_info,
    export_expert,
    fill_gaps,
    import_expert,
    learn_expert,
    list_experts,
    make_expert,
    refresh_expert,
    resume_expert_learning,
)
from deepr.cli.commands.semantic.research import check, detect_research_mode, learn, research, team

__all__ = [
    "agentic",
    "chat_with_expert",
    "check",
    "delete_expert",
    "detect_research_mode",
    "expert",
    "expert_info",
    "export_expert",
    "fill_gaps",
    "import_expert",
    "learn",
    "learn_expert",
    "list_experts",
    "make",
    "make_expert",
    "refresh_expert",
    "research",
    "resume_expert_learning",
    "team",
]
