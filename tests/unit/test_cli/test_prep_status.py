"""Regression tests for `deepr prep status`.

The command previously imported `deepr.services.queue.get_queue`, which does not
exist, and called the async `list_jobs` synchronously. Both faults meant the
command raised at runtime for every invocation. These tests exercise the command
end to end against an empty local queue so the wiring stays correct.
"""

from click.testing import CliRunner

from deepr.cli.commands.prep import status


def test_prep_status_reports_missing_batch_without_crashing() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(status, ["nonexistent-batch"])

    # The command must construct the queue and await list_jobs cleanly, then
    # report the missing batch. A broken import or a synchronous async call would
    # surface here as an unexpected exception rather than a clean abort.
    assert result.exit_code == 1
    assert "Batch not found: nonexistent-batch" in result.output
    if result.exception is not None:
        assert isinstance(result.exception, SystemExit)
