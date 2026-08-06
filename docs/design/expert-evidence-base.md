# Evidence base for the expert redesign

Status: research synthesis, 2026-08-05.
Feeds: [expert-v2-architecture.md](expert-v2-architecture.md), [expert-insight-layer.md](expert-insight-layer.md).

Three parallel literature reviews (expertise science, personal knowledge
management and learning science, LLM agent memory 2025-26) were run against the
v2 design. This records what the evidence **supports**, what it **contradicts**,
and what it says to **not build**. Claims are tiered: robust, contested, or
folk. Where the evidence goes against a design choice already made here, that is
recorded rather than smoothed over.

## 1. What the evidence supports

| Design choice | Supporting evidence |
|---|---|
| **Retain the corpus; never discard sources** | Irreversible lossy compaction compounds error super-linearly, while reversible schemes that keep raw copies stay near an error floor. Repeated summarization of summaries is a documented degradation mode ("context collapse", "brevity bias"). |
| **Do the expensive reasoning offline, on a schedule** | Sleep-time compute reports ~5x less test-time compute for equal accuracy and 2.5x lower cost per query when queries share a context. For a corpus queried repeatedly, write-time-heavy is the economically correct design. |
| **Anchor every finding to source spans** | Provenance is structurally unrecoverable after the fact. The dominant real-world failure diagnosis is not hallucination but "accurately reporting what is in the knowledge base". |
| **A study pass, not a summarization pass** | Summarization is rated *low utility* in the learning literature because quality is skill-dependent and the summarizer cannot judge its own output. Self-explanation, defined as generating inferences about causal connections, is g = 0.55. Elaborate causally; do not summarize. |
| **Findings proposed, admission gated separately** | Cross-document contradiction detection runs at ~70% precision in the best-documented system. Contradictions are candidates for review, never facts. |
| **Ungrounded findings labeled, not deleted** | Reference-free LLM evaluation is unreliable exactly where it matters; auto-deletion would apply an unreliable judgment irreversibly. |
| **Corpus, not belief store, is the study input** | Self-verification is circular: a model that writes a plausible-but-false claim will read it later, find it internally consistent, and certify it. Verification must be out-of-band. |

## 2. What the evidence contradicts, and what changes

### 2.1 Persona prompting does not improve factual accuracy

**This is the finding that most directly challenges the perspective-lens half of
the design.** Two independent studies:

- 162 personas across 6 relationship types and 8 expertise domains, 4 model
  families, 2,410 MMLU factual questions: no improvement over a no-persona
  control, with small negative effects. Notably, the 2023 preprint claimed
  personas "consistently improve" performance; the 2024 revision reversed it.
- A 2025 replication across two benchmarks: no accuracy improvement, no
  consistent benefit from expert personas, and domain-mismatched personas
  sometimes *degrade* performance.

**The honest reading.** Those studies measure *factual accuracy on questions
with known answers*. The perspective lenses here are not trying to answer a
factual question more accurately; they are trying to surface **different
content** from the same corpus. Those are different claims, and the evidence
does not settle the second one.

**But that is a hypothesis, not a defence.** The correct response is the one the
literature prescribes: benchmark the lens set against **N-sample self-consistency
from one strong model at matched token spend**. If six lenses do not beat six
samples of a single generic "report what matters here" prompt, the lens taxonomy
is buying cost rather than quality and should be cut to the interrogation axis.

**Action:** perspective lenses ship behind that comparison, not ahead of it. See
Section 4.

### 2.2 Diversity must come from inputs, not labels

Multi-agent debate largely reduces to ensembling: at a matched number of
responses it underperforms simple majority voting, and consensus-seeking debate
loses information through sycophancy, landing near the *average* of participants
rather than the best. The active ingredient is **diversity of evidence and
independence of errors**, not deliberation and not role assignment.

**Action:** lenses must differ in what they *read* and what they are *scored on*,
not only in how they are addressed. Where practical, vary the retrieval slice
per lens rather than sending every lens the identical corpus. Preserve
disagreement between lenses as an explicit output; never average it away.

### 2.3 Review matters more than capture, and nothing here forces review

Note-taking without review buys d = 0.22; the external-storage (review) function
outweighs the encoding function. Every documented knowledge-system graveyard is
a system where nothing forced re-encounter.

**Action, and it reorders the build:** a **lint pass** (contradictions, stale
claims, orphans, gaps) is not a later feature. *Build lint before building bulk
ingest.* A system that can ingest faster than it can lint is a graveyard
generator.

## 3. What the evidence says is missing from the design

These are gaps, not refinements. Each has strong support.

### 3.1 Conditionalization: the strongest single directive

Expert knowledge is indexed by its **conditions of applicability**, not stored as
free-floating propositions. Unconditionalized knowledge is *inert*: it is not
retrieved when needed. The decisive illustration is that "too many cooks spoil
the broth" and "many hands make light work" are both true and contradict each
other as bare propositions; the expertise is entirely in knowing which applies
when.

A corpus of true claims without applicability conditions is therefore not merely
incomplete, it is **internally inconsistent by construction**. Deepr's belief
records carry confidence, trust class, and provenance, but no conditions.

**Required:** every stored claim carries when it applies, when it does not, what
would make it not apply, and which competing claim applies instead.

### 3.2 Expectancies, so anomalies are computable

Expert noticing is **violated expectancy**, not statistical outlier detection.
The problem-detection literature explicitly warns that analytic outlier tools
"flag irrelevant outliers and miss important ones" because they are insensitive
to the cognitive dimension. Detecting a problem is frequently equivalent to
*reconceptualizing the situation*, not accumulating discrepancies past a
threshold.

**Required for the scheduled/triggered guidance the operator asked for:** an
expert that can only retrieve cannot notice. To notice, it must hold, per
situation type, what should be true, what should happen next, and what would be
surprising. Then a watch pass is a diff against the expectancy set.

### 3.3 Negative knowledge as a first-class type

Minsky's structural argument: competence often consists of *never making a
mistake*, this knowledge **never appears in behavior**, and rule-based systems
encode everything as "IF X, DO Y" and therefore cannot represent it at all.
Later work defines negative knowledge as experientially acquired knowledge of
what is wrong and to be avoided, and ties its development to post-action
reflection.

The `failure` lens partially reaches this, but it currently produces failure
*modes* observed in sources, not the "plausible move that is wrong" class.

**Required:** an explicit ask, with its own shape: the tempting action, why it is
wrong, what to do instead. It will not be recovered by summarizing successes.

### 3.4 Separate strategy from domain content

The MYCIN lesson: rules conflated diagnostic strategy, taxonomy, causal
knowledge, and world facts, which is why the system could recite a rule and
still not explain anything. NEOMYCIN separated them into four layers. **A system
whose knowledge is one undifferentiated pile of retrieved text is
architecturally MYCIN.**

### 3.5 A validity layer, scored per task and never per expert

Skilled intuition requires (a) an environment regular enough to provide valid
cues and (b) adequate opportunity to learn them through rapid, unequivocal
feedback. Where those fail, confident output reproduces luck. Expertise
**fractionates**: the same professional is expert at one sub-task and not at an
adjacent one, and neither they nor observers can easily locate the boundary.

There is a ready-made checklist: stimulus stability (static vs dynamic), physical
vs behavioral system, expert consensus on cues, predictability, feedback
availability, decomposability.

**Required:** score the *sub-task*, not the domain and never the expert. And
attach operating characteristics rather than a confidence number, because
subjective confidence tracks the internal consistency of the evidence rather
than its quality: "evidence that is both redundant and flimsy tends to produce
judgments held with too much confidence."

This is the sharpest available critique of Deepr's existing confidence field.

### 3.6 Declare the audience before ingesting

Learning-by-teaching effects roughly double when the obligation to teach is set
**before** study rather than after (g ≈ 0.48 vs 0.27); set afterwards, the effect
largely disappears. An expert built from an undeclared corpus with no audience
is built under the weak condition.

Deepr has `expert blueprint` for operator-attested purpose; only a small
minority of experts have one. **Required:** purpose declared before ingest, and
used as an input to the study pass rather than as documentation after the fact.

### 3.7 Keep both the compressed and uncompressed form

Human expertise **encapsulates**: causal chains compress into compact scripts and
the intermediate steps become genuinely inaccessible, which is why experts are
fast and also why they explain badly. Software has no such constraint and should
keep both: the compressed form for recognition, the chain for explanation and
for atypical cases.

### 3.8 Multiple representations, deliberately

Complex knowledge is systematically over-simplified in predictable ways
(treating interacting parts as additive, continuous processes as discrete,
interdependent elements as isolated). The prescribed remedy is **multiple
representations rather than one tidy model**, precisely because a single
representation invites over-trust.

This is independent support for the lens design, from a different literature
than the persona studies that challenge it.

## 4. Do not build

Each of these is attractive and specifically unsupported or harmful.

1. **Resonance-based highlighting / progressive summarization.** The core
   operation is highlighting, the one technique with evidence of *harm* to
   inference, wrapped in a compounding-loss compression chain.
2. **Self-linting presented as verification.** Circular by construction.
   Verification must be out-of-band.
3. **Atomic-note granularity as a quality target.** No evidence. Choose
   granularity for retrieval and revision cost, and say that is why.
4. **Graph visualization or link counts as health.** Emergent-structure-from-links
   is an untested folk claim.
5. **A Dreyfus-style expert maturity ladder.** No evidence for discrete stages;
   its central claim is contradicted by the data. It is the most popular and
   least supported framework in the field.
6. **Spaced repetition of an artifact as if it were a learner.** Files do not
   forget. Scheduled re-encounter is justified as staleness detection and
   revision, not retention.
7. **Periodic whole-store re-summarization.** Produces brevity bias and context
   collapse. Use append-plus-curate with deterministic merge.
8. **Citing agent-memory benchmark numbers to justify architecture.** In the
   most-used benchmark, an audit found 6.4% of the answer key wrong and the
   judge accepting ~63% of deliberately incorrect answers; two vendors published
   three incompatible numbers for the same system.
9. **Artifact size as a success metric.** Report questions answered that the
   corpus alone could not answer, contradictions surfaced, claims that failed
   verification, staleness backlog.

## 5. Failures of aggregation, not collection

A fourth review covered analytic tradecraft: intelligence analysis, think
tanks, forecasting tournaments, and the post-mortems of documented failures. Its
central finding reframes the problem.

**In every documented failure examined, the raw material for the correct answer
was already inside the system.** The State/INR and DOE dissents in the 2002 Iraq
NIE were written down and were right. Curveball's unreliability was known to
some. In the hidden-profile experiments, groups collectively held enough
information to find the optimal answer and did not surface it.

The failures were failures of **aggregation, propagation, and revision**, not of
collection.

That is exactly where a persistent-expert system sits. Worse, it reproduces at
least two of the documented mechanisms **by construction unless built against**.

### 5.1 Shared-information bias is reproduced for free by retrieval

Across 65 studies and 3,189 groups, groups mention roughly two standard
deviations more commonly-held than uniquely-held information, and are **eight
times less likely** to reach the correct answer when the decisive evidence is
held by only one member. The mechanism requires no bias and no motive: shared
information simply has more chances to surface. **Communication medium had no
effect**, so a better interface does not fix it.

Relevance-ranked retrieval is that sampling process. It surfaces what is
well-represented and buries the singleton document that changes the conclusion.

The meta-analysis found that the stronger predictor of decision quality was
**information coverage** - breadth of distinct evidence touched - not depth of
the top matches.

**Required:** measure and report coverage of the corpus per study pass, and
deliberately surface singleton evidence (claims appearing in exactly one source)
rather than letting frequency decide. Report what the pass never touched.

### 5.2 Confidence rises with volume while accuracy does not

Heuer's horse-race handicapper study: given progressively more information,
experts "expressed steadily increasing confidence in their judgments as more
information was received" while accuracy did not improve.

**Required, as a testable invariant:** ingesting more redundant corpus must not
raise stated confidence. Confidence must be a function of the evidence graph -
distinct roots, their independence, agreement, contradiction - never of
retrieval volume or corpus size.

### 5.3 Provenance depth, not citation count

The WMD Commission found daily products left readers with "an impression of many
corroborating reports where in fact there were very few sources." The
information-cascade model formalizes why: once a cascade starts, private
information stops entering the record, so an apparent consensus can rest on the
first few signals. **Stability of a consensus is not evidence of its evidential
depth.**

**Required:** count distinct evidentiary **roots**, not citing documents. Flag a
heavily-cited belief whose root cardinality is one or two. A corpus full of
secondary coverage will trip this constantly, which is the point.

### 5.4 Uncertainty must compose through every derivation

The Butler Review found "a risk of over-cautious or worst case estimates,
**shorn of their caveats, becoming the 'prevailing wisdom'**." The Senate
committee named the same thing "layering": assessments built on previous
judgments "without carrying forward the uncertainties of the underlying
judgments."

Both inquiries are explicit that layering itself is legitimate and useful. The
failure is uncarried uncertainty.

**Required:** a derived claim can never be more confident than its weakest
premise, enforced at write time. Do not ban derivation; instrument it.

### 5.5 Challenge harder as confidence rises

Groups with **unanimous** prior preferences failed hidden profiles at an odds
ratio of **17.09**, against 2.62 for weakly-held ones. The Senate committee found
the presumption of Iraqi WMD "was so strong that formalized IC mechanisms
established to challenge assumptions and group think were not utilized."

**Required, and it inverts the natural design:** high-confidence, long-held,
frequently-reinforced beliefs get *more* challenge budget, not less. The obvious
implementation skips them.

### 5.6 Generate independently; never deliberate first

The strongest finding in the group-process literature. Imposing turn-taking on
individuals working *alone in separate cubicles* destroyed their advantage over
groups, isolating **production blocking** as the cause rather than social
loafing. Delay between having an idea and being able to voice it causes
suppression and forgetting, and damages the organization of idea generation, not
just throughput.

Independently, social influence reliably collapses estimate diversity without
improving accuracy, while raising confidence. The moderator is **topology**:
uniform decentralized influence converges toward truth; **centralized influence
converges toward the anchor**.

**This validates the current lens design and constrains its future.** Lenses run
independently over the same corpus with no cross-talk, which is correct. It also
means: **an orchestrator that summarizes lens output and rebroadcasts it is the
centralized failure topology.** Do not add a synthesis round that feeds lens
output back to lenses.

**Also measurable:** log dispersion, accuracy where resolvable, and stated
confidence per round. The failure signature is spread falling while error stays
flat and confidence rises.

### 5.7 Communicating uncertainty: the one finding to implement verbatim

N=924, four presentation formats for a probability lexicon:

| Format | Reader's range matched the intended one |
|---|---|
| Words only ("very unlikely") | 32% |
| Tooltip on hover | 40% |
| Table behind a link | 39% |
| **Inline: "very unlikely (05-20%)"** | **66%** |

Only the inline form was significantly better. Roughly half of readers never
opened the linked table, and those who did used it for two of eight items.
**Optional access to a lexicon is equivalent to no lexicon.**

Separately, probability and confidence are routinely conflated, and the
conflation destroys decision-relevant information: "between 0 and 100 percent"
and "50 percent" argue for different actions, and collapsing them loses that.

**Required:** render numeric bands inline with every estimative word, and keep
probability and evidential confidence as two fields, always.

### 5.8 Structured analytic techniques are convention, not validated method

Worth stating because it is tempting to import the whole toolkit. Reviews of the
twelve core techniques find mixed results for Analysis of Competing Hypotheses,
and brainstorming and A/B teaming largely ineffective at mitigating bias. A
2018 assessment concluded "no one knows how close the current generation of SATs
comes to achieving either" bias or noise reduction.

The famous Team A / Team B exercise is routinely cited *for* red-teaming; the
record supports the opposite reading. The panel was selected for its prior, given
an explicit advocacy mandate, worked under time pressure, was judged against no
scoring rule, and produced confident error with the *appearance* of adversarial
rigor.

**Borrow these as interface designs and forcing functions. Do not assume the
benefit, and do not cite them as validated.**

### 5.9 Scoring must use a proper rule and separate calibration from resolution

A scoring rule is *proper* when a forecaster maximizes their expected score by
reporting their true belief. An improper rule creates an incentive to misreport.

Brier decomposes as reliability minus resolution plus uncertainty. A forecaster
who always states the base rate is perfectly calibrated and useless: resolution
is zero. **A forecast is useful only when resolution exceeds reliability.**

The negative result that matters: a randomized trial found bare performance
feedback **did not improve calibration on harder cases**, because participants
confronted with mistakes lowered confidence indiscriminately. **A naive "here is
your score" loop trains hedging - it improves apparent calibration by destroying
resolution.**

Also: uncertainty is a property of the *question*, not the expert, so scores are
not comparable across question sets without standardizing within question.

### 5.10 Do not claim

Added to the do-not-build list in Section 4, a set of claims that are widely
repeated and do not survive scrutiny. Deepr's documentation must not assert:

- That diversity provably trumps ability. The theorem is real but narrow,
  required patching after a published counterexample, is highly sensitive to
  problem structure, and concerns functional rather than demographic diversity.
- That diversity *causes* lower collective error. The prediction theorem is an
  algebraic identity; empirically, diversity and error have shown no significant
  correlation across three experiments.
- That Team B validates red-teaming.
- That structured analytic techniques are validated.
- That superforecasters beat professional analysts by 30 percent. That figure
  came from a newspaper attribution and did not survive the tournament's final
  year.

## 6. The limit to state plainly

The cues that most distinguish experts are, empirically, **absent from the
literature of their own field**. The canonical demonstration elicited an
early-sepsis assessment guide from expert nurses containing "information not
available in the current literature", and it took incident-anchored interviewing
to get it. Negative knowledge leaves no trace in records of practice, because
averted problems generate no reports.

Separately, documents are overwhelmingly *retrospective explanation*, which is
the report genre with the worst established validity: people lack introspective
access to their own processes and substitute plausible causal theories. Anything
a corpus says about *why* someone did something is a hypothesis about causes,
not data.

**Therefore:** a document-built expert can be an excellent conditionalized,
deep-structure-indexed, expectancy-bearing case library with an honest validity
model. That is genuinely valuable. It is not the same thing as a human expert,
and Deepr should not claim it is. Where the environment is irregular, cues are
invalid, or feedback is absent, the correct behavior is to **decline to be an
expert** and instead surface base rates, comparison classes, and a range of
outcomes.
