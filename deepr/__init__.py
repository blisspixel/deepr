"""Deepr package exports.

Keep package import lightweight by lazily importing heavy modules.
"""

from typing import TYPE_CHECKING, Any

__version__ = "2.8.1"
__author__ = "blisspixel"

if TYPE_CHECKING:
    from .config import AppConfig
    from .core.settings import Settings

__all__ = ["AppConfig", "Settings", "create_provider", "create_storage", "get_settings"]


def __getattr__(name: str) -> Any:
    """Lazily resolve top-level exports."""
    if name == "AppConfig":
        from .config import AppConfig

        return AppConfig

    if name in {"Settings", "get_settings"}:
        from .core.settings import Settings, get_settings

        return Settings if name == "Settings" else get_settings

    if name == "create_provider":
        from .providers import create_provider

        return create_provider

    if name == "create_storage":
        from .storage import create_storage

        return create_storage

    # Backwards-compatible module exports used by tests and patch paths.
    if name in {"providers", "storage", "core", "config"}:
        import importlib

        return importlib.import_module(f".{name}", __name__)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
