# Runtime and capacity evidence

Status: primary-source research and targeted static review. No model inference,
provider account API, credential inspection, installation, or deployment was
performed. This note is evidence for planning, not execution authority.

The next product outcome remains the v2.51 blinded four-arm value evaluation.
External runtimes have improved transport, packaging, and durable execution.
They do not demonstrate that Deepr's maintained experts improve decisions.
One newly verified confinement gap deserves an immediate compatibility/safety
correction before further Claude plan dispatch. It does not justify widening
the product or reordering the later release gates.

The correction is now implemented in the worktree: the production Claude
adapter refuses execution. The [containment decision](../design/claude-managed-policy-containment.md)
defines restoration requirements, and the [verification record](../validation/research-review-2026-09-13.md)
separates focused regression evidence from final-suite results.

## Decision implications

| Priority | Action | Reason and completion evidence |
| --- | --- | --- |
| Immediate safety correction | Refuse Claude plan execution while managed-policy side effects remain unproven. | The existing empty-tool invocation can still run a managed session hook. Verify refusal before account probes and child launch, without credentials or inference. |
| v2.51 | Use already admitted owned-local capacity for the frozen longitudinal evaluation. | Record model/runtime identity, source-world hashes, all four arms, failures, costs, latency, and review assignments. Capacity availability must not become evidence that memory helps. |
| v2.52 | Bind later observations to original predictions and propose reviewed revisions. | Preserve historical reconstruction and separate valid time from observation time. No outcome directly changes policy or knowledge. |
| v2.53 | Complete durable parent accounting with offline request and failure fixtures. | Provider budget controls still do not prove exact maximum liability. Test ambiguous completion, duplicate settlement, concurrent admission, cancellation, and route/BYOK changes. |
| v2.54 and later | Validate one exact host profile when it removes a measured user limitation. | Pin runtime, transport, protocol era, discovered tools, workspace, and failure behavior. A portable package or upstream support label is insufficient. |

## Ten highest-value source records

All sources were opened on 2026-09-13. A date below is a displayed publication
or update date where available; otherwise only the access date is claimed.
Mutable documentation is current evidence, not an immutable historical fixture.

1. **Ollama FAQ.** Living documentation, accessed 2026-09-13.
   The server supports disabling cloud models and web search through
   `disable_ollama_cloud` or `OLLAMA_NO_CLOUD=1`, followed by a restart.
   This supports Deepr's owned-server gate. A loopback URL, a model name, or a
   variable set only in the Deepr client process does not establish the
   running server's configuration. Preserve server ownership, local-model,
   and cloud-disabled evidence before admitting local evaluation capacity.
   [Official FAQ](https://docs.ollama.com/faq#how-do-i-disable-ollama-cloud-features).

2. **Claude Code CLI reference.** Living documentation, accessed 2026-09-13.
   Empty `--tools` removes built-in model tools; MCP needs separate controls.
   `--safe-mode` disables ordinary customizations but explicitly preserves
   managed-policy hooks and certain command customizations. `--restricted`
   still loads managed settings. These flags do not prove an inert child.
   This changes immediate safety work; it does not enable a new capacity tier.
   [CLI flags](https://code.claude.com/docs/en/cli-reference#cli-flags).

3. **Claude paid-plan usage credits.** Article dated 2026-08-10, accessed
   2026-09-13. The former extra-usage URL redirects to a usage-credits article.
   Credits allow paid continuation beyond included usage, apply across Claude
   and Claude Code, and can be disabled. Keep the requirement for current
   authenticated paid-overage-off evidence. The terminology change does not
   prove that the provider's `extra_usage` JSON field changed; absent or
   unfamiliar metadata must remain ineligible. No account was checked here.
   [Manage usage credits](https://support.claude.com/en/articles/12429409-manage-usage-credits-for-paid-claude-plans).

4. **OpenRouter workspace budgets.** Living documentation, accessed
   2026-09-13. Workspace controls now document
   `include_byok_in_budgets`, including the Default workspace. BYOK inclusion
   is opt-in and measures the equivalent OpenRouter price. The same page
   explicitly says in-flight requests finish and can exceed the budget.
   Therefore, a workspace limit is useful evidence but cannot independently
   prove Deepr's hard total ceiling or an underlying provider's actual BYOK
   bill. Keep inference blocked and distinguish workspace and API-key controls.
   [Workspace budgets](https://openrouter.ai/docs/guides/features/workspaces/workspace-budgets).

5. **OpenRouter BYOK routing.** Living documentation, accessed 2026-09-13.
   Provider keys can be prioritized or retained as fallbacks. Default behavior
   can fall through to shared OpenRouter capacity; a provider setting can
   restrict that fallback. Consequently, a requested model/provider and
   an API-key limit do not by themselves freeze the billing route. Future
   fixtures must bind actual account-level BYOK posture and each attempted
   route. This research did not read or change a provider account.
   [BYOK documentation](https://openrouter.ai/docs/guides/overview/auth/byok).

6. **MCP 2026-07-28 release.** Published 2026-07-28, accessed 2026-09-13.
   The release introduces a stateless protocol core, per-request capability
   metadata, explicit discovery, and a formal extension system. Tasks move
   into an extension; Roots, Sampling, Logging, and legacy HTTP+SSE have a
   minimum twelve-month deprecation window. Deepr already documents both
   protocol eras. Preserve conformance and use explicit application handles
   for conversations/runs; transport sessions are not knowledge or workflow
   authority. Add extensions only for a demonstrated limitation.
   [Official release](https://blog.modelcontextprotocol.io/posts/2026-07-28/).

7. **Agent Plugins specification 1.0.0.** Published status and version
   confirmed on 2026-09-13; no publication date inferred. Portable components
   are Skills and MCP. A conforming client can support only one component
   type or one principal MCP transport, and independent component failures
   need not stop the rest of a plugin. Successful installation is therefore
   weaker than usable Deepr tools. Validate actual discovery and a bounded
   read-only call in each exact host before claiming compatibility.
   [Normative specification](https://agent-plugins.org/specification).

8. **Agent Skills specification.** Living specification, accessed
   2026-09-13. `SKILL.md` carries metadata and instructions, with optional
   scripts/resources. `allowed-tools` remains experimental and its support
   varies by host. Treat expert exports as instructions plus explicit
   dependencies. Their presence cannot authorize execution or demonstrate
   sandboxing. Retain Deepr's quarantine on Python/MCP skill execution and
   defer expert-maintained executable skills until measured value exists.
   [Specification](https://agentskills.io/specification).

9. **Open Knowledge Format 0.2.** Version confirmed in upstream main on
   2026-09-13; no immutable commit or publication date claimed in this note.
   The format remains Markdown/YAML, with permissive optional metadata.
   Full runtime receipts/verdicts, attester portability, and sandboxing are
   explicitly deferred. Deepr's derived OKF export and verification-gated
   import remain appropriate. A `verified` field must not become trusted
   reviewer identity, executable authority, or proof of correctness.
   [OKF specification](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md).

10. **Cloudflare Rules of Workflows.** Updated 2026-09-10, accessed
    2026-09-13. Steps are individually retryable; external effects must be
    idempotent. Deterministic step names, explicit state, and avoiding effects
    outside durable steps support recovery. The documentation itself warns
    that an external request can commit before a failure is observed.
    Apply those lessons to Deepr's current journal and parent transaction.
    A workflow engine does not remove the need for provider idempotency,
    conservative ambiguous settlement, or bounded retries, and does not
    justify deploying a second orchestrator.
    [Rules of Workflows](https://developers.cloudflare.com/workflows/build/rules-of-workflows/).

## Targeted Claude confinement finding

At inspection, README and Supported Surface describe Claude as the executable
plan adapter. The trigger is an otherwise eligible Claude dispatch on a
machine or account whose managed policy contains a `SessionStart` command hook.
The model needs no tool access to trigger a session lifecycle hook.

`_claude_argv` in `src/deepr/backends/plan_quota/adapters.py` passes safe mode,
empty built-in tools, empty strict MCP, and disabled persistence. The safety
gate in `safety.py` uses adapter properties and sanitized environment, with no
effective-policy proof. Its child environment retains home/config locations.
`cli_runner.py` and `process_launch.py` supply a scratch working directory and
owned process lifetime; they do not sandbox filesystem reads or outbound
network activity. Existing argv tests prove flag construction, not managed
hook suppression.

The official hooks documentation says session hooks run when a session starts
and that only managed-level `disableAllHooks` can disable managed hooks.
Managed configuration can arrive from files, MDM, or a server. Checking one
local file or adding ordinary `--settings` cannot establish complete absence.
[Hook disabling](https://code.claude.com/docs/en/hooks#disable-or-remove-hooks),
[session startup](https://code.claude.com/docs/en/hooks#sessionstart),
[managed settings and precedence](https://code.claude.com/docs/en/settings#settings-precedence).

This is a source-backed conditional defect, not a live exploit reproduction.
No assertion is made that the current machine has a managed hook. A hook's
precise effect depends on its configured command, but no-surprise-bills and
side-effect confinement are already unproven before that effect is known.

The smallest defensible correction is a fail-closed adapter block until
effective managed-policy and runtime containment can be proven before launch.
Regression coverage should establish that explicit selection, automatic
selection, and empty-environment calls cannot reach quota/account probing or
the runner. Do not replace this with a user acknowledgement or an assumed-safe
flag. Re-admission needs independent evidence about the exact runtime and
all policy sources, under zero paid dispatch.

## Resolved conflicts and remaining uncertainty

- Search snippets for OpenRouter workspace budgets can omit current optional
  BYOK inclusion. The opened page governs this report. The newer option still
  explicitly permits in-flight overshoot.
- Safe mode and an empty model tool list address different surfaces. The
  managed-hook exception is explicit upstream behavior, not merely an absence
  of safety documentation.
- Some workflow summaries use broad exactly-once language. The detailed
  retry guidance governs external effects, which can commit before a failed
  response and therefore need independent idempotency/reconciliation.
- No source here establishes current credential identity, included quota,
  account control, host compatibility, local-server ownership, or improved
  expert judgment for this installation. Each remains a separate runtime or
  experimental claim requiring its own saved evidence.
- No source warrants enabling paid inference, hidden fallback, automatic
  learning, remote control, or a new hosted runtime before the existing
  promotion gates. Research is complete when these decision-changing claims
  are resolved; another broad standards sweep would not advance v2.51.
