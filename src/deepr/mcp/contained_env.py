"""Contained, zero-spend environment construction for local MCP hosts."""

from __future__ import annotations

import re

_ZERO_SPEND_ENV = {
    "DEEPR_RESEARCH_MODE": "read_only",
    "DEEPR_MCP_AUTO_APPROVE": "0",
    "DEEPR_MCP_ADVERTISE_FULL_TOOL_LIST": "0",
    "DEEPR_LOG_LEVEL": "WARNING",
    "DEEPR_MAX_COST_PER_JOB": "0",
    "DEEPR_MAX_COST_PER_DAY": "0",
    "DEEPR_MAX_COST_PER_WEEK": "0",
    "DEEPR_MAX_COST_PER_MONTH": "0",
    "DEEPR_PER_JOB_LIMIT": "0",
    "DEEPR_DAILY_LIMIT": "0",
    "DEEPR_WEEKLY_LIMIT": "0",
    "DEEPR_MONTHLY_LIMIT": "0",
}


def build_contained_read_only_env(
    root_placeholder: str,
    *,
    advertise_full_tool_list: bool = False,
) -> dict[str, str]:
    """Return explicit roots and zero spend ceilings for a host child process."""
    if re.fullmatch(r"\$\{[A-Z][A-Z0-9_]*\}", root_placeholder) is None:
        raise ValueError("root_placeholder must be one explicit ${NAME} host variable")
    root = f"{root_placeholder}/deepr"
    env = {
        "DEEPR_DATA_DIR": root,
        "DEEPR_EXPERTS_PATH": f"{root}/experts",
        "DEEPR_REPORTS_PATH": f"{root}/reports",
        "DEEPR_COST_DATA_DIR": f"{root}/costs",
        "DEEPR_CAPACITY_DATA_DIR": f"{root}/capacity",
        "DEEPR_BUDGET_FILE": f"{root}/budget.json",
        **_ZERO_SPEND_ENV,
    }
    if advertise_full_tool_list:
        env["DEEPR_MCP_ADVERTISE_FULL_TOOL_LIST"] = "1"
    return env


__all__ = ["build_contained_read_only_env"]
