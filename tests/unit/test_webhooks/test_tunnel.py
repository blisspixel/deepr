"""No-surprise-spend contracts for external tunnel services."""

from unittest.mock import MagicMock, patch

import pytest

from deepr.webhooks.tunnel import NgrokTunnel


def test_ngrok_start_blocks_before_subprocess_or_http() -> None:
    tunnel = NgrokTunnel(ngrok_path="paid-ngrok", port=5000)

    with (
        patch("subprocess.Popen", side_effect=AssertionError("must not spawn")) as spawn,
        patch("requests.get", side_effect=AssertionError("must not call")) as request,
        pytest.raises(RuntimeError, match="cannot prove the account, plan, overage posture"),
    ):
        tunnel.start()

    spawn.assert_not_called()
    request.assert_not_called()


def test_ngrok_stop_terminates_only_owned_process() -> None:
    tunnel = NgrokTunnel()
    process = MagicMock()
    tunnel.process = process
    tunnel.public_url = "https://example.invalid"

    with patch("subprocess.run", side_effect=AssertionError("must not kill unrelated processes")) as run:
        tunnel.stop()

    process.terminate.assert_called_once_with()
    process.wait.assert_called_once_with(timeout=5)
    run.assert_not_called()
    assert tunnel.process is None
    assert tunnel.public_url is None


def test_ngrok_stop_handles_timeout_and_oserror_gracefully() -> None:
    import subprocess

    tunnel = NgrokTunnel()
    process = MagicMock()
    process.wait.side_effect = subprocess.TimeoutExpired(cmd="ngrok", timeout=5)
    tunnel.process = process
    tunnel.public_url = "https://example.invalid"

    tunnel.stop()

    process.terminate.assert_called_once_with()
    assert tunnel.process is None
    assert tunnel.public_url is None

    # Also test OSError on terminate
    tunnel2 = NgrokTunnel()
    process2 = MagicMock()
    process2.terminate.side_effect = OSError("Process already dead")
    tunnel2.process = process2

    tunnel2.stop()

    assert tunnel2.process is None
