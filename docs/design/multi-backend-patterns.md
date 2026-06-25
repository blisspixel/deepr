# Using the agentic-CLI fleet well: verification patterns, not round-robin

Status: design note, 2026-06-21. Grounded in a June-2026 literature sweep on
multi-model patterns. Cross-cuts the plan-quota CLI backends
([plan-quota-cli-backends.md](plan-quota-cli-backends.md)), the absorb
verification path, and the capacity waterfall. Read
[AGENTIC_BALANCE.md](../plans/AGENTIC_BALANCE.md) first - this note must not turn
Deepr into a generic orchestrator; it sharpens how Deepr uses execution capacity
to verify *its own* knowledge.

## 1. Selection today is validated, not round-robin

A common worry: are the subscription CLIs picked by dumb rotation? No.
`waterfall.py:_choose_plan_quota` selects a backend only when it is **installed**
(`shutil.which`) **and operator-admitted** for the task class **and** passes the
deterministic auth/billing safety gate (`evaluate_plan_quota_safety`: auth mode
is plan, no metered key would bill, billing acknowledged) **and** is not inside
an exhaustion cooldown. Exhaustion is **reset-aware**: an observed `EXHAUSTED`
event with a future `reset_at` blocks the backend; once the reset passes it
self-heals (`_exhaustion_cleared`). It picks one backend with a human-readable
reason - never blind rotation. (`deepr capacity probe-plan` additionally does a
real `$0`/quota round-trip to confirm a CLI actually works.)

**Honest limitation:** most vendor CLIs do **not** expose *remaining* quota
through the execution command, so "has quota" cannot be guessed from CLI
presence. Deepr detects exhaustion **reactively** for execution runs (parsing
vendor "try again in Nh" messages into a cooldown). The first proactive
metadata probe is Codex: `deepr capacity refresh-quota codex` reads local
session-log `rate_limits` and writes a trusted ledger event without a model
call. Other backends stay explicit or reactive until their own metadata probes
exist, which is why auto-routing onto a subscription stays opt-in
(`admit-plan`) and explicit `--plan` remains the works-now path.

## 2. The evidence: averaging adds cost, challenging adds truth

The ensemble intuition assumes model errors are *independent* so aggregation
cancels noise. The 2025-2026 evidence says that is **false for
generation/synthesis but true for verification** - and that split drives every
recommendation here:

- **Errors are correlated across models and vendors.** Models agree ~60% of the
  time *when both are wrong*; larger frontier models from different vendors have
  *more* correlated errors, not fewer ([Correlated Errors, ICML 2025](https://arxiv.org/abs/2506.07962)).
  "Consensus is not verification": no aggregation method beat a single sample
  even at 25x cost on truthfulness ([2026](https://arxiv.org/html/2603.06612)).
- **But a *different* model catches errors self-checking cannot.** Among items
  one model was confidently wrong on, only ~9.6% tripped a different-family model
  the same way ([Too Consistent to Detect, 2025](https://arxiv.org/pdf/2505.17656)).
  The residual independent slice is exactly where a cross-model *challenge*
  earns its keep - the difference between *averaging* (useless) and *adversarial
  checking* (valuable).

## 3. Pattern verdicts

| Pattern | Verdict | Why |
|---|---|---|
| **Fan-out ensemble / vote** (same task to all, compare) | **Avoid for synthesis** | Correlated errors -> voting adds cost not truth; mixing models loses to the single best (Self-MoA, [ICLR 2025](https://arxiv.org/abs/2502.00674)); self-consistency's edge has collapsed for capable models. |
| **Relay / sequential refine** (A -> B -> C polish) | **Only if grounded** | Feedback-free iteration *degrades* output and propagates early errors ([self-correct, ICLR 2024](https://arxiv.org/abs/2310.01798)); worth it only when each hop adds a grounded signal (retrieval/tools/tests), and the *last* hop is verification, not polish. |
| **Maker-checker** (different model verifies/refines) | **Build - highest ROI** | Exploits the independent error slice; cross-vendor + fresh-context + grounded is the one pattern that measurably catches wrong claims. |
| **Multi-agent debate** | **Skip** | Doesn't beat a single strong model + a skeptic; fragile to one confident-wrong agent dragging the group ([2025](https://arxiv.org/pdf/2511.07784), [Nature 2026](https://www.nature.com/articles/s41598-026-42705-7)). Its useful core *is* maker-checker. |

## 4. The Deepr design: cross-vendor maker-checker for belief verification

Deepr already routes the absorb-time contradiction/dedup decision into a model
verdict (`ReportAbsorber._verify_contradiction`, `verify_contradictions=True`).
That is the maker-checker seam. The research says four constraints make it
actually work; adopt them:

1. **Cross-vendor checker.** The checker must be a *different vendor/family* than
   the maker (Codex maker -> Claude checker, or vice versa). Self-preference bias
   is real (most models favor their own family independent of quality), and
   same-family errors correlate. Make vendor diversity a **routing requirement**,
   not a preference - which is deterministic (form), so it belongs in code, while
   the verdict itself stays model judgment (meaning) per AGENTIC_BALANCE.
2. **Fresh context.** The checker sees only `{claim, supporting evidence}`, never
   the maker's reasoning trace. Cross-context review beats same-session
   self-review even with the *same* model; the mechanism is information
   independence, and it's cheap (~5K tokens, not 50K).
3. **Disconfirm, don't rate.** Prompt the checker to find what is *wrong* /
   unsupported, not to score quality. The dominant failure mode is true-but-
   unsupported claims (post-hoc citation), so the check must test whether the
   evidence *entails* the claim.
4. **Bounded fan-out.** 1 maker + 1 cross-vendor checker by default; escalate to
   a 2nd *different-vendor* checker only on disagreement or a flagged high-stakes
   claim; stop at 2 (returns are convex - ~1 checker captures most of the gain).

Capacity behavior: each extra call spends quota/compute, so the checker runs on
plan/local capacity through the same waterfall and budget gate; cross-vendor
requires >=2 admitted vendors. When only one vendor (or only local) is available,
degrade to a **fresh-context same-model** check (weaker but still better than
self-review) and record the lower assurance - never silently skip verification,
never silently escalate to metered.

What this is **not**: Deepr is not orchestrating other vendors' agents through a
workflow. It is using execution capacity to verify *its own* extracted claims and
emit *one* verified result. The host still owns the outer workflow (not-the-
orchestrator non-goal holds).

## 5. Sequenced slices

1. **Cross-vendor + fresh-context checker** on the existing absorb verification:
   when >=2 vendors are admitted, route the contradiction/grounding verdict to a
   *different-vendor* backend with a claim+evidence-only prompt; record the
   checker identity + assurance level on the belief.
2. **Disconfirm-prompt + entailment focus**: reshape the verdict prompt to "find
   the unsupported part," reusing the entailment screen.
3. **Bounded escalation**: 2nd different-vendor checker only on disagreement /
   high-stakes; ledger the decision (folds into the targeted-spend gate).
4. **Assurance in the handoff contract**: surface "verified by N cross-vendor
   checkers" so host agents can weight a belief by how hard it was checked.

## 6. What NOT to build

- Fan-out-and-vote as a primary synthesis path (theater; correlated errors).
- Blind relay polishing (amplifies early errors).
- Multi-round debate (cost + persuasion-cascade fragility; no win over a single
  strong model + one cross-vendor skeptic).
- Same-family verification dressed up as "multi-model" (self-preference defeats
  the point).
- Any pattern that turns Deepr into the workflow owner across other agents.
