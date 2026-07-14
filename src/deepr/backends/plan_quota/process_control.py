"""Private parent-to-supervisor status channel for Linux plan processes."""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass

_MAX_STATUS_BYTES = 256


@dataclass
class SupervisorControlPipe:
    """Parent-owned status channel that vendor output cannot forge."""

    read_fd: int
    write_fd: int | None

    def close_write(self) -> None:
        if self.write_fd is not None:
            with contextlib.suppress(OSError):
                os.close(self.write_fd)
            self.write_fd = None

    def read_status(self) -> str | None:
        data = b""
        try:
            while len(data) <= _MAX_STATUS_BYTES:
                chunk = os.read(self.read_fd, _MAX_STATUS_BYTES + 1 - len(data))
                if not chunk:
                    break
                data += chunk
        except OSError:
            return None
        finally:
            self._close_read()
        if len(data) > _MAX_STATUS_BYTES:
            return None
        try:
            return data.decode("ascii", errors="strict").strip() or None
        except UnicodeDecodeError:
            return None

    def close(self) -> None:
        self.close_write()
        self._close_read()

    def _close_read(self) -> None:
        if self.read_fd >= 0:
            with contextlib.suppress(OSError):
                os.close(self.read_fd)
            self.read_fd = -1


def open_supervisor_control_pipe() -> SupervisorControlPipe:
    """Create one non-inherited read end and passable write end."""
    read_fd, write_fd = os.pipe()
    return SupervisorControlPipe(read_fd, write_fd)
