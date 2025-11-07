"""MCP Server for Deepr Experts.

Exposes expert chat functionality via Model Context Protocol
for use by other AI agents (Claude Desktop, Cursor, etc.).
"""
import os
import sys
import asyncio
import json
from typing import Any, Dict, List
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from deepr.experts.profile import ExpertProfile, ExpertStore
from deepr.experts.chat import ExpertChatSession


class DeeprMCPServer:
    """MCP server for Deepr experts."""

    def __init__(self):
        self.store = ExpertStore()
        self.sessions: Dict[str, ExpertChatSession] = {}

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
