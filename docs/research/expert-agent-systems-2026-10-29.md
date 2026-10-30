# Expert agents, research teams, and temporal memory

Research review: 2026-10-29. This assessment supports
[the persistent expert design](../design/persistent-expert-agent.md) and
[ADR 0008](../decisions/0008-persistent-domain-agent-boundary.md).
ROADMAP remains the active-work authority. These sources establish design
patterns and reported results, not Deepr compatibility or superior expertise.

## Method and limits

Reviewed primary project documentation, selected pinned source files, research
abstracts and author reports, and Deepr contracts/callers. No upstream package
was installed or executed, no provider was invoked, and no new model trial was
run. Paper results below were not independently reproduced. This is a targeted
architecture review, not an exhaustive literature survey or security audit.

The local source baseline is `ee640080` (v2.51.5 plus the preserved local trial).
Upstream snapshots were fetched on the review date:

| Project | Inspected commit | Selected references |
| --- | --- | --- |
| Paperclip | `929e840595c8933ca485ac7a2e99413e1e11ca64` | [task ownership and updates](https://github.com/paperclipai/paperclip/blob/929e840595c8933ca485ac7a2e99413e1e11ca64/docs/guides/agent-developer/task-workflow.md), [heartbeat protocol](https://github.com/paperclipai/paperclip/blob/929e840595c8933ca485ac7a2e99413e1e11ca64/docs/guides/agent-developer/heartbeat-protocol.md), [architecture](https://github.com/paperclipai/paperclip/blob/929e840595c8933ca485ac7a2e99413e1e11ca64/docs/start/architecture.md), [budgets](https://github.com/paperclipai/paperclip/blob/929e840595c8933ca485ac7a2e99413e1e11ca64/docs/guides/board-operator/costs-and-budgets.md) |
| Pi | `0c3675e6472c5cb8c1d880fdf79179c21348617e` | [agent loop](https://github.com/earendil-works/pi/blob/0c3675e6472c5cb8c1d880fdf79179c21348617e/packages/agent/src/agent-loop.ts), [core contract](https://github.com/earendil-works/pi/blob/0c3675e6472c5cb8c1d880fdf79179c21348617e/packages/agent/README.md), [sessions](https://github.com/earendil-works/pi/blob/0c3675e6472c5cb8c1d880fdf79179c21348617e/packages/coding-agent/docs/sessions.md), [compaction](https://github.com/earendil-works/pi/blob/0c3675e6472c5cb8c1d880fdf79179c21348617e/packages/coding-agent/docs/compaction.md) |
| Hermes | `a938f00f0f3cdf00fdb93d9a82a9ae447e9b857f` | [session search](https://github.com/NousResearch/hermes-agent/blob/a938f00f0f3cdf00fdb93d9a82a9ae447e9b857f/tools/session_search_tool.py), [skills](https://github.com/NousResearch/hermes-agent/blob/a938f00f0f3cdf00fdb93d9a82a9ae447e9b857f/website/docs/user-guide/features/skills.md), [personality](https://github.com/NousResearch/hermes-agent/blob/a938f00f0f3cdf00fdb93d9a82a9ae447e9b857f/website/docs/user-guide/features/personality.md) |
| Graphiti | `72b5c59c06607e09ea855be61b6ff5a3446fc951` | [edge fields](https://github.com/getzep/graphiti/blob/72b5c59c06607e09ea855be61b6ff5a3446fc951/graphiti_core/edges.py), [retrieval configuration](https://github.com/getzep/graphiti/blob/72b5c59c06607e09ea855be61b6ff5a3446fc951/graphiti_core/search/search_config.py), [deduplication prompts](https://github.com/getzep/graphiti/blob/72b5c59c06607e09ea855be61b6ff5a3446fc951/graphiti_core/prompts/dedupe_edges.py) |

Exact retrieved bytes, SHA-256 hashes, tree inventories, and observation times
are retained in the gitignored review workspace. One Hermes `memory_tool.py`
download received HTTP 429; no claim here rests on inspecting that file. Its
memory behavior is attributed to the separately reviewed official docs. These
commit pins are research snapshots, not newly approved adapter/runtime pins.

## What to take from the systems

### Paperclip: ownership and continuity of work

Paperclip's task workflow documents atomic checkout, conflict refusal,
idempotent reacquisition by the owner, run-linked updates, blocked states,
parent/goal relationships, and approvals bound to plan revisions. Its execution
adapters connect a control plane to agent runtimes; heartbeat capture preserves
results and session state. The useful pattern for Deepr is accountable episode
ownership and explicit continuation, not an organizational chart inside every
expert. The budget docs describe cost reporting and auto-pausing; they do not
establish Deepr's required pre-dispatch provider hard ceiling.

**Decision:** adapt ownership, progress, artifact identity, and blocked-work
semantics to existing investigation records. Keep company tasks, staffing,
general scheduling, and cross-project orchestration in an optional host.
No Paperclip adapter is selected or qualified by this review.

### Pi: a composable model and tool loop

Pi's core separates agent messages from provider messages, supports context
transformation and request preparation, runs tool results back into subsequent
turns, and exposes steering and turn finalization. Sessions and compaction are
explicit harness concerns. These are useful reference points for the missing
connection between a Deepr consultation and its research tools.

**Decision:** adapt progressive context, observable steps, interruption, and
bounded continuation. Keep Deepr's Python stack and authority seams. A local
SDK/RPC integration can be evaluated later; source availability does not prove
confinement, model eligibility, or managed-host compatibility. Avoid copying an
unbounded continuation loop or adopting a second canonical memory store.

### Hermes: continuity across identity, experience, and methods

Hermes distinguishes personality, bounded persistent memory, past-session
search, and on-demand skills. The official [memory guide](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory)
describes compact memory snapshots and separate user information. The inspected
skill and session interfaces make procedures and past work available beyond
the current conversation. These are stronger product references than defining
learning as more extracted claims.

**Decision:** keep Deepr personality, episodic recall, and procedural memory
distinct but connected. A saved skill is a candidate method whose future use
must be scoped and reviewed; creating a file does not establish improvement.
Do not import automatic unrestricted skill modification as write authority.

### Grok Bot: the continuing colleague experience

Grok documents named persistent Bots with tools and a workspace. Its
[skills and routines guide](https://docs.x.ai/grok-bot/skills-routines-and-automations)
starts with a one-time task, then a reliable reusable method, then automation.
This supports a complete expert workflow before fleet expansion. The
[product overview](https://docs.x.ai/grok-bot/overview) is a UX reference;
it does not expose enough implementation detail to infer its memory algorithm.

**Decision:** make the same expert usable across questions, investigations, and
reviewed learning. A cloud computer, messaging gateway, or public bot fleet is
not a prerequisite for that experience.

### Graphiti: temporal relationships and provenance

The inspected edge model separates creation/expiry metadata from validity
intervals and retains episode references. Its search configuration supports
multiple candidate retrieval approaches. This is relevant to historical
eligibility and connected evidence, not proof that an automatically extracted
edge is true. The [Zep paper](https://arxiv.org/abs/2501.13956v1) reports temporal
memory retrieval results in its own evaluated settings.

**Decision:** adopt explicit temporal query obligations, provenance, and hybrid
candidate recall. Preserve reviewed semantic updates and existing stores.
Compare a graph route with text/embedding routes before selecting infrastructure.
A graph can preserve a wrong assertion faithfully; it cannot independently
validate the assertion or make a summary use the correct revision.

## Research beyond product analogies

| Primary source | Finding relevant to the design | Deepr implication and limit |
| --- | --- | --- |
| [Google AI co-scientist](https://research.google/blog/accelerating-scientific-breakthroughs-with-an-ai-co-scientist/) | Research roles generate, reflect on, rank, and refine hypotheses and proposals with scientist interaction. | Preserve hypotheses, competing explanations, and experiment selection as expert work. Ranking is not empirical confirmation; local reproduction is untested. |
| [Anthropic multi-agent research](https://www.anthropic.com/research/multi-agent-research-system) | Adaptive search and separate researcher contexts help breadth-first work, with substantial resource overhead and coordination limits. | Use explicit subquestions and evidence-bearing handoffs when work is independent. Do not make a team mandatory for simple or tightly dependent tasks. |
| [Google scaling agent systems](https://research.google/blog/towards-a-science-of-scaling-agent-systems-when-and-why-agent-systems-work/) | Controlled configurations show benefits depend on task structure; coordination can hurt sequential work. | Compare a single expert with bounded teams under declared total resource limits. Agent count is not a quality target. |
| [Open Deep Research supervisor](https://github.com/langchain-ai/open_deep_research/blob/main/src/open_deep_research/deep_researcher.py) | A research brief feeds a supervisor that selects further research or completion. | Borrow explicit question decomposition and completion decisions. Current main was reviewed as a pattern, not pinned or executed as a dependency. |
| [ACE, v3](https://arxiv.org/abs/2510.04618v3) | Treats context as an evolving playbook; incremental generation/reflection/curation addresses loss from repeated rewriting. | Version procedural changes and retain original evidence. Benchmark gains do not establish Deepr improvement or justify self-approval. |
| [A-MEM, v11](https://arxiv.org/abs/2502.12110v11) | Agent-organized notes and evolving links support contextual memory organization. | Use linked explanatory notes and candidate associations; preserve source qualifications and historical versions rather than silently rewriting prior meaning. |
| [Mem0](https://arxiv.org/abs/2504.19413v1) | Evaluates selective extraction/consolidation and a graph variant against several conversational-memory baselines. | Measure useful memory against full context and simpler retrieval, including latency. The graph variant's reported result is not evidence that every memory task needs a graph service. |
| [AgeMem, v3](https://arxiv.org/abs/2601.01885v3) | Exposes short/long-term memory operations as actions and trains their selection with reinforcement learning. | Memory use belongs in the agent's decision space. Tool exposure alone does not reproduce a trained policy; weight training is outside the first Deepr scope. |
| [LangMem concepts](https://langchain-ai.github.io/langmem/concepts/conceptual_guide/) | Separates semantic, episodic, and procedural memory and distinguishes creation from storage integration. | Separate observations, interpretations, and procedures while reusing canonical owners. Retain concise public rationale, not private chain-of-thought transcripts. |
| [LongMemEval](https://arxiv.org/abs/2410.10813) | Separates extraction, multi-session reasoning, temporal reasoning, updates, and abstention. | Use diagnostic dimensions rather than a single recall score; benchmark question answering is not complete expert evaluation. |
| [LongMemEval-V2](https://arxiv.org/abs/2605.12493v1) | Work-in-progress evaluation adds dynamic state, workflow knowledge, environment gotchas, and premise awareness; active evidence gathering has latency tradeoffs. | Test methods and experience as well as facts. Compare dynamic retrieval with compiled context, and report total latency and preprocessing. |

The research supports a connected memory-and-action design. It does not support
declaring a universal winning framework, copying leaderboard percentages into
Deepr claims, or turning a negative local test into a conclusion that memory is
ineffective. Full-context reasoning defects also mean the base model must be
evaluated separately from retrieval and persistence.

## Synthesis and rejected shortcuts

### Second research pass: memory failure and control

After drafting the architecture, a second search focused on mechanisms that
could invalidate it. [HaluMem](https://arxiv.org/abs/2511.03506) evaluates
extraction, updating, and answering separately; the authors report that memory
errors can accumulate before an answer is generated. This reinforces retaining
stage-specific observations and testing reconciliation, rather than judging
only the final prose.

[Experience-following research](https://arxiv.org/abs/2505.16067) reports error
propagation and misapplied replay under naive memory growth. It motivates
counterexamples, retrieval exclusion, and obsolete-method tests in the plan.
It does not justify deleting inconvenient negative results or using an age
threshold as a semantic invalidation rule.

[Memory-induced tool drift](https://arxiv.org/abs/2605.24941) studies how stored
personality biases can affect tool parameters outside their applicable scope.
The reported experiments motivate a specific test: changing an expert's style
must not alter admitted permissions, resource limits, or task requirements.
This is a reason to keep personality and action authority separate, not to
remove personality from the product.

[MemCon](https://arxiv.org/abs/2607.13591) treats retrieval, plan reuse, and
consolidation choices as an adaptive control problem and reports results from a
learned policy. This suggests a later comparison against fixed retrieval rules.
It does not establish that Deepr should deploy an online optimizer now: feedback
quality, policy evaluation, and rollback remain separate S5 requirements.

These additional sources are author-reported research, not reproduced results.
They strengthen the planned failure cases and staged evaluation rather than
adding dependencies or changing the first implementation scope.

### Architectural conclusion

The strongest direction is a persistent domain agent with complementary memory
types and a bounded adaptive loop. The temporal graph supplies relationships
and history; the wiki supplies readable understanding; the episode supplies
work continuity; procedures supply reusable methods. The model decides what to
inspect and how to reason. The admission service decides which writes are
authorized, with semantic review supplying judgments rather than keyword rules.

Keep these distinctions explicit:

- A persisted observation is not an admitted interpretation.
- A proposed method is not an executable capability or demonstrated skill.
- A source-grounded explanation can be useful without being a forecast.
- A resolved prediction does not automatically change a policy or personality.
- A larger context, graph, or team can increase cost and propagate mistakes.
- A successful task can teach a narrowly useful method without proving a
  general increase in intelligence.

Reject a wholesale harness rewrite, mandatory graph database, giant mutable
summary, automatic transcript-to-truth ingestion, unsupervised skill optimizer,
and fleet-first delivery. Revisit each infrastructure choice only against a
measured constraint and a reversible evaluation. External hosts remain useful
partners, rather than prerequisites or replacements for expert authority.

## Documentation review and reconciliation

The review inventoried all Markdown files returned by `rg --files -g '*.md'
under `docs/` plus root Markdown: 220 files at the starting checkpoint. All
were scanned for definitions, persona/memory language, temporal semantics,
orchestration restrictions, and stale capability assertions. Forty-nine files
matched those targeted terms. This is a broad consistency scan, not a claim
that every line in all historical documents was revalidated.

Focused reading covered the approach, README, roadmap, supported surface,
architecture, expert guide, vision, living-expertise gates, agentic balance,
expert definition, harness boundary/bridge/lessons, local runtime options,
temporal graph, event memory, position justification, skills learning, expert
library, V2 architecture/identity, fleet, maturity, investigations, and the
local validation record. Relevant source and unit-test owners
were traced directly; there was no available codegraph to rebuild or rely on.

| Conflict found | Reconciliation |
| --- | --- |
| Expert described as state plus verbs, with personality treated mainly as a distraction | Define a persistent domain agent; distinguish stable style and research posture from changing conclusions and authority. |
| Synchronous-only boundary versus persistent investigations | ADR 0008 and the harness boundary allow bounded domain episodes across invocations; external workflow control remains host-owned. |
| Preparation dominates the active roadmap while inquiry and methods appear much later | Add a supervised complete-workflow development sequence spanning existing S1-S3; keep release and promotion gates intact. |
| Earlier roadmap rejects every internal supervisor and all model-mediated memory change | Qualify the historical judgment: bounded domain control and staged semantic revision are in scope; unrestricted writes and a general orchestrator remain out. |
| Skills note claims no evaluation or position history, and equates survival with stronger expertise | Reconcile with current history, experience, and eval seams; survival/repetition alone establishes no quality. |
| Expert-library note promises always-current fleets and automatic metered waterfall | Replace with bounded library direction and current capacity truth; defer maintenance scale until useful single-expert work is proven. |
| Vision duplicates stale versioned implementation claims | Keep it aspirational and point current behavior to Supported Surface. |
| Temporal graph and Event Memory V2 can read as competing new storage mandates | Mark the older graph diagnosis historical; preserve incremental semantic/query work and defer authority migration. |

The second pass follows links and checks active instructions against the new
decision, distinguishing historical evidence from operative guidance. Archived
trials and old research results remain intact. The current limitation is still
the same: no adaptive expert session or improved judgment is shipped by these
documentation changes.
