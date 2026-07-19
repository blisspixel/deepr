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
    "--allow-unauthenticated-loopback",
    is_flag=True,
    envvar="DEEPR_WEB_ALLOW_UNAUTHENTICATED_LOOPBACK",
    help=(
        "Explicitly allow tokenless access from this machine while bound to loopback. "
        "Never permits a non-loopback bind."
    ),
)
def web(host: str, port: int, debug: bool, allow_unauthenticated_loopback: bool) -> None:
    """Start the Deepr web dashboard.

    Launches the Flask web interface with real-time WebSocket updates.

    \b
    Examples:
        deepr web                  # Requires DEEPR_API_KEY
        deepr web --allow-unauthenticated-loopback
        deepr web -p 8080          # Use port 8080
        deepr web --host 0.0.0.0   # Refused by the built-in development server
        deepr web --debug          # Enable debug mode
    """
    try:
        from deepr.web import app as web_app
    except ImportError as exc:
        raise click.ClickException(
            f"Web dependencies not installed: {exc}\nInstall with: pip install -e '.[web]'"
        ) from exc

    api_key = os.getenv("DEEPR_API_KEY", "").strip()
    loopback = _is_loopback(host)

    if not loopback:
        raise click.ClickException(
            "Refusing to run the Werkzeug development server on a non-loopback host. "
            "Use a production WSGI server and configure DEEPR_API_KEY before exposing the dashboard."
        )

    if not api_key and not allow_unauthenticated_loopback:
        raise click.ClickException(
            "Refusing to start without DEEPR_API_KEY. Loopback locality is not caller "
            "authentication. Set DEEPR_API_KEY, or explicitly accept tokenless local "
            "access with --allow-unauthenticated-loopback."
        )

    # The application module is imported before Click dispatch in some hosts.
    # Apply the validated launch contract to the already-registered HTTP and
    # Socket.IO callbacks instead of relying on import-time environment state.
    web_app._API_KEY = api_key
    web_app._ALLOW_UNAUTHENTICATED_LOOPBACK = allow_unauthenticated_loopback

    click.echo("\n  Deepr Web Dashboard")
    click.echo(f"  http://{host}:{port}")
    click.echo("")

    web_app.socketio.run(
        web_app.app,
        debug=debug,
        host=host,
        port=port,
        allow_unsafe_werkzeug=loopback,
    )
