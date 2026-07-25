"""Regression test: background-job submission must not be silent in default mode.

MINIMAL is the default output mode and promises a single success line. The
background-job path printed only in VERBOSE and JSON modes, so a default-mode
`deepr research` against a background-capable provider reserved cost, submitted
the job, and exited 0 with no output at all - no job id to poll, no sign that
anything happened.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from click.testing import CliRunner

from deepr.cli.commands.run import _handle_background_job
from deepr.cli.output import OutputContext, OutputMode
from deepr.queue.base import JobStatus


def _queue() -> MagicMock:
    queue = MagicMock()
    queue.update_status = AsyncMock(return_value=True)
    return queue


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "expects_output"),
    [
        (OutputMode.MINIMAL, True),
        (OutputMode.VERBOSE, True),
        (OutputMode.QUIET, False),
    ],
)
async def test_background_submission_output_by_mode(mode: OutputMode, expects_output: bool) -> None:
    queue = _queue()
    runner = CliRunner()

    with runner.isolation() as outstreams:
        await _handle_background_job("research-abc123456789", "resp_xyz", OutputContext(mode=mode), queue)
    output = outstreams[0].getvalue().decode("utf-8")

    queue.update_status.assert_awaited_once_with(
        job_id="research-abc123456789", status=JobStatus.PROCESSING, provider_job_id="resp_xyz"
    )
    if expects_output:
        # The job id prefix must be present so the operator can poll it.
        assert "research-abc" in output
        assert "deepr status" in output
    else:
        assert output == ""
