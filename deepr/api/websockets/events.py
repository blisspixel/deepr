"""Socket.IO event handlers."""

import logging

from flask_socketio import emit, join_room, leave_room

logger = logging.getLogger(__name__)


def register_socketio_events(socketio):
    """Register Socket.IO event handlers."""

    @socketio.on("connect")
    def handle_connect():
        """Handle client connection."""
        logger.info("Client connected")
        emit("connected", {"message": "Connected to Deepr API"})

    @socketio.on("disconnect")
    def handle_disconnect():
        """Handle client disconnection."""
        logger.info("Client disconnected")

    @socketio.on("subscribe_jobs")
    def handle_subscribe_jobs(data):
        """
        Subscribe to job updates.

        Client can subscribe to:
        - All jobs: {"scope": "all"}
        - Specific job: {"scope": "job", "job_id": "123"}
        """
        scope = data.get("scope", "all")

        if scope == "all":
            join_room("jobs")
            emit("subscribed", {"scope": "jobs", "message": "Subscribed to all jobs"})
            logger.info("Client subscribed to all jobs")

        elif scope == "job":
            job_id = data.get("job_id")
            if job_id:
                join_room(f"job_{job_id}")
                emit("subscribed", {"scope": "job", "job_id": job_id})
                logger.info(f"Client subscribed to job {job_id}")

    @socketio.on("unsubscribe_jobs")
    def handle_unsubscribe_jobs(data):
        """Unsubscribe from job updates."""
        scope = data.get("scope", "all")

        if scope == "all":
            leave_room("jobs")
            emit("unsubscribed", {"scope": "jobs"})

        elif scope == "job":
            job_id = data.get("job_id")
            if job_id:
                leave_room(f"job_{job_id}")
                emit("unsubscribed", {"scope": "job", "job_id": job_id})


def emit_job_created(socketio, job):
    """Emit job created event."""
    socketio.emit("job_created", job.to_dict(), room="jobs")
    logger.info(f"Emitted job_created for {job.id}")


def emit_job_updated(socketio, job):
    """Emit job updated event."""
    socketio.emit("job_updated", job.to_dict(), room="jobs")
    socketio.emit("job_updated", job.to_dict(), room=f"job_{job.id}")
    logger.info(f"Emitted job_updated for {job.id}")


def emit_job_completed(socketio, job):
    """Emit job completed event."""
    socketio.emit("job_completed", job.to_dict(), room="jobs")
    socketio.emit("job_completed", job.to_dict(), room=f"job_{job.id}")
    logger.info(f"Emitted job_completed for {job.id}")


def emit_job_failed(socketio, job, error):
    """Emit job failed event."""
    data = job.to_dict()
    data["error"] = error
    socketio.emit("job_failed", data, room="jobs")
    socketio.emit("job_failed", data, room=f"job_{job.id}")
    logger.info(f"Emitted job_failed for {job.id}")


def emit_cost_warning(socketio, warning):
    """Emit cost warning event."""
    socketio.emit("cost_warning", warning, room="jobs")
    logger.warning(f"Emitted cost_warning: {warning}")


def emit_cost_exceeded(socketio, exceeded):
    """Emit cost exceeded event."""
    socketio.emit("cost_exceeded", exceeded, room="jobs")
    logger.error(f"Emitted cost_exceeded: {exceeded}")
