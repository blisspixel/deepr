"""Compatibility import for the canonical bounded job poller."""

from deepr.worker.poller import JobPoller, run_poller

__all__ = ["JobPoller", "run_poller"]


if __name__ == "__main__":
    import asyncio

    asyncio.run(run_poller())
