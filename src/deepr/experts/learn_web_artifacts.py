"""Durable source and report artifacts for ``expert learn-web``.

The web-learning command uses the same source-pack, manifest, source-note, and
content-addressed snapshot contracts as subscription sync. This module owns only
form and persistence. It never decides whether a source is relevant or whether
one source supports a claim.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from deepr.experts.source_pack_compiler import build_source_notes, build_source_pack_manifest
from deepr.experts.sync_support import slug, write_source_snapshots
from deepr.utils.atomic_io import atomic_write_json


class LearnWebArtifactError(RuntimeError):
    """Raised when a web-learning run cannot persist its replay artifacts."""


@dataclass(frozen=True)
class LearnWebArtifacts:
    """Relative artifact refs plus candidate-selectable source-note refs."""

    source_pack: str
    source_pack_manifest: str
    source_notes: str
    report: str
    source_ref_catalog: dict[str, str]

    @property
    def report_id(self) -> str:
        return self.report or self.source_pack


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _source_ref_catalog(source_notes: dict[str, Any]) -> dict[str, str]:
    catalog: dict[str, str] = {}
    for note in source_notes.get("notes", []) or []:
        if not isinstance(note, dict):
            continue
        readiness = note.get("readiness", {}) or {}
        windows = note.get("windows", []) or []
        if not isinstance(readiness, dict) or readiness.get("ready_for_claim_extraction") is not True:
            continue
        if not windows or not isinstance(windows[0], dict):
            continue
        label = str(note.get("label", "") or "")
        note_id = str(note.get("note_id", "") or "")
        window_id = str(windows[0].get("window_id", "") or "")
        if label and note_id and window_id:
            catalog[label] = f"source_note:{note_id}:{window_id}"
    return catalog


def persist_learn_web_artifacts(
    *,
    expert_root: Path,
    expert_name: str,
    topic: str,
    research: dict[str, Any],
    started_at: datetime,
) -> LearnWebArtifacts:
    """Persist one retrieval attempt before any belief mutation.

    Under-ready attempts still produce source-pack, manifest, and source-note
    diagnostics. A synthesized answer additionally produces a durable report
    that points back to those artifacts. All returned paths are relative to the
    expert root so they remain portable with the expert directory.
    """
    raw_source_pack = research.get("source_pack")
    if not isinstance(raw_source_pack, dict):
        raise LearnWebArtifactError("web research returned no source-pack contract")

    source_pack = copy.deepcopy(raw_source_pack)
    try:
        write_source_snapshots(source_pack, expert_root)
        timestamp = started_at.strftime("%Y%m%dT%H%M%S%fZ")
        filename = f"{timestamp}_{slug(topic)}.json"
        artifact_root = expert_root / "learn_web_artifacts"
        source_pack_path = artifact_root / "source_packs" / filename
        manifest_path = artifact_root / "source_pack_manifests" / filename
        source_note_path = artifact_root / "source_notes" / filename
        report_path = artifact_root / "reports" / filename
        for directory in (source_pack_path.parent, manifest_path.parent, source_note_path.parent):
            directory.mkdir(parents=True, exist_ok=True)

        source_pack_ref = _relative(source_pack_path, expert_root)
        manifest_ref = _relative(manifest_path, expert_root)
        source_note_ref = _relative(source_note_path, expert_root)
        payload = {
            "schema_version": "deepr.learn_web_source_pack.v1",
            "expert_name": expert_name,
            "topic": topic,
            "started_at": started_at.isoformat(),
            "source_pack": source_pack,
        }
        atomic_write_json(source_pack_path, payload)
        manifest = build_source_pack_manifest(payload, source_pack_artifact=source_pack_ref)
        atomic_write_json(manifest_path, manifest)
        source_notes = build_source_notes(
            payload,
            source_pack_artifact=source_pack_ref,
            source_pack_manifest_artifact=manifest_ref,
        )
        atomic_write_json(source_note_path, source_notes)

        report_ref = ""
        answer = str(research.get("answer", "") or "").strip()
        if answer:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_ref = _relative(report_path, expert_root)
            atomic_write_json(
                report_path,
                {
                    "schema_version": "deepr.learn_web_report.v1",
                    "expert_name": expert_name,
                    "topic": topic,
                    "started_at": started_at.isoformat(),
                    "source_pack_artifact": source_pack_ref,
                    "source_pack_manifest_artifact": manifest_ref,
                    "source_note_artifact": source_note_ref,
                    "sources": research.get("sources", []),
                    "report": answer,
                },
            )
    except (OSError, TypeError, ValueError) as exc:
        raise LearnWebArtifactError(f"could not persist web-learning artifacts: {exc}") from exc

    return LearnWebArtifacts(
        source_pack=source_pack_ref,
        source_pack_manifest=manifest_ref,
        source_notes=source_note_ref,
        report=report_ref,
        source_ref_catalog=_source_ref_catalog(source_notes),
    )
