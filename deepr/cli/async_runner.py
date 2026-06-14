"""Back-compat re-export of the shared async runner.

The implementation moved to ``deepr.utils.async_runner`` (Phase Q1.3) so the
CLI, web, and API surfaces share one helper. Existing
``from deepr.cli.async_runner import run_async_command`` imports keep working.
"""

from deepr.utils.async_runner import run_async_command

__all__ = ["run_async_command"]
