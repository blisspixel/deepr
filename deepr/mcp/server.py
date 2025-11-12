"""MCP Server for Deepr.

Exposes Deepr research and expert functionality via Model Context Protocol
for use by other AI agents (Claude Desktop, Cursor, etc.).

Tools exposed:
- deepr_research: Submit deep research jobs
- deepr_check_status: Check research job status
- deepr_get_result: Get completed research results
- deepr_agentic_research: Start autonomous multi-step research workflows
- deepr_list_experts: List available domain experts
- deepr_query_expert: Query a domain expert
- deepr_get_expert_info: Get detailed expert information
"""
import os
import sys
import asyncio
import json
from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from deepr.experts.profile import ExpertProfile, ExpertStore
from deepr.experts.chat import ExpertChatSession
from deepr.providers import create_provider
from deepr.storage import create_storage
from deepr.core.research import ResearchOrchestrator
from deepr.core.documents import DocumentManager
from deepr.core.reports import ReportGenerator
from deepr.config import load_config


class DeeprMCPServer:
    """MCP server for Deepr research and experts."""

    def __init__(self):
        """Initialize MCP server with research and expert capabilities."""
        # Expert-related components
        self.store = ExpertStore()
        self.sessions: Dict[str, ExpertChatSession] = {}

        # Research-related components
        self.config = load_config()
        self.active_jobs: Dict[str, Dict] = {}  # Track submitted jobs

    async def list_experts(self) -> List[Dict]:
        """List all available experts.

        Returns:
            List of expert summaries
        """
        try:
            experts = self.store.list_all()
            return [
                {
                    "name": expert["name"],
                    "domain": expert["domain"],
                    "description": expert["description"],
                    "documents": expert["stats"]["documents"],
                    "conversations": expert["stats"]["conversations"]
                }
                for expert in experts
            ]
        except Exception as e:
            return [{"error": str(e)}]

    async def get_expert_info(self, expert_name: str) -> Dict:
        """Get detailed information about a specific expert.

        Args:
            expert_name: Name of the expert

        Returns:
            Expert information dictionary
        """
        try:
            expert = self.store.load(expert_name)
            if not expert:
                return {"error": f"Expert '{expert_name}' not found"}

            return {
                "name": expert.name,
                "domain": expert.domain,
                "description": expert.description,
                "vector_store_id": expert.vector_store_id,
                "stats": {
                    "documents": expert.total_documents,
                    "conversations": expert.stats.get("conversations", 0),
                    "research_jobs": len(expert.research_jobs),
                    "total_cost": expert.stats.get("total_cost", 0.0)
                },
                "created_at": expert.created_at.isoformat() if expert.created_at else None,
                "last_knowledge_refresh": expert.last_knowledge_refresh.isoformat() if expert.last_knowledge_refresh else None
            }
        except Exception as e:
            return {"error": str(e)}

    async def query_expert(
        self,
        expert_name: str,
        question: str,
        budget: float = 0.0,
        agentic: bool = False
    ) -> Dict:
        """Query an expert with a question.

        Args:
            expert_name: Name of the expert
            question: Question to ask
            budget: Optional budget for research (if agentic)
            agentic: Enable agentic mode (expert can trigger research)

        Returns:
            Expert response with sources and cost
        """
        try:
            # Load expert
            expert = self.store.load(expert_name)
            if not expert:
                return {"error": f"Expert '{expert_name}' not found"}

            # Create or reuse session
            session_key = f"{expert_name}_{id(question)}"
            if session_key not in self.sessions:
                self.sessions[session_key] = ExpertChatSession(
                    expert,
                    budget=budget if agentic else None,
                    agentic=agentic
                )

            session = self.sessions[session_key]

            # Send message
            response_text = await session.send_message(question)

            # Get session summary for cost tracking
            summary = session.get_session_summary()

            # Clean up session
            del self.sessions[session_key]

            return {
                "answer": response_text,
                "expert": expert_name,
                "cost": summary["cost_accumulated"],
                "budget_remaining": summary.get("budget_remaining"),
                "research_triggered": summary["research_jobs_triggered"]
            }

        except Exception as e:
            return {"error": str(e)}

    async def deepr_research(
        self,
        prompt: str,
        model: str = "o4-mini-deep-research",
        provider: str = "openai",
        enable_web_search: bool = True,
        enable_code_interpreter: bool = True,
        budget: Optional[float] = None,
        files: Optional[List[str]] = None
    ) -> Dict:
        """Submit a deep research job.

        Args:
            prompt: Research question or prompt
            model: Model to use (default: o4-mini-deep-research)
            provider: Provider to use (openai, azure, gemini, grok)
            enable_web_search: Enable web search tool
            enable_code_interpreter: Enable code interpreter tool
            budget: Optional budget limit in dollars
            files: Optional list of file paths to include

        Returns:
            Job information with job_id, estimated_time, cost_estimate
        """
        try:
            # Create provider instance
            if provider == "openai":
                api_key = self.config.get("api_key")
            elif provider == "azure":
                api_key = self.config.get("azure_api_key")
            elif provider == "gemini":
                api_key = self.config.get("gemini_api_key")
            elif provider == "grok":
                api_key = self.config.get("xai_api_key")
            else:
                return {"error": f"Unknown provider: {provider}"}

            if not api_key:
                return {"error": f"No API key configured for provider: {provider}"}

            provider_instance = create_provider(provider, api_key)
            storage_instance = create_storage("local", base_path="data/reports")
            doc_manager = DocumentManager()
            report_generator = ReportGenerator()

            orchestrator = ResearchOrchestrator(
                provider_instance,
                storage_instance,
                doc_manager,
                report_generator
            )

            # Submit research
            job_id = await orchestrator.submit_research(
                prompt=prompt,
                model=model,
                documents=files if files else None,
                enable_web_search=enable_web_search,
                enable_code_interpreter=enable_code_interpreter,
                cost_sensitive=budget is not None and budget < 0.20
            )

            # Estimate cost based on model
            if "o4-mini" in model:
                cost_estimate = 0.10
                estimated_time = "5-10 minutes"
            elif "o3" in model:
                cost_estimate = 0.50
                estimated_time = "10-20 minutes"
            else:
                cost_estimate = 0.15
                estimated_time = "5-15 minutes"

            # Track job
            self.active_jobs[job_id] = {
                "job_id": job_id,
                "prompt": prompt,
                "model": model,
                "provider": provider,
                "submitted_at": datetime.now().isoformat(),
                "status": "submitted",
                "provider_instance": provider_instance
            }

            return {
                "job_id": job_id,
                "status": "submitted",
                "estimated_time": estimated_time,
                "cost_estimate": cost_estimate,
                "message": f"Research job submitted successfully. Use deepr_check_status with job_id '{job_id}' to check progress."
            }

        except Exception as e:
            return {"error": str(e)}

    async def deepr_check_status(self, job_id: str) -> Dict:
        """Check the status of a research job.

        Args:
            job_id: Job ID returned from deepr_research

        Returns:
            Job status information including progress and cost
        """
        try:
            if job_id not in self.active_jobs:
                return {"error": f"Job '{job_id}' not found"}

            job_info = self.active_jobs[job_id]
            provider_instance = job_info["provider_instance"]

            # Check status with provider
            try:
                status = await provider_instance.get_job_status(job_id)

                job_info["status"] = status["status"]
                job_info["progress"] = status.get("progress", "unknown")
                job_info["elapsed_time"] = status.get("elapsed_time")
                job_info["cost_so_far"] = status.get("cost", 0.0)

                return {
                    "job_id": job_id,
                    "status": status["status"],
                    "progress": status.get("progress"),
                    "elapsed_time": status.get("elapsed_time"),
                    "cost_so_far": status.get("cost", 0.0),
                    "submitted_at": job_info["submitted_at"]
                }

            except Exception as provider_error:
                # If provider doesn't have the job yet, it might still be queued
                return {
                    "job_id": job_id,
                    "status": "submitted",
                    "message": "Job submitted, waiting for provider to begin processing",
                    "submitted_at": job_info["submitted_at"]
                }

        except Exception as e:
            return {"error": str(e)}

    async def deepr_get_result(self, job_id: str) -> Dict:
        """Get the results of a completed research job.

        Args:
            job_id: Job ID returned from deepr_research

        Returns:
            Research results including markdown report and metadata
        """
        try:
            if job_id not in self.active_jobs:
                return {"error": f"Job '{job_id}' not found"}

            job_info = self.active_jobs[job_id]
            provider_instance = job_info["provider_instance"]

            # Check if completed
            status = await provider_instance.get_job_status(job_id)

            if status["status"] != "completed":
                return {
                    "job_id": job_id,
                    "status": status["status"],
                    "message": f"Job not yet complete. Current status: {status['status']}"
                }

            # Get result
            result = await provider_instance.get_job_result(job_id)

            # Clean up
            del self.active_jobs[job_id]

            return {
                "job_id": job_id,
                "status": "completed",
                "markdown_report": result.get("report", ""),
                "cost_final": result.get("cost", 0.0),
                "metadata": result.get("metadata", {}),
                "sources": result.get("sources", [])
            }

        except Exception as e:
            return {"error": str(e)}

    async def deepr_agentic_research(
        self,
        goal: str,
        expert_name: Optional[str] = None,
        budget: float = 5.0,
        sources: Optional[List[str]] = None,
        files: Optional[List[str]] = None,
        model: str = "o4-mini-deep-research",
        provider: str = "openai"
    ) -> Dict:
        """Start an agentic research workflow that can trigger multiple research jobs.

        This is different from deepr_research - it uses an expert agent that can
        autonomously decide when to trigger additional research based on findings.

        Args:
            goal: High-level research goal
            expert_name: Expert to use for agentic reasoning (optional, creates temp expert if not provided)
            budget: Total budget for the agentic workflow
            sources: Preferred sources to prioritize
            files: Files to include as context
            model: Model to use for research jobs
            provider: Provider to use

        Returns:
            Workflow information with workflow_id, expert_name, plan, estimated_cost
        """
        try:
            import uuid
            workflow_id = str(uuid.uuid4())

            # If expert_name provided, use existing expert
            if expert_name:
                expert = self.store.load(expert_name)
                if not expert:
                    return {"error": f"Expert '{expert_name}' not found"}
            else:
                # For now, return a plan without actually creating a temporary expert
                # This can be enhanced later with temporary expert creation
                return {
                    "workflow_id": workflow_id,
                    "status": "planned",
                    "message": "Agentic research requires an expert. Please provide expert_name or create one first.",
                    "suggestion": "Use deepr_list_experts to see available experts, or create one with the CLI: deepr expert make <name> <domain>"
                }

            # Create agentic session
            session = ExpertChatSession(
                expert,
                budget=budget,
                agentic=True  # Enable agentic mode
            )

            # Enhanced prompt for agentic behavior
            agentic_prompt = f"""Research Goal: {goal}

I need you to conduct comprehensive research on this goal. You have autonomous research capabilities with a budget of ${budget:.2f}.

Please:
1. Analyze what research is needed to fully address this goal
2. Break it down into research questions
3. Conduct research autonomously (you can trigger research jobs as needed)
4. Synthesize findings into a comprehensive report

"""
            if sources:
                agentic_prompt += f"\nPreferred sources: {', '.join(sources)}\n"

            if files:
                agentic_prompt += f"\nContext files provided: {len(files)} files\n"

            # Start the agentic workflow
            response = await session.send_message(agentic_prompt)

            # Track the workflow
            workflow_info = {
                "workflow_id": workflow_id,
                "goal": goal,
                "expert_name": expert.name,
                "budget": budget,
                "budget_remaining": budget,
                "status": "in_progress",
                "started_at": datetime.now().isoformat(),
                "session": session
            }

            self.active_jobs[workflow_id] = workflow_info

            return {
                "workflow_id": workflow_id,
                "status": "in_progress",
                "expert_name": expert.name,
                "budget_allocated": budget,
                "initial_response": response[:500] + "..." if len(response) > 500 else response,
                "message": f"Agentic workflow started. The expert will autonomously conduct research and report back. Use deepr_check_status with workflow_id '{workflow_id}' to monitor progress."
            }

        except Exception as e:
            return {"error": str(e)}


# Simplified stdio-based MCP server (no dependencies required)
async def run_stdio_server():
    """Run MCP server using stdio for communication."""
    server = DeeprMCPServer()

    # Read from stdin, write to stdout
    print("Deepr MCP Server started", file=sys.stderr)
    print("Listening for requests on stdin...", file=sys.stderr)

    while True:
        try:
            # Read request from stdin
            line = sys.stdin.readline()
            if not line:
                break

            request = json.loads(line.strip())
            method = request.get("method")
            params = request.get("params", {})

            # Handle request
            result = None
            if method == "list_experts":
                result = await server.list_experts()
            elif method == "get_expert_info":
                result = await server.get_expert_info(**params)
            elif method == "query_expert":
                result = await server.query_expert(**params)
            elif method == "deepr_research":
                result = await server.deepr_research(**params)
            elif method == "deepr_check_status":
                result = await server.deepr_check_status(**params)
            elif method == "deepr_get_result":
                result = await server.deepr_get_result(**params)
            elif method == "deepr_agentic_research":
                result = await server.deepr_agentic_research(**params)
            else:
                result = {"error": f"Unknown method: {method}"}

            # Write response to stdout
            response = {"id": request.get("id"), "result": result}
            print(json.dumps(response), flush=True)

        except KeyboardInterrupt:
            break
        except Exception as e:
            error_response = {
                "id": request.get("id") if "request" in locals() else None,
                "error": str(e)
            }
            print(json.dumps(error_response), flush=True)


def main():
    """Entry point for MCP server."""
    try:
        asyncio.run(run_stdio_server())
    except KeyboardInterrupt:
        print("\nShutting down MCP server...", file=sys.stderr)


if __name__ == "__main__":
    main()
