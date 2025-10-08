"""Flask application factory for Deepr API."""

import os
from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO

from .routes import jobs, results, cost, config as config_routes, planner
from .middleware.errors import register_error_handlers
from .websockets.events import register_socketio_events


socketio = SocketIO(cors_allowed_origins="*")


def create_app(config_name: str = "development") -> Flask:
    """
    Create and configure Flask application.

    Args:
        config_name: Configuration name (development, production, testing)

    Returns:
        Configured Flask application
    """
    app = Flask(__name__)

    # Load configuration
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev-secret-key-change-in-production"),
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16MB max upload
        JSON_SORT_KEYS=False,
        CORS_ORIGINS=os.getenv("CORS_ORIGINS", "*").split(","),
    )

    # Enable CORS
    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})

    # Initialize SocketIO
    socketio.init_app(app)

    # Register WebSocket events
    register_socketio_events(socketio)

    # Register blueprints
    app.register_blueprint(jobs.bp, url_prefix="/api/v1/jobs")
    app.register_blueprint(results.bp, url_prefix="/api/v1/results")
    app.register_blueprint(cost.bp, url_prefix="/api/v1/cost")
    app.register_blueprint(config_routes.bp, url_prefix="/api/v1/config")
    app.register_blueprint(planner.bp, url_prefix="/api/v1/planner")

    # Register error handlers
    register_error_handlers(app)

    # Health check endpoint
    @app.route("/health")
    def health():
        return {"status": "healthy", "version": "2.0.0"}

    # Root endpoint
    @app.route("/")
    def index():
        return {
            "name": "Deepr API",
            "version": "2.0.0",
            "description": "Research automation platform API",
            "docs": "/api/docs",
        }

    return app
