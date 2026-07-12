# Design: evidence-gated polyglot evolution

Status: accepted. Python-first hardening is authorized. No Rust, Go, or Mojo
production dependency is authorized by this decision.

## Decision

Deepr remains a Python product and intelligence system. It will use optimized
native libraries already available through Python, fix measured Python
bottlenecks, and establish a versioned local performance harness before adding
another implementation language.

A language extraction is allowed only when all of these are true:

1. A production-shaped benchmark identifies one stable bounded capability, not
   a file or a general desire for speed.
2. That capability materially contributes to an end-to-end latency, throughput,
   memory, durability, isolation, or deployment SLO miss.
3. Python architecture, bounded concurrency, batching, caching, and existing
   native libraries have been measured first.
4. The candidate has a versioned contract, a Python reference, differential
   tests, adversarial inputs, observability, cancellation behavior, and a safe
   fallback.
5. The end-to-end gain remains material after serialization, FFI, packaging,
   startup, and operational costs are included.

This follows the roadmap principles to close the loop before widening it and to
treat self-improvement as a verification problem. A polyglot stack is an
available tool, not an architectural objective.

## Why this decision was needed

Deepr now spans provider adapters, expert memory, web retrieval, local and plan
capacity, queues, MCP, A2A, a web application, and a packaged frontend. That
surface makes broad claims about language performance tempting, but generic
benchmarks do not identify Deepr's limiting resource.

The useful question is not whether Rust, Go, or Mojo can beat Python on a
microbenchmark. It is whether one language boundary improves an important Deepr
property enough to offset another compiler, package manager, security-update
stream, CI matrix, release artifact, debugger, telemetry bridge, and contract.

## Measured Deepr baseline

These read-only measurements were taken on the Windows development workstation
on 2026-07-11. They characterize the current scale and are not portable product
claims.

| Workload | Observed result |
|---|---:|
| Live expert directories | 36 |
| Belief stores | 33 |
| All live belief-store data | about 2 MB |
| Largest store | 105 beliefs, 40 edges, 149 KB JSON |
| Largest-store load | 1.06 ms median, 1.56 ms p95 |
| Lexical recall over 100 items | 0.59 ms median |
| Lexical recall over 1,000 items | 5.43 ms median |
| Lexical recall over 5,000 items | 26.77 ms median |
| Cost ledger | 409 events, 177 KB, 1.91 ms constructor, 2.52 ms full read |
| Quota ledger | 550 events, 267 KB |
| Two recorded local council runs | 373 seconds and 829 seconds |
| `deepr --version` before lazy loading | about 3.4 to 5.4 seconds warm, with a slower first run |

At current scale, expert storage and deterministic retrieval are millisecond
workloads. Model turns are minute workloads. Rewriting the current storage or
orchestration core would not improve the dominant end-to-end path.

One synthetic semantic-recall probe did expose a real local hotspot. Scanning
5,000 vectors with 384 dimensions through the current coordinate-by-coordinate
Python path took about 657 ms, while a raw NumPy matrix calculation took about
6 ms. This is directional rather than API-equivalent, but it proves that the
first candidate is better NumPy use, not a new language.

## Python work that comes first

### 1. Cold-start and import boundaries

The root CLI imported every command before Click could answer `--version`.
Provider and expert package initializers also eagerly imported SDK, chat, and
NumPy paths. Import-time observations included about 0.75 seconds for Google
GenAI, 0.68 seconds for Anthropic, 0.58 seconds for OpenAI, and 0.23 seconds for
the Azure stack.

The first fix is lazy command and provider loading while preserving the public
Python and CLI contracts.

Acceptance targets:

- `deepr --version` p95 below 300 ms on the reference workstation.
- Root help p95 below 750 ms.
- A no-provider command does not import OpenAI, Anthropic, Google, Azure, NumPy,
  or expert-chat modules.
- Existing command names, aliases, options, exit behavior, and public package
  exports remain compatible.

Shipped 2026-07-11: a 20-process Windows run measured `deepr --version` at
about 223 ms p95 and root help at about 217 ms p95. Import-posture regressions
prove those paths do not load provider SDKs, NumPy, or expert chat.

### 2. Async I/O, bounds, and cancellation

Several `async` surfaces still perform blocking `requests` calls or sequential
network operations. Page content is also buffered before downstream character
truncation. These are Python implementation and resource-boundary issues, not
language limitations.

The sequence is:

1. Remove blocking HTTP work from the event loop with async clients or bounded
   worker-thread adapters.
2. Stream response bodies under a byte and decompression ceiling.
3. Add bounded page-fetch and provider-status concurrency with stable result
   ordering.
4. Propagate deadlines and cancellation and preserve exact attempt caps.

Acceptance targets:

- Five mocked 500 ms fetches under a four-wide bound complete near two batch
  latencies, not five serial latencies.
- Event-loop lag stays below 50 ms in that fixture.
- Cancellation stops outstanding work.
- Source order, SSRF checks, readiness, retry count, and no-model-on-under-ready
  behavior remain unchanged.
- Oversized or decompression-expanded bodies fail with a typed bounded error.
- One hundred mocked 100 ms status checks at concurrency ten complete below
  1.5 seconds and settle each job at most once.

### 3. Semantic recall through NumPy

Semantic recall should use a normalized contiguous matrix, cache query lexical
terms once, and use partial top-k selection. Exact candidate parity and stable
tie ordering are required. The cosine tolerance is at most `1e-6`.

The initial reference target is a 10,000 by 768 scan below 50 ms p95 without a
per-query matrix rebuild. Rust or an ANN service is reconsidered only if real
expert scale still violates a recall SLO after this change.

### 4. Batch persistence

Some belief and vector operations rewrite a whole JSON projection once per
item. At 105 beliefs this is not important. At thousands it becomes avoidable
write amplification.

Add bulk mutation APIs that validate the full batch, append canonical events,
and write each derived projection once atomically. Add rebuildable adjacency
and vector indexes when measured lookup scale requires them. Canonical events
and append-only ledgers remain authoritative.

### 5. Concurrency-safe ledgers

The cost ledger already serializes interprocess writes. The quota ledger used a
per-instance thread lock even though helper calls construct separate instances,
so concurrent probes could append through unrelated locks. The quota ledger
must receive the same cross-process serialization and crash-recovery tests
before experimenting with free-threaded Python.

The cost ledger currently rebuilds its idempotency view from JSONL for each
keyed append. At 409 events this is cheap. If a 100,000-event benchmark misses
the append SLO, add a rebuildable SQLite side index while keeping JSONL
canonical.

## Language boundaries

### Python stays authoritative

Python continues to own:

- provider SDK integration and routing;
- expert semantics, prompts, synthesis, and calibrated judgments;
- verification, evaluation, and graph-commit policy;
- CLI, web, MCP, and A2A product behavior;
- source-pack composition and capacity policy;
- cost authorization and knowledge-mutation authority.

These paths change quickly and mostly wait on models, networks, subprocesses,
or SQLite. Python provides the strongest ecosystem and the lowest iteration
cost here.

### Rust is a future deterministic-engine candidate

The first credible Rust seam is the planned ExpertEventV2 deterministic engine
after a Python reference and shadow replay exist:

- canonical event validation and serialization;
- content hashes and causal-parent validation;
- deterministic projection replay;
- replica union and malformed-event quarantine;
- large-history compaction and index construction.

Rust must not decide contradiction, grounding, atomicity, semantic deduplication,
or other questions of meaning.

Prefer a standalone stdin/stdout executable for the first experiment because it
provides process isolation and a simple observable contract. A PyO3 extension
is justified only when measured boundary overhead or copying prevents the
standalone form from meeting its SLO. PyO3 supports native Python modules and
recommends Maturin as the easiest packaging route, but native wheels would add
an OS, architecture, Python ABI, SBOM, and release matrix to Deepr.

Promotion requires:

- byte-identical golden replay on Windows and Linux;
- exact differential tests against the Python reference;
- fuzzed malformed, oversized, and torn input handling;
- 100,000 and 1,000,000 event CPU and RSS benchmarks;
- at least 3x improvement in the limiting component or 50 percent lower RSS;
- at least 10 percent improvement in the affected end-to-end p95 or a required
  durability property that Python cannot meet cleanly;
- an exercised fallback and rollback path.

### Go is a future hosted-runner candidate

Go becomes reasonable only if Deepr gains an independently deployable,
multi-host operational component that owns queue leases, heartbeats, process
supervision, deadlines, cancellation, worker health, backpressure, and
admission transport.

Python would still own expert meaning, cost policy, and verified memory
mutation. The boundary should be HTTP, gRPC, a queue protocol, or a separate
executable. An in-process Go extension is rejected because cgo introduces
pointer-lifetime and garbage-collector constraints without a current Deepr
need.

The trigger is sustained control-plane saturation after Python async fixes,
measured without provider latency. An API existing is not itself a reason to
extract it.

### Mojo has no current Deepr workload

Deepr does not own an inference engine, tensor operator, GPU kernel, or custom
accelerator computation. Ollama and remote providers own model execution, and
NumPy already moves vector work into compiled code.

Mojo 1.0 is in beta as of May 2026. Modular positions the language primarily
for high-performance CPU and GPU kernels and says the beta still needs polish
before final release. Deepr will revisit Mojo only if it owns a measured custom
kernel that remains slow after comparison with NumPy and mature ML libraries.

### Python 3.14 free-threading is an experiment

The ordinary Python 3.14 CI job is not a `3.14t` free-threaded build. CPython
3.14 officially supports free-threading as an optional build, but extension
modules can re-enable the GIL, single-threaded execution has overhead, memory
use can increase, and shared iterators or state still require explicit
synchronization.

An allowed-to-fail `3.14t` stress job may be added only after file-backed
stores, quota-ledger writes, and cross-verb expert mutations are serialized.
Promotion requires:

- the full suite and repeated concurrency stress runs pass;
- eight to sixteen worker threads produce byte-equivalent durable state;
- no deadlocks, lost events, duplicate settlements, or hidden GIL fallback;
- at least 1.5x throughput on a real CPU-bound Deepr workload;
- no more than 10 percent single-thread slowdown or 20 percent RSS growth.

Free-threading does not accelerate async waits, provider calls, Ollama
generation, or code that remains single-threaded.

## Performance harness

Add a versioned, provider-free harness with these scenarios:

- CLI version and root-help cold start;
- expert load and lexical or semantic recall at 100, 1,000, and 10,000 beliefs;
- graph-commit batches;
- ledger append and rebuild at 1,000, 10,000, and 100,000 events;
- five-page mocked fresh retrieval;
- one hundred mocked poll cycles;
- MCP read tools at 32 and 64 concurrent clients.

Each result records p50, p95, p99, CPU time, peak RSS, event-loop lag, workload
size, Python build, OS, and hardware. Shared CI verifies correctness and
complexity. Timing regression gates run only on a stable scheduled runner.
Profile with standard-library tools first, then use py-spy or Memray when a
scenario identifies a hotspot.

## Boundary contract for any extraction

Every cross-language capability must define:

- a versioned input and output schema;
- stable error taxonomy and exit behavior;
- maximum input, output, and memory bounds;
- deadlines, cancellation, and retry ownership;
- idempotency and write authority;
- backpressure and concurrency limits;
- trace, metric, and log correlation fields;
- compatibility and deprecation policy;
- build provenance, SBOM, vulnerability update, and release ownership;
- a Python reference or fallback until rollout evidence permits removal.

Rollout follows prototype, shadow, opt-in pilot, limited production, then broad
production. A peak microbenchmark cannot skip shadow comparison or end-to-end
measurement.

## Alternatives rejected

- Rewrite the CLI in Go or Rust: rejected because eager imports explain the
  current cold start and can be removed without replacing product logic.
- Move current expert storage to Rust: rejected because the largest store loads
  in about 1 ms and all stores total about 2 MB.
- Add a Go API gateway now: rejected because existing bounded aiohttp surfaces
  have no demonstrated control-plane saturation.
- Add Mojo for local-model work: rejected because Deepr dispatches inference
  but does not own its kernels.
- Adopt all four languages by layer: rejected because layer diagrams do not
  establish a measurable boundary benefit.
- Trust generic 5x to 20x infrastructure-cost estimates: rejected until a
  Deepr-shaped workload, end-to-end budget, and deployment topology reproduce
  the claimed saving.

## Primary references

- [Python 3.14 free-threading HOWTO](https://docs.python.org/3/howto/free-threading-python.html)
- [Python 3.14 free-threaded extension guidance](https://docs.python.org/3/howto/free-threading-extensions.html)
- [PyO3 user guide](https://pyo3.rs/main/index.html)
- [PyO3 building and distribution](https://pyo3.rs/main/building-and-distribution)
- [Go cgo pointer rules](https://pkg.go.dev/cmd/cgo#hdr-Passing_pointers)
- [Modular 26.3 and Mojo 1.0 beta](https://www.modular.com/blog/modular-26-3-mojo-1-0-beta-max-video-gen-and-more)
- [Mojo manual](https://docs.modular.com/mojo/manual/)

The external references were rechecked on 2026-07-11. Repository measurements
must be rerun before using them as a future extraction decision.
