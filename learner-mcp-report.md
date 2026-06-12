---
# MCP State Checklist (2026)
**Model Context Protocol (MCP): Host/Server Interop Checklist**

## Capability Negotiation
- Support dynamic discovery of available tools, resources, and prompts via tool search and list endpoints.
- Return only minimal tool manifests by default to reduce context; use semantic search (e.g., BM25) for agent-driven discovery.
- Implement capability filtering to show only permitted/affordable tools per session/context.
- Use explicit capability advertisement files (manifest/agent card for A2A scenarios).

## Tool, Resource, and Prompt Schemas
- Tools: Each defines a task, schema for parameters, cost, modes (research, validate, consult, reflect), and error conventions. Key built-ins:
  - Research jobs (deep, agentic/multi-step)
  - Status/progress, expert consultation, report retrieval, validation, gap ranking/routing, skill install/list, reflection/self-evaluation
  - Task management: pause/resume/cancel, get progress
- Resources: URI-based, covering live campaign/job status, research plans, beliefs, report artifacts, logs, expert state, skills, and knowledge gaps.
- Prompts: Predefined templates for deep research, expert Q&A, comparison/decision analysis. Exposed in a prompt registry for agent invocation.

## Transport Options & Constraints
- Primary transport: JSON-RPC 2.0 over stdio (stdin/stdout)—portable across OpenClaw, VS Code, Claude Desktop, Cursor, Zed.
- Environment: Python 3.12+ runtime, API key provisioning via environment variables, with optional provider support (OpenAI, xAI, Gemini, Azure).
- Structured error returns for all tools, with retry and fallback guidance.
- Subscription-based resource updates (push, not poll), reducing token usage for live progress/artifact changes.
- Job tracking: memory/SQLite for persistence; supports recovery of session state and long-running or resumable jobs.
- Logging: Structured JSON for compatibility with external log aggregators.

## Breaking Changes Since Early Releases
- Tool manifest/context handling moved to dynamic search/discovery; full tool lists are no longer returned by default.
- Separation of resources, prompts, and tools with unified schema; legacy tool-only MCP servers may lack full resource or prompt capabilities.
- MCPSampling added: hosts/servers can request completions from client models, enabling collaborative synthesis and delegation.
- Structured handoff contracts for research outputs and expert responses—breaking for any client expecting opaque text.
- Strong move toward expert validation, campaign management, and agent-to-agent (A2A) interop; hosts must adapt to expanded workflow envelopes.
- Skill portability via agentskills.io; skills now declaratively bundled for cross-platform compatibility.

## “Interop Musts” for Hosts/Servers
- Implement full dynamic tool/resource/prompt discovery (not hardcoded identifiers).
- Handle structured errors and prompt fallback/retry behavior.
- Expose and subscribe to resource URIs for job, expert, and artifact state—handle push update flows.
- Accept and return JSON handoff contracts for research/expert results.
- Enforce cost/approval gates per session or operation (including distinction between free, low, and high-cost tools).
- Enable/propagate streaming and partial-result flows for long-running or multi-phase tasks.
- Support agent skill manifests and registration (for portable skill/adaptive capability imports).
- For A2A compatibility, serve/consume Agent Card manifests and adopt standard task lifecycle: submit, track, stream updates, complete/fail.
- Maintain compatibility with MCP spec evolution (track breaking changes; use semantic versioning).

---

This checklist reflects requirements and best practices for implementing, hosting, or interoperating with Model Context Protocol servers (MCP, 2026), covering tool/resource/prompt schemas, negotiation, transport constraints, evolution, and mandatory interop mechanisms.