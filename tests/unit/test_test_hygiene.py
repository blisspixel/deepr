"""Regression tests for test-suite isolation guarantees."""

from __future__ import annotations

import socket

import pytest
from pytest_socket import SocketBlockedError, SocketConnectBlockedError


def test_unit_gate_blocks_outbound_sockets():
    """Unit tests must fail closed on accidental provider or web calls."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.01)
        with pytest.warns(UserWarning, match="socket.socket.connect"):
            with pytest.raises((SocketBlockedError, SocketConnectBlockedError)):
                sock.connect(("203.0.113.1", 80))


def test_unit_gate_allows_loopback_sockets():
    """Loopback remains available for local fixtures and smoke helpers."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.settimeout(1.0)
    client.settimeout(1.0)

    try:
        server.bind(("127.0.0.1", 0))
        server.listen(1)

        client.connect(server.getsockname())
        connection, _address = server.accept()
        connection.close()
    finally:
        client.close()
        server.close()
