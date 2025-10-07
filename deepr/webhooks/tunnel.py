"""Ngrok tunnel management for local development."""

import subprocess
import time
import requests
from typing import Optional


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
        self.process: Optional[subprocess.Popen] = None
        self.public_url: Optional[str] = None

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
            self.process = subprocess.Popen(
                [self.ngrok_path, "http", str(self.port)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # Poll for public URL
            for _ in range(60):
                try:
                    response = requests.get(
                        "http://127.0.0.1:4040/api/tunnels", timeout=2
                    )
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
            raise RuntimeError(f"Ngrok startup failed: {e}")

    def stop(self):
        """Stop ngrok tunnel."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                pass

        self._kill_existing()

    def _kill_existing(self):
        """Kill any existing ngrok processes."""
        import os

        if os.name == "nt":  # Windows
            subprocess.run(
                "taskkill /F /IM ngrok.exe",
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:  # Unix
            subprocess.run(
                "pkill ngrok",
                shell=True,
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
