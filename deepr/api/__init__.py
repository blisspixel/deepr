"""
Deepr REST API module.

Provides RESTful API endpoints for the web interface.
"""

from .app import create_app

__all__ = ["create_app"]
