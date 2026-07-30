"""Compatibility contracts for the retired duplicate poller."""

from deepr.research_agent.poller import JobPoller as CompatibilityPoller
from deepr.research_agent.poller import run_poller as compatibility_run_poller
from deepr.worker.poller import JobPoller, run_poller


def test_research_agent_poller_reuses_canonical_worker() -> None:
    assert CompatibilityPoller is JobPoller
    assert compatibility_run_poller is run_poller
