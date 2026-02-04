"""MCP Server for Deepr.

Exposes Deepr research and expert functionality via Model Context Protocol
for use by AI agents (OpenClaw, Claude Desktop, Cursor, VS Code, Zed).

Architecture:
    StdioServer (transport) -> method dispatch -> DeeprMCPServer (business logic)
                                                  -> MCPResourceHandler (resources)
                                                  -> JobManager (state tracking)
                                                  -> GatewayTool (tool discovery)
                                                  -> ToolRegistry (BM25 search)

Tools exposed:
- deepr_tool_search: Dynamic tool discovery (gateway pattern, ~85% context reduction)
- deepr_status: Health check and server status
- deepr_research: Submit deep research jobs
- deepr_check_status: Check research job status
- deepr_get_result: Get completed research results
- deepr_cancel_job: Cancel a running research job
- deepr_agentic_research: Start autonomous multi-step research workflows
- deepr_list_experts: List available domain experts
- deepr_query_expert: Query a domain expert
- deepr_get_expert_info: Get detailed expert information

Resources:
- deepr://campaigns/{id}/status - Job state and progress
- deepr://campaigns/{id}/plan - Research plan
- deepr://campaigns/{id}/beliefs - Accumulated findings
- deepr://reports/{id}/final.md - Completed research report
- deepr://reports/{id}/summary.json - Report metadata
- deepr://logs/{id}/search_trace.json - Search query history
- deepr://experts/{id}/profile - Expert profile
- deepr://experts/{id}/beliefs - Expert beliefs
- deepr://experts/{id}/gaps - Knowledge gaps
"""
import os
import sys
import asyncio
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict

from deepr.core.errors import DeeprError
from deepr.experts.profile import ExpertProfile, ExpertStore
from deepr.experts.chat import ExpertChatSession
from deepr.providers import create_provider
from deepr.storage import create_storage
from deepr.core.research import ResearchOrchestrator
from deepr.core.documents import DocumentManager
from deepr.core.reports import ReportGenerator
from deepr.config import load_config

from deepr.mcp.transport.stdio import StdioServer, Message
from deepr.mcp.state.resource_handler import MCPResourceHandler, get_resource_handler
from deepr.mcp.state.job_manager import JobManager, JobPhase
from deepr.mcp.state.task_durability import TaskDurabilityManager, TaskStatus, DurableTask
from deepr.mcp.state.async_dispatcher import AsyncTaskDispatcher
from deepr.mcp.search.registry import ToolRegistry, ToolSchema, create_default_registry
from deepr.mcp.search.gateway import GatewayTool
from deepr.mcp.security import SSRFProtector
from deepr.mcp.security.instruction_signing import InstructionSigner, SignedInstruction
from deepr.mcp.security.output_verification import OutputVerifier
from deepr.mcp.security.tool_allowlist import ToolAllowlist, ResearchMode

# Prompt primitives (template menus for MCP clients)
try:
    from skills.deepr_research_prompts import list_prompts, get_prompt  # type: ignore
except ImportError:
    # Fallback: load prompts module from skills directory without sys.path manipulation
    try:
        import importlib.util
        _prompts_path = Path(__file__).parent.parent.parent / "skills" / "deepr-research" / "prompts.py"
        _spec = importlib.util.spec_from_file_location("deepr_prompts", _prompts_path)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        list_prompts = _mod.list_prompts
        get_prompt = _mod.get_prompt
    except (ImportError, FileNotFoundError, AttributeError, OSError) as e:
        logging.getLogger(__name__).debug("Could not load prompts module: %s", e)
        def list_prompts():
            return []
        def get_prompt(name, arguments):
            return {"error": "Prompts module not available"}


# Configure structured JSON logging to stderr (for OpenClaw log aggregation)
logger = logging.getLogger("deepr.mcp")
_log_handler = logging.StreamHandler(sys.stderr)
_log_format = os.environ.get("DEEPR_LOG_FORMAT", "text")
if _log_format == "json":
    _log_handler.setFormatter(logging.Formatter(
        '{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}'
    ))
else:
    _log_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    ))
logger.addHandler(_log_handler)
logger.setLevel(getattr(logging, os.environ.get("DEEPR_LOG_LEVEL", "INFO").upper(), logging.INFO))


# Server version and start time for health checks
from deepr import __version__ as SERVER_VERSION
_server_start_time: float = 0.0


@dataclass
class ToolError:
    """Structured error response returned by tools instead of raising exceptions.

    Agents can parse these fields to decide on retry/fallback strategies.
    """
    error_code: str
    message: str
    retry_hint: Optional[str] = None
    fallback_suggestion: Optional[str] = None

    def to_dict(self) -> dict:
        d: dict = {"error_code": self.error_code, "message": self.message}
        if self.retry_hint:
            d["retry_hint"] = self.retry_hint
        if self.fallback_suggestion:
            d["fallback_suggestion"] = self.fallback_suggestion
        return d


def _make_error(
    code: str,
    message: str,
    retry_hint: Optional[str] = None,
    fallback: Optional[str] = None,
) -> dict:
    """Convenience for returning a structured error dict from a tool."""
    return ToolError(
        error_code=code,
        message=message,
        retry_hint=retry_hint,
        fallback_suggestion=fallback,
    ).to_dict()


class DeeprMCPServer:
    """MCP server for Deepr research and experts.

    Integrates with:
    - MCPResourceHandler: unified resource reads, subscriptions, expert resources
    - JobManager: research job lifecycle and notifications
    - ToolRegistry + GatewayTool: dynamic tool discovery via BM25 search
    """

    def __init__(self):
        """Initialize MCP server with research and expert capabilities."""
        # Expert-related components
        self.store = ExpertStore()
        self.sessions: Dict[str, ExpertChatSession] = {}

        # Research-related components
        self.config = load_config()
        self.active_jobs: Dict[str, Dict] = {}  # Provider instance cache

        # MCP infrastructure
        self.resource_handler = get_resource_handler()
        self.registry = create_default_registry()
        self.gateway = GatewayTool(self.registry)

        # Security: SSRF protection for outbound requests
        allowed_domains_env = os.environ.get("DEEPR_ALLOWED_DOMAINS", "")
        allowed_domains = (
            [d.strip() for d in allowed_domains_env.split(",") if d.strip()]
            if allowed_domains_env
            else None
        )
        self.ssrf_protector = SSRFProtector(
            allowed_domains=allowed_domains,
            audit_log=True,
        )

        # Task durability for reconnection support
        self.durability_manager = TaskDurabilityManager()
        self.async_dispatcher = AsyncTaskDispatcher()

        # Security: instruction signing, output verification, tool allowlist
        self.instruction_signer = InstructionSigner()
        self.output_verifier = OutputVerifier()

        # Research mode from environment (default: standard)
        research_mode_str = os.environ.get("DEEPR_RESEARCH_MODE", "standard")
        try:
            research_mode = ResearchMode(research_mode_str)
        except ValueError:
            research_mode = ResearchMode.STANDARD
            logger.warning("Invalid DEEPR_RESEARCH_MODE '%s', using 'standard'", research_mode_str)
        self.tool_allowlist = ToolAllowlist(mode=research_mode)

        # Register the tools in the registry
        _register_new_tools(self.registry)

    # ------------------------------------------------------------------ #
    # Tool: deepr_status (health check)
    # ------------------------------------------------------------------ #
    async def deepr_status(self) -> Dict:
        """Health check returning server version, uptime, active jobs, and cost summary."""
        try:
            from deepr.experts.cost_safety import get_cost_safety_manager
            cost_safety = get_cost_safety_manager()
            spending = cost_safety.get_spending_summary()
        except (ImportError, KeyError, ValueError):
            spending = {"daily": {"spent": 0, "remaining": "unknown"}, "monthly": {"spent": 0}}

        uptime = time.time() - _server_start_time if _server_start_time else 0
        active_count = len(self.resource_handler.jobs.list_jobs(phase=None))

        return {
            "status": "healthy",
            "version": SERVER_VERSION,
            "uptime_seconds": round(uptime, 1),
            "active_jobs": active_count,
            "transport": "stdio",
            "cost_summary": {
                "daily_spent": spending.get("daily", {}).get("spent", 0),
                "daily_remaining": spending.get("daily", {}).get("remaining", "unknown"),
                "monthly_spent": spending.get("monthly", {}).get("spent", 0),
            },
            "capabilities": {
                "tools": self.registry.count(),
                "dynamic_discovery": True,
                "resource_subscriptions": True,
                "elicitation": True,
            },
            "security": {
                "research_mode": self.tool_allowlist.mode.value,
                "allowed_tools": len(self.tool_allowlist.get_allowed_tools()),
                "blocked_tools": len(self.tool_allowlist.get_blocked_tools()),
                "tools_requiring_confirmation": len(self.tool_allowlist.get_tools_requiring_confirmation()),
                "instruction_signing": True,
                "output_verification": True,
            },
        }

    # ------------------------------------------------------------------ #
    # Tool: deepr_tool_search (gateway / dynamic discovery)
    # ------------------------------------------------------------------ #
    async def deepr_tool_search(self, query: str, limit: int = 3) -> Dict:
        """Search Deepr capabilities by natural language query."""
        return self.gateway.search(query, limit=limit)

    # ------------------------------------------------------------------ #
    # Tool: deepr_cancel_job
    # ------------------------------------------------------------------ #
    async def deepr_cancel_job(self, job_id: str) -> Dict:
        """Cancel a running research job."""
        state = self.resource_handler.jobs.get_state(job_id)
        if not state:
            return _make_error("JOB_NOT_FOUND", f"Job '{job_id}' not found")

        terminal = {JobPhase.COMPLETED, JobPhase.FAILED, JobPhase.CANCELLED}
        if state.phase in terminal:
            return _make_error(
                "JOB_ALREADY_TERMINAL",
                f"Job '{job_id}' already in terminal state: {state.phase.value}",
            )

        await self.resource_handler.jobs.update_phase(job_id, JobPhase.CANCELLED)
        self.resource_handler.persist_job(job_id)
        # Clean up provider cache
        self.active_jobs.pop(job_id, None)

        return {
            "job_id": job_id,
            "status": "cancelled",
            "message": f"Job '{job_id}' has been cancelled.",
        }

    # ------------------------------------------------------------------ #
    # Tool: deepr_list_experts
    # ------------------------------------------------------------------ #
    async def list_experts(self) -> List[Dict]:
        """List all available experts."""
        try:
            experts = self.store.list_all()
            return [
                {
                    "name": expert["name"],
                    "domain": expert["domain"],
                    "description": expert["description"],
                    "documents": expert["stats"]["documents"],
                    "conversations": expert["stats"]["conversations"],
                }
                for expert in experts
            ]
        except (OSError, KeyError, ValueError) as e:
            return [_make_error("EXPERT_LIST_FAILED", str(e))]

    # ------------------------------------------------------------------ #
    # Tool: deepr_get_expert_info
    # ------------------------------------------------------------------ #
    async def get_expert_info(self, expert_name: str) -> Dict:
        """Get detailed information about a specific expert."""
        try:
            expert = self.store.load(expert_name)
            if not expert:
                return _make_error("EXPERT_NOT_FOUND", f"Expert '{expert_name}' not found")

            return {
                "name": expert.name,
                "domain": expert.domain,
                "description": expert.description,
                "vector_store_id": expert.vector_store_id,
                "stats": {
                    "documents": expert.total_documents,
                    "conversations": expert.stats.get("conversations", 0),
                    "research_jobs": len(expert.research_jobs),
                    "total_cost": expert.stats.get("total_cost", 0.0),
                },
                "created_at": expert.created_at.isoformat() if expert.created_at else None,
                "last_knowledge_refresh": (
                    expert.last_knowledge_refresh.isoformat()
                    if expert.last_knowledge_refresh
                    else None
                ),
            }
        except (OSError, KeyError, ValueError) as e:
            return _make_error("EXPERT_INFO_FAILED", str(e))

    # ------------------------------------------------------------------ #
    # Tool: deepr_query_expert
    # ------------------------------------------------------------------ #
    async def query_expert(
        self,
        expert_name: str,
        question: str,
        budget: float = 0.0,
        agentic: bool = False,
    ) -> Dict:
        """Query an expert with a question."""
        try:
            expert = self.store.load(expert_name)
            if not expert:
                return _make_error("EXPERT_NOT_FOUND", f"Expert '{expert_name}' not found")

            session_key = f"{expert_name}_{id(question)}"
            if session_key not in self.sessions:
                self.sessions[session_key] = ExpertChatSession(
                    expert,
                    budget=budget if agentic else None,
                    agentic=agentic,
                )

            session = self.sessions[session_key]
            response_text = await session.send_message(question)
            summary = session.get_session_summary()

            del self.sessions[session_key]

            return {
                "answer": response_text,
                "expert": expert_name,
                "cost": summary["cost_accumulated"],
                "budget_remaining": summary.get("budget_remaining"),
                "research_triggered": summary["research_jobs_triggered"],
            }
        except (OSError, KeyError, ValueError, DeeprError) as e:
            return _make_error("EXPERT_QUERY_FAILED", str(e))

    # ------------------------------------------------------------------ #
    # Tool: deepr_research
    # ------------------------------------------------------------------ #
    async def deepr_research(
        self,
        prompt: str,
        model: str = "o4-mini-deep-research",
        provider: str = "openai",
        enable_web_search: bool = True,
        enable_code_interpreter: bool = True,
        budget: Optional[float] = None,
        files: Optional[List[str]] = None,
    ) -> Dict:
        """Submit a deep research job."""
        try:
            # Generate trace_id for end-to-end request tracking
            trace_id = uuid.uuid4().hex[:16]

            # Estimate cost based on model
            if "o4-mini" in model:
                cost_estimate = 0.15
                estimated_time = "5-10 minutes"
            elif "o3" in model:
                cost_estimate = 0.50
                estimated_time = "10-20 minutes"
            else:
                cost_estimate = 0.20
                estimated_time = "5-15 minutes"

            # CRITICAL: Validate budget BEFORE any API calls
            from deepr.experts.cost_safety import get_cost_safety_manager

            cost_safety = get_cost_safety_manager()
            session_id = f"mcp_research_{uuid.uuid4().hex[:8]}"

            allowed, reason, _ = cost_safety.check_operation(
                session_id=session_id,
                operation_type="mcp_research",
                estimated_cost=cost_estimate,
                require_confirmation=False,
            )

            if not allowed:
                return _make_error(
                    "BUDGET_EXCEEDED",
                    f"Research blocked by cost safety: {reason}",
                    retry_hint="Wait for daily limit reset or increase budget with 'deepr budget set'",
                    fallback=f"Daily spent: ${cost_safety.daily_cost:.2f}",
                )

            if budget is not None and cost_estimate > budget:
                return _make_error(
                    "BUDGET_INSUFFICIENT",
                    f"Estimated cost ${cost_estimate:.2f} exceeds budget ${budget:.2f}",
                    retry_hint=f"Set budget >= ${cost_estimate:.2f}",
                )

            # SSRF: validate any user-provided file URLs
            if files:
                for f in files:
                    if f.startswith(("http://", "https://")):
                        try:
                            self.ssrf_protector.validate_url(f)
                        except ValueError as ssrf_err:
                            return _make_error(
                                "SSRF_BLOCKED",
                                str(ssrf_err),
                                fallback="Only public URLs are allowed as file sources",
                            )

            # Create provider instance
            api_key = self._get_api_key(provider)
            if not api_key:
                return _make_error(
                    "PROVIDER_NOT_CONFIGURED",
                    f"No API key configured for provider: {provider}",
                    fallback="Configure via .env file or environment variables",
                )

            provider_instance = create_provider(provider, api_key)
            storage_instance = create_storage("local", base_path="data/reports")
            doc_manager = DocumentManager()
            report_generator = ReportGenerator()

            orchestrator = ResearchOrchestrator(
                provider_instance, storage_instance, doc_manager, report_generator
            )

            job_id = await orchestrator.submit_research(
                prompt=prompt,
                model=model,
                documents=files if files else None,
                enable_web_search=enable_web_search,
                enable_code_interpreter=enable_code_interpreter,
                cost_sensitive=budget is not None and budget < 0.20,
                budget_limit=budget,
                session_id=session_id,
            )

            # Track in JobManager for resource subscriptions
            await self.resource_handler.jobs.create_job(
                job_id=job_id,
                goal=prompt,
                model=model,
                estimated_cost=cost_estimate,
                estimated_time=estimated_time,
            )
            # Store trace_id in job metadata for end-to-end tracking
            state = self.resource_handler.jobs.get_state(job_id)
            if state:
                state.metadata["trace_id"] = trace_id
                state.metadata["session_id"] = session_id

            # Persist to SQLite
            self.resource_handler.persist_job(job_id)

            # Cache provider instance for status checks
            self.active_jobs[job_id] = {
                "provider_instance": provider_instance,
                "submitted_at": datetime.now().isoformat(),
            }

            logger.info("Research job %s submitted (trace=%s)", job_id, trace_id)

            spending = cost_safety.get_spending_summary()
            resource_uris = self.resource_handler.get_resource_uri_for_job(job_id)

            return {
                "job_id": job_id,
                "trace_id": trace_id,
                "status": "submitted",
                "estimated_time": estimated_time,
                "cost_estimate": cost_estimate,
                "daily_spent": spending["daily"]["spent"],
                "daily_remaining": spending["daily"]["remaining"],
                "resource_uris": resource_uris,
                "message": (
                    f"Research job submitted. Use deepr_check_status with job_id "
                    f"'{job_id}' to check progress, or subscribe to "
                    f"{resource_uris['status']} for push notifications."
                ),
            }

        except ValueError as ve:
            return _make_error("VALIDATION_ERROR", str(ve))
        except Exception as e:
            logger.exception("deepr_research failed")
            return _make_error("INTERNAL_ERROR", str(e))

    # ------------------------------------------------------------------ #
    # Tool: deepr_check_status
    # ------------------------------------------------------------------ #
    async def deepr_check_status(self, job_id: str) -> Dict:
        """Check the status of a research job."""
        try:
            # First check JobManager (canonical state)
            state = self.resource_handler.jobs.get_state(job_id)

            if job_id not in self.active_jobs and not state:
                return _make_error("JOB_NOT_FOUND", f"Job '{job_id}' not found")

            job_cache = self.active_jobs.get(job_id, {})
            provider_instance = job_cache.get("provider_instance")

            if provider_instance:
                try:
                    status = await provider_instance.get_job_status(job_id)
                    # Sync provider status into JobManager
                    phase_map = {
                        "completed": JobPhase.COMPLETED,
                        "failed": JobPhase.FAILED,
                        "in_progress": JobPhase.EXECUTING,
                        "queued": JobPhase.QUEUED,
                    }
                    provider_phase = phase_map.get(
                        status.get("status", ""), JobPhase.EXECUTING
                    )
                    await self.resource_handler.jobs.update_phase(
                        job_id,
                        provider_phase,
                        cost_so_far=status.get("cost", 0.0),
                    )
                    self.resource_handler.persist_job(job_id)

                    return {
                        "job_id": job_id,
                        "status": status["status"],
                        "progress": status.get("progress"),
                        "elapsed_time": status.get("elapsed_time"),
                        "cost_so_far": status.get("cost", 0.0),
                        "submitted_at": job_cache.get("submitted_at"),
                    }
                except Exception:
                    # Provider status check may fail transiently; fall through
                    # to JobManager state below.
                    pass

            # Fallback to JobManager state
            if state:
                return {
                    "job_id": job_id,
                    "status": state.phase.value,
                    "progress": state.progress,
                    "cost_so_far": state.cost_so_far,
                    "submitted_at": state.started_at.isoformat(),
                }

            return {
                "job_id": job_id,
                "status": "submitted",
                "message": "Job submitted, waiting for provider to begin processing",
            }

        except Exception as e:
            return _make_error("STATUS_CHECK_FAILED", str(e))

    # ------------------------------------------------------------------ #
    # Tool: deepr_get_result
    # ------------------------------------------------------------------ #
    async def deepr_get_result(self, job_id: str) -> Dict:
        """Get the results of a completed research job."""
        try:
            job_cache = self.active_jobs.get(job_id)
            if not job_cache:
                return _make_error("JOB_NOT_FOUND", f"Job '{job_id}' not found")

            provider_instance = job_cache.get("provider_instance")
            if not provider_instance:
                return _make_error("PROVIDER_LOST", "Provider instance no longer available")

            status = await provider_instance.get_job_status(job_id)

            if status["status"] != "completed":
                return {
                    "job_id": job_id,
                    "status": status["status"],
                    "message": f"Job not yet complete. Current status: {status['status']}",
                }

            result = await provider_instance.get_job_result(job_id)

            # Update JobManager to completed
            await self.resource_handler.jobs.update_phase(
                job_id, JobPhase.COMPLETED, progress=1.0,
                cost_so_far=result.get("cost", 0.0),
            )
            self.resource_handler.persist_job(job_id)

            # Clean up
            del self.active_jobs[job_id]

            report = result.get("report", "")
            cost_final = result.get("cost", 0.0)
            metadata = result.get("metadata", {})
            sources = result.get("sources", [])

            # Lazy loading: if report is large, return summary + resource URI
            # so agents can fetch the full report on demand
            max_inline = int(os.environ.get("DEEPR_MAX_INLINE_CHARS", "8000"))
            if len(report) > max_inline:
                # Build a truncated summary with key sections
                summary_text = report[:2000]
                if "\n## " in report[2000:]:
                    # Try to include at least the next section header
                    next_section = report.find("\n## ", 2000)
                    if next_section > 0 and next_section < 3000:
                        summary_text = report[:next_section]

                return {
                    "job_id": job_id,
                    "status": "completed",
                    "summary": summary_text + "\n\n... (truncated)",
                    "full_report_uri": f"deepr://reports/{job_id}/final.md",
                    "report_length": len(report),
                    "cost_final": cost_final,
                    "metadata": metadata,
                    "sources_count": len(sources),
                    "hint": (
                        "Report truncated for context efficiency. "
                        "Use resources/read with the full_report_uri to get the complete report."
                    ),
                }

            return {
                "job_id": job_id,
                "status": "completed",
                "markdown_report": report,
                "cost_final": cost_final,
                "metadata": metadata,
                "sources": sources,
                "resource_uri": f"deepr://reports/{job_id}/final.md",
            }

        except Exception as e:
            return _make_error("RESULT_FETCH_FAILED", str(e))

    # ------------------------------------------------------------------ #
    # Tool: deepr_agentic_research
    # ------------------------------------------------------------------ #
    async def deepr_agentic_research(
        self,
        goal: str,
        expert_name: Optional[str] = None,
        budget: float = 5.0,
        sources: Optional[List[str]] = None,
        files: Optional[List[str]] = None,
        model: str = "o4-mini-deep-research",
        provider: str = "openai",
    ) -> Dict:
        """Start an agentic research workflow."""
        try:
            workflow_id = str(uuid.uuid4())
            trace_id = uuid.uuid4().hex[:16]

            from deepr.experts.cost_safety import get_cost_safety_manager, CostSafetyManager

            cost_safety = get_cost_safety_manager()
            max_agentic_budget = min(budget, CostSafetyManager.ABSOLUTE_MAX_PER_OPERATION)

            if budget > max_agentic_budget:
                return _make_error(
                    "BUDGET_EXCEEDS_MAX",
                    f"Agentic budget ${budget:.2f} exceeds maximum ${max_agentic_budget:.2f}",
                    retry_hint=f"Use budget=${max_agentic_budget:.2f} or lower",
                )

            session_id = f"agentic_{workflow_id[:8]}"
            allowed, reason, _ = cost_safety.check_operation(
                session_id=session_id,
                operation_type="agentic_research",
                estimated_cost=max_agentic_budget,
                require_confirmation=False,
            )

            if not allowed:
                spending = cost_safety.get_spending_summary()
                return _make_error(
                    "BUDGET_EXCEEDED",
                    f"Agentic research blocked: {reason}",
                    retry_hint="Wait for daily limit reset",
                    fallback=f"Daily remaining: ${spending['daily']['remaining']}",
                )

            if expert_name:
                expert = self.store.load(expert_name)
                if not expert:
                    return _make_error(
                        "EXPERT_NOT_FOUND", f"Expert '{expert_name}' not found"
                    )
            else:
                return _make_error(
                    "EXPERT_REQUIRED",
                    "Agentic research requires an expert.",
                    fallback=(
                        "Use deepr_list_experts to see available experts, or create "
                        "one with the CLI: deepr expert make <name> <domain>"
                    ),
                )

            # Track in JobManager
            await self.resource_handler.jobs.create_job(
                job_id=workflow_id,
                goal=goal,
                model=model,
                estimated_cost=max_agentic_budget,
                estimated_time="varies",
            )
            await self.resource_handler.jobs.update_phase(
                workflow_id, JobPhase.EXECUTING
            )
            # Store trace_id in job metadata
            state = self.resource_handler.jobs.get_state(workflow_id)
            if state:
                state.metadata["trace_id"] = trace_id
            self.resource_handler.persist_job(workflow_id)

            session = ExpertChatSession(
                expert, budget=max_agentic_budget, agentic=True
            )

            agentic_prompt = (
                f"Research Goal: {goal}\n\n"
                f"I need you to conduct comprehensive research on this goal. "
                f"You have autonomous research capabilities with a budget of "
                f"${max_agentic_budget:.2f}.\n\n"
                f"Please:\n"
                f"1. Analyze what research is needed to fully address this goal\n"
                f"2. Break it down into research questions\n"
                f"3. Conduct research autonomously\n"
                f"4. Synthesize findings into a comprehensive report\n"
            )
            if sources:
                agentic_prompt += f"\nPreferred sources: {', '.join(sources)}\n"
            if files:
                agentic_prompt += f"\nContext files provided: {len(files)} files\n"

            response = await session.send_message(agentic_prompt)

            self.active_jobs[workflow_id] = {
                "provider_instance": None,
                "session": session,
                "submitted_at": datetime.now().isoformat(),
            }

            spending = cost_safety.get_spending_summary()
            resource_uris = self.resource_handler.get_resource_uri_for_job(workflow_id)

            logger.info("Agentic workflow %s started (trace=%s)", workflow_id, trace_id)

            return {
                "workflow_id": workflow_id,
                "trace_id": trace_id,
                "status": "in_progress",
                "expert_name": expert.name,
                "budget_allocated": max_agentic_budget,
                "daily_spent": spending["daily"]["spent"],
                "daily_remaining": spending["daily"]["remaining"],
                "initial_response": (
                    response[:500] + "..." if len(response) > 500 else response
                ),
                "resource_uris": resource_uris,
                "message": (
                    f"Agentic workflow started. Use deepr_check_status with "
                    f"workflow_id '{workflow_id}' to monitor progress."
                ),
            }

        except Exception as e:
            logger.exception("deepr_agentic_research failed")
            return _make_error("INTERNAL_ERROR", str(e))

    # ------------------------------------------------------------------ #
    # Task Durability Methods
    # ------------------------------------------------------------------ #
    async def deepr_get_task_progress(self, task_id: str) -> Dict:
        """Get progress for a durable task."""
        task = await self.durability_manager.get_task(task_id)
        if not task:
            return _make_error("TASK_NOT_FOUND", f"Task '{task_id}' not found")
        return task.to_dict()

    async def deepr_list_recoverable_tasks(self, job_id: str) -> Dict:
        """List recoverable tasks for a job."""
        tasks = await self.durability_manager.get_recoverable_tasks(job_id)
        return {
            "job_id": job_id,
            "recoverable_tasks": [t.to_dict() for t in tasks],
            "count": len(tasks),
        }

    async def deepr_resume_task(self, task_id: str) -> Dict:
        """Resume a paused task."""
        task = await self.durability_manager.resume_task(task_id)
        if not task:
            return _make_error("TASK_NOT_FOUND", f"Task '{task_id}' not found or not resumable")
        return {
            "task_id": task_id,
            "status": task.status.value,
            "checkpoint": task.checkpoint,
            "message": f"Task '{task_id}' resumed from checkpoint",
        }

    async def deepr_pause_task(self, task_id: str) -> Dict:
        """Pause a running task."""
        task = await self.durability_manager.pause_task(task_id)
        if not task:
            return _make_error("TASK_NOT_FOUND", f"Task '{task_id}' not found")
        return {
            "task_id": task_id,
            "status": task.status.value,
            "checkpoint": task.checkpoint,
            "message": f"Task '{task_id}' paused",
        }

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def validate_outbound_url(self, url: str) -> Optional[dict]:
        """Validate a URL against SSRF rules. Returns error dict or None if valid."""
        try:
            self.ssrf_protector.validate_url(url)
            return None
        except ValueError as e:
            return _make_error("SSRF_BLOCKED", str(e))

    def _get_api_key(self, provider: str) -> Optional[str]:
        """Resolve API key for a provider from config or environment."""
        key_map = {
            "openai": ("api_key", "OPENAI_API_KEY"),
            "azure": ("azure_api_key", "AZURE_OPENAI_API_KEY"),
            "gemini": ("gemini_api_key", "GEMINI_API_KEY"),
            "grok": ("xai_api_key", "XAI_API_KEY"),
        }
        config_key, env_key = key_map.get(provider, (None, None))
        if config_key:
            return self.config.get(config_key) or os.environ.get(env_key, "")
        return None


# ------------------------------------------------------------------ #
# Tool Registration
# ------------------------------------------------------------------ #

def _register_new_tools(registry: ToolRegistry) -> None:
    """Register the three new tools (status, cancel, tool_search) in the registry."""
    registry.register(ToolSchema(
        name="deepr_status",
        description=(
            "Health check for the Deepr MCP server. Returns version, uptime, "
            "active jobs count, daily/monthly cost summary, and available capabilities. "
            "Use this to verify the server is running and check spending before starting research."
        ),
        input_schema={
            "type": "object",
            "properties": {},
        },
        category="system",
        cost_tier="free",
    ))

    registry.register(ToolSchema(
        name="deepr_cancel_job",
        description=(
            "Cancel a running research job. Use when the user wants to stop an "
            "in-progress research task. Cannot cancel already completed or failed jobs."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "Job ID from deepr_research or deepr_agentic_research",
                },
            },
            "required": ["job_id"],
        },
        category="research",
        cost_tier="free",
    ))

    # Note: deepr_tool_search is already defined in GatewayTool.SCHEMA
    # but we register it in the registry too so it appears in full tool lists.
    registry.register(GatewayTool.SCHEMA)


# ------------------------------------------------------------------ #
# MCP Protocol Handlers (JSON-RPC methods)
# ------------------------------------------------------------------ #

def _build_tools_list(server: DeeprMCPServer, use_gateway: bool = True) -> list:
    """Build the tools list for tools/list response.

    If use_gateway is True, only return the gateway tool (dynamic discovery).
    If False, return all tools (for clients that don't support dynamic discovery).
    """
    if use_gateway:
        return [GatewayTool.get_gateway_schema()]
    return [t.to_mcp_format() for t in server.registry.all_tools()]


async def _handle_initialize(server: DeeprMCPServer, params: dict) -> dict:
    """Handle MCP initialize handshake."""
    return {
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "tools": {"listChanged": False},
            "resources": {"subscribe": True, "listChanged": False},
            "prompts": {"listChanged": False},
            "logging": {},
        },
        "serverInfo": {
            "name": "deepr-research",
            "version": SERVER_VERSION,
        },
    }


async def _handle_tools_list(server: DeeprMCPServer, params: dict) -> dict:
    """Handle tools/list."""
    # If client sent _fullList hint, return all tools
    full_list = params.get("_fullList", False)
    tools = _build_tools_list(server, use_gateway=not full_list)
    return {"tools": tools}


async def _handle_tools_call(server: DeeprMCPServer, params: dict) -> dict:
    """Handle tools/call - dispatch to appropriate tool method.

    Integrates security checks:
    1. Tool allowlist - checks if tool is allowed in current research mode
    2. Instruction signing - signs the instruction for audit trail
    3. Output verification - records output hash for integrity verification
    """
    name = params.get("name", "")
    arguments = params.get("arguments", {})
    job_id = arguments.get("job_id") or arguments.get("workflow_id")

    # Security: Check tool allowlist
    validation = server.tool_allowlist.validate_tool_call(name)
    if not validation["allowed"]:
        logger.warning("Tool '%s' blocked by allowlist: %s", name, validation["reason"])
        return {
            "content": [{"type": "text", "text": json.dumps(
                _make_error(
                    "TOOL_BLOCKED",
                    validation["reason"],
                    fallback=f"Current research mode: {validation['mode']}",
                )
            )}],
            "isError": True,
        }

    # Security: Check if confirmation is required (for future elicitation integration)
    if validation["requires_confirmation"]:
        logger.info("Tool '%s' requires confirmation in mode '%s'", name, validation["mode"])
        # Note: Full elicitation integration would prompt user here
        # For now, we log and proceed (confirmation handling is in elicitation module)

    # Security: Sign the instruction for audit trail
    instruction = {"tool": name, "arguments": arguments}
    signed = server.instruction_signer.sign(instruction)
    logger.debug("Signed instruction for tool '%s': nonce=%s", name, signed.nonce)

    tool_dispatch = {
        "deepr_status": lambda args: server.deepr_status(),
        "deepr_tool_search": lambda args: server.deepr_tool_search(
            query=args.get("query", ""),
            limit=args.get("limit", 3),
        ),
        "deepr_cancel_job": lambda args: server.deepr_cancel_job(
            job_id=args.get("job_id", ""),
        ),
        "deepr_research": lambda args: server.deepr_research(**args),
        "deepr_check_status": lambda args: server.deepr_check_status(
            job_id=args.get("job_id", ""),
        ),
        "deepr_get_result": lambda args: server.deepr_get_result(
            job_id=args.get("job_id", ""),
        ),
        "deepr_agentic_research": lambda args: server.deepr_agentic_research(**args),
        "deepr_list_experts": lambda args: server.list_experts(),
        "deepr_query_expert": lambda args: server.query_expert(**args),
        "deepr_get_expert_info": lambda args: server.get_expert_info(
            expert_name=args.get("expert_name", ""),
        ),
        # Task durability endpoints
        "deepr_get_task_progress": lambda args: server.deepr_get_task_progress(
            task_id=args.get("task_id", ""),
        ),
        "deepr_list_recoverable_tasks": lambda args: server.deepr_list_recoverable_tasks(
            job_id=args.get("job_id", ""),
        ),
        "deepr_resume_task": lambda args: server.deepr_resume_task(
            task_id=args.get("task_id", ""),
        ),
        "deepr_pause_task": lambda args: server.deepr_pause_task(
            task_id=args.get("task_id", ""),
        ),
    }

    handler = tool_dispatch.get(name)
    if not handler:
        return {
            "content": [{"type": "text", "text": json.dumps(
                _make_error("TOOL_NOT_FOUND", f"Unknown tool: {name}")
            )}],
            "isError": True,
        }

    try:
        result = await handler(arguments)

        # Security: Record output for verification
        verified_output = server.output_verifier.record_output(
            tool_name=name,
            content=result,
            job_id=job_id,
            metadata={
                "instruction_nonce": signed.nonce,
                "research_mode": server.tool_allowlist.mode.value,
            },
        )
        logger.debug(
            "Recorded output for tool '%s': id=%s, hash=%s",
            name, verified_output.id, verified_output.content_hash[:16]
        )

        text = json.dumps(result, default=str)
        is_error = isinstance(result, dict) and "error_code" in result

        return {
            "content": [{"type": "text", "text": text}],
            "isError": is_error,
            # Include verification metadata for audit trail
            "_verification": {
                "output_id": verified_output.id,
                "content_hash": verified_output.content_hash,
                "instruction_nonce": signed.nonce,
            },
        }
    except Exception as e:
        logger.exception(f"Tool {name} failed")
        return {
            "content": [{"type": "text", "text": json.dumps(
                _make_error("TOOL_EXECUTION_FAILED", str(e))
            )}],
            "isError": True,
        }


async def _handle_resources_list(server: DeeprMCPServer, params: dict) -> dict:
    """Handle resources/list."""
    uris = server.resource_handler.list_resources()
    resources = [
        {"uri": uri, "name": uri.split("/")[-1], "mimeType": "application/json"}
        for uri in uris
    ]
    return {"resources": resources}


async def _handle_resources_read(server: DeeprMCPServer, params: dict) -> dict:
    """Handle resources/read."""
    uri = params.get("uri", "")
    response = server.resource_handler.read_resource(uri)

    if response.success:
        return {
            "contents": [{
                "uri": uri,
                "mimeType": "application/json",
                "text": json.dumps(response.data, default=str),
            }]
        }

    return {
        "contents": [{
            "uri": uri,
            "mimeType": "application/json",
            "text": json.dumps({"error": response.error}),
        }]
    }


async def _handle_resources_subscribe(server: DeeprMCPServer, params: dict) -> dict:
    """Handle resources/subscribe."""
    uri = params.get("uri", "")

    async def _notification_callback(data: dict):
        # In stdio mode, notifications are written directly to stdout
        # The transport layer handles this
        pass

    result = await server.resource_handler.handle_subscribe(uri, _notification_callback)
    return result


async def _handle_resources_unsubscribe(server: DeeprMCPServer, params: dict) -> dict:
    """Handle resources/unsubscribe."""
    sub_id = params.get("subscription_id", "")
    result = await server.resource_handler.handle_unsubscribe(sub_id)
    return result


async def _handle_prompts_list(server: DeeprMCPServer, params: dict) -> dict:
    """Handle prompts/list - return available prompt templates."""
    return {"prompts": list_prompts()}


async def _handle_prompts_get(server: DeeprMCPServer, params: dict) -> dict:
    """Handle prompts/get - render a prompt template with arguments."""
    name = params.get("name", "")
    arguments = params.get("arguments", {})
    return get_prompt(name, arguments)


# ------------------------------------------------------------------ #
# Backward-compatible method names (old raw dispatch)
# ------------------------------------------------------------------ #

_LEGACY_METHOD_MAP = {
    "list_experts": "deepr_list_experts",
    "get_expert_info": "deepr_get_expert_info",
    "query_expert": "deepr_query_expert",
}


# ------------------------------------------------------------------ #
# Server Entry Point
# ------------------------------------------------------------------ #

async def run_stdio_server():
    """Run MCP server using StdioServer for proper JSON-RPC dispatch."""
    global _server_start_time
    _server_start_time = time.time()

    deepr_server = DeeprMCPServer()
    stdio = StdioServer()

    # Register MCP protocol methods
    async def handle_initialize(params: dict) -> dict:
        return await _handle_initialize(deepr_server, params)

    async def handle_tools_list(params: dict) -> dict:
        return await _handle_tools_list(deepr_server, params)

    async def handle_tools_call(params: dict) -> dict:
        return await _handle_tools_call(deepr_server, params)

    async def handle_resources_list(params: dict) -> dict:
        return await _handle_resources_list(deepr_server, params)

    async def handle_resources_read(params: dict) -> dict:
        return await _handle_resources_read(deepr_server, params)

    async def handle_resources_subscribe(params: dict) -> dict:
        return await _handle_resources_subscribe(deepr_server, params)

    async def handle_resources_unsubscribe(params: dict) -> dict:
        return await _handle_resources_unsubscribe(deepr_server, params)

    async def handle_prompts_list(params: dict) -> dict:
        return await _handle_prompts_list(deepr_server, params)

    async def handle_prompts_get(params: dict) -> dict:
        return await _handle_prompts_get(deepr_server, params)

    # Register standard MCP methods
    stdio.register_method("initialize", handle_initialize)
    stdio.register_method("tools/list", handle_tools_list)
    stdio.register_method("tools/call", handle_tools_call)
    stdio.register_method("resources/list", handle_resources_list)
    stdio.register_method("resources/read", handle_resources_read)
    stdio.register_method("resources/subscribe", handle_resources_subscribe)
    stdio.register_method("resources/unsubscribe", handle_resources_unsubscribe)
    stdio.register_method("prompts/list", handle_prompts_list)
    stdio.register_method("prompts/get", handle_prompts_get)

    # Register legacy method names for backward compatibility
    for legacy_name, new_name in _LEGACY_METHOD_MAP.items():
        async def _make_legacy(params, tool_name=new_name):
            return await _handle_tools_call(
                deepr_server, {"name": tool_name, "arguments": params}
            )
        stdio.register_method(legacy_name, _make_legacy)

    logger.info("Deepr MCP Server v%s started (stdio transport)", SERVER_VERSION)
    logger.info("Registered %d tools, gateway discovery enabled", deepr_server.registry.count())

    await stdio.run()


def main():
    """Entry point for MCP server."""
    try:
        asyncio.run(run_stdio_server())
    except KeyboardInterrupt:
        logger.info("Shutting down MCP server...")


if __name__ == "__main__":
    main()
