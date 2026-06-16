"""MCP provider enhancements — Resources, Prompts, and Sampling.

Exposes expert state as MCP resources, provides reusable prompt
templates, and supports sampling requests with fallback.
"""

from deepr.mcp.provider.prompts import PromptRenderer
from deepr.mcp.provider.resources import ResourceHandler
from deepr.mcp.provider.sampling import SamplingHandler

__all__ = [
    "PromptRenderer",
    "ResourceHandler",
    "SamplingHandler",
]
