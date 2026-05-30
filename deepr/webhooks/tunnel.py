"""Ngrok tunnel management for local development."""

import subprocess
import time

import requests


class NgrokTunnel:
    """Manages ngrok tunnel for webhook URLs."""

    def __init__(self, ngrok_path: str = "ngrok", port: int = 5000):
        """
        Initialize ngrok tunnel manager.

        Args:
            ngrok_path: Path to ngrok executable
            port: Local port to tunnel
        """
        self.ngrok_path = ngrok_path
        self.port = port
        self.process: subprocess.Popen | None = None
        self.public_url: str | None = None

    def start(self) -> str:
        """
        Start ngrok tunnel.

        Returns:
            Public HTTPS URL

        Raises:
            RuntimeError: If tunnel startup fails
        """
        try:
            # Kill any existing ngrok processes
            self._kill_existing()
            time.sleep(1)

            # Start ngrok
            self.process = subprocess.Popen(  # ngrok_path user-supplied or discovered; tunnel is opt-in for webhook public exposure during development/testing only.
                [self.ngrok_path, "http", str(self.port)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # Poll for public URL
            for _ in range(60):
                try:
                    response = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=2)
                    tunnels = response.json().get("tunnels", [])

                    for tunnel in tunnels:
                        url = tunnel.get("public_url", "")
                        if url.startswith("https://"):
                            self.public_url = url
                            return f"{self.public_url}/webhook"

                    time.sleep(1)

                except Exception:
                    time.sleep(1)

            raise RuntimeError("Failed to retrieve ngrok public URL")

        except Exception as e:
            self.stop()
            raise RuntimeError(f"Ngrok startup failed: {e}") from e

    def stop(self):
        """Stop ngrok tunnel."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                pass  # best-effort ngrok process terminate during shutdown; may already be dead

        self._kill_existing()

    def _kill_existing(self):
        """Kill any existing ngrok processes."""
        import os

        if os.name == "nt":  # Windows
            subprocess.run(  # Standard Windows system utility...
                ["taskkill", "/F", "/IM", "ngrok.exe"],
                shell=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:  # Unix
            subprocess.run(  # Standard Unix utility...
                ["pkill", "ngrok"],
                shell=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
