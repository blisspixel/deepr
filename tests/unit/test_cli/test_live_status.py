"""Tests for live shimmer status utility."""

from unittest.mock import MagicMock, patch

from deepr.cli.live_status import LiveShimmerStatus, shimmer_status


def test_live_status_noop_when_disabled():
    console = MagicMock()
    status = LiveShimmerStatus(console, "Starting...", enabled=False)
    status.start()
    status.update("Working...")
    status.stop()


@patch("deepr.cli.live_status.Live")
def test_live_status_starts_and_updates(mock_live_cls):
    live_obj = MagicMock()
    mock_live_cls.return_value = live_obj

    console = MagicMock()
    status = LiveShimmerStatus(console, "Starting...", enabled=True)
    # force animation path even under non-tty test console
    status._enabled = True
    status.start()
    status.update("Updated")
    status.stop()

    assert live_obj.start.called
    assert live_obj.update.called
    assert live_obj.stop.called


def test_shimmer_status_context_manager():
    console = MagicMock()
    with shimmer_status("Doing work...", console=console, enabled=False) as status:
        status.update("Done")
