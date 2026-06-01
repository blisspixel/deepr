# Changelog

All notable changes to Deepr will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.12.0] - 2026-06-01

### Added
- **Expert health-check (Phase 4, knowledge maintenance loop).**
  ``deepr expert health-check NAME`` runs a read-side, cost-$0 audit of an
  expert's knowledge state - freshness, belief contradictions (free heuristic,
  no LLM), claims missing source provenance, beliefs decayed below the
  confidence threshold, the open-gap backlog, and documents ingested but never
  synthesized. Output is two-phase: findings (each with a severity) plus a
  recommended-action menu where every corrective step carries its CLI command,
  estimated cost, and the approval tier that would gate it. The audit only
  proposes; it never mutates or spends. Exposed as the ``deepr_expert_health_check``
  MCP tool (SENSITIVE: blocked in read-only, confirm in standard/extended).
- **Expert absorb (Phase 4, output-to-knowledge feedback loop).**
  ``deepr expert absorb NAME REPORT_ID`` promotes a completed research report
  into an expert's permanent beliefs, verification-gated: one extraction call
  turns the report into atomic, report-grounded candidate claims; weak claims
  and any that contradict existing beliefs are rejected (the contradiction gate
  reuses the same free heuristic as health-check); survivors are integrated via
  ``BeliefStore.add_belief`` (deduped) with the report id as provenance.
  ``--dry-run`` previews without writing. Exposed as the ``deepr_expert_absorb``
  MCP tool (WRITE: mutating + paid, gated accordingly). MCP surface now 21 tools.
- **Native Distillr integration (first-party instrument, Phase 2b #2).** When
  the ``distill-mcp`` binary is on ``PATH`` (``pip install distillr``), Deepr
  auto-discovers and mounts the distillr MCP server with no user
  configuration, alongside recon. Built-in skill (``deepr/skills/distillr/``)
  exposes ``query_library`` (free corpus search), ``discover``,
  ``ingest_papers`` / ``ingest_youtube`` / ``ingest_sites``, and ``refresh``
  (delta re-ingest, the freshness engine behind "stay current").
- **Corpus absorption.** ``KnowledgeAbsorber.categorize_distillr_response``
  parses distillr's ingestion/query output into academic findings that cite
  the corpus synthesis artifact for provenance, integrating only the first
  non-empty result set to avoid double counting.
- **Budget-capped, approval-gated ingestion.** Unlike free recon, the distillr
  profile carries a per-call ``budget_limit`` (default $2) enforced by
  ``BudgetPropagator``; only the free ``query_library`` auto-approves, and
  ``progress: true`` reuses the existing MCP ``ProgressNotifier`` for long runs.
- **Native Primr integration (first-party instrument, Phase 2b #3).** When the
  ``primr-mcp`` binary is on ``PATH`` (``pip install primr``), Deepr
  auto-discovers and mounts the primr MCP server. Built-in skill
  (``deepr/skills/primr/``) exposes ``estimate_run`` (free pre-flight),
  ``quick_lookup`` (fast recon+scrape context), ``research_company``,
  ``generate_strategy``, ``batch_analyze``, and ``check_jobs``. Primr is the
  heaviest instrument (35-50 min, paid), so every cost-incurring tool is
  approval-gated, the per-call ``budget_limit`` is $5, the timeout is 60m, and
  long runs stream progress and resume via the existing task-durability layer.
- **Multi-category company absorption.**
  ``KnowledgeAbsorber.categorize_primr_response`` is the first parser to emit
  across categories: the recon pre-flight becomes infrastructure facts (higher
  confidence) while the brief, hiring signals, and strategic initiatives become
  strategic knowledge, each citing the report artifact for provenance.
  This completes Phase 2b (recon + distillr + primr all integrated).

- **Engineering standards foundation (Phase E).** New continuous
  code-quality track in the roadmap with firm, blocking gate targets. This
  release lands the foundation:
  - **Python baseline raised to 3.12** (``requires-python >=3.12``); CI matrix
    now 3.12 / 3.13 (blocking) + 3.14 (non-blocking until optional-dep wheels
    are confirmed). 3.9/3.10 (EOL / test-collection failures) and 3.11
    (supported only to Oct 2027) dropped; a 3.12 floor holds security coverage
    to Oct 2028. ``ruff target-version`` is ``py312``.
  - **``uv`` adopted as the canonical toolchain**: ``uv.lock`` and
    ``.python-version`` committed for reproducible dev/CI/container
    environments; CI installs via ``uv pip install``. setuptools remains the
    build backend so ``pip install`` keeps working downstream.
  - **Syntax modernized to the 3.12 baseline** via Ruff autofix: PEP 604
    unions (``X | None``), ``datetime.UTC``, exception/import aliases
    (~1.6k mechanical, test-verified changes). ``ruff target-version`` is now
    ``py312``.
  - **mypy** wired into CI as a non-blocking baseline (``[tool.mypy]`` config
    added; baseline 314 errors / 76 files), ratcheting toward a blocking
    ``--strict`` gate. **Strict islands shipped:** ``deepr/core`` (44 kernel
    errors) and ``deepr/providers`` (82 errors across all adapters - including
    realigning grok's vector-store stubs to the base provider contract) are now
    ``mypy --strict``-clean and enforced by a **blocking**
    ``mypy --strict deepr/core deepr/providers deepr/mcp`` CI step. ``deepr/mcp``
    was driven strict-clean and **flipped into the blocking gate this release**
    (the third strict island); the migration also fixed a latent bug where the
    expert-info MCP tools used dict-subscript access on ``ExpertProfile`` objects.
  - **pip-audit** wired into CI and already **blocking**: the baseline it
    surfaced was cleared immediately (see Security), so a new known
    vulnerability now fails the build.
  - **Dependabot** enabled (pip + github-actions + npm, weekly).
  - **Branch coverage** enabled (stricter than line coverage): the gate is now
    ``fail_under = 78`` over branch coverage (was 80 line), ratcheting toward 95.
  - **C901 complexity cap** (max-complexity 10) surfaced as an advisory CI
    signal alongside the S-rules; 134 over-cap functions tracked for refactor.
  - **Mutation testing** (mutmut) wired as a scheduled / on-demand non-blocking
    workflow over the kernel (budget, cost ledger, cost safety), with config in
    ``[tool.mutmut]``.
  - **SBOM** (hash-pinned dependency bill of materials via ``uv export``)
    published as a CI build artifact.
  - **Python floor raised again to 3.12** (from the 3.11 set earlier this
    cycle): 3.11 is supported only to Oct 2027; a 3.12 floor holds security
    coverage to Oct 2028. ``ruff target-version = "py312"``, CI matrix 3.12/3.13
    + 3.14 (non-blocking), Dockerfile base ``python:3.12-slim``.

### Security
- **flask-cors bumped 4.x -> 6.x**, clearing CVE-2024-6839, CVE-2024-6844, and
  CVE-2024-6866 (all fixed in 6.0.0). The old ``<5.0.0`` pin held the project
  on the vulnerable 4.0.2; the new pip-audit CI gate caught it on its first
  run. Deepr's usage (``CORS(app, origins=...)``) is unchanged across the bump.

### Changed
- ``ConfigLoader.load()`` first-party auto-discovery generalized from
  recon-only to a table (recon, distillr, primr); user-defined profiles still
  take precedence over any auto-discovered one of the same name.
- ``scripts/check_docs_consistency.py`` (CI) now also guards the built-in
  skill count against ``deepr/skills/``.

### Fixed
- **Runaway knowledge-graph edge growth (multi-GB `edges.json`).**
  `EdgeBuilder.build_edges` created a co-occurrence edge for every pair of
  concepts in a section (O(C^2)), and the concept extractor emits a concept for
  every 2-5 word n-gram, so a single large section generated millions of edges;
  with `min_pmi=0.0` nothing was pruned. One expert's `edges.json` reached
  26 GB (51k concepts). The builder now pairs only the top
  `max_concepts_per_section` (default 40) concepts - headings/key-phrases first
  - and `KnowledgeGraph` enforces a hard `max_edges` safety cap (default 1M)
  that drops further new edges with a one-time warning while still merging
  existing ones. Re-index affected experts to rebuild a healthy graph.
- Stale recon **integration** tests (not run by CI, which executes only
  ``tests/unit/``) updated to the shipped ``RECON_PROFILE_TEMPLATE`` tool
  names and modern ``asyncio.run`` (the deprecated ``get_event_loop`` form
  raised on Python 3.11+). Count-based config-loader unit tests are now
  isolated from host-installed first-party binaries.
- **``expert learn --resume`` crashed** - ``do_resume()`` built
  ``LearningTopic`` without the required ``description``/``priority`` fields and
  ``LearningCurriculum`` without ``generated_at``, a guaranteed ``TypeError``
  whenever resume ran. All required fields are now passed.
- **``expert refresh`` crashed on a never-refreshed expert** - the stats display
  called ``.strftime()`` on ``last_knowledge_refresh`` (``datetime | None``)
  unconditionally. Guarded; shows "never" when unset.
- **``expert absorb`` crashed on malformed model output** - an extraction
  response of ``{"claims": null}`` (or a non-list value) hit ``None[:n]``.
  Non-list ``claims`` now degrades to zero candidates.
- **Date-dependent test flake** - ``test_reset_if_needed_daily`` set
  ``last_reset`` to "yesterday", so on the 1st of any month the monthly bucket
  also reset (correct production behaviour), failing CI on those dates. Pinned
  to a mocked mid-month ``now``.
- Replaced the remaining deprecated ``datetime.utcnow()`` calls across the test
  suite with ``datetime.now(UTC)`` (production code was already clean).

---

## [2.11.0] - 2026-05-27

First-party native integration of Recon, the passive domain intelligence
tool, plus a follow-on hardening / version-centralization sweep.

### Added
- **Native Recon integration (first-party instrument).** When the
  ``recon`` binary is on ``PATH`` (``pip install recon-tool``), Deepr now
  auto-discovers and mounts the recon MCP server with no user
  configuration. Built-in skill (``deepr/skills/recon/``) covers the real
  shipped tool surface: ``lookup_tenant``, ``analyze_posture``,
  ``assess_exposure``, ``find_hardening_gaps``, ``chain_lookup``,
  ``get_posteriors``, ``explain_dag``.
- **Autonomous recon probe in expert chat.** When an expert is in
  ``agentic`` mode and the user message contains a domain, Deepr fires
  ``lookup_tenant`` at cost $0 and surfaces high-confidence
  infrastructure findings (services, related domains, tenant/provider,
  email-security posture) directly into the system prompt for that turn.
  ``KnowledgeAbsorber.categorize_recon_response`` is a specialized parser
  that emits >= 0.8 confidence findings from the real recon response
  shape.
- **`deepr doctor` Native Instruments check** reports whether recon is
  available and suggests ``pip install -U recon-tool`` when missing.
- **CI advisory security lint** via ``ruff check --select S`` (Bandit-
  equivalent) runs on every push with ``continue-on-error: true`` so
  findings show up in the log without retroactively gating on legacy
  ``try/except/pass`` and partial-executable-path findings.

### Changed
- **Single source of truth for version.** ``AgentCardGenerator``,
  ``MCPClient`` clientInfo, ``SkillPackager`` default, and the web
  ``/health`` endpoint now import ``deepr.__version__`` instead of
  hardcoded ``"2.10.0"`` / ``"2.9.0"`` strings (and matching tests
  updated to assert against ``DEEPR_VERSION``). This closes a recurring
  silent-drift bug class.
- **ExpertSkillWrapper gap-tool map** updated for the real recon tool
  names (``lookup_tenant``, ``analyze_posture``, ``chain_lookup``) with
  legacy ``domain_lookup`` retained as a fallback for user-defined
  skills.

### Security
- **`doc_reviewer.scan_docs` symlink/traversal hardening.** Rejects
  symlinks, uses ``validate_path`` + realpath containment, and skips
  files larger than 2 MB before any content is read.
- **`config.load_config` no longer leaks provider API keys** in its
  return dict; callers needing real keys must go through the provider
  factory or environment variables. Removes an accidental cross-context
  key disclosure path.
- **`bin/deepr-api`** documents that ``DEEPR_ALLOW_PUBLIC_BIND=1`` is
  acknowledgement of a real risk (data disclosure + provider-spend
  abuse), not a routine convenience flag.
- **Documentation hardening** in ``deepr/api/app.py`` and
  ``deepr/web/app.py`` makes the local-dev-only nature of the
  unauthenticated default explicit.

### Fixed
- **MCP / async exception handling.** ``MCPClientProxy.call_tool`` and
  ``SkillExecutor`` now re-raise ``CancelledError``, ``SystemExit``, and
  ``KeyboardInterrupt`` instead of swallowing them into a generic
  ``{"error": ...}``. Remaining broad ``except`` blocks now carry an
  intent-explaining comment.
- **`assert` replaced with explicit logging + safe return** in
  ``StdioTransport._read_loop``, ``LiveShimmerStatus._run``, and
  ``ExpertSkillWrapper.execute`` (asserts are stripped under ``python
  -O``; the previous code could fall off the end with ``None`` in
  pathological cases).
- **`AzureFoundryProvider.__del__`** clean-up swallow is now explicitly
  documented as intentional (must not raise during interpreter
  shutdown).
- **`ConfigLoader.load`** no longer raises ``FileNotFoundError`` when
  the integrations config is absent; it returns auto-discovered profiles
  (recon if installed) and an empty list otherwise.

### Tests
- Patch ``discover_recon_profile`` in two config-loader tests so they
  do not depend on whether the ``recon`` binary happens to be installed
  on the dev / CI machine.
- ``test_a2a_integration`` and ``test_packager`` now assert against
  ``DEEPR_VERSION`` so future version bumps don't break tests.
- Replace ``assert False`` with ``raise AssertionError`` (ruff B011).
- Remove unused locals across A2A / MCP / services coverage tests.
- ``tests/integration/test_grok_search.py`` moved to
  ``grok_search_demo.py`` — it was a manual demo, not a pytest test, so
  it no longer triggers collection errors when ``xai_sdk`` is missing.

### Roadmap
- Phase 2b first-party instrument sequencing made explicit:
  Recon (1) -> Distillr (2) -> Primr (3). Recon is now the pilot
  delivered.

---

## [2.10.3] - 2026-05-17

Five-round bug-hunt sweep covering cost/budget, async/concurrency, storage
durability, provider correctness, auth, skill subsystem, CLI flag validation,
deploy templates, MCP client + transports, frontend accessibility, and
documentation accuracy. ~360 fixes across ~190 files. All 4,341+ unit tests
pass. Coverage threshold raised from 60% to 75%.

### Security
- **Skill executor RCE closed.** Skill ``module``/``function`` fields are
  now resolved with ``importlib.util.spec_from_file_location`` against a
  path inside the skill directory; ``module: os, function: system`` is
  refused. Function names are validated as public identifiers; dunders
  blocked. ``sys.path`` is never modified.
- **Skill MCP subprocess allowlist.** ``server_command`` must be on a
  per-skill allowlist (built-ins only by default; opt in via
  ``DEEPR_SKILL_ALLOW_MCP_COMMANDS=*``). MCP subprocesses no longer
  inherit the full host environment — only ``server.env`` keys, plus a
  minimal ``PATH``/``HOME`` set.
- **Skill path traversal closed.** ``prompt_file`` rejects absolute paths
  and any path that resolves outside the skill directory.
  ``SkillManager(expert_name=...)`` sanitises the expert name through
  ``deepr.utils.security.sanitize_name``.
- **Webhook server fail-closed.** Refuses anonymous POSTs when
  ``DEEPR_WEBHOOK_SECRET`` is unset; refuses to start on a non-loopback
  bind without a secret. Adds a 1 MiB body cap.
- **A2A server bearer-auth gate.** ``POST /tasks`` and
  ``POST /tasks/{id}/cancel`` now require ``DEEPR_A2A_TOKEN`` when set.
  Refuses non-loopback bind without a token unless
  ``DEEPR_A2A_ALLOW_PUBLIC=1``. 1 MiB body cap, header / body read
  timeouts.
- **MCP HTTP transport bearer over plain HTTP** now emits a warning at
  subscribe time when the URL is non-loopback. Body cap set explicitly.
- **`deepr templates show/delete/use`** sanitise the template name —
  ``../`` no longer reads or deletes arbitrary files.
- **MCP confirmation gate** strips the ``_approved`` kwarg before
  dispatch so handlers without that parameter no longer crash with
  ``TypeError``.
- **Shared cloud `security.py`** uses ``hmac.compare_digest`` with
  ``TypeError`` catch (was raw ``==``).
- **`InstructionSigner` convenience helpers** now share a singleton so
  ``sign_instruction`` / ``verify_instruction`` actually round-trip when
  ``DEEPR_SIGNING_KEY`` is unset.
- **Azure**: legacy unauthenticated ``deploy/azure/function_app/``
  directory removed; cancel_job uses Cosmos ETag (``If-Match``) with
  retry loop; documents now write a top-level ``job_id`` field matching
  the container's ``/job_id`` partition key.
- **GCP**: cancel_job wrapped in a Firestore transactional decorator.

### Cost correctness
- **`CostSafetyManager.ABSOLUTE_MAX_PER_OPERATION`** + ``ABSOLUTE_MAX_DAILY``
  + ``ABSOLUTE_MAX_MONTHLY`` class attributes added (round-2 patch fixed
  a swallowed AttributeError; this exposes the constants the MCP server
  + CLI reference).
- **Reservation pattern.** ``cost_safety.check_and_reserve()`` returns
  a reservation_id; ``record_cost(reservation_id=...)`` settles the
  reservation. N-way parallel fan-out (council, task planner, batch
  executor) can no longer over-commit against the daily cap.
- **`services/research_api.py`** ``cost_limit`` semantics fixed: when
  the model's estimate exceeds the caller's cap we now reject upfront
  instead of treating the cap as the spend.
- **`services/batch_executor.py`** + **`services/research_api.py`** now
  call ``record_cost`` after successful submission so daily / monthly
  spend doesn't drift below reality.
- **`services/batch_auto.py`** ``execute_batch`` enforces a
  ``cost_safety.check_operation`` gate against the total routing-cost
  estimate (previously a 100-query batch could spend $100+ unchecked).
- **`experts/chat.py`** ``_deep_research`` uses ``get_cost_estimate``
  from the registry (was hardcoded ``$0.20`` for a ``$2.00`` model).
  Multi-round tool loops re-check ``cost_session.can_proceed`` between
  rounds. ``_quick_lookup`` gets a pre-flight check and registry-driven
  pricing; cached-token discount honoured.
- **`mcp/client/pool.py`** clamps server-reported cost so a malicious
  server returning ``cost=0`` cannot bypass spend tracking and ``-1``
  cannot credit budget back.
- **`web/app.py`** ``POST /api/jobs`` enforces ``CostController.check_cost_limit``;
  ``/api/experts/council`` clamps caller budget against
  ``ABSOLUTE_MAX_PER_OPERATION``; ``/api/experts/chat`` clamps against
  daily remaining.
- **`core/costs.py`** ``record_cost`` now calls ``reset_if_needed()``
  first so a job recorded just after UTC midnight lands in the new
  day's bucket.

### Correctness
- **`agents/orchestrator.py`** no longer drops subtasks beyond
  ``len(workers)``; workers are picked round-robin via
  ``idx % len(workers)``. Output keys sort numerically so ``worker-10``
  lands after ``worker-2``.
- **`observability/routing_log.py`** ``get_events`` returns the LAST N
  rows, not the FIRST N — every analytics query in this module was
  silently analysing the oldest history slice.
- **`observability/circuit_breaker.py`** OPEN → HALF_OPEN transition
  now holds ``self._lock`` so concurrent callers can't both fire a
  probe.
- **`observability/traces.py`** ``TraceContext.get_current`` uses a
  ``contextvars.ContextVar`` instead of ``threading.local`` so async
  coroutines on the same thread see their own context.
- **`research_agent/poller.py`** treats ``cancelled``, ``canceled``,
  ``expired`` as terminal; adds exponential backoff (capped 5 min) on
  persistent errors. ``queued`` is a recognised no-op.
- **`core/research.py`** ``_temporal_trackers`` is popped on
  ``cancel_job`` and ``process_completion`` so long-running orchestrators
  don't leak one entry per job.
- **`core/company_research.py`** constructor + ``submit_research`` call
  now use the real ``ResearchOrchestrator`` API. Previously every call
  crashed at init.
- **`providers/anthropic_provider.py`** for-else on the multi-turn
  tool loop now surfaces a truncation note when ``max_turns`` is hit
  without convergence; usage is accumulated across turns and ``get_status``
  returns the stored response (previously every call recorded $0).
- **`providers/registry.py`** ``get_token_pricing`` normalises Grok's
  dot/hyphen aliases (was an 80% undercharge on multi-agent); cached
  token discount applied; partial-match candidates sorted by length so
  ``flash-lite`` doesn't match ``flash``.
- **`providers/openai_provider.py`** rate-limit fallback uses
  ``dataclasses.replace`` instead of mutating the caller's request.
- **`providers/gemini_provider.py`** reads ``chunk.usage_metadata``
  for real token counts (including thinking tokens) instead of
  ``len(text)//4`` estimates.
- **`providers/azure_provider.py`** adds retries on transient errors;
  defends against ``response.model = None``.

### Durability
- **`deepr/utils/atomic_io.py`** introduced (``atomic_write_bytes``,
  ``atomic_write_text``, ``atomic_write_json``, ``append_jsonl_durable``).
  ~17 storage call sites migrated.
- **Cost ledger** appends now ``flush() + os.fsync()`` so the last
  event survives a crash.
- **`queue/local_queue.py`** runs in WAL mode; ledger event is written
  BEFORE the SQLite commit so a crash between the two can't leave a
  job marked completed without a billing row. Partial UNIQUE index on
  ``provider_job_id`` blocks double-billing on submit-retry races.
- **`mcp/state/persistence.py`** ``save_job`` is atomic via
  ``with self._conn:`` — all three INSERTs commit together.

### Async / lifecycle
- **`mcp/transport/stdio.py`** ``stop()`` drains in-flight handler
  tasks with a 5-second grace; ``_in_flight`` initialised in
  ``__init__`` rather than lazily in the read loop.
- **`mcp/transport/http.py`** ``HttpClient.subscribe()`` cancels any
  prior subscription task before creating a new one (was leaking
  zombie SSE streams). ``_handle_post`` returns a generic 500 instead
  of echoing exception text. SSE subscriber dict overwrite now signals
  the old handler to exit cleanly.
- **`mcp/client/base.py`** spawns a background ``_drain_stderr`` so
  a chatty MCP server doesn't fill the ~64 KB pipe buffer and hang.
  Reconnect backoff has full jitter. Timeout in ``_send_request``
  forces a reconnect to prevent JSON-RPC framing corruption.
- **`mcp/state/async_dispatcher.py`** waits for dependencies BEFORE
  acquiring the concurrency semaphore — fixes a deadlock on chains
  longer than ``max_concurrent``.
- **`experts/task_planner.py`** parallel ``_run_step`` coroutines
  serialise through an ``asyncio.Lock`` on the shared session;
  ``ExpertChatSession`` is no longer concurrently mutated.
- **`a2a/server.py`** writer cleanup uses ``await writer.wait_closed()``.
- **`a2a/task_manager.py`** bounded eviction of terminal tasks.
- **`mcp/security/output_verification.py`** chain head primed from DB
  on init (was breaking chains on every restart).

### CLI
- **`deepr templates`** sanitises template name via ``sanitize_name``.
- **`deepr jobs cancel`** routes by ``job.provider``, not the global
  config default.
- **`deepr interactive`** maps model names to providers correctly
  (was routing Grok / Claude to ``gemini``).
- **`--cost-limit`** accepts ``FloatRange(min=0.0)``; **``--phases``**
  accepts ``IntRange(1, 10)``; **``--perspectives``** accepts
  ``IntRange(1, 12)`` — runaway-spend bypasses closed.
- **`deepr team`** uses ``web_search_preview`` for OpenAI providers
  (was using the unknown name ``web_search``).
- **`deepr search --keyword-only`** is now respected (precedence bug
  ``not keyword_only or True`` evaluated to ``True``).
- **`deepr costs limits`** now persists daily / monthly limits to
  ``cost_data.json`` and validates ``>= 0``.

### Round 4 — auto-mode, emitter, agent budgets, frontend safety
- **`research/auto_mode.py`** fallback model selection no longer crashes
  when the configured model is missing from the registry; falls back to
  a sane default.
- **`observability/metadata_emitter.py`** per-job temporal tracker
  replaces the shared field — fixes the race where parallel jobs
  clobbered each other's elapsed-time accounting.
- **`agents/budget.py`** ``AgentBudget.check`` propagates parent
  remaining downward correctly when a worker spawns a sub-worker so
  bounded fan-out no longer over-spends its slice.
- **Frontend safety**: result-detail citation rendering no longer
  crashes on malformed URLs (``new URL`` wrapped in try/catch);
  budget sliders debounced (was firing mutations on every pixel drag);
  cost-intelligence utilisation handles zero-denominator division.

### Round 5 — cost gates, MCP stability, frontend a11y
- **LLM cost-safety gates** added to seven previously uncovered call
  sites that could otherwise drive unbounded spend on long inputs:
  ``experts/citation_validator``, ``gap_discovery``, ``conflict_resolver``,
  ``curriculum``, ``map_reduce`` (map + reduce), ``multi_pass``
  (extract/cross-ref/synthesise), ``synthesis`` (synthesize + extract),
  ``task_planner`` (decompose + synth), ``embedding_cache`` (per-doc +
  query).
- **`experts/skills/executor.py`** MCPClientProxy now drains stderr in a
  background task so a chatty MCP subprocess can't fill the pipe buffer
  and deadlock.
- **`experts/skills/definition.py`** trigger-regex compilation protected
  from ReDoS — pattern length capped at 256 chars, nested-quantifier
  backtracking patterns rejected.
- **`mcp/client/pool.py`** terminal ``ProgressEvent`` now emitted on
  tool completion (the ``_progress_notifier`` was stored but never
  triggered — subscribers saw zero events).
- **`storage/findings_store.py`** in-memory index mutations now guarded
  by ``threading.RLock``.
- **`cli/commands/research.py`** ``cancel`` merges nested
  ``asyncio.run()`` calls into a single event loop so lookup + cancel
  share the same loop.
- **Frontend a11y**: htmlFor/id pairing on settings + research-studio
  inputs; aria-label on search and slider widgets; aria-valuemin/max/now
  on cost-intelligence slider; responsive sidebar hiding
  (trace-explorer ``<lg``, expert-profile ``<md``).
- **Dead frontend code removed**: ``use-local-storage`` /
  ``use-media-query`` hooks, ``activity-feed`` /
  ``memory-indicator`` components.

### Documentation
- This file. CHANGELOG was empty for v2.10.3 (3 commits' worth of work
  had no release notes).
- ``--agentic`` flag references removed — flag doesn't exist; agentic
  is the default, ``--no-research`` disables.
- ``deploy/azure/README.md`` + ``deploy.sh`` corrected to ``functions/``
  (the ``function_app/`` directory was removed).
- MCP tool count: 16 → 18 in ``README.md`` and ``mcp/README.md``.
- Test count: 4300+ → 4341+ in ``README.md``, ``ROADMAP.md``,
  ``SECURITY.md``, ``docs/VISION.md``.
- Coverage threshold: 60% → 75% in ``CONTRIBUTING.md`` and ``ROADMAP.md``.

---

## [2.10.2] - 2026-05-13

Security and hardening patch. No breaking changes for default operation;
adds explicit opt-out flags for previously implicit unsafe behavior.

### Security
- **Web dashboard refuses unsafe Werkzeug binds.** `python -m deepr.web.app`
  now refuses to start the Werkzeug development server on any non-loopback
  host, drops `allow_unsafe_werkzeug=True`, and requires either
  `DEEPR_API_KEY` or `DEEPR_ALLOW_PUBLIC_BIND=1` to bind beyond `127.0.0.1`.
- **MCP confirmation gate enforced.** Tools that require confirmation in
  the current research mode now return `CONFIRMATION_REQUIRED` instead of
  being dispatched silently. Callers must pass `arguments._approved=true`
  or set `DEEPR_MCP_AUTO_APPROVE=1` to opt back into the legacy
  log-and-continue behavior.
- **MCP tool allowlist covers the real surface.** Registered
  `deepr_research`, `deepr_agentic_research`, `deepr_cancel_job`,
  `deepr_expert_manifest`, `deepr_rank_gaps`, `deepr_query_expert`, and
  six read-only Deepr tools with explicit categories so allowlist
  decisions reflect the actual exposed tools instead of treating each as
  "unknown".
- **Bearer-token compare handles non-ASCII headers.** Both
  `deepr/api/app.py` and `deepr/web/app.py` now catch the `TypeError`
  that `hmac.compare_digest` raises for non-ASCII `str` inputs and
  return `401 Unauthorized` instead of letting it escape into the
  generic 500 handler.
- **`POST /api/experts` validates string fields.** `description` and
  `domain` must be strings and are truncated to 1000/200 characters,
  preventing persisted objects/arrays from tripping the React Expert
  Hub error boundary across all clients.
- **`POST /api/jobs` (modular API) enforces guards before provider call.**
  Added 1 MB body cap, 50K prompt-length cap, model allowlist, and
  pre-submit `CostController.check_cost_limit()` check.
- **`/api/demo/clear` gated behind `DEEPR_DEMO=1`** plus an explicit
  `{"confirm": "DELETE_ALL_DATA"}` body. Returns 403/400 otherwise.
- **`/api/benchmarks/estimate` cannot fan out subprocesses.** Per-route
  6/min rate limit, module-level execution lock, and a 2-minute
  per-(tier, quick, no_judge) result cache so concurrent estimates
  serialize on a single Python child.
- **Portrait endpoint records cost and is rate-limited.** Cooldown +
  provider allowlist already shipped; v2.10.2 adds a 5/hour route
  limiter and writes generated portraits to the canonical cost ledger
  via `CostSafetyManager.record_cost`.
- **Citation-validation GET caches results.** Per-expert mtime-keyed
  10-minute TTL cache prevents dashboard polling from re-fanning out
  paid LLM validation batches.
- **AWS worker reads cancellation from DynamoDB.** Worker now consults
  the API's `JobsTable` instead of an S3 `metadata.json` the API never
  creates; status/cost/completion updates flow back via `UpdateItem`,
  and reports are written under `results/{job_id}/report.md` so the API
  `get_result` endpoint can serve them.
- **Grok multi-agent budget pre-flight.** `AgentBudget.check()` runs
  before each worker chat-completion call and synthesis is skipped when
  the operation budget has been exhausted.
- **Removed dead `deepr/api/routes/` submodule.** The never-imported
  modular routes (job/result/cost/config blueprints) shipped with stale
  `check_job_limit`/`to_dict()` calls and would have been an
  unauthenticated provider-spend surface if wired in.

### Changed
- **GPT-5.2 chat sessions cost at registry rates.** `ExpertChatSession`
  now computes token cost via a `_chat_token_cost(usage, model)` helper
  that pulls input/output prices from the model registry instead of
  hard-coding the legacy GPT-5 $1.25/$10 per-1M rates. GPT-5.2 sessions
  accumulate at the correct $1.75/$14 per-1M.
- **Gemini Deep Research priced from the registry.** `gemini-deep-research`
  and `deep-research` aliases now resolve to
  `deep-research-pro-preview-12-2025` ($2.50/job) in both
  `get_cost_estimate()` and `MODEL_COST_ESTIMATES`, so orchestrator and
  MCP budget guards no longer approve $1+ jobs against the $0.20
  unknown-model default.
- **Gemini 3.x Pro tiered pricing.** `_calculate_cost` applies the 2x
  multiplier for prompts above 200K input tokens; `get_cost_estimate()`
  accepts an optional `input_tokens` hint so pre-flight budget checks
  reflect the tier.
- **Consensus engine Gemini cost.** Bumped provider budget estimate to
  $0.20 (Gemini 3.1 Pro Preview base) and replaced the flat $0.05
  placeholder with token-accurate cost from `usage_metadata` including
  the tiered multiplier.
- `CostDashboard.record` and buffered cost recording now emit canonical
  ledger events.
- `DEEPR_COST_TRACKING_STRICT=1` enables fail-fast behavior when ledger
  writes fail in cost dashboard/safety paths.

### Added
- Canonical append-only cost ledger at `data/costs/cost_ledger.jsonl`
  with idempotency-key support (`deepr/observability/cost_ledger.py`).
- `deepr costs doctor` command for zero-cost tracker integrity checks
  (ledger writable + drift vs dashboard totals).
- Queue cost persistence records positive cost deltas with idempotency
  metadata to avoid duplicate attribution.
- `CostSafetyManager.record_cost` writes canonical ledger events for
  non-queue spend paths (used by the portrait endpoint).
- Rich animated ASCII startup banner with cross-platform fallbacks
  (compact/narrow terminals, legacy Windows, non-UTF output).
- Startup banner env controls: `DEEPR_BANNER_MODE=off|static|light|full`
  and `DEEPR_BANNER_DURATION=<seconds>`.

---
## [2.9.1] - 2026-02-16

### Added
- `deepr web` CLI command to start the web dashboard (replaces `python deepr/web/app.py`)
  - `--host`, `--port` / `-p`, `--debug` options
  - Graceful error if web dependencies are not installed

### Changed
- Documentation updated to use `deepr web` instead of `python deepr/web/app.py`

---

## [2.9.0] - 2026-02-16

### Added

**Agentic Expert Chat**
- Streaming expert chat over WebSocket (Socket.IO) with real-time token delivery, tool call visibility, and follow-up suggestions
- 27 slash commands organized by category (Mode, Session, Reasoning, Control, Management, Utility) with `/` prefix in web and `\` prefix in CLI
- Command registry (`deepr/experts/commands.py`) with shared parsing for CLI and web, alias resolution, and category grouping
- 4 chat modes: ASK (quick answers, KB-only tools), RESEARCH (default, all tools), ADVISE (consulting-style structured recommendations), FOCUS (always-on chain-of-thought reasoning)
- Mode switching via `/ask`, `/research`, `/advise`, `/focus` commands; mode badge displayed in chat header
- Visible reasoning: ThoughtStream callbacks pipe real-time thinking steps to frontend via `chat_thought` WebSocket events; collapsible ThinkingPanel shows planning, search, evidence, and decision steps with confidence indicators
- Context compaction: `/compact` summarizes earlier messages while preserving recent context, enabling longer sessions without token budget exhaustion; auto-suggest banner after 30+ messages or 80K+ estimated tokens
- Human-in-the-loop approval flows: `ApprovalManager` with three tiers (auto-approve, notify, confirm) based on operation cost and budget; inline confirmation dialog in chat for expensive operations
- Expert council: `/council` command queries multiple experts in parallel on cross-domain questions, synthesizes agreements and disagreements; also available as `POST /api/experts/council` REST endpoint
- Hierarchical task decomposition: `/plan` command breaks complex queries into subtasks with dependency graph, executes independent subtasks in parallel with live progress per step
- Memory commands: `/remember` pins facts to session, `/forget` removes them, `/memories` lists all; pinned memories included in system prompt
- Session management: `/clear` resets chat, `/new` starts fresh session, `/save` and `/load` for named sessions, `/export` to markdown or JSON
- Reasoning commands: `/trace` shows full reasoning chain, `/why` explains last decision, `/decisions` lists all decisions, `/thinking on/off` toggles verbose reasoning display
- Control commands: `/model` switches model, `/tools` lists available tools, `/effort` adjusts reasoning depth, `/budget` shows remaining budget, `/status` shows session stats
- Conversations API: `GET/POST /api/experts/<name>/conversations` for listing and loading past chat sessions
- Expert portrait generation: AI-generated SVG portraits based on expert domain and description, cached per expert, displayed in profile header
- Web slash command autocomplete: floating menu triggered by `/` in chat input, grouped by category, keyboard navigable
- Frontend chat components: `ThinkingPanel`, `ConfirmDialog`, `CompactBanner`, `PlanDisplay`, `MemoryIndicator`, `SlashCommandMenu`, `MessageActions`, `ToolCallBlock`

**Expert Skills System**
- Domain-specific capability packages that give experts unique tools and reasoning
- `SkillDefinition` format: `skill.yaml` manifest + `prompt.md` overlay + Python/MCP tools
- Three-tier storage: built-in (`deepr/skills/`), user global (`~/.deepr/skills/`), expert-local (`data/experts/{name}/skills/`)
- `SkillManager`: discovery across all tiers, keyword/regex trigger matching, domain-based suggestion
- `SkillExecutor`: Python tool execution via importlib, MCP bridging via JSON-RPC stdio proxy
- Progressive disclosure in expert chat: skill summaries always in system prompt, full prompt loaded only on activation
- Tool namespacing (`skill_name__tool_name`) prevents conflicts across skills
- Budget tracking per skill with cost tier estimates (free/low/medium/high)
- Profile schema migration v2→v3 adding `installed_skills` field (backward compatible)
- 4 built-in skills shipping in `deepr/skills/`:
  - `web-search-enhanced`: structured data extraction from research text
  - `code-analysis`: dependency audit + cyclomatic complexity analysis
  - `financial-data`: financial ratio calculations (P/E, P/B, debt-to-equity, ROE, margins)
  - `data-visualization`: markdown table generation + ASCII bar charts
- CLI: `deepr skill list/install/remove/create/info` command group
- CLI: `deepr expert run-skill` for direct tool execution
- Web API: `GET/POST/DELETE /api/experts/<name>/skills/<skill>`, `GET /api/skills`
- MCP: `deepr_list_skills` and `deepr_install_skill` tools
- Frontend: Skills tab (6th tab) in Expert Profile with install/remove buttons
- 124 new unit tests for skills definition, manager, and executor

**Expert Intelligence**
- Multi-provider consensus gap-filling (`--consensus` flag)
- Semantic citation validation (`SupportClass` enum, `--validate-citations` flag)
- Multi-pass gap-filling pipeline (`--deep` flag)
- Automated gap discovery via claim clustering (`deepr expert discover-gaps`)
- Conflict resolution agent with multi-provider adjudication (`deepr expert resolve-conflicts`)

### Changed
- Shared constants module (`deepr/experts/constants.py`) centralizes model names, tool identifiers, and budget fractions across council, task planner, command handlers, and WebSocket events
- `_run_in_thread()` helper in WebSocket events replaces duplicated asyncio event loop boilerplate
- Frontend: extracted reusable `SkillCard` and `EmptyState` components, reducing expert-profile.tsx bundle by 1.5KB
- Frontend: replaced 4 inline empty state patterns and 2 inline skill card renderings with shared components

### Fixed
- Removed unused imports `AppConfig` and `create_provider` in `experts.py` discover-gaps command
- Removed unused import `KnowledgeSynthesizer` and unused variable `do_validate` in `app.py` fill-gaps endpoint
- ThinkingPanel showed "Thought for " with empty duration when timestamps were identical (now shows "<1s")
- Compact toast showed "undefined messages" when backend omitted count (added fallback)
- Chat auto-scroll: `userScrolledRef` was never set to true (added `onScroll` handler)
- Duplicate React keys in active tool call list (key now includes `startedAt` timestamp)
- Chat mode was not sent to backend `startChat()` (added mode parameter to WebSocket emit)
- Unsafe `(data as any).mode` cast in chat complete handler replaced with proper typed field
- Dead `setChatInput(fu)` in follow-up handler removed (was immediately overwritten)
- Clipboard copy in message actions now has try/catch for environments where `navigator.clipboard` is unavailable
- Confirm dialog cost display uses `formatCurrency()` for consistent formatting
- Council synthesis missing newline separators between expert perspectives
- Task planner result truncation was slicing a list instead of truncating the joined string
- Removed unused `_PROVIDERS` constant in portraits module
- Removed redundant alias entries in command handlers (registry already resolves aliases)
- Moved lazy imports (`uuid`, `os`, `AsyncOpenAI`) to top level in approval and council modules

---

## [2.8.1] - 2026-02-14

### Added

**Models & Benchmarks Page**
- New web page (`/models`) with model registry browser showing all registered models grouped by provider
- Benchmark results viewer with quality rankings by tier (chat/news/research), quality bar charts, and per-task-type radar charts
- Run benchmarks from the UI with tier, quick/full, judge toggle, and budget controls
- Cost estimation (dry-run) before starting a benchmark run
- Benchmark history file selector to load and compare different runs
- Routing configuration display showing current auto-mode preferences
- Provider key status indicators (configured vs not set)
- Backend APIs: `GET /api/benchmarks`, `GET /api/benchmarks/latest`, `GET /api/benchmarks/<filename>`, `POST /api/benchmarks/start`, `POST /api/benchmarks/estimate`, `GET /api/benchmarks/status`, `GET /api/benchmarks/routing-preferences`
- Model registry API: `GET /api/registry`

**Help Page**
- New web page (`/help`) with API key setup guide linking to all provider consoles
- CLI quick reference with common commands
- Model tier explanations (research, news, chat) with strengths and cost guidance
- "When to use Deepr" section comparing against single-vendor tools
- Free tier callouts for providers that offer free API access

**Demo Data Endpoint**
- `POST /api/demo/load` backend endpoint that creates sample experts and research jobs
- "Load Demo Data" button in Settings page Environment section
- Populates the UI with sample data for exploring the dashboard without a running research pipeline

**UX Improvements**
- Cost Intelligence accuracy disclaimer banner (costs are Deepr-internal estimates, check provider billing consoles)
- Standardized error states across all 10+ pages: muted icon, "Unable to load [thing]", consistent backend-down messaging, retry buttons
- Loading skeleton on Cost Intelligence page (was showing $0 values during load)
- Expert Profile tabs overflow scroll on mobile (5 tabs: Chat, Claims, Gaps, Decisions, History)
- Overview empty state no longer references CLI commands — links to web-native budget controls instead
- Expert Hub error state copy improvement
- `deepr config set` now supports CLI UX aliases:
  - `cli.animations` -> `DEEPR_ANIMATIONS` (`off|light|full`)
  - `cli.branding` -> `DEEPR_BRANDING` (`off|on|auto`)
  - Unknown `cli.*` keys now fail with explicit validation errors

### Fixed
- Removed dead code: `api/activity.ts`, `api/traces.ts`, `components/shared/stat-card.tsx` (never imported)
- Added `p-6` padding to Help page wrapper (missing from all other pages' pattern)
- Export dropdown in Result Detail now closes on Escape key press
- "Submit Research" → "New Research" button text consistency in Results Library
- Unsafe type assertion in Expert Profile history query replaced with proper `ExpertHistoryEvent` interface
- Gemini provider import hardening:
  - provider initialization now degrades safely when `google-genai` is present but incompatible
  - clear runtime errors are retained for unavailable Gemini client operations
  - prevents unrelated command/test breakage from optional SDK import failures

**Background Job Polling + WebSocket Push**
- Flask-SocketIO initialization with `cors_allowed_origins="*"` and threading async mode
- Background poller thread that checks PROCESSING jobs every 15 seconds via provider API
- WebSocket events: `job_created` on submit, `job_completed`/`job_failed` on poller detection
- `to_dict()` method on `ResearchJob` dataclass (enum, datetime, Path serialization)
- `POST /api/jobs/cleanup-stale` endpoint to mark stuck/orphaned jobs as failed
- `socketio.run()` replaces `app.run()` for WebSocket support
- Frontend already handled all events via `use-websocket.ts` — now actually connected

**Web Dashboard UX Overhaul**
- Skeleton loading states: `CardGridSkeleton`, `DetailSkeleton`, `FormSkeleton`, `DashboardSkeleton` replacing all spinner patterns
- Honest progress phases: replaced fake time-based 6-phase progress with 3 status-based phases (Queued/Processing/Complete)
- Standardized all form controls to shadcn/ui components (Input, Select, Button) across research-studio, expert-hub, results-library, expert-profile
- Copy-to-clipboard button on result-detail page with toast feedback
- Cmd+Enter / Ctrl+Enter keyboard shortcut to submit research from textarea
- Drag-and-drop file upload on research studio with visual feedback and file type filtering
- Pagination on results library (12 per page, page controls, total count)
- Mobile hamburger navigation via Sheet component (sidebar hidden on small screens)
- FOUC prevention: critical CSS inlined in index.html
- Skip-to-content link for keyboard/screen-reader accessibility
- Settings page: Environment info card showing provider, queue, storage, API key status
- Research Live completed state: enriched with prompt text, 4-stat grid (cost, tokens, completed date, model), content preview with markdown stripping

### Fixed
- Timezone naive/aware datetime comparison errors across 10+ locations in app.py (`_ensure_utc()` helper)
- JSX unicode escape `\u21B5` rendering as literal text in keyboard hint (moved to JS expression)
- Flask serving stale asset hashes when restarted before rebuild
- Results API sort crashing on naive datetime comparison
- Activity feed sort crashing on naive datetime comparison

---

## [2.8.0] - 2026-02-04

### Added

**Provider Intelligence (5.1, 5.3)**
- Latency percentiles (p50, p95, p99) in `ProviderMetrics` for performance analysis
- Success rate tracking by task type (research, chat, synthesis, planning)
- `deepr providers benchmark --history` command to view historical benchmark data
- `deepr providers benchmark --json` for machine-readable output
- Exploration vs exploitation in provider routing (10% exploration rate, configurable)
- Auto-disable failing providers (>50% failure rate, 1hr cooldown)
- `deepr providers status` shows auto-disabled providers with cooldown info

**Advanced Context (6.4, 6.5)**
- Temporal knowledge tracking wired into `ResearchOrchestrator`
- `--temporal` flag in `deepr research trace` shows findings/hypothesis timeline
- `--lineage` flag in `deepr research trace` shows context flow visualization (tree view)
- Context chaining via `ContextChainer` for phase-to-phase handoff
- Temporal data export in trace files

**Web Dashboard Overhaul**
- Rebuilt frontend with React 18, Vite, Tailwind CSS 3.4, and Radix UI (shadcn/ui pattern) component library
- 10 pages with code-split lazy loading via React.lazy and Suspense
- New pages: Overview (activity feed, system health), Research Studio (mode selector, model picker), Research Live (WebSocket progress), Result Detail (markdown viewer, citation sidebar, export), Expert Hub (list, stats, knowledge gaps), Expert Profile (chat, gaps, history), Cost Intelligence (charts, budget sliders, anomaly detection), Trace Explorer (execution spans, timing, cost)
- WebSocket integration for real-time job status updates (Socket.io client connected in AppShell)
- Command palette (Ctrl+K) for quick navigation across all pages
- Light/dark/system theme support via Zustand store
- Toast notifications via Sonner for all user-facing actions
- Recharts for cost trends, model breakdown, and utilization charts
- Fixed: division by zero in cost utilization calculations
- Fixed: unsafe URL parsing in citation display
- Fixed: budget sliders firing mutations on every pixel drag (debounced)
- Fixed: expert profile "Research this" button was not wired
- Fixed: research studio mode selector was ignored in submit payload
- Fixed: citation sidebar invisible on mobile viewports
- Removed dead code: unused type files, legacy pages, stale constants, unused components

**Expert System**
- `deepr expert plan` command to preview a learning curriculum without creating an expert or spending money
- Outputs as Rich table (default), JSON (`--json`), CSV (`--csv`), or prompts only (`-q`)
- Supports `--budget`, `--topics`, and `--no-discovery` options

**Expert & Decision Formalization (Phase 5)**
- Canonical types in `core/contracts.py`: `Source`, `Claim`, `Gap`, `DecisionRecord`, `ExpertManifest` with full serialization (`to_dict()`/`from_dict()`)
- `TrustClass` enum (primary, secondary, tertiary, self_generated) and `DecisionType` enum (routing, stop, pivot, budget, belief_revision, gap_fill, conflict_resolution, source_selection)
- `gap_scorer.py` with EV/cost ranking: `score_gap()` and `rank_gaps()` for rational gap prioritization
- Adapter methods: `Belief.to_claim()`, `KnowledgeGap.to_gap()` on existing classes for backward compatibility
- `ExpertProfile.get_manifest()` composes claims, scored gaps, and decision records into a typed snapshot
- `ThoughtStream.record_decision()` creates structured `DecisionRecord` objects alongside existing thought logging
- `--explain` flag now shows decision table (type, decision, confidence, cost impact) in CLI
- Web: Expert Profile page gains Claims tab, Decisions tab, and scored Gaps tab with EV/cost badges
- Web: Trace Explorer gains collapsible decision sidebar for the current job
- Web API: `GET /api/experts/<name>/manifest`, `/claims`, `/decisions` endpoints
- MCP: `deepr_expert_manifest` and `deepr_rank_gaps` tools for agent consumption
- 69 new unit tests (contracts, gap scorer, adapters)

**Real-Time Progress (7.3)**
- `ResearchProgressTracker` for live progress updates during research
- `--progress` flag in `deepr research wait` shows phase tracking with progress bar
- Phase detection (queued → initializing → searching → analyzing → synthesizing → finalizing)
- Partial results streaming when provider supports it
- Customizable poll intervals via `--poll-interval`

**Output Improvements (7.6)**
- `print_truncated()` utility for long output with "use --full to see all"
- `make_hyperlink()` and `print_report_link()` for clickable links in supported terminals

### Changed

- `ProviderMetrics.record_success()` and `record_failure()` now accept optional `task_type` parameter
- `AutonomousProviderRouter.record_result()` now accepts optional `task_type` parameter
- `AutonomousProviderRouter.select_provider()` now filters auto-disabled providers and adds exploration
- `get_status()` includes latency percentiles and task type stats per provider
- Enhanced providers CLI with historical data display and JSON export
- `MetadataEmitter.save_trace()` now includes temporal knowledge data when tracker is set
- Removed deprecated `run single` and `run campaign` commands (use `research` instead)

---

## [2.7.0] - 2026-02-04

### Added

**Context Discovery (6.1-6.3)**
- `deepr search query "topic"` command with semantic + keyword search across prior research
- `deepr search index` to index reports with embeddings (text-embedding-3-small)
- `deepr search stats` to view index statistics
- Automatic related research detection on `deepr research submit`
- `--context <job-id>` flag to include prior research as context
- `--no-context-discovery` flag to skip automatic detection
- Stale context warnings (>30 days old)
- Context truncation for token budget management
- Job ID prefix matching (can use `--context abc123` instead of full UUID)

**Observability Improvements (4.2, 4.4, 4.5)**
- Instrumented `core/research.py` with spans for submit, completion, cancel operations
- Instrumented `experts/chat.py` with spans for tool calls and message handling
- Cost attribution per span with token counts
- ThoughtStream decision summary generation (`generate_decision_summary()`, `get_why_summary()`)
- Research quality metrics: `EntropyStoppingCriteria`, `InformationGainTracker`, `QualityMetrics`
- Temporal knowledge tracking with `TemporalKnowledgeTracker`

**Code Quality**
- Configuration consolidation: single `Settings` class in `core/settings.py`
- ExpertProfile refactoring with composed managers (`budget_manager.py`, `activity_tracker.py`)
- 300+ new tests (3100+ total)

### Changed

- Interactive mode (`deepr` with no args) now shows model picker with cost estimates
- Improved test stability with faster hypothesis strategies

### Fixed

- Flaky hypothesis test `test_episode_tags_preserved` (42+ second generation time)
- Windows console Unicode encoding for ThoughtStream summaries

---

## [2.6.0] - 2026-02-03

### Added

**Documentation Overhaul**
- Rewrote README to better communicate value proposition for enterprise users (cloud architects, CIOs)
- Added "MCP + Skills" section highlighting research infrastructure for AI agents
- New workflow example: Claude Code → query expert → fill knowledge gaps → continue with accurate info
- Emphasized expert system differentiation: self-aware, self-improving, persistent, portable
- Enterprise-focused examples: competitive intelligence, due diligence at scale, institutional knowledge retention
- Updated decision table and "What You Can Do" section with AI agent capabilities first

**CLI Trace Flags (4.1)**
- `--explain` flag on `deepr research` and `deepr run focus` shows task hierarchy with model/cost reasoning
- `--timeline` flag renders Rich table with offset, task, status, duration, cost per phase
- `--full-trace` flag dumps complete trace JSON to `data/traces/{job_id}_trace.json`
- `TraceFlags` dataclass wired through CLI command decorators, backward compatible

**Output Modes (7.1)**
- `OutputMode` enum: MINIMAL (default), VERBOSE, JSON, QUIET
- `OutputContext` and `OutputFormatter` for consistent output across commands
- `@output_options` decorator adds `--verbose`, `--json`, `--quiet` to commands
- Conflicting flags rejected with clear error messages

**Gemini Deep Research Agent (5.4)**
- Native Gemini Deep Research support via Google Interactions API (`client.interactions.create()`)
- Dual-mode `GeminiProvider`: deep research agent for async research, `generate_content` for regular queries
- Model detection routes `deep-research` models to Interactions API automatically
- File Search Store integration for document grounding (`client.file_search_stores.create()`)
- Citation URL resolution for Google grounding redirect URLs
- Adaptive polling intervals: 5s (first 60s), 10s (60-300s), 20s (300s+)
- Experimental API warning suppression for stable operation
- Added `gemini/deep-research` to model capabilities registry
- 19 new tests covering deep research submission, status polling, file stores, citations, and adaptive polling

**Auto-Fallback on Provider Failures (5.2)**
- `AutonomousProviderRouter` wired into `_run_single()` in `cli/commands/run.py`
- Retry with fallback: timeout retries once then falls back, rate limit falls back immediately, auth error skips provider
- Max 3 fallback attempts before failure
- `_classify_provider_error()` bridges provider errors to core error hierarchy
- Vector store graceful degradation when falling back to non-OpenAI providers
- Fallback events emitted to trace and shown in `--explain` output
- `--no-fallback` flag on `focus`, `single`, `docs`, `run_alias`, `research` commands

**Cost Attribution Dashboard (4.3)**
- `deepr costs breakdown --period` flag (today, week, month, all) replaces `--days`
- `deepr costs timeline` command with ASCII bar chart, anomaly detection (>2x average), `--weekly` aggregation
- `deepr costs expert "Name"` subcommand shows per-expert cost breakdown, budget utilization, per-operation costs
- `CostAggregator.get_entries_by_expert()` and `get_expert_breakdown()` helpers
- Cost metadata (`total_cost`, `cost_by_model`) stored in `reports/{job_id}/metadata.json`

**Docker and Deployment**
- Dockerfile with Python 3.11-slim, non-root user (UID 1000), healthcheck
- `.dockerignore` reducing build context from 168MB to ~2MB
- `docker-compose.yml` with bridge network, resource limits (512MB, 1 CPU)

**Cloud Deployment Templates (10.1)**
- AWS SAM/CloudFormation template (`deploy/aws/`) with Lambda API, SQS queue, Fargate worker, DynamoDB, S3
- Azure Bicep template (`deploy/azure/`) with Functions, Queue Storage, Container Apps, Cosmos DB, Blob Storage
- GCP Terraform template (`deploy/gcp/`) with Cloud Functions, Pub/Sub, Cloud Run, Firestore, Cloud Storage
- Shared API library (`deploy/shared/deepr_api_common/`) with validation, security headers, response utilities
- API key authentication via Authorization Bearer token and X-Api-Key header
- CORS preflight OPTIONS handling on all endpoints
- Security headers (HSTS, X-Frame-Options, X-Content-Type-Options, Cache-Control)
- 90-day TTL on job documents for automatic cleanup (DynamoDB, Firestore, Cosmos DB)
- Input validation with sanitization (prompt length, model validation, UUID format)
- Detailed deployment documentation in `deploy/README.md`

**CI and Code Quality Tooling**
- GitHub Actions CI workflow: lint (ruff) + unit tests on push to `main` and PRs, Python 3.11/3.12 matrix
- `.pre-commit-config.yaml` with ruff (lint+format), trailing-whitespace, end-of-file-fixer, check-yaml, check-added-large-files, debug-statements
- `[tool.coverage]` in `pyproject.toml`: source/omit config, 60% minimum threshold, show_missing
- `[tool.ruff]` configuration in `pyproject.toml`
- `CONTRIBUTING.md` with setup, dev workflow, code style, testing, and guidelines
- CI enforces coverage minimum (`--cov-fail-under=60`) via `pytest-cov`
- `pytest-cov` added to `[project.optional-dependencies] dev`

### Fixed
- Fixed `pyproject.toml` URLs pointing to wrong GitHub organization
- Moved `test_conversation_memory.py` from unit to integration tests (was loading 4.3GB knowledge graph)
- Fixed model registry tests referencing `gpt-5` instead of `gpt-5.2`
- Fixed staleness urgency test expecting wrong value for missing cutoff date
- Fixed skill frontmatter token count test (limit bumped from 200 to 300 after metadata growth)
- Fixed flaky Hypothesis test `test_negation_detected_as_contradiction` (negation words in generated inputs + deadline exceeded on cold init)
- Fixed flaky Hypothesis test `test_normalize_produces_absolute_path` (drive-relative paths like `H:0` misidentified as absolute on Windows)

### Changed
- Test suite grew from 1300 to 2820+ tests
- Unified all version strings to 2.6.0 across package, CLI, API, and user-agent
- Replaced 47 `print()` calls in 13 library modules with structured `logging` (lazy `%s` formatting)
- Consolidated model pricing into single registry source of truth (`deepr/providers/registry.py`); removed hardcoded pricing from `base.py`, `research.py`, and provider modules
- Tightened exception handling in core, providers, and MCP server (bare `except Exception` replaced with `openai.OpenAIError`, `GenaiAPIError`, `DeeprError`, `OSError`, etc.)
- Tightened exception handling in storage and services: `storage/local.py` (5 catches → `OSError`), `storage/blob.py` (7 catches → `AzureError`), `core/jobs.py` (4 catches → `json.JSONDecodeError`/`KeyError`/`TypeError`/`ValueError`), `utils/scrape/fetcher.py` (1 catch → `requests.RequestException`/`json.JSONDecodeError`/`KeyError`/`ValueError`)
- Split monolithic `cli/commands/semantic.py` (3,318 lines) into `cli/commands/semantic/` package: `research.py` (research/learn/team/check commands), `artifacts.py` (make/agentic commands), `experts.py` (expert subcommands). Backward-compatible re-exports in `__init__.py`
- Removed `sys.path.insert()` hack in MCP server; uses standard package imports
- Removed 4 DEBUG `print()` statements left in production code (`semantic.py`)
- Fixed 3 bare `except:` catches with specific exception types (`prep.py`, `web/app.py`)
- Single-sourced version string: 5 modules now import `__version__` from `deepr/__init__.py` instead of hardcoding
- Replaced last `sys.path.insert()` in MCP server (skills loading) with `importlib.util.spec_from_file_location()`
- Converted remaining `print()` in `formatting/normalize.py` and `formatting/converters.py` to structured logging
- Dockerfile uses `pip install --no-cache-dir .` instead of editable install

- Removed redundant `black` from pre-commit hooks (ruff-format covers formatting) and `[tool.black]` from `pyproject.toml`
- Replaced 10 stub TODO comments in API routes with explanatory comments noting CLI-managed features
- Cleaned up API route stubs in `config.py`, `jobs.py`, `cost.py`, `results.py`

### Removed
- Deleted dead legacy CLI module (`deepr/cli.py`, 350 lines) shadowed by `deepr/cli/` package
- Deleted `setup.py` (fully redundant with `pyproject.toml`)

## [2.5.0] - 2026-01-15

### Added

**MCP Advanced Patterns Implementation**
- Added Dynamic Tool Discovery with BM25/vector search in `deepr/mcp/search/registry.py`
- Added Resource Subscriptions for event-driven async monitoring in `deepr/mcp/state/subscriptions.py`
- Added Human-in-the-Loop Elicitation for cost governance in `deepr/mcp/state/elicitation.py`
- Added Sandboxed Execution for isolated research contexts in `deepr/mcp/state/sandbox.py`
- Added JobManager for background task coordination in `deepr/mcp/state/job_manager.py`
- Added ResourceHandler for MCP resource protocol in `deepr/mcp/state/resource_handler.py`
- Added ExpertResources for expert profile/beliefs/gaps resources in `deepr/mcp/state/expert_resources.py`

**Transport Layer**
- Added Stdio transport for local process communication in `deepr/mcp/transport/stdio.py`
- Added Streamable HTTP transport for cloud deployment in `deepr/mcp/transport/http.py`
- StdioTransport ensures research data never leaves local process tree
- StreamingHttpTransport supports SSE for server-to-client notifications
- HttpClient for connecting to remote MCP servers

**Agent Trajectory Evaluation**
- Added TrajectoryMetrics for tracking agent performance in `deepr/mcp/evaluation/metrics.py`
- Tracks trajectory efficiency (steps vs optimal golden path)
- Tracks citation accuracy (beliefs with cited sources)
- Tracks hallucination rate (invented parameters not in schema)
- Tracks context economy (tokens per task)
- MetricsTracker for aggregating metrics across sessions

**MCP Server Architecture**
- Job pattern for async research: `deepr_research()` returns immediately, poll with `deepr_check_status()`
- SQLite persistence for job state across server restarts
- Reports exposed as MCP Resources (`deepr://reports/{job_id}/final.md`, `summary.json`, etc.)
- Progress notifications via subscription manager
- Structured error responses with `ToolError` dataclass (error_code, retry_hint, fallback_suggestion)
- Trace ID propagation for end-to-end debugging

**Claude Skill Infrastructure**
- Created `skills/deepr-research/` directory following Claude Skill conventions
- Added SKILL.md with activation keywords and progressive disclosure
- Added reference documents for research modes, expert system, cost guidance, prompt patterns, troubleshooting, and MCP patterns
- Added scripts for research decision classification and result formatting
- Added templates for research report output
- LLM-optimized tool descriptions with usage hints, negative guidance, example invocations
- Prompt primitives: `deep_research_task`, `expert_consultation`, `comparative_analysis`
- Install scripts (`install.sh`, `install.ps1`) with env var checking
- `deepr_status` health check tool

**Security Hardening**
- SSRF protection: blocks requests to private/internal IPs, optional domain allowlist
- Path traversal protection via `PathValidator` in sandbox module
- MCP Sampling primitives for human-in-the-loop (`SamplingRequest`, `SamplingResponse`)

**Multi-Runtime Configuration**
- Config templates for OpenClaw, Claude Desktop, Cursor, VS Code
- Docker variant config with volume mounts
- Per-runtime setup guides in `mcp/README.md`

**Claude-Specific Optimizations**
- Chain of Thought guidance prepended to research tool descriptions
- Lazy loading for large reports (summary + resource URI, configurable threshold)

**Elicitation System**
- ElicitationHandler for structured user input requests via JSON-RPC
- BudgetDecision enum with APPROVE_OVERRIDE, OPTIMIZE_FOR_COST, ABORT options
- CostOptimizer for dynamic model switching when optimizing for cost
- Budget limit triggers that pause jobs and request user decisions
- JSON Schema support for structured elicitation responses

**Sandbox System**
- SandboxManager for isolated execution contexts
- PathValidator with path traversal attack prevention
- SandboxConfig for configurable isolation settings
- Filesystem isolation with strict working directory enforcement
- Report synthesis and merge for extracting results from sandboxed contexts

**Test Coverage**
- 302 tests passing across MCP and skill modules
- 34 tests for transport layer (stdio and HTTP)
- 34 tests for trajectory metrics
- 37 tests for elicitation module
- 36 tests for sandbox module
- Property-based tests using Hypothesis for core skill logic

## [2.3.0] - 2025-11-15

### Added

**Always-On Prompt Refinement**
- Added `DEEPR_AUTO_REFINE` configuration option in .env
- When enabled, automatically applies prompt refinement to all research submissions
- No need to specify `--refine-prompt` flag each time
- Provides seamless best practices for all queries

**Campaign Pause/Resume Controls**
- Added `deepr prep pause` command to pause active research campaigns
- Added `deepr prep resume` command to resume paused campaigns
- Execute command now checks pause status before running
- Enables mid-campaign intervention for human oversight
- Supports both specific plan IDs and most recent campaign

**Persistent Vector Store Management**
- Added `deepr vector create` command to create reusable vector stores
- Added `deepr vector list` command to list all vector stores
- Added `deepr vector info` command to show vector store details
- Added `deepr vector delete` command to remove vector stores
- Added `--vector-store` flag to `deepr research submit` for reusing existing stores
- Vector stores can be looked up by ID or name
- Enables document indexing once, reuse across multiple research jobs

**Batch Job Download and Queue Sync**
- Added `--all` flag to `deepr research get` for downloading all completed jobs
- Added `deepr queue sync` command to update all job statuses without downloading
- Automatically checks provider for all pending jobs and downloads completed ones
- Useful for batch processing after submitting multiple research jobs
- Queue sync updates local status to match provider without downloading results

**Enhanced Cost Management**
- Added `--period` flag to `deepr cost summary` (today, week, month, all)
- Cost breakdown by model showing per-model spending and job counts
- Budget tracking with percentage of daily/monthly limits
- Improved statistics with total jobs, completed count, and averages

**Research Export**
- Added `deepr research export` command for exporting in multiple formats
- Supports markdown, txt, json, and html export formats
- Automatic output path generation or custom output location
- Includes job metadata, content, and usage statistics in exports

**Build and Installation**
- Added pyproject.toml for modern Python packaging
- Created INSTALL.md with platform-specific instructions
- Added install scripts for Linux/macOS (install.sh) and Windows (install.bat)
- Added Makefile for common development tasks
- Added build scripts (build.bat for Windows)
- Updated setup.py to version 2.3.0
- Console script entry point enables `deepr` command globally

**Configuration Management**
- Added `deepr config validate` command to check configuration and API connectivity
- Added `deepr config show` command to display current settings (sanitized)
- Added `deepr config set` command to update configuration values
- Validates API keys, directories, and budget limits
- Tests provider connectivity during validation

**Analytics and Insights**
- Added `deepr analytics report` command for usage analytics
- Success rates, model performance, cost analysis by time period
- Added `deepr analytics trends` showing daily job counts and costs
- Added `deepr analytics failures` for failure pattern analysis
- Identifies most cost-effective models and provides recommendations

**Prompt Templates**
- Added `deepr templates save` to save reusable prompts with placeholders
- Added `deepr templates list` to view all saved templates
- Added `deepr templates show` to display template details
- Added `deepr templates delete` to remove templates
- Added `deepr templates use` to submit research using templates
- Tracks usage count for each template
- Supports placeholder substitution (e.g., {industry}, {region})

### Changed
- Execute command now prevents execution of paused campaigns
- Improved human-in-the-loop controls with pause/resume workflow
- Research submit command now supports both new file uploads and existing vector stores
- Simplified README Quick Start to focus on pip install workflow

## [2.2.0] - 2025-10-29

### Added

**File Upload & Vector Stores**
- Added `--files` / `-f` flag to `deepr research submit` for document upload
- Automatic vector store creation and indexing for semantic search
- Support for PDF, DOCX, TXT, MD, and code files
- Successfully tested with multi-document research workflows

**Automatic Prompt Refinement**
- Added `--refine-prompt` flag to optimize research queries automatically
- Uses GPT-5.2-mini to enhance prompts with temporal context and structure (~$0.001 per refinement)
- Automatically adds current date context ("As of October 2025...")
- Suggests structured deliverables and flags missing business context
- Provides before/after comparison of prompt improvements

**Ad-Hoc Result Retrieval**
- Added `deepr research get <job-id>` command for on-demand result downloads
- Check provider status and download results without continuous worker
- Perfect for daily check-ins, CI/CD integration, and casual usage
- Eliminates need for 24/7 worker process

**Detailed Cost Breakdowns**
- Added `--cost` flag to `deepr research result` command
- Shows comprehensive token usage breakdown (input/output/reasoning)
- Displays separate cost calculations for input and output tokens
- Includes model pricing information (per 1M tokens)
- Shows job metadata and prompt context

**Human-in-the-Loop Controls**
- Added `--review-before-execute` flag to `deepr prep plan` command
- Tasks start unapproved when flag is used, requiring explicit human approval
- Prevents autonomous execution without oversight
- Use `deepr prep review` to approve/reject tasks before execution

**Provider Resilience**
- Implemented retry logic with exponential backoff (3 attempts: 1s, 2s, 4s delays)
- Graceful degradation: automatically falls back from o3-deep-research to o4-mini-deep-research
- Handles rate limits, connection errors, and timeouts automatically
- Ensures research completes even if preferred model is unavailable

### Changed

**CLI Commands**
- Renamed `poll` to `get` for clearer intent (retrieve results)
- Improved command descriptions and help text across all commands
- Enhanced error messages with actionable guidance

**Documentation**
- Restructured README Quick Start with clear numbered steps
- Added prerequisites section (Python 3.9+, Node.js 16+)
- Added "Why Deepr?" value proposition with key differentiators
- Clarified target audience (researchers, analysts, product teams, developers, AI agents)
- Added cost warning and budget management guidance
- Updated all time/cost estimates to "Estimated: ~$X" format
- Added descriptive context before code example sections
- Fixed grammar issues ("becoming an expert", improved wording)
- Updated Multi-Provider Support section with current October 2025 models
- Removed all emojis from documentation

**ROADMAP**
- Updated from v2.1 to v2.2 release status
- Marked priorities 1-6 as complete or partially complete
- Added implementation details for each completed feature
- Clarified model references (GPT-5, o3-deep-research, o4-mini-deep-research)
- Updated version timeline (v2.3, v2.4, v2.5)
- Updated Agentic Levels table to reflect current progress

### Fixed
- Fixed version inconsistencies throughout documentation (v2.1 → v2.2)
- Fixed port references (backend: 5000, frontend: 3000)
- Corrected model naming for clarity
- Improved Unicode handling in CLI output for Windows compatibility

### Meta-Research
- Used Deepr itself to analyze README and ROADMAP for refinement opportunities
- Applied 12+ specific recommendations from research report
- Research cost: $2.00 for comprehensive documentation review
- Demonstrated platform capabilities through self-improvement

## [2.1.0] - 2025-10-XX

### Added
- Multi-phase research campaigns with adaptive planning
- GPT-5.2 as research lead for reviewing and planning phases
- Context chaining with automatic summarization
- Dynamic research teams (experimental)
- Web UI with real-time updates and cost analytics

### Changed
- Improved background worker with stuck job detection
- Enhanced cost tracking from OpenAI token usage

## [2.0.0] - 2025-10-XX

### Added
- Initial release of Deepr
- Single deep research jobs via CLI
- OpenAI Deep Research integration (o3, o4-mini models)
- SQLite queue and filesystem storage
- Background worker with automatic polling
- Basic web UI

---

For more details on upcoming features, see [ROADMAP.md](ROADMAP.md).
