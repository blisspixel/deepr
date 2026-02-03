"""
Deepr: Modular research automation pipeline.

Supports multiple AI providers (OpenAI, Azure) and storage backends (local, blob).
"""

__version__ = "2.6.0"
__author__ = "blisspixel"

from .config import AppConfig
from .providers import create_provider
from .storage import create_storage

__all__ = ["AppConfig", "create_provider", "create_storage"]
