"""Local evidence-first investigation executor."""

from __future__ import annotations

import copy
from collections.abc import Awaitable, Callable
from typing import Any, cast

from deepr.backends.fresh_context import (
    FreshContext,
    FreshContextConfig,
    deep_fresh_context_config,
    make_free_deep_context_builder,
)
from deepr.experts.chat_backends import ExpertChatBackend
from deepr.experts.investigation.inputs import materialize_input_context, requested_urls
from deepr.experts.investigation.learning import stage_expert_learning
from deepr.experts.investigation.models import (
    DEFAULT_LOCAL_CONTEXT_WINDOW_TOKENS,
    LEARNING_MANIFEST_KIND,
    LEARNING_MANIFEST_SCHEMA_VERSION,
    TERMINAL_STATES,
    LearningMode,
    Phase,
    ProtocolMode,
    RunState,
    safe_ref,
    sha256_bytes,
    sha256_json,
    utc_now,
    validate_plan,
)
from deepr.experts.investigation.perspective_learning import build_perspective_graph_commit_envelope
from deepr.experts.investigation.protocol import (
    charter_prompt,
    checker_prompt,
    compile_charter,
    compile_check,
    compile_discussion,
    compile_position,
    compile_result,
    discussion_prompt,
    position_prompt,
    render_input_context,
    render_source_pack,
    synthesis_prompt,
)
from deepr.experts.investigation.runtime import (
    InvestigationBudgetExhausted,
    InvestigationCancelled,
    InvestigationPaused,
    InvestigationRuntime,
)
from deepr.experts.investigation.store import InvestigationStore

ContextBuilder = Callable[[str], Awaitable[FreshContext | str]]


def _expert_key(index: int, expert: dict[str, Any]) -> str:
    return f"e{index + 1:02d}-{safe_ref(str(expert['name']))}"


def _input_refs(plan: dict[str, Any]) -> set[str]:
    return {
        str(item["input_id"]) for item in plan["input_bundle"]["items"] if item["input_type"] in {"inline_text", "file"}
    }


def _retrieval_query(plan: dict[str, Any], expert: dict[str, Any]) -> str:
    """Build a diverse query only from hash-bound operator-visible material."""
    approved_urls = requested_urls(plan["input_bundle"])
    domain = str(expert.get("domain", "") or "").strip()
    lens = f"Research lens: {domain}" if domain else ""
    parts = [str(plan["question"]), lens, *approved_urls]
    normalized = "\n".join(part.strip() for part in parts if part.strip())
    return normalized[:4096]


def _empty_source_pack(query: str, error: str) -> dict[str, Any]:
    return {
        "schema_version": "deepr.source_pack.v1",
        "query": query,
        "generated_at": utc_now(),
        "mode": "deep",
        "search_backend": "none",
        "browser_backend": "none",
        "search_queries": [],
        "source_count": 0,
        "content_addressed_source_count": 0,
        "retrieved_source_count": 0,
        "generation_readiness": {
            "ready": False,
            "mode": "deep",
            "ready_source_count": 0,
            "required_source_count": 3,
            "retrieved_source_count": 0,
            "explicit_url_count": 0,
        },
        "errors": [error],
        "sources": [],
        "retrieval_candidates": [],
    }


def _default_context_builder(plan: dict[str, Any]) -> ContextBuilder:
    """Bind free retrieval limits to the hash-bound per-expert envelope."""
    base = deep_fresh_context_config()
    retrieval = plan["retrieval"]
    config = FreshContextConfig(
        max_search_results=base.max_search_results,
        max_fetches=int(retrieval["max_pages_per_expert"]),
        max_chars_per_source=base.max_chars_per_source,
        max_total_chars=base.max_total_chars,
        max_search_queries=int(retrieval["max_queries_per_expert"]),
        min_content_addressed_sources=base.min_content_addressed_sources,
        min_explicit_url_sources=base.min_explicit_url_sources,
    )
    return cast(ContextBuilder, make_free_deep_context_builder(config=config))


def _attempted_page_fetches(context: FreshContext) -> int:
    """Count browser attempts without treating search-only candidates as pages."""
    return sum(1 for source in context.sources if source.fetched or source.not_modified or bool(source.error))


def _persist_source_snapshots(
    runtime: InvestigationRuntime,
    source_pack: dict[str, Any],
    *,
    prefix: str,
) -> dict[str, Any]:
    packed = copy.deepcopy(source_pack)
    sources = packed.get("sources")
    if not isinstance(sources, list):
        packed["sources"] = []
        return packed
    for index, source in enumerate(sources, start=1):
        if not isinstance(source, dict):
            continue
        runtime.control_gate(after_dispatch=True)
        source["label"] = f"{prefix}-S{index}"
        content = str(source.pop("content", "") or "").strip()
        digest = str(source.get("content_hash", "") or "")
        if not content or sha256_bytes(content.encode("utf-8")) != digest:
            if content:
                source["snapshot_error"] = "content_hash_mismatch"
            continue
        reference = runtime.store.write_source_snapshot(
            runtime.run_id,
            content=content,
            content_sha256=digest,
            max_disk_bytes=runtime.bounds.max_disk_bytes,
        )
        source["snapshot_ref"] = reference["path"]
    return packed


def _source_catalog(source_packs: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], set[str]]:
    catalog: list[dict[str, Any]] = []
    refs: set[str] = set()
    for expert_key, source_pack in source_packs.items():
        for source in source_pack.get("sources", []) or []:
            if not isinstance(source, dict):
                continue
            reference = str(source.get("label", "") or "")
            if not reference:
                continue
            refs.add(reference)
            catalog.append(
                {
                    "ref": reference,
                    "expert_source_pack": expert_key,
                    "title": str(source.get("title", "") or ""),
                    "url": str(source.get("url", "") or ""),
                    "content_hash": str(source.get("content_hash", "") or ""),
                    "snapshot_ref": str(source.get("snapshot_ref", "") or ""),
                }
            )
    catalog.sort(key=lambda item: item["ref"])
    return catalog, refs


def _peer_packets(
    *,
    plan_sha256: str,
    target_name: str,
    positions: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    peers = [(name, position) for name, position in positions.items() if name != target_name]
    peers.sort(key=lambda item: sha256_json({"plan": plan_sha256, "target": target_name, "peer": item[0]}))
    packets: list[dict[str, Any]] = []
    alias_map: dict[str, str] = {}
    for index, (name, position) in enumerate(peers):
        alias = f"Peer {chr(ord('A') + index)}"
        alias_map[alias] = name
        packets.append(
            {
                "peer_alias": alias,
                "claims": position.get("claims", []),
                "assumptions": position.get("assumptions", []),
                "unknowns": position.get("unknowns", []),
                "strongest_alternative": position.get("strongest_alternative", ""),
                "null_hypothesis": position.get("null_hypothesis", ""),
                "perspective_candidates": position.get("perspective_candidates", []),
                "proposed_cruxes": position.get("proposed_cruxes", []),
            }
        )
    return packets, alias_map


class InvestigationExecutor:
    """Run a hash-bound local plan through finite, replayable phases."""

    def __init__(
        self,
        *,
        store: InvestigationStore,
        backend: ExpertChatBackend,
        context_builder: ContextBuilder | None = None,
    ) -> None:
        self.store = store
        self.backend = backend
        self.context_builder = context_builder

    async def run_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        validated = validate_plan(plan)
        self.store.create(validated)
        return await self.execute(str(validated["run_id"]))

    async def execute(self, run_id: str) -> dict[str, Any]:
        with self.store.execution_lock(run_id):
            current = self.store.load_state(run_id)
            try:
                current_state = RunState(str(current["state"]))
            except ValueError:
                current_state = RunState.FAILED
            if current_state in TERMINAL_STATES:
                return current
            runtime = InvestigationRuntime(self.store, run_id, self.backend)
            try:
                return await self._execute(runtime)
            except InvestigationPaused as exc:
                runtime.record_error(exc)
                return runtime.finish(RunState.PAUSED, phase=Phase(str(runtime.state["phase"])))
            except InvestigationCancelled as exc:
                runtime.record_error(exc)
                return runtime.finish(RunState.CANCELLED, phase=Phase(str(runtime.state["phase"])))
            except InvestigationBudgetExhausted as exc:
                runtime.record_error(exc)
                return runtime.finish(RunState.BUDGET_EXHAUSTED, phase=Phase(str(runtime.state["phase"])))
            except Exception as exc:
                runtime.record_error(exc)
                runtime.finish(RunState.FAILED, phase=Phase(str(runtime.state["phase"])))
                raise

    async def _execute(self, runtime: InvestigationRuntime) -> dict[str, Any]:
        plan = runtime.plan
        experts = list(plan["experts"])
        protocol = ProtocolMode(str(plan["protocol"]))
        learning = LearningMode(str(plan["learning"]))
        input_context_items = materialize_input_context(plan["input_bundle"])
        input_context = render_input_context(input_context_items)
        caller_refs = _input_refs(plan)
        context_builder = self.context_builder or _default_context_builder(plan)
        self._write_preflight(runtime, experts)
        charters, expert_keys = await self._run_charters(runtime, experts, input_context)
        source_packs = await self._run_research(runtime, experts, expert_keys, charters, context_builder)
        source_catalog, external_refs, source_evidence_context = self._evidence_contexts(
            experts,
            expert_keys,
            source_packs,
        )
        all_refs = caller_refs | external_refs
        checker_input_context = render_input_context(input_context_items, maximum=20_000)
        synthesis_input_context = render_input_context(input_context_items, maximum=12_000)
        positions = await self._run_positions(
            runtime,
            experts,
            expert_keys,
            charters,
            source_packs,
            input_context,
            caller_refs,
        )
        discussions = await self._run_discussions(runtime, experts, expert_keys, positions, all_refs, protocol)
        final_positions = await self._run_revisions(
            runtime,
            experts,
            expert_keys,
            charters,
            source_packs,
            input_context,
            positions,
            discussions,
            caller_refs,
            protocol,
        )
        position_list = [final_positions[str(expert["name"])] for expert in experts]
        check = await self._run_check(
            runtime,
            experts,
            position_list,
            source_catalog,
            checker_input_context,
            source_evidence_context,
            all_refs,
        )
        synthesis = await self._run_synthesis(
            runtime,
            experts,
            position_list,
            check,
            source_catalog,
            synthesis_input_context,
            source_evidence_context,
            all_refs,
        )
        learning_manifest = await self._run_learning(
            runtime,
            experts,
            expert_keys,
            source_packs,
            final_positions,
            check,
            learning,
        )
        return self._finish_result(
            runtime,
            experts,
            protocol,
            source_catalog,
            check,
            synthesis,
            learning_manifest,
        )

    @staticmethod
    def _write_preflight(runtime: InvestigationRuntime, experts: list[dict[str, Any]]) -> None:
        runtime.transition(Phase.PREFLIGHT)
        if runtime.artifact("preflight") is not None:
            return
        plan = runtime.plan
        preflight = {
            "schema_version": "deepr-investigation-preflight-v1",
            "kind": "deepr.expert.investigation_preflight",
            "run_id": runtime.run_id,
            "plan_sha256": plan["plan_sha256"],
            "input_bundle_sha256": plan["input_bundle"]["bundle_sha256"],
            "frozen_expert_count": len(experts),
            "capacity": plan["capacity"],
            "bounds": plan["bounds"],
            "model_calls": 0,
            "cost_usd": 0.0,
            "verified_at": utc_now(),
        }
        runtime.put_artifact("preflight", phase=Phase.PREFLIGHT, key="preflight", payload=preflight)

    @staticmethod
    async def _run_charters(
        runtime: InvestigationRuntime,
        experts: list[dict[str, Any]],
        input_context: str,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
        plan = runtime.plan
        runtime.transition(Phase.CHARTERS)
        charters: dict[str, dict[str, Any]] = {}
        expert_keys: dict[str, str] = {}
        for index, expert in enumerate(experts):
            expert_name = str(expert["name"])
            expert_key = _expert_key(index, expert)
            expert_keys[expert_name] = expert_key
            logical_key = f"charter:{expert_key}"
            charter = runtime.artifact(logical_key)
            if charter is None:
                raw = await runtime.complete(
                    charter_prompt(
                        question=str(plan["question"]),
                        expert=expert,
                        input_context=input_context,
                        requested_urls=requested_urls(plan["input_bundle"]),
                    )
                )
                charter = compile_charter(raw, expert_name=expert_name, question=str(plan["question"]))
                runtime.put_artifact(
                    logical_key,
                    phase=Phase.CHARTERS,
                    key=f"charter-{expert_key}",
                    payload=charter,
                )
            charters[expert_name] = charter
        return charters, expert_keys

    @staticmethod
    async def _run_research(
        runtime: InvestigationRuntime,
        experts: list[dict[str, Any]],
        expert_keys: dict[str, str],
        _charters: dict[str, dict[str, Any]],
        context_builder: ContextBuilder,
    ) -> dict[str, dict[str, Any]]:
        plan = runtime.plan
        runtime.transition(Phase.RESEARCH)
        source_packs: dict[str, dict[str, Any]] = {}
        for index, expert in enumerate(experts, start=1):
            expert_name = str(expert["name"])
            expert_key = expert_keys[expert_name]
            logical_key = f"source-pack:{expert_key}"
            source_pack = runtime.artifact(logical_key)
            if source_pack is None:
                query = _retrieval_query(plan, expert)
                reservation = runtime.reserve_retrieval(
                    expert_key,
                    search_queries=int(plan["retrieval"]["max_queries_per_expert"]),
                    page_fetches=int(plan["retrieval"]["max_pages_per_expert"]),
                )
                try:
                    context = await context_builder(query)
                except Exception as exc:
                    source_pack = _empty_source_pack(query, f"retrieval failed: {type(exc).__name__}: {exc}")
                else:
                    if isinstance(context, FreshContext):
                        runtime.settle_retrieval(
                            reservation,
                            actual_search_queries=len(context.search_queries),
                            actual_page_fetches=_attempted_page_fetches(context),
                        )
                        source_pack = dict(context.to_source_pack(include_content=True))
                    else:
                        runtime.settle_retrieval(reservation, actual_search_queries=0, actual_page_fetches=0)
                        source_pack = _empty_source_pack(query, "context builder returned unstructured text")
                source_pack = _persist_source_snapshots(runtime, source_pack, prefix=f"E{index:02d}")
                source_pack["expert_name"] = expert_name
                source_pack["expert_key"] = expert_key
                runtime.put_artifact(
                    logical_key,
                    phase=Phase.RESEARCH,
                    key=f"source-pack-{expert_key}",
                    payload=source_pack,
                )
            source_packs[expert_key] = source_pack
        return source_packs

    @staticmethod
    def _evidence_contexts(
        experts: list[dict[str, Any]],
        expert_keys: dict[str, str],
        source_packs: dict[str, dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], set[str], str]:
        source_catalog, external_refs = _source_catalog(source_packs)
        blocks: list[str] = []
        for index, expert in enumerate(experts, start=1):
            expert_name = str(expert["name"])
            rendered, _refs = render_source_pack(source_packs[expert_keys[expert_name]], prefix=f"E{index:02d}")
            blocks.append(f"Expert source pack: {expert_name}\n{rendered}")
        return source_catalog, external_refs, "\n\n".join(blocks)

    @staticmethod
    async def _run_positions(
        runtime: InvestigationRuntime,
        experts: list[dict[str, Any]],
        expert_keys: dict[str, str],
        charters: dict[str, dict[str, Any]],
        source_packs: dict[str, dict[str, Any]],
        input_context: str,
        caller_refs: set[str],
    ) -> dict[str, dict[str, Any]]:
        plan = runtime.plan
        runtime.transition(Phase.POSITIONS)
        positions: dict[str, dict[str, Any]] = {}
        for index, expert in enumerate(experts, start=1):
            expert_name = str(expert["name"])
            expert_key = expert_keys[expert_name]
            logical_key = f"position:{expert_key}"
            position = runtime.artifact(logical_key)
            if position is None:
                source_context, own_source_refs = render_source_pack(source_packs[expert_key], prefix=f"E{index:02d}")
                allowed = caller_refs | own_source_refs
                raw = await runtime.complete(
                    position_prompt(
                        question=str(plan["question"]),
                        expert=expert,
                        charter=charters[expert_name],
                        input_context=input_context,
                        source_context=source_context,
                        allowed_refs=allowed,
                    )
                )
                position = compile_position(raw, expert_name=expert_name, allowed_refs=allowed)
                runtime.put_artifact(
                    logical_key,
                    phase=Phase.POSITIONS,
                    key=f"position-{expert_key}",
                    payload=position,
                )
            positions[expert_name] = position
        return positions

    @staticmethod
    async def _run_discussions(
        runtime: InvestigationRuntime,
        experts: list[dict[str, Any]],
        expert_keys: dict[str, str],
        positions: dict[str, dict[str, Any]],
        all_refs: set[str],
        protocol: ProtocolMode,
    ) -> dict[str, dict[str, Any]]:
        if protocol is ProtocolMode.INDEPENDENT:
            return {}
        runtime.transition(Phase.DISCUSSION)
        discussions: dict[str, dict[str, Any]] = {}
        for expert in experts:
            expert_name = str(expert["name"])
            expert_key = expert_keys[expert_name]
            logical_key = f"discussion:{expert_key}"
            discussion = runtime.artifact(logical_key)
            if discussion is None:
                peer_packets, alias_map = _peer_packets(
                    plan_sha256=str(runtime.plan["plan_sha256"]),
                    target_name=expert_name,
                    positions=positions,
                )
                routing = {
                    "schema_version": "deepr-investigation-peer-routing-v1",
                    "kind": "deepr.expert.investigation_peer_routing",
                    "target_expert": expert_name,
                    "alias_map": alias_map,
                    "packet_sha256": sha256_json(peer_packets),
                    "identity_visible_to_target": False,
                }
                runtime.put_artifact(
                    f"peer-routing:{expert_key}",
                    phase=Phase.DISCUSSION,
                    key=f"peer-routing-{expert_key}",
                    payload=routing,
                )
                raw = await runtime.complete(
                    discussion_prompt(
                        question=str(runtime.plan["question"]),
                        expert=expert,
                        own_position=positions[expert_name],
                        blinded_peers=peer_packets,
                        allowed_refs=all_refs,
                    )
                )
                discussion = compile_discussion(
                    raw,
                    expert_name=expert_name,
                    allowed_aliases=set(alias_map),
                    allowed_refs=all_refs,
                )
                runtime.put_artifact(
                    logical_key,
                    phase=Phase.DISCUSSION,
                    key=f"discussion-{expert_key}",
                    payload=discussion,
                )
            discussions[expert_name] = discussion
        return discussions

    @staticmethod
    async def _run_revisions(
        runtime: InvestigationRuntime,
        experts: list[dict[str, Any]],
        expert_keys: dict[str, str],
        charters: dict[str, dict[str, Any]],
        source_packs: dict[str, dict[str, Any]],
        input_context: str,
        positions: dict[str, dict[str, Any]],
        discussions: dict[str, dict[str, Any]],
        caller_refs: set[str],
        protocol: ProtocolMode,
    ) -> dict[str, dict[str, Any]]:
        final_positions = dict(positions)
        if protocol is not ProtocolMode.DEEP:
            return final_positions
        runtime.transition(Phase.REVISIONS)
        for index, expert in enumerate(experts, start=1):
            expert_name = str(expert["name"])
            expert_key = expert_keys[expert_name]
            logical_key = f"revision:{expert_key}"
            revision = runtime.artifact(logical_key)
            if revision is None:
                source_context, own_refs = render_source_pack(source_packs[expert_key], prefix=f"E{index:02d}")
                allowed_refs = caller_refs | own_refs
                raw = await runtime.complete(
                    position_prompt(
                        question=str(runtime.plan["question"]),
                        expert=expert,
                        charter=charters[expert_name],
                        input_context=input_context,
                        source_context=source_context,
                        allowed_refs=allowed_refs,
                        operation="revision",
                        prior_position=positions[expert_name],
                        discussion=discussions[expert_name],
                    )
                )
                revision = compile_position(
                    raw,
                    expert_name=expert_name,
                    allowed_refs=allowed_refs,
                    phase="revision",
                )
                runtime.put_artifact(
                    logical_key,
                    phase=Phase.REVISIONS,
                    key=f"revision-{expert_key}",
                    payload=revision,
                )
            final_positions[expert_name] = revision
        return final_positions

    @staticmethod
    async def _run_check(
        runtime: InvestigationRuntime,
        experts: list[dict[str, Any]],
        positions: list[dict[str, Any]],
        source_catalog: list[dict[str, Any]],
        caller_input_context: str,
        source_evidence_context: str,
        all_refs: set[str],
    ) -> dict[str, Any]:
        runtime.transition(Phase.CHECK)
        check = runtime.artifact("check")
        if check is not None:
            return check
        expert_model = str(runtime.plan["capacity"]["model"])
        review_model = str(runtime.plan["capacity"].get("review_model", expert_model))
        independence = (
            "different_pinned_local_model_unvalidated_independence"
            if review_model != expert_model
            else "same_local_model_reduced_independence"
        )
        raw = await runtime.complete(
            checker_prompt(
                question=str(runtime.plan["question"]),
                positions=positions,
                source_catalog=source_catalog,
                caller_input_context=caller_input_context,
                source_evidence_context=source_evidence_context,
                allowed_refs=all_refs,
                model_independence=independence,
            )
        )
        check = compile_check(
            raw,
            allowed_experts={str(expert["name"]) for expert in experts},
            allowed_refs=all_refs,
            independence=independence,
            claim_lineage={
                (str(position["expert_name"]), str(claim["claim_id"])): str(claim["lineage_status"])
                for position in positions
                for claim in position.get("claims", [])
                if isinstance(claim, dict)
            },
            perspective_candidates={
                (str(position["expert_name"]), str(candidate["candidate_id"]))
                for position in positions
                for candidate in position.get("perspective_candidates", [])
                if isinstance(candidate, dict)
            },
        )
        runtime.put_artifact("check", phase=Phase.CHECK, key="independent-check", payload=check)
        return check

    @staticmethod
    async def _run_synthesis(
        runtime: InvestigationRuntime,
        experts: list[dict[str, Any]],
        positions: list[dict[str, Any]],
        check: dict[str, Any],
        source_catalog: list[dict[str, Any]],
        caller_input_context: str,
        source_evidence_context: str,
        all_refs: set[str],
    ) -> dict[str, Any]:
        runtime.transition(Phase.SYNTHESIS)
        synthesis = runtime.artifact("synthesis")
        if synthesis is not None:
            return synthesis
        expected_experts = [str(expert["name"]) for expert in experts]
        raw = await runtime.complete(
            synthesis_prompt(
                question=str(runtime.plan["question"]),
                positions=positions,
                check=check,
                expected_experts=expected_experts,
                source_catalog=source_catalog,
                caller_input_context=caller_input_context,
                source_evidence_context=source_evidence_context,
                allowed_refs=all_refs,
            )
        )
        synthesis = compile_result(
            raw,
            question=str(runtime.plan["question"]),
            allowed_refs=all_refs,
            expected_experts=expected_experts,
        )
        runtime.put_artifact("synthesis", phase=Phase.SYNTHESIS, key="synthesis", payload=synthesis)
        return synthesis

    @staticmethod
    async def _run_learning(
        runtime: InvestigationRuntime,
        experts: list[dict[str, Any]],
        expert_keys: dict[str, str],
        source_packs: dict[str, dict[str, Any]],
        positions: dict[str, dict[str, Any]],
        check: dict[str, Any],
        learning: LearningMode,
    ) -> dict[str, Any] | None:
        if learning is not LearningMode.STAGE:
            return None
        runtime.transition(Phase.LEARNING)
        manifest = runtime.artifact("learning:manifest")
        if manifest is not None:
            return manifest
        entries: list[dict[str, Any]] = []
        for expert in experts:
            expert_name = str(expert["name"])
            expert_key = expert_keys[expert_name]
            entry = await stage_expert_learning(
                runtime,
                expert=expert,
                expert_key=expert_key,
                source_pack=source_packs[expert_key],
            )
            perspective_key = f"learning:perspective-envelope:{expert_key}"
            perspective_envelope = runtime.artifact(perspective_key)
            position_key = f"revision:{expert_key}"
            if runtime.artifact(position_key) is None:
                position_key = f"position:{expert_key}"
            position_reference = runtime.artifact_reference(position_key) or {}
            check_reference = runtime.artifact_reference("check") or {}
            if perspective_envelope is None:
                perspective_envelope = build_perspective_graph_commit_envelope(
                    run_id=runtime.run_id,
                    expert_name=expert_name,
                    domain=str(expert.get("domain", "") or ""),
                    position=positions[expert_name],
                    check=check,
                    position_artifact=str(position_reference.get("path", "") or ""),
                    check_artifact=str(check_reference.get("path", "") or ""),
                )
                runtime.put_artifact(
                    perspective_key,
                    phase=Phase.LEARNING,
                    key=f"perspective-graph-commit-envelope-{expert_key}",
                    payload=perspective_envelope,
                )
            perspective_ready = int((perspective_envelope.get("summary", {}) or {}).get("ready_write_count", 0) or 0)
            entry.update(
                {
                    "perspective_status": str(
                        (perspective_envelope.get("summary", {}) or {}).get("status", "empty") or "empty"
                    ),
                    "perspective_ready_write_count": perspective_ready,
                    "perspective_graph_commit_envelope_artifact": str(
                        (runtime.artifact_reference(perspective_key) or {}).get("path", "") or ""
                    ),
                    "perspective_truth_verified": False,
                    "perspective_novelty_verified": False,
                    "perspective_human_reviewed": False,
                }
            )
            entries.append(entry)
        manifest = {
            "schema_version": LEARNING_MANIFEST_SCHEMA_VERSION,
            "kind": LEARNING_MANIFEST_KIND,
            "run_id": runtime.run_id,
            "entries": entries,
            "summary": {
                "expert_count": len(entries),
                "ready_write_count": sum(int(entry.get("ready_write_count", 0) or 0) for entry in entries),
                "automatic_verifier_accepted_count": sum(
                    1 for entry in entries if entry.get("automatic_verifier_accepted") is True
                ),
                "human_reviewed_count": 0,
                "expert_state_write_count": 0,
                "perspective_ready_write_count": sum(
                    int(entry.get("perspective_ready_write_count", 0) or 0) for entry in entries
                ),
                "total_staged_write_count": sum(
                    int(entry.get("ready_write_count", 0) or 0)
                    + int(entry.get("perspective_ready_write_count", 0) or 0)
                    for entry in entries
                ),
            },
            "contract": {
                "source_pack_evidence_only": True,
                "factual_belief_source_pack_evidence_only": True,
                "domain_relevance_required": True,
                "dialogue_is_evidence": False,
                "perspective_proposals_from_expert_positions": True,
                "perspective_proposals_are_factual_beliefs": False,
                "perspective_truth_or_novelty_verified": False,
                "writes_expert_state": False,
                "human_reviewed": False,
                "apply_requires_explicit_command": True,
            },
            "generated_at": utc_now(),
        }
        runtime.put_artifact(
            "learning:manifest",
            phase=Phase.LEARNING,
            key="learning-manifest",
            payload=manifest,
        )
        return manifest

    @staticmethod
    def _finish_result(
        runtime: InvestigationRuntime,
        experts: list[dict[str, Any]],
        protocol: ProtocolMode,
        source_catalog: list[dict[str, Any]],
        check: dict[str, Any],
        synthesis: dict[str, Any],
        learning_manifest: dict[str, Any] | None,
    ) -> dict[str, Any]:
        runtime.transition(Phase.COMPLETE)
        result = runtime.artifact("result")
        if result is not None:
            return runtime.finish(RunState.COMPLETED)
        plan = runtime.plan
        result = copy.deepcopy(synthesis)
        result.pop("content_sha256", None)
        result.update(
            {
                "run_id": runtime.run_id,
                "plan_sha256": plan["plan_sha256"],
                "protocol": protocol.value,
                "experts": [str(expert["name"]) for expert in experts],
                "source_catalog": source_catalog,
                "artifact_refs": {
                    "check": runtime.artifact_reference("check"),
                    "synthesis": runtime.artifact_reference("synthesis"),
                    "learning_manifest": runtime.artifact_reference("learning:manifest"),
                },
                "capacity": {
                    "class": "local",
                    "model": plan["capacity"]["model"],
                    "review_model": plan["capacity"].get("review_model", plan["capacity"]["model"]),
                    "context_window_tokens": plan["capacity"].get(
                        "context_window_tokens", DEFAULT_LOCAL_CONTEXT_WINDOW_TOKENS
                    ),
                    "review_context_window_tokens": plan["capacity"].get(
                        "review_context_window_tokens",
                        plan["capacity"].get("context_window_tokens", DEFAULT_LOCAL_CONTEXT_WINDOW_TOKENS),
                    ),
                    "fallback": "none",
                    "usage": copy.deepcopy(runtime.state["usage"]),
                    "cost_usd": 0.0,
                },
                "learning": learning_manifest,
                "contract": {
                    "evidence_first": True,
                    "consensus_is_verification": False,
                    "checker_independence": check["independence"],
                    "writes_expert_state": False,
                    "human_reviewed": False,
                    "semantic_review_status": "unreviewed",
                    "quality_claim": False,
                },
            }
        )
        result["content_sha256"] = sha256_json(result)
        runtime.put_artifact("result", phase=Phase.COMPLETE, key="result", payload=result)
        return runtime.finish(RunState.COMPLETED)


__all__ = ["ContextBuilder", "InvestigationExecutor"]
