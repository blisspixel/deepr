"""
MCP Resource Handler.

Integrates subscriptions, job management, expert resources,
and report/log artifacts into a unified resource handling
interface for the MCP server.

Supported resource URI schemes:
    deepr://campaigns/{id}/status
    deepr://campaigns/{id}/plan
    deepr://campaigns/{id}/beliefs
    deepr://reports/{id}/final.md
    deepr://reports/{id}/summary.json
    deepr://logs/{id}/search_trace.json
    deepr://logs/{id}/decisions.md
    deepr://experts/{id}/profile
    deepr://experts/{id}/beliefs
    deepr://experts/{id}/gaps
"""

import json
import logging
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass

from .subscriptions import SubscriptionManager, parse_resource_uri
from .job_manager import JobManager, JobPhase
from .expert_resources import ExpertResourceManager
from .persistence import JobPersistence

logger = logging.getLogger("deepr.mcp.resources")


@dataclass
class ResourceResponse:
    """Response from a resource read operation."""
    
    uri: str
    data: Optional[dict]
    error: Optional[str] = None
    
    @property
    def success(self) -> bool:
        return self.error is None and self.data is not None


class MCPResourceHandler:
    """
    Unified handler for MCP resources.

    Provides a single interface for:
    - Reading campaign resources (status, plan, beliefs)
    - Reading report artifacts (final.md, summary.json)
    - Reading log artifacts (search_trace.json, decisions.md)
    - Reading expert resources (profile, beliefs, gaps)
    - Managing subscriptions
    - Emitting updates
    """

    # Base path for reports on disk (relative to project root)
    REPORTS_BASE = Path("data/reports")

    def __init__(self, reports_base: Optional[Path] = None, db_path: Optional[Path] = None):
        self._subscriptions = SubscriptionManager()
        self._jobs = JobManager(self._subscriptions)
        self._experts = ExpertResourceManager()
        self._reports_base = reports_base or self.REPORTS_BASE

        # SQLite persistence: survives server restarts
        self._persistence: Optional[JobPersistence] = None
        if db_path is not False:  # False disables persistence (for tests)
            try:
                self._persistence = JobPersistence(db_path=db_path)
                self._restore_jobs_from_db()
            except Exception as e:
                logger.warning("Job persistence unavailable: %s", e)
                self._persistence = None
    
    def _restore_jobs_from_db(self) -> None:
        """Restore job state from SQLite on startup and mark incomplete jobs as failed."""
        if not self._persistence:
            return

        failed_count = self._persistence.mark_incomplete_as_failed()
        if failed_count:
            logger.info("Marked %d incomplete jobs as failed after restart", failed_count)

        for state in self._persistence.list_jobs():
            self._jobs._jobs[state.job_id] = state
            result = self._persistence.load_job(state.job_id)
            if result:
                _, plan, beliefs = result
                if plan:
                    self._jobs._plans[state.job_id] = plan
                if beliefs:
                    self._jobs._beliefs[state.job_id] = beliefs

        restored = len(self._jobs._jobs)
        if restored:
            logger.info("Restored %d jobs from persistence", restored)

    def persist_job(self, job_id: str) -> None:
        """Persist current job state to SQLite.

        Call this after create_job, update_phase, add_belief, update_plan.
        """
        if not self._persistence:
            return

        state = self._jobs.get_state(job_id)
        if not state:
            return

        plan = self._jobs.get_plan(job_id)
        beliefs = self._jobs.get_beliefs(job_id)

        try:
            self._persistence.save_job(state, plan=plan, beliefs=beliefs)
        except Exception as e:
            logger.warning("Failed to persist job %s: %s", job_id, e)

    @property
    def persistence(self) -> Optional[JobPersistence]:
        """Access persistence layer (may be None if disabled)."""
        return self._persistence

    @property
    def subscriptions(self) -> SubscriptionManager:
        """Access subscription manager."""
        return self._subscriptions
    
    @property
    def jobs(self) -> JobManager:
        """Access job manager."""
        return self._jobs
    
    @property
    def experts(self) -> ExpertResourceManager:
        """Access expert resource manager."""
        return self._experts
    
    def read_resource(self, uri: str) -> ResourceResponse:
        """
        Read a resource by URI.
        
        Args:
            uri: Resource URI (deepr://campaigns/... or deepr://experts/...)
        
        Returns:
            ResourceResponse with data or error
        """
        parsed = parse_resource_uri(uri)
        
        if not parsed:
            return ResourceResponse(
                uri=uri,
                data=None,
                error=f"Invalid resource URI: {uri}"
            )
        
        if parsed.resource_type == "campaigns":
            return self._read_campaign_resource(parsed.resource_id, parsed.subresource, uri)
        elif parsed.resource_type == "experts":
            return self._read_expert_resource(parsed.resource_id, parsed.subresource, uri)
        elif parsed.resource_type == "reports":
            return self._read_report_resource(parsed.resource_id, parsed.subresource, uri)
        elif parsed.resource_type == "logs":
            return self._read_log_resource(parsed.resource_id, parsed.subresource, uri)

        return ResourceResponse(
            uri=uri,
            data=None,
            error=f"Unknown resource type: {parsed.resource_type}"
        )
    
    def _read_campaign_resource(
        self,
        job_id: str,
        subresource: str,
        uri: str
    ) -> ResourceResponse:
        """Read a campaign resource."""
        if subresource == "status":
            state = self._jobs.get_state(job_id)
            if state:
                return ResourceResponse(uri=uri, data=state.to_dict())
            return ResourceResponse(uri=uri, data=None, error=f"Job not found: {job_id}")
        
        elif subresource == "plan":
            plan = self._jobs.get_plan(job_id)
            if plan:
                return ResourceResponse(uri=uri, data=plan.to_dict())
            return ResourceResponse(uri=uri, data=None, error=f"Plan not found: {job_id}")
        
        elif subresource == "beliefs":
            beliefs = self._jobs.get_beliefs(job_id)
            if beliefs:
                return ResourceResponse(uri=uri, data=beliefs.to_dict())
            return ResourceResponse(uri=uri, data=None, error=f"Beliefs not found: {job_id}")
        
        return ResourceResponse(
            uri=uri,
            data=None,
            error=f"Unknown campaign subresource: {subresource}"
        )
    
    def _read_report_resource(
        self,
        job_id: str,
        subresource: str,
        uri: str,
    ) -> ResourceResponse:
        """Read a report artifact from disk.

        Supported subresources:
            final.md - Full research report (markdown)
            summary.json - Report metadata (cost, model, sources)
        """
        job_dir = self._reports_base / job_id

        if subresource == "final.md":
            # Try common report filenames
            for name in ("final_report.md", "report.md", "output.md"):
                path = job_dir / name
                if path.exists():
                    try:
                        content = path.read_text(encoding="utf-8")
                        return ResourceResponse(
                            uri=uri,
                            data={"content": content, "format": "markdown"},
                        )
                    except Exception as e:
                        return ResourceResponse(uri=uri, data=None, error=str(e))
            return ResourceResponse(
                uri=uri, data=None, error=f"Report not found for job: {job_id}"
            )

        elif subresource == "summary.json":
            for name in ("metadata.json", "summary.json"):
                path = job_dir / name
                if path.exists():
                    try:
                        data = json.loads(path.read_text(encoding="utf-8"))
                        return ResourceResponse(uri=uri, data=data)
                    except Exception as e:
                        return ResourceResponse(uri=uri, data=None, error=str(e))
            # Fallback: build summary from job state
            state = self._jobs.get_state(job_id)
            if state:
                return ResourceResponse(uri=uri, data=state.to_dict())
            return ResourceResponse(
                uri=uri, data=None, error=f"Summary not found for job: {job_id}"
            )

        return ResourceResponse(
            uri=uri, data=None, error=f"Unknown report subresource: {subresource}"
        )

    def _read_log_resource(
        self,
        job_id: str,
        subresource: str,
        uri: str,
    ) -> ResourceResponse:
        """Read a log artifact from disk.

        Supported subresources:
            search_trace.json - Search queries and results for provenance
            decisions.md - Human-readable decision log
        """
        job_dir = self._reports_base / job_id

        file_map = {
            "search_trace.json": ("search_trace.json", "trace.json"),
            "decisions.md": ("decisions.md",),
        }
        candidates = file_map.get(subresource)
        if not candidates:
            return ResourceResponse(
                uri=uri, data=None, error=f"Unknown log subresource: {subresource}"
            )

        for name in candidates:
            path = job_dir / name
            if path.exists():
                try:
                    raw = path.read_text(encoding="utf-8")
                    if name.endswith(".json"):
                        return ResourceResponse(uri=uri, data=json.loads(raw))
                    return ResourceResponse(
                        uri=uri, data={"content": raw, "format": "markdown"}
                    )
                except Exception as e:
                    return ResourceResponse(uri=uri, data=None, error=str(e))

        return ResourceResponse(
            uri=uri, data=None, error=f"Log '{subresource}' not found for job: {job_id}"
        )

    def _read_expert_resource(
        self,
        expert_id: str,
        subresource: str,
        uri: str
    ) -> ResourceResponse:
        """Read an expert resource."""
        data = self._experts.resolve_uri(uri)
        
        if data:
            return ResourceResponse(uri=uri, data=data)
        
        return ResourceResponse(
            uri=uri,
            data=None,
            error=f"Expert resource not found: {uri}"
        )
    
    def list_resources(self, resource_type: Optional[str] = None) -> list[str]:
        """
        List available resource URIs.

        Args:
            resource_type: Optional filter ("campaigns", "experts", "reports", "logs")

        Returns:
            List of resource URIs
        """
        uris = []

        if resource_type is None or resource_type == "campaigns":
            for job in self._jobs.list_jobs():
                uris.extend([
                    f"deepr://campaigns/{job.job_id}/status",
                    f"deepr://campaigns/{job.job_id}/plan",
                    f"deepr://campaigns/{job.job_id}/beliefs",
                ])

        if resource_type is None or resource_type == "reports":
            # Scan reports directory for job IDs with report files
            if self._reports_base.exists():
                for job_dir in self._reports_base.iterdir():
                    if job_dir.is_dir():
                        jid = job_dir.name
                        for name in ("final_report.md", "report.md", "output.md"):
                            if (job_dir / name).exists():
                                uris.append(f"deepr://reports/{jid}/final.md")
                                break
                        for name in ("metadata.json", "summary.json"):
                            if (job_dir / name).exists():
                                uris.append(f"deepr://reports/{jid}/summary.json")
                                break

        if resource_type is None or resource_type == "logs":
            if self._reports_base.exists():
                for job_dir in self._reports_base.iterdir():
                    if job_dir.is_dir():
                        jid = job_dir.name
                        for name in ("search_trace.json", "trace.json"):
                            if (job_dir / name).exists():
                                uris.append(f"deepr://logs/{jid}/search_trace.json")
                                break
                        if (job_dir / "decisions.md").exists():
                            uris.append(f"deepr://logs/{jid}/decisions.md")

        if resource_type is None or resource_type == "experts":
            for expert in self._experts.list_experts():
                uris.extend([
                    f"deepr://experts/{expert.expert_id}/profile",
                    f"deepr://experts/{expert.expert_id}/beliefs",
                    f"deepr://experts/{expert.expert_id}/gaps",
                ])

        return uris
    
    async def handle_subscribe(
        self,
        uri: str,
        callback,
        wildcard: bool = False
    ) -> dict:
        """
        Handle a subscribe request.
        
        Args:
            uri: Resource URI to subscribe to
            callback: Async callback for notifications
            wildcard: Subscribe to all subresources
        
        Returns:
            Response dict with subscription_id or error
        """
        try:
            sub_id = await self._subscriptions.subscribe(uri, callback, wildcard)
            return {
                "subscription_id": sub_id,
                "uri": uri,
                "wildcard": wildcard
            }
        except ValueError as e:
            return {"error": str(e)}
    
    async def handle_unsubscribe(self, subscription_id: str) -> dict:
        """
        Handle an unsubscribe request.
        
        Args:
            subscription_id: ID from subscribe response
        
        Returns:
            Response dict with success status
        """
        success = await self._subscriptions.unsubscribe(subscription_id)
        return {"success": success, "subscription_id": subscription_id}
    
    def get_resource_uri_for_job(self, job_id: str) -> dict:
        """
        Get all resource URIs for a job.
        
        Args:
            job_id: Job identifier
        
        Returns:
            Dict with status, plan, and beliefs URIs
        """
        return {
            "status": f"deepr://campaigns/{job_id}/status",
            "plan": f"deepr://campaigns/{job_id}/plan",
            "beliefs": f"deepr://campaigns/{job_id}/beliefs"
        }
    
    def get_resource_uri_for_expert(self, expert_id: str) -> dict:
        """
        Get all resource URIs for an expert.
        
        Args:
            expert_id: Expert identifier
        
        Returns:
            Dict with profile, beliefs, and gaps URIs
        """
        return {
            "profile": f"deepr://experts/{expert_id}/profile",
            "beliefs": f"deepr://experts/{expert_id}/beliefs",
            "gaps": f"deepr://experts/{expert_id}/gaps"
        }


# Singleton instance for use across the MCP server
_handler_instance: Optional[MCPResourceHandler] = None


def get_resource_handler() -> MCPResourceHandler:
    """Get the singleton resource handler instance."""
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = MCPResourceHandler()
    return _handler_instance


def reset_resource_handler() -> None:
    """Reset the singleton (for testing)."""
    global _handler_instance
    _handler_instance = None
