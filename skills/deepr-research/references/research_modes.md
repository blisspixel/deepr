# Research capacity reference

## Works now in v2.36

| Capacity | Supported use | Cost posture |
|----------|---------------|--------------|
| Local Ollama | Expert setup, sync, absorb, fresh/deep context, local eval, read-only query/consult | `$0` Deepr marginal cost; uses local hardware |
| Explicit non-metered plan CLI | Selected expert sync, sync-all, gap-fill, absorb, learn, query/consult, and probes | `$0` Deepr ledger event; may consume external quota Deepr cannot prove |
| Bounded API | One fully priced research request; separately bounded API council synthesis | Metered; reserve the hard maximum before dispatch |
| Stored state | Expert reads, handoffs, memory cards, loop status, reports | `$0` and no provider dispatch |

Registry presence alone does not make a provider mode executable. Managed
Gemini Deep Research, xAI multi-agent research, Azure Foundry agents, hosted
file/vector context, automatic metered fallback, and multi-call metered runs are
gated.

## Choose a path

```text
Does stored expert state already answer the question?
  YES -> Inspect or consult through explicit local/plan capacity.
  NO  -> Is one current cited report enough?
          YES -> Preview and approve one bounded API research job.
          NO  -> Decompose with the user and submit separately approved
                 bounded jobs. Do not start an autonomous campaign.
```

For scheduled expert maintenance, choose only admitted local capacity or a
trusted-quota non-metered plan backend. A busy local GPU produces a waiting
outcome with retry guidance and never falls through to another capacity class.

## Single-job async pattern

```text
1. Submit deepr_research with explicit provider, model, and budget.
2. Retain job_id, trace_id, and returned resource URIs.
3. Subscribe to the returned status URI or call deepr_check_status.
4. Retrieve the final report with deepr_get_result.
5. Preserve citations and report actual settled cost.
```

The returned resource URI is authoritative. Do not assume every job has a
multi-phase campaign plan or intermediate belief stream.

## Gated adapters

The following may remain discoverable for compatibility but must return a typed
block before provider work:

- `deepr_agentic_research`;
- metered batch, team, campaign, continuation, or prepared execution;
- automatic cross-provider retry/fallback;
- hosted upload, file search, or vector-store research attachment;
- standalone metered expert chat and metered expert lifecycle mutation.

Do not work around these gates with repeated single calls, hidden retries, or a
larger budget. If the user wants several separate jobs, show and approve each
bounded envelope independently.
