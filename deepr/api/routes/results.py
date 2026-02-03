"""Results retrieval API routes."""

import asyncio
from flask import Blueprint, request, jsonify, send_file
from pathlib import Path

from ...storage import create_storage
from ...config import load_config


bp = Blueprint("results", __name__)


def get_storage():
    """Get storage instance from config."""
    config = load_config()
    storage_type = config.get("storage", "local")
    base_path = config.get("results_dir", "results")
    return create_storage(storage_type, base_path=base_path)


@bp.route("", methods=["GET"])
def list_results():
    """
    List all results with filtering and pagination.

    Query parameters:
        search: Full-text search query
        tags: Filter by tags (comma-separated)
        limit: Number of results (default: 50, max: 100)
        offset: Pagination offset (default: 0)
        sort: Sort field (date, cost, name)
        order: Sort order (asc, desc)

    Returns:
        200: List of results
    """
    try:
        search = request.args.get("search")
        tags = request.args.get("tags", "").split(",") if request.args.get("tags") else []
        limit = min(int(request.args.get("limit", 50)), 100)
        offset = int(request.args.get("offset", 0))
        sort = request.args.get("sort", "date")
        order = request.args.get("order", "desc")

        storage = get_storage()

        # List all result files
        results = asyncio.run(storage.list_results(
            limit=limit,
            offset=offset,
            sort=sort,
            order=order
        ))

        return jsonify({
            "results": results,
            "limit": limit,
            "offset": offset,
            "total": len(results),
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<job_id>", methods=["GET"])
def get_result(job_id: str):
    """
    Get result details by job ID.

    Returns:
        200: Result details
        404: Result not found
    """
    try:
        storage = get_storage()
        result = asyncio.run(storage.get_result(job_id))

        if not result:
            return jsonify({"error": "Result not found"}), 404

        return jsonify({"result": result}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<job_id>/download/<format>", methods=["GET"])
def download_result(job_id: str, format: str):
    """
    Download result in specified format.

    Supported formats: md, docx, txt, json, pdf

    Returns:
        200: File download
        404: Result not found
        400: Invalid format
    """
    try:
        valid_formats = ["md", "docx", "txt", "json", "pdf"]
        if format not in valid_formats:
            return jsonify({"error": f"Invalid format. Must be one of: {', '.join(valid_formats)}"}), 400

        storage = get_storage()
        file_path = asyncio.run(storage.get_result_path(job_id, format))

        if not file_path or not Path(file_path).exists():
            return jsonify({"error": "Result not found"}), 404

        # Determine mimetype
        mimetypes = {
            "md": "text/markdown",
            "txt": "text/plain",
            "json": "application/json",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "pdf": "application/pdf",
        }

        return send_file(
            file_path,
            mimetype=mimetypes.get(format, "application/octet-stream"),
            as_attachment=True,
            download_name=f"research_{job_id}.{format}"
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/search", methods=["GET"])
def search_results():
    """
    Full-text search across all results.

    Query parameters:
        q: Search query (required)
        limit: Number of results (default: 20)

    Returns:
        200: Search results
        400: Missing query
    """
    try:
        query = request.args.get("q")
        if not query:
            return jsonify({"error": "Search query (q) is required"}), 400

        limit = min(int(request.args.get("limit", 20)), 50)

        storage = get_storage()
        # Full-text search not yet implemented; use deepr search CLI instead
        results = []

        return jsonify({
            "query": query,
            "results": results,
            "total": len(results),
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<job_id>/tags", methods=["POST"])
def add_tags(job_id: str):
    """
    Add tags to a result.

    Request body:
        {
            "tags": ["tag1", "tag2"]
        }

    Returns:
        200: Tags added
        404: Result not found
    """
    try:
        data = request.get_json()
        tags = data.get("tags", [])

        if not tags:
            return jsonify({"error": "Tags array is required"}), 400

        storage = get_storage()
        success = asyncio.run(storage.add_tags(job_id, tags))

        if not success:
            return jsonify({"error": "Result not found"}), 404

        return jsonify({"message": "Tags added successfully", "tags": tags}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<job_id>/tags/<tag>", methods=["DELETE"])
def remove_tag(job_id: str, tag: str):
    """
    Remove a tag from a result.

    Returns:
        200: Tag removed
        404: Result not found
    """
    try:
        storage = get_storage()
        success = asyncio.run(storage.remove_tag(job_id, tag))

        if not success:
            return jsonify({"error": "Result not found"}), 404

        return jsonify({"message": "Tag removed successfully"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
