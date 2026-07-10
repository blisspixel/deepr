"""HTTP projection for research cancellation outcomes."""

from collections.abc import Callable

from flask import jsonify

from deepr.queue.base import JobStatus, ResearchJob


def cancellation_response(job: ResearchJob | None, cancel: Callable[[ResearchJob], bool]):
    """Return truthful HTTP status for one cancellation request."""
    if job is None:
        return jsonify({"error": "Job not found"}), 404
    if job.status == JobStatus.CANCELLED:
        if cancel(job):
            return jsonify({"success": True})
        return jsonify({"error": "Cancellation closure could not be confirmed"}), 503
    if job.status not in {JobStatus.QUEUED, JobStatus.PROCESSING}:
        return jsonify({"error": "Terminal job state cannot be cancelled"}), 409
    if not cancel(job):
        return jsonify({"error": "Job cancellation could not be confirmed"}), 503
    return jsonify({"success": True})


__all__ = ["cancellation_response"]
