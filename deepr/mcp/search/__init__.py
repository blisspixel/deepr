"""
Dynamic Tool Discovery module for Deepr MCP Server.

This module implements the gateway pattern that reduces context by ~85%
by exposing only a single search tool that returns relevant tool schemas on demand.
"""

from .gateway import GatewayTool
from .registry import ToolRegistry, ToolSchema

__all__ = ["ToolRegistry", "ToolSchema", "GatewayTool"]
