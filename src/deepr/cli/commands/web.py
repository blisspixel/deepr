"""Web dashboard command - start the Deepr web server."""

import ipaddress
import os

import click


def _is_loopback(host: str) -> bool:
    """Return True if host is a loopback address (or 'localhost')."""
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@click.command()
@click.option(
    "--host",
    default="127.0.0.1",
    show_default=True,
    help="Host to bind to. Defaults to loopback for safety. Use 0.0.0.0 to expose on all interfaces (requires DEEPR_API_KEY).",
)
@click.option("--port", "-p", default=5000, type=int, help="Port to bind to")
@click.option("--debug", is_flag=True, help="Enable debug mode with auto-reload")
@click.option(
    "--allow-unauthenticated-public-bind",
    is_flag=True,
    help=(
        "Acknowledge an unauthenticated public-bind request. The built-in Werkzeug launcher "
        "still refuses non-loopback hosts; use a production WSGI server."
    ),
)
def web(host: str, port: int, debug: bool, allow_unauthenticated_public_bind: bool) -> None:
    """Start the Deepr web dashboard.

    Launches the Flask web interface with real-time WebSocket updates.

    \b
    Examples:
        deepr web                  # Bind to 127.0.0.1:5000 (safe default)
        deepr web -p 8080          # Use port 8080
        deepr web --host 0.0.0.0   # Refused by the built-in development server
        deepr web --debug          # Enable debug mode
    """
    try:
        from deepr.web.app import app, socketio
    except ImportError as exc:
        raise click.ClickException(
            f"Web dependencies not installed: {exc}\nInstall with: pip install -e '.[web]'"
        ) from exc

    api_key_set = bool(os.getenv("DEEPR_API_KEY", "").strip())
    loopback = _is_loopback(host)

    if not loopback and not api_key_set and not allow_unauthenticated_public_bind:
        raise click.ClickException(
            "Refusing to bind '" + host + "' without DEEPR_API_KEY set. The dashboard would be reachable by any\n"
            "network peer without authentication. Either:\n"
            "  - Set DEEPR_API_KEY in your environment to require an API key, or\n"
            "  - Run with --host 127.0.0.1 (the safe default), or\n"
            "  - Pass --allow-unauthenticated-public-bind if you explicitly accept the risk\n"
            "    (only on a trusted network)."
        )

    if not loopback:
        raise click.ClickException(
            "Refusing to run the Werkzeug development server on a non-loopback host. "
            "Use a production WSGI server and configure DEEPR_API_KEY before exposing the dashboard."
        )

    click.echo("\n  Deepr Web Dashboard")
    click.echo(f"  http://{host}:{port}")
    click.echo("")

    socketio.run(
        app,
        debug=debug,
        host=host,
        port=port,
        allow_unsafe_werkzeug=loopback,
    )
