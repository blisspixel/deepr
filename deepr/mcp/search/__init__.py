"""
Dynamic Tool Discovery module for Deepr MCP Server.

This module implements the gateway pattern that reduces context by ~85%
by exposing only a single search tool that returns relevant tool schemas on demand.
"""

from .registry import ToolRegistry, ToolSchema
from .gateway import GatewayTool

__all__ = ["ToolRegistry", "ToolSchema", "GatewayTool"]
