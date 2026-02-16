"""Command handler functions for expert chat slash commands.

Each handler has the signature::

    async def handle_xxx(session, args: str, context: dict) -> CommandResult

*session* is an ``ExpertChatSession`` (may be ``None`` for client-only commands).
*context* is a dict with optional keys like ``cli`` (bool), ``web`` (bool).
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from deepr.experts.commands import (
    MODE_CONFIGS,
    ChatMode,
    CommandRegistry,
    CommandResult,
)
from deepr.experts.constants import TOOL_DESCRIPTIONS

if TYPE_CHECKING:
    from deepr.experts.chat import ExpertChatSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mode commands
# ---------------------------------------------------------------------------


async def handle_ask(session: ExpertChatSession, args: str, context: dict) -> CommandResult:
    return _switch_mode(session, ChatMode.ASK)


async def handle_research(session: ExpertChatSession, args: str, context: dict) -> CommandResult:
    return _switch_mode(session, ChatMode.RESEARCH)


async def handle_advise(session: ExpertChatSession, args: str, context: dict) -> CommandResult:
    return _switch_mode(session, ChatMode.ADVISE)


async def handle_focus(session: ExpertChatSession, args: str, context: dict) -> CommandResult:
    return _switch_mode(session, ChatMode.FOCUS)


async def handle_mode(session: ExpertChatSession, args: str, context: dict) -> CommandResult:
    if not args.strip():
        cfg = MODE_CONFIGS[session.chat_mode]
        lines = [f"Current mode: **{session.chat_mode.value}** — {cfg['description']}"]
        lines.append("")
        lines.append("Available modes:")
        for mode, mcfg in MODE_CONFIGS.items():
            marker = " (active)" if mode == session.chat_mode else ""
            lines.append(f"  /{mode.value} — {mcfg['description']}{marker}")
        return CommandResult(output="\n".join(lines))

    name = args.strip().lower()
    try:
        target = ChatMode(name)
    except ValueError:
        return CommandResult(output=f"Unknown mode: {name}. Use /mode to see options.", success=False)
    return _switch_mode(session, target)


def _switch_mode(session: ExpertChatSession, mode: ChatMode) -> CommandResult:
    old = session.chat_mode
    session.chat_mode = mode
    cfg = MODE_CONFIGS[mode]
    return CommandResult(
        output=f"Switched to **{mode.value}** mode — {cfg['description']}",
        mode_changed=mode,
        data={"old_mode": old.value, "new_mode": mode.value},
    )


# ---------------------------------------------------------------------------
# Session commands
# ---------------------------------------------------------------------------


async def handle_clear(session: ExpertChatSession | None, args: str, context: dict) -> CommandResult:
    if session:
        session.messages = []
    return CommandResult(output="Conversation history cleared.", clear_chat=True)


async def handle_compact(session: ExpertChatSession, args: str, context: dict) -> CommandResult:
    result = await session.compact_conversation()
    count = result.get("original_messages", 0)
    return CommandResult(
        output=f"Compacted {count} messages into a summary.",
        data=result,
    )


async def handle_remember(session: ExpertChatSession, args: str, context: dict) -> CommandResult:
    text = args.strip()
    if not text:
        return CommandResult(output="Usage: /remember <text>", success=False)
    session.pinned_memories.append(text)
    idx = len(session.pinned_memories)
    return CommandResult(output=f"Remembered ({idx}): {text}")


async def handle_forget(session: ExpertChatSession, args: str, context: dict) -> CommandResult:
    text = args.strip()
    if not text:
        return CommandResult(output="Usage: /forget <index>", success=False)
    try:
        idx = int(text) - 1
        if 0 <= idx < len(session.pinned_memories):
            removed = session.pinned_memories.pop(idx)
            return CommandResult(output=f"Forgot: {removed}")
        return CommandResult(
            output=f"Invalid index. You have {len(session.pinned_memories)} pinned memories.", success=False
        )
    except ValueError:
        return CommandResult(output="Usage: /forget <number>", success=False)


async def handle_memories(session: ExpertChatSession, args: str, context: dict) -> CommandResult:
    if not session.pinned_memories:
        return CommandResult(output="No pinned memories. Use /remember <text> to pin facts.")
    lines = ["Pinned memories:"]
    for i, mem in enumerate(session.pinned_memories, 1):
        lines.append(f"  {i}. {mem}")
    return CommandResult(output="\n".join(lines))


async def handle_new(session: ExpertChatSession | None, args: str, context: dict) -> CommandResult:
    if session:
        session.messages = []
    return CommandResult(output="Started a new conversation.", clear_chat=True)


# ---------------------------------------------------------------------------
# Reasoning commands
# ---------------------------------------------------------------------------


async def handle_trace(session: ExpertChatSession, args: str, context: dict) -> CommandResult:
    if not session.reasoning_trace:
        return CommandResult(output="No reasoning trace available yet.")
    lines = ["Reasoning trace:"]
    for i, step in enumerate(session.reasoning_trace, 1):
        step_type = step.get("step", "unknown")
        query = step.get("query", "")
        reasoning = step.get("reasoning", "")
        line = f"  {i}. [{step_type}]"
        if query:
            line += f" {query[:80]}"
        if reasoning:
            line += f"\n     Why: {reasoning[:120]}"
        lines.append(line)
    return CommandResult(output="\n".join(lines), data={"trace": session.reasoning_trace})


async def handle_why(session: ExpertChatSession, args: str, context: dict) -> CommandResult:
    decisions = session.thought_stream.decision_records
    if not decisions:
        return CommandResult(output="No decisions recorded yet. Ask a question first.")
    last = decisions[-1]
    output = f"Last decision: {last.decision}\nConfidence: {last.confidence:.0%}\nReasoning: {last.reasoning}"
    return CommandResult(output=output)


async def handle_decisions(session: ExpertChatSession, args: str, context: dict) -> CommandResult:
    records = session.thought_stream.decision_records
    if not records:
        return CommandResult(output="No decisions recorded yet.")
    lines = ["Decisions this session:"]
    for i, rec in enumerate(records, 1):
        lines.append(f"  {i}. [{rec.confidence:.0%}] {rec.decision}")
    return CommandResult(output="\n".join(lines))


async def handle_thinking(session: ExpertChatSession, args: str, context: dict) -> CommandResult:
    arg = args.strip().lower()
    if arg == "on":
        session.verbose_thinking = True
        session.thought_stream.verbose = True
        return CommandResult(output="Verbose thinking enabled.")
    elif arg == "off":
        session.verbose_thinking = False
        session.thought_stream.verbose = False
        return CommandResult(output="Verbose thinking disabled.")
    else:
        current = "on" if session.verbose_thinking else "off"
        return CommandResult(output=f"Thinking display is currently **{current}**. Use /thinking on|off")


# ---------------------------------------------------------------------------
# Control commands
# ---------------------------------------------------------------------------


async def handle_model(session: ExpertChatSession, args: str, context: dict) -> CommandResult:
    if not args.strip():
        return CommandResult(output=f"Current model: {session.expert.model}")
    # Note: model switching would need deeper integration; for now just inform
    return CommandResult(output=f"Model switching is managed by the router. Current: {session.expert.model}")


async def handle_tools(session: ExpertChatSession, args: str, context: dict) -> CommandResult:
    cfg = MODE_CONFIGS[session.chat_mode]
    allowed = cfg["tools"]
    lines = [f"Tools available in **{session.chat_mode.value}** mode:"]
    for tool_name in allowed:
        desc = TOOL_DESCRIPTIONS.get(tool_name, tool_name)
        lines.append(f"  - {tool_name}: {desc}")
    if session.active_skills:
        lines.append("")
        lines.append("Skill tools:")
        for skill in session.active_skills:
            for tool in skill.tools:
                lines.append(f"  - {skill.name}/{tool.name}")
    return CommandResult(output="\n".join(lines))


async def handle_effort(session: ExpertChatSession, args: str, context: dict) -> CommandResult:
    level = args.strip().lower()
    mapping = {"low": "low", "med": "medium", "medium": "medium", "high": "high"}
    if level not in mapping:
        current = getattr(session, "_reasoning_effort", "medium")
        return CommandResult(output=f"Current effort: {current}. Use /effort low|med|high")
    session._reasoning_effort = mapping[level]
    return CommandResult(output=f"Reasoning effort set to **{mapping[level]}**.")


async def handle_budget(session: ExpertChatSession, args: str, context: dict) -> CommandResult:
    if not args.strip():
        remaining = session.budget - session.cost_accumulated
        return CommandResult(
            output=f"Budget: ${session.budget:.2f} | Spent: ${session.cost_accumulated:.4f} | Remaining: ${remaining:.4f}"
        )
    try:
        new_budget = float(args.strip().lstrip("$"))
        session.budget = new_budget
        return CommandResult(output=f"Budget updated to ${new_budget:.2f}")
    except ValueError:
        return CommandResult(output="Usage: /budget [amount]", success=False)


# ---------------------------------------------------------------------------
# Management commands
# ---------------------------------------------------------------------------


async def handle_save(session: ExpertChatSession, args: str, context: dict) -> CommandResult:
    name = args.strip() or None
    sid = session.save_conversation(name)
    return CommandResult(output=f"Conversation saved: {sid}", data={"session_id": sid})


async def handle_load(session: ExpertChatSession, args: str, context: dict) -> CommandResult:
    sid = args.strip()
    if not sid:
        return CommandResult(output="Usage: /load <session_id>", success=False)
    try:
        from deepr.experts.profile import ExpertStore

        store = ExpertStore()
        conv_dir = store.get_conversations_dir(session.expert.name)
        conv_file = conv_dir / f"{sid}.json"
        if not conv_file.exists():
            return CommandResult(output=f"Conversation '{sid}' not found.", success=False)
        with open(conv_file, encoding="utf-8") as f:
            data = json.load(f)
        session.messages = data.get("messages", [])
        return CommandResult(
            output=f"Loaded conversation {sid} ({len(session.messages)} messages).",
            data={"session_id": sid, "messages": len(session.messages)},
        )
    except Exception as e:
        return CommandResult(output=f"Failed to load: {e}", success=False)


async def handle_export(session: ExpertChatSession, args: str, context: dict) -> CommandResult:
    fmt = args.strip().lower() or "md"
    if fmt == "json":
        content = json.dumps(session.messages, indent=2, ensure_ascii=False)
        return CommandResult(output="Exported as JSON.", export_content=content, data={"format": "json"})
    # Default: markdown
    lines: list[str] = [f"# Chat with {session.expert.name}", ""]
    for msg in session.messages:
        role = "**You**" if msg["role"] == "user" else f"**{session.expert.name}**"
        lines.append(f"{role}: {msg.get('content', '')}")
        lines.append("")
    content = "\n".join(lines)
    return CommandResult(output="Exported as Markdown.", export_content=content, data={"format": "md"})


async def handle_council(session: ExpertChatSession, args: str, context: dict) -> CommandResult:
    query = args.strip()
    if not query:
        return CommandResult(output="Usage: /council <query>", success=False)
    try:
        from deepr.experts.council import ExpertCouncil

        council = ExpertCouncil()
        result = await council.consult(query, budget=min(5.0, session.budget - session.cost_accumulated))
        session.cost_accumulated += result.get("total_cost", 0.0)
        return CommandResult(output=result.get("synthesis", "Council consultation complete."), data=result)
    except Exception as e:
        return CommandResult(output=f"Council error: {e}", success=False)


async def handle_plan(session: ExpertChatSession, args: str, context: dict) -> CommandResult:
    query = args.strip()
    if not query:
        return CommandResult(output="Usage: /plan <query>", success=False)
    try:
        from deepr.experts.task_planner import TaskPlanner

        planner = TaskPlanner(session)
        plan = await planner.decompose(query)
        return CommandResult(
            output=plan.get("display", "Plan created."),
            data=plan,
        )
    except Exception as e:
        return CommandResult(output=f"Planning error: {e}", success=False)


# ---------------------------------------------------------------------------
# Utility commands
# ---------------------------------------------------------------------------


async def handle_help(session: ExpertChatSession | None, args: str, context: dict) -> CommandResult:
    registry = CommandRegistry.get_instance()
    specific = args.strip().lstrip("/").lstrip("\\")
    if specific:
        cmd = registry.get(specific)
        if cmd:
            aliases = ", ".join(f"/{a}" for a in cmd.aliases) if cmd.aliases else "none"
            return CommandResult(
                output=f"/{cmd.name} {cmd.args}\n{cmd.description}\nAliases: {aliases}\nCategory: {cmd.category.value}"
            )
        return CommandResult(output=f"Unknown command: /{specific}", success=False)

    groups = registry.commands_by_category()
    lines: list[str] = ["**Available Commands**", ""]
    for cat in [c for c in groups]:
        lines.append(f"**{cat.value}**")
        for cmd in groups[cat]:
            arg_str = f" {cmd.args}" if cmd.args else ""
            lines.append(f"  /{cmd.name}{arg_str} — {cmd.description}")
        lines.append("")
    lines.append("Type your question to chat. Use / (web) or \\ (CLI) prefix for commands.")
    return CommandResult(output="\n".join(lines))


async def handle_status(session: ExpertChatSession, args: str, context: dict) -> CommandResult:
    summary = session.get_session_summary()
    mode_label = MODE_CONFIGS[session.chat_mode]["label"]
    lines = [
        f"Expert: {summary['expert_name']}",
        f"Mode: {mode_label}",
        f"Messages: {summary['messages_exchanged']}",
        f"Cost: ${summary['cost_accumulated']:.4f} / ${session.budget:.2f}",
        f"Model: {summary['model']}",
        f"Research jobs: {summary['research_jobs_triggered']}",
        f"Reasoning steps: {summary['reasoning_steps']}",
    ]
    if session.pinned_memories:
        lines.append(f"Pinned memories: {len(session.pinned_memories)}")
    return CommandResult(output="\n".join(lines), data=summary)


async def handle_quit(session: ExpertChatSession | None, args: str, context: dict) -> CommandResult:
    return CommandResult(output="Ending chat session.", end_session=True)


# ---------------------------------------------------------------------------
# Handler dispatch table
# ---------------------------------------------------------------------------

HANDLERS: dict[str, Any] = {
    "ask": handle_ask,
    "research": handle_research,
    "advise": handle_advise,
    "focus": handle_focus,
    "mode": handle_mode,
    "clear": handle_clear,
    "compact": handle_compact,
    "remember": handle_remember,
    "forget": handle_forget,
    "memories": handle_memories,
    "new": handle_new,
    "trace": handle_trace,
    "why": handle_why,
    "decisions": handle_decisions,
    "thinking": handle_thinking,
    "model": handle_model,
    "tools": handle_tools,
    "effort": handle_effort,
    "budget": handle_budget,
    "save": handle_save,
    "load": handle_load,
    "export": handle_export,
    "council": handle_council,
    "plan": handle_plan,
    "help": handle_help,
    "status": handle_status,
    "quit": handle_quit,
}


async def dispatch_command(
    session: ExpertChatSession | None,
    raw_input: str,
    context: dict | None = None,
) -> CommandResult | None:
    """Parse *raw_input* and dispatch to the appropriate handler.

    Returns ``None`` if the input is not a command.
    """
    registry = CommandRegistry.get_instance()
    cmd, args = registry.parse(raw_input)
    if cmd is None:
        return None

    handler = HANDLERS.get(cmd.name)
    if handler is None:
        return CommandResult(output=f"Unknown command: /{cmd.name}", success=False)

    return await handler(session, args, context or {})
