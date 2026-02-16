"""Web dashboard command — start the Deepr web server."""

import click


@click.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", "-p", default=5000, type=int, help="Port to bind to")
@click.option("--debug", is_flag=True, help="Enable debug mode with auto-reload")
def web(host: str, port: int, debug: bool):
    """Start the Deepr web dashboard.

    Launches the Flask web interface with real-time WebSocket updates.

    \b
    Examples:
        deepr web                  # Start on http://localhost:5000
        deepr web -p 8080          # Use port 8080
        deepr web --debug          # Enable debug mode
    """
    try:
        from deepr.web.app import app, socketio
    except ImportError as exc:
        raise click.ClickException(
            f"Web dependencies not installed: {exc}\nInstall with: pip install -e '.[web]'"
        ) from exc

    display_host = "localhost" if host == "0.0.0.0" else host
    click.echo("\n  Deepr Web Dashboard")
    click.echo(f"  http://{display_host}:{port}\n")

    socketio.run(
        app,
        debug=debug,
        host=host,
        port=port,
        allow_unsafe_werkzeug=True,
    )
