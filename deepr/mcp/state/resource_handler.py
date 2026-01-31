"""
MCP Resource Handler.

Integrates subscriptions, job management, and expert resources
into a unified resource handling interface for the MCP server.
"""

from typing import Optional, Any
from dataclasses import dataclass

from .subscriptions import SubscriptionManager, parse_resource_uri
from .job_manager import JobManager, JobPhase
from .expert_resources import ExpertResourceManager


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
    - Reading expert resources (profile, beliefs, gaps)
    - Managing subscriptions
    - Emitting updates
    """
    
    def __init__(self):
        self._subscriptions = SubscriptionManager()
        self._jobs = JobManager(self._subscriptions)
        self._experts = ExpertResourceManager()
    
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
            resource_type: Optional filter ("campaigns" or "experts")
        
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
