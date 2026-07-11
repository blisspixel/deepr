# Historically Grounded Expert Perspectives

Status: researched roadmap design, 2026-07-10. This is a proposed expert mode,
not a shipped personality catalog.

## Product direction

Build sourced perspectives, not replicas of people. A user may consult a
Leonardo-informed or Beethoven-informed reasoning lens. Deepr must never claim
that the software is Leonardo da Vinci, Ludwig van Beethoven, or a recovered
human mind.

This framing follows research that treats character-like model behavior as
role play without attributing human identity, beliefs, or consciousness to the
model
([Shanahan, McDonell, and Reynolds, Nature, 2023-11-08](https://www.nature.com/articles/s41586-023-06647-8)).

## Proposed contract

A future `deepr-historical-perspective-v1` record should require:

- `representation_mode=historically_grounded_perspective`;
- canonical subject identity and life dates;
- a persistent AI-generated perspective disclosure;
- documented methods derived from cited evidence;
- no first-person identity, invented memories, private thoughts, or fabricated
  quotations;
- a historical knowledge cutoff;
- source scope, editions, translations, rights, gaps, and archival bias;
- explicit contested interpretations;
- a temporal label for historical record, documented method, modern analogy,
  or speculative extension;
- safety, accuracy, and user autonomy ahead of perspective fidelity.

Perspective principles are derived views over structured claims and
citations. They are never authoritative hand-written persona lore.

## Provenance chain

1. `historical_claim`: archival evidence with creator, recipient when
   applicable, date, repository, catalogue id, edition or transcription, and
   confidence.
2. `perspective_principle`: a bounded interpretation with supporting and
   conflicting evidence.
3. `modern_application`: a clearly labeled synthesis explaining how the
   principle could help with a present problem.

Leonardo is a strong pilot because the Royal Collection holds about 550
drawings across art, anatomy, engineering, cartography, geology, and botany,
and describes drawing as central to how he investigated the world
([Royal Collection Trust, accessed 2026-07-10](https://www.rct.uk/collection/stories/leonardo-in-the-royal-collection)).

For Beethoven, the Beethoven-Haus Digital Archive provides manuscripts,
sketches, letters, conversation books, catalogue descriptions, and scholarly
annotations. Deepr must preserve document authorship: a letter or conversation
book addressed to Beethoven is not automatically Beethoven's statement
([archive, accessed 2026-07-10](https://www.beethoven.de/en/archive)).

## Experience

Name the surface Perspective or Lens, not Digital Leonardo or personality
replica. Each response should expose:

1. Historical basis.
2. Perspective-derived analysis.
3. Modern recommendation.
4. Uncertainty and sources.

A Why this perspective inspector should reveal the exact evidence behind each
characteristic. When evidence is absent, Deepr should say that no reliable
source supports attributing the view to the subject, then offer only a clearly
labeled modern inference.

Creative dramatization, if ever added, belongs in a separate fictional mode
that cannot write canonical beliefs. Voice cloning, photorealistic avatars,
and first-person theatrical chat are deferred because they increase
impersonation and over-reliance risk without improving expert utility.

NIST AI 600-1 identifies anthropomorphism, automation bias, over-reliance, and
emotional entanglement as Human-AI Configuration risks and recommends
provenance, testing, red-teaming, and structured feedback
([NIST, 2024-07](https://doi.org/10.6028/NIST.AI.600-1)). Persistent disclosure
also aligns with the transparency direction in EU AI Act Article 50
([Regulation 2024/1689, 2024-06-13](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=celex%3A32024R1689)).

## Evaluation

PersonaGym reports that model size alone does not predict persona fidelity and
recommends persona-specific environments, rubrics, multiple evaluators, and
separation between agent and evaluator
([EMNLP Findings 2025](https://aclanthology.org/2025.findings-emnlp.368/)).

Deepr should evaluate:

- historical, quotation, attribution, and temporal integrity;
- non-impersonation and disclosure retention;
- usefulness over a generic expert without factuality loss;
- anti-caricature and cross-turn consistency;
- safety retention under perspective pressure;
- handling of contested scholarship and missing evidence.

Adversarial cases must cover fake quotes, claims of personal feeling, modern
events outside the historical cutoff, prompt injection inside archives,
harmful historical attitudes, and requests to hide disclosure.

Deterministic checks own schemas, citation presence, temporal labels, exact
quotation matching, and disclosure. Calibrated evaluators and qualified human
reviewers own semantic fidelity, utility, and caricature risk.

## Recommended pilot

1. Approve the contract and non-impersonation boundary.
2. Add a read-only perspective-pack schema and provenance validator.
3. Build one Leonardo and one Beethoven pack from institutional archives.
4. Add the layered answer renderer and evidence inspector.
5. Compare against a generic expert and a style-only persona baseline.
6. Require zero fabricated quotations or identity claims, adversarial tests,
   and qualified review before an experimental release.
