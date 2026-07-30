"""Release-blocked external tunnel management."""

import subprocess
from types import TracebackType


class NgrokTunnel:
    """Retain tunnel inventory while blocking unaccounted external service use."""

    def __init__(self, ngrok_path: str = "ngrok", port: int = 5000) -> None:
        self.ngrok_path = ngrok_path
        self.port = port
        self.process: subprocess.Popen[bytes] | None = None
        self.public_url: str | None = None

    def start(self) -> str:
        """Refuse startup before process creation or an external service call."""
        raise RuntimeError(
            "Ngrok tunnel startup is disabled because Deepr cannot prove the account, plan, overage posture, "
            "or a provider-enforced cost ceiling. Use a manually managed endpoint outside Deepr's $5 guarantee."
        )

    def stop(self) -> None:
        """Stop only the process owned by this instance, if one exists."""
        if self.process is None:
            return
        try:
            self.process.terminate()
            self.process.wait(timeout=5)
        except Exception:
            pass
        finally:
            self.process = None
            self.public_url = None

    def __enter__(self) -> "NgrokTunnel":
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.stop()
