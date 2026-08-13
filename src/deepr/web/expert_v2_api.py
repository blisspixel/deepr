"""Read-only HTTP access to what an expert actually is.

The web API served an expert as `document_count`, `finding_count`, `gap_count`
and `total_cost` - fields that describe any CRUD application, which is why the
UI built on them looked like any CRUD application. Nothing in the v2 expert
layer was reachable over HTTP at all: no standpoint, no positions, no evidence
chain, no history of what the expert used to think.

That is the whole gap this closes. Every route here is a read of something the
CLI already writes, exposed so a browser can show the one thing a terminal
cannot: an evidence chain you can follow by clicking, from a position, through
the finding that supports it, down to the highlighted sentence in the retained
source.

Every route is $0. No model call, no network, no mutation.

**Absent is 404, empty is 200.** An expert that has never been briefed has no
`hold/current.json`, and saying so is different from returning an empty list of
positions - the second reads as "this expert holds no views", which is a claim
about the expert rather than about the pipeline.

Routes are registered as module-level functions rather than closures inside one
registrar. Nested, the registration function scored a cyclomatic complexity of
52 for what is really a handful of independent reads.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from flask import Flask, jsonify

from deepr.experts.expert_layout import (
    canonical_expert_dir,  # via the module, so a patched expert root is honoured
    evidence_graph_in,
    part_in,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
"""A retained source is addressed by content hash and nothing else.

Checked before the sha reaches ``CorpusStore.read``, which builds
``sources/<sha[:2]>/<sha>.md`` by string interpolation and would happily follow
``../`` out of the corpus. Validating the shape here means path confinement is
a property of the input rather than of every caller remembering."""

#: route suffix -> (layout part, response key, message when absent)
_SIMPLE_PARTS: tuple[tuple[str, str, str, str], ...] = (
    ("self", "self", "self", "This expert has not written a self-account yet."),
    ("hold", "hold_current", "hold", "This expert has not landed on any positions yet."),
    ("hold/history", "hold_history", "history", "This expert has no recorded position history."),
    ("noticed", "noticed", "noticed", "This expert has not studied its corpus yet."),
    ("became", "became", "became", "This expert has no recorded perspective graph."),
    ("attend", "attend", "attend", "This expert has no research practice recorded."),
    ("met/examination", "met_examination", "examination", "This expert has not been examined."),
)

Resolver = Callable[[str], tuple[str, Path, Any]]


def _read_json(path: Path) -> dict[str, Any] | None:
    """Parsed contents, or None when missing or unusable.

    Missing and corrupt are the same answer on purpose: a file that cannot be
    parsed is no more usable than one that is absent, and returning half a
    document to the UI is how a corrupt artifact gets rendered as fact.
    """
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def roster_entry(expert_name: str) -> dict[str, Any]:
    """The few v2 fields that let a roster tell one expert from another.

    Read per expert rather than served from its own route because the hub lists
    the whole fleet, and fifty-seven extra round trips to render one screen is
    a worse trade than reading fifty-seven small files.

    Never raises. A roster that fails to load because one expert has a corrupt
    self-account is worse than a roster with one thin row.
    """
    try:
        directory = canonical_expert_dir(expert_name)
        account = _read_json(part_in(directory, "self")) or {}
        hold = _read_json(part_in(directory, "hold_current")) or {}
        positions = hold.get("positions") or []
        # From the study rather than the v1 counter, which reports 0 for every
        # expert built through the v2 loop: Keel has 98 findings and the
        # roster showed "0 findings" beside "14 positions", which reads as an
        # expert that invented its views.
        noticed = _read_json(part_in(directory, "noticed")) or {}
        totals = noticed.get("totals") or {}
        independence = noticed.get("independence") or {}
        return {
            "chosen_name": str(account.get("chosen_name") or ""),
            "standpoint": str(account.get("standpoint") or ""),
            "glad_to_be_asked_about": [str(q) for q in (account.get("glad_to_be_asked_about") or [])][:3],
            "preferred_lens": str(account.get("preferred_lens") or ""),
            "position_count": len(positions),
            "falsifiable_count": sum(1 for p in positions if p.get("is_falsifiable")),
            "mind_changes": len(account.get("shifts") or []),
            "studied_findings": int(totals.get("findings", 0) or 0),
            "grounded_findings": int(totals.get("grounded_findings", 0) or 0),
            "source_count": int(independence.get("source_count", 0) or 0),
        }
    except Exception:
        return {
            "chosen_name": "",
            "standpoint": "",
            "glad_to_be_asked_about": [],
            "preferred_lens": "",
            "position_count": 0,
            "falsifiable_count": 0,
            "mind_changes": 0,
            "studied_findings": 0,
            "grounded_findings": 0,
            "source_count": 0,
        }


def roster_readiness(entry: dict[str, Any], *, portrait_url: object) -> dict[str, Any]:
    """Report missing presentation structure without judging semantic quality.

    These checks guard observable form only. They do not conclude that a
    standpoint is correct, findings are important, or the expert is good.
    """
    missing: list[str] = []
    if not str(entry.get("standpoint") or "").strip():
        missing.append("standpoint")
    if int(entry.get("position_count", 0) or 0) <= 0:
        missing.append("positions")
    if int(entry.get("studied_findings", 0) or 0) <= 0:
        missing.append("studied findings")
    if int(entry.get("source_count", 0) or 0) <= 0:
        missing.append("retained sources")
    if not isinstance(portrait_url, str) or not portrait_url.strip():
        missing.append("portrait")
    return {"roster_ready": not missing, "roster_missing": missing}


def _enrich_self(payload: dict[str, Any], name: str) -> dict[str, Any]:
    """Derive what the UI branches on rather than trusting the stored file.

    `has_standpoint` and `has_changed_its_mind` are computed from the account,
    so a stale file cannot disagree with the flags a screen switches on.
    """
    from deepr.experts.expert_profile_card import ExpertProfile

    account = payload.get("self") or {}
    profile = ExpertProfile.from_dict({**account, "expert_name": account.get("expert_name") or name})
    payload["self"] = {
        **account,
        "has_standpoint": profile.has_standpoint,
        "has_changed_its_mind": profile.has_changed_its_mind,
        "concerns": profile.concerns(),
    }
    return payload


def _register_part_route(
    app: Flask,
    route: str,
    part_name: str,
    key: str,
    absent: str,
    resolve: Resolver,
    logger: logging.Logger,
) -> None:
    """Register one read-a-file route.

    Endpoints are namespaced `expert_v2_*` because app.py already owns
    `get_expert_history`, and Flask refuses a duplicate endpoint name.
    """

    def view(name: str):
        try:
            decoded, directory, err = resolve(name)
            if err:
                return err
            data = _read_json(part_in(directory, part_name))
            if data is None:
                return jsonify({"error": absent, "expert": decoded}), 404
            payload = {key: data, "expert": decoded, "cost_usd": 0.0}
            return jsonify(_enrich_self(payload, decoded) if key == "self" else payload)
        except Exception as exc:
            logger.error("Error reading %s for %s: %s", key, name, exc)
            return jsonify({"error": "Internal server error"}), 500

    app.add_url_rule(
        f"/api/experts/<name>/{route}",
        endpoint=f"expert_v2_{key.replace('/', '_')}",
        view_func=view,
        methods=["GET"],
    )


def _register_evidence_route(app: Flask, resolve: Resolver, logger: logging.Logger) -> None:
    """What rests on what: position -> finding -> source, with concentration."""

    def view(name: str):
        try:
            decoded, directory, err = resolve(name)
            if err:
                return err
            data = _read_json(evidence_graph_in(directory))
            if data is None:
                return jsonify({"error": "This expert has no evidence graph built.", "expert": decoded}), 404
            return jsonify({"evidence": data, "expert": decoded, "cost_usd": 0.0})
        except Exception as exc:
            logger.error("Error reading evidence graph for %s: %s", name, exc)
            return jsonify({"error": "Internal server error"}), 500

    app.add_url_rule("/api/experts/<name>/evidence", endpoint="expert_v2_evidence", view_func=view, methods=["GET"])


def _corpus_records(index: Path) -> list[dict[str, Any]]:
    """Every line in the index that describes a source.

    Keyed on the presence of `sha256` rather than on position, so the schema
    header is excluded by not being a source rather than by being first, and a
    second header line or a reordered file changes nothing. One malformed line
    is skipped rather than hiding the rest of the corpus.
    """
    records: list[dict[str, Any]] = []
    for line in index.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and "sha256" in record:
            records.append(record)
    return records


def _register_corpus_route(app: Flask, resolve: Resolver, logger: logging.Logger) -> None:
    """What it has read, with publisher and trust class per source."""

    def view(name: str):
        try:
            decoded, directory, err = resolve(name)
            if err:
                return err
            index = directory / "corpus" / "index.jsonl"
            if not index.exists():
                return jsonify({"error": "This expert has retained no sources.", "expert": decoded}), 404
            entries = _corpus_records(index)
            return jsonify(
                {
                    "corpus": {
                        "sources": entries,
                        "active": [e for e in entries if not e.get("superseded_by")],
                    },
                    "expert": decoded,
                    "cost_usd": 0.0,
                }
            )
        except Exception as exc:
            logger.error("Error reading corpus for %s: %s", name, exc)
            return jsonify({"error": "Internal server error"}), 500

    app.add_url_rule("/api/experts/<name>/corpus", endpoint="expert_v2_corpus", view_func=view, methods=["GET"])


def _source_payload(store: Any, sha: str, decoded: str, text: str) -> dict[str, Any]:
    """One retained source with the index metadata that describes it.

    Looked up in every entry rather than only the active ones. A superseded
    source is still readable by sha - that is the point of addressing by
    content - and reading it back with a blank title and publisher would make
    the older of two versions look like an unattributed fragment.
    """
    entry = store.entries.get(sha) if isinstance(getattr(store, "entries", None), dict) else None
    if entry is None:
        entry = next((e for e in store.active_entries() if getattr(e, "sha256", "") == sha), None)
    return {
        "source": {
            "sha256": sha,
            "text": text,
            "title": getattr(entry, "title", "") if entry else "",
            "url": getattr(entry, "url", "") if entry else "",
            "publisher": getattr(entry, "publisher", "") if entry else "",
            "trust_class": getattr(entry, "trust_class", "") if entry else "",
            "added_at": getattr(entry, "added_at", "") if entry else "",
        },
        "expert": decoded,
        "cost_usd": 0.0,
    }


def _register_source_route(app: Flask, resolve: Resolver, logger: logging.Logger) -> None:
    """The retained text of one source, so an anchor can be shown in place.

    This is the route that makes the rest legible. Without it a citation is a
    title; with it, a claim reaches the sentence it rests on. Served as JSON
    rather than as a download because the caller highlights a substring inside
    it rather than saving it.
    """

    def view(name: str, sha: str):
        try:
            if not _SHA256_RE.match(sha or ""):
                return jsonify({"error": "A source is addressed by its sha256."}), 400
            decoded, directory, err = resolve(name)
            if err:
                return err

            from deepr.experts.corpus_store import CorpusStore

            try:
                # Anchored to the directory resolve() returned. CorpusStore
                # otherwise derives its own root through a binding this module
                # deliberately routes around, so a patched or custom expert
                # root would read the wrong corpus.
                store = CorpusStore(decoded, storage_dir=directory / "corpus")
            except Exception:
                return jsonify({"error": "This expert has retained no sources.", "expert": decoded}), 404

            text = store.read(sha)
            if text is None:
                return jsonify({"error": "No retained source with that hash.", "expert": decoded}), 404
            return jsonify(_source_payload(store, sha, decoded, text))
        except Exception as exc:
            logger.error("Error reading source %s for %s: %s", sha, name, exc)
            return jsonify({"error": "Internal server error"}), 500

    app.add_url_rule("/api/experts/<name>/source/<sha>", endpoint="expert_v2_source", view_func=view, methods=["GET"])


def _stage_artifacts(directory: Path) -> dict[str, dict[str, Any] | None]:
    """Load every artifact the stage contract refers to, or None where unusable."""
    from deepr.experts.expert_layout import resolve_relative
    from deepr.experts.stage_contract import STAGES

    wanted = {s.produces for s in STAGES if s.produces}
    wanted |= {r.artifact for s in STAGES for r in s.requires}

    artifacts: dict[str, dict[str, Any] | None] = {}
    for relative in sorted(wanted):
        path = resolve_relative(directory, relative)
        if not path.exists():
            artifacts[relative] = None
        elif path.suffix == ".jsonl":
            try:
                lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
                artifacts[relative] = {"active_count": len(lines)}
            except OSError:
                artifacts[relative] = None
        else:
            artifacts[relative] = _read_json(path)
    return artifacts


def _register_stages_route(app: Flask, resolve: Resolver, logger: logging.Logger) -> None:
    """Where this expert is in the loop, and what failed rather than never ran."""

    def view(name: str):
        try:
            decoded, directory, err = resolve(name)
            if err:
                return err
            from deepr.experts.stage_contract import evaluate_all, next_stage

            states = evaluate_all(_stage_artifacts(directory))
            nxt = next_stage(states)
            return jsonify(
                {
                    "stages": [s.to_dict() for s in states],
                    "next": nxt.name if nxt else None,
                    "expert": decoded,
                    "cost_usd": 0.0,
                }
            )
        except Exception as exc:
            logger.error("Error evaluating stages for %s: %s", name, exc)
            return jsonify({"error": "Internal server error"}), 500

    app.add_url_rule("/api/experts/<name>/stages", endpoint="expert_v2_stages", view_func=view, methods=["GET"])


def _register_fleet_health_route(app: Flask, logger: logging.Logger) -> None:
    """Every expert's artifact hygiene, in one pass over the consult log.

    Fleet-scoped deliberately: `last_consulted_days` reads a single append-only
    trace store, so asking per expert would read the same log once per expert.
    """

    def view():
        try:
            from deepr.experts.expert_health import assess_expert, fleet_summary, last_consulted_days
            from deepr.experts.profile import ExpertStore

            consulted = last_consulted_days()
            fleet = []
            for profile in ExpertStore().list_all():
                expert_name = getattr(profile, "name", "")
                if not expert_name:
                    continue
                fleet.append(
                    assess_expert(
                        name=expert_name,
                        expert_dir=canonical_expert_dir(expert_name),
                        beliefs=0,
                        consulted_days_ago=consulted.get(expert_name),
                    )
                )
            return jsonify({"summary": fleet_summary(fleet), "experts": [h.to_dict() for h in fleet], "cost_usd": 0.0})
        except Exception as exc:
            logger.error("Error building fleet health: %s", exc)
            return jsonify({"error": "Internal server error"}), 500

    app.add_url_rule("/api/fleet/health", endpoint="expert_v2_fleet_health", view_func=view, methods=["GET"])


def register_expert_v2_api(
    app: Flask,
    decode_expert_name: Callable[[str], tuple[str, Any]],
    logger: logging.Logger,
) -> None:
    """Register the read-only v2 expert routes."""

    def resolve(name: str) -> tuple[str, Path, Any]:
        """Decoded name and directory, or an error response to return.

        Resolved through `canonical_expert_dir`, which is the same function
        every other reader of the v2 layout uses, so these routes and the CLI
        can never disagree about where an expert lives.

        Deliberately not parameterised on an `experts_dir`: this module took
        one and ignored it, which is a signature that lies. The layout helpers
        look the root up on the module at call time, so redirecting the fleet
        is done by pointing `deepr.experts.paths` somewhere else and every
        reader follows - rather than by threading a directory through each
        route and hoping they all use it.
        """
        decoded, err = decode_expert_name(name)
        if err:
            return "", Path(), err
        return decoded, canonical_expert_dir(decoded), None

    for route, part_name, key, absent in _SIMPLE_PARTS:
        _register_part_route(app, route, part_name, key, absent, resolve, logger)

    _register_evidence_route(app, resolve, logger)
    _register_corpus_route(app, resolve, logger)
    _register_source_route(app, resolve, logger)
    _register_stages_route(app, resolve, logger)
    _register_fleet_health_route(app, logger)
