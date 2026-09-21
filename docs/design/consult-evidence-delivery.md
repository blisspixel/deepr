# Deliver retained evidence to the answering model

Status: repair in progress, 2026-09-20.

The Python exemplar examination exposed a mismatch between assembled context
and delivered context. A consultation retained roughly eleven thousand
characters of evidence, but council synthesis used the first thousand
characters of each perspective. The standing introduction displaced the
question's reasoning and source passages. A later whole-prompt slice could
also remove instructions or contributors. One-expert answers invented plural
agreements and disagreements under the mandatory council template.

Keep the existing one-call, read-only consultation and capacity boundaries.
Use a 16,000-character user-prompt ceiling. The 6,000-character diagnostic
still omitted question-relevant findings. Build a bounded prompt
from structured blocks, reserving the complete question, instructions, and
each contributing expert's identity before allocating evidence fairly. For a
briefed expert, interleave reasoned positions with findings and their source
passages. Retain dissent and revision conditions with the position. Do not
truncate a position into a stronger claim or silently omit a contributor.
Report omitted blocks. If the required request envelope cannot fit, refuse
before dispatch rather than silently shortening the question.

Rank selected findings by their relevance to the question before allocating
bounded passages. Keep a position's support available, but do not let sorted
finding identifiers give tangential material priority over direct evidence.
Match excerpts using the same whitespace/case normalization as study, then
deliver the original source bytes. Select a separate source window for each
finding; a shared shortened document can lose a later finding's support.

Also search the retained reference text directly, so an omitted study note does
not hide an available manual section. Bound this local lookup to 240,000
characters and four 1,400-character original windows. Text overlap routes
candidate passages only; it certifies neither relevance nor entailment. Deliver
these passages before compressed interpretations and disclose the lookup limit.
This is inspectable stored-reference access, not live search or a tool loop.

The local paths previously forced reasoning off. Preserve the installed model's
default instead, and bound local consultation output to 8,000 tokens so reasoning
does not have to compete with the answer inside a 1,200-token allowance. Keep
the existing elapsed-time refusal and truncated-output failure. Other capacity
budgets remain unchanged. Only final answer content is presented. This is a
quality hypothesis to test, not evidence of qualification.
[Runtime thinking behavior](https://github.com/ollama/ollama/blob/main/docs/capabilities/thinking.mdx)
and [compatible endpoint controls](https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx)
were checked on 2026-09-20.

The full consultation artifact remains inspectable. Its confidence field stays
compatible and does not become an expert accuracy probability. The model must
answer the actual question in a useful domain-specific form. Agreement and
disagreement describe evidence actually supplied; a single contributor does
not imply a panel or independent corroboration. Current checks cannot be
invented. This repair does not implement live preparation or semantic review
of every retained finding.

Successful dispatch records `context_delivery` in the consultation artifact:
the actual system and user prompts, user-prompt hash, character limit and count,
and `stored_context_only` freshness boundary. This additive record lets a
reviewer distinguish assembled research from delivered evidence. Omission
notices are part of the actual prompt. Old artifacts without this field have
no delivery receipt; do not infer that all of their context reached the model.

Verify delivery of evidence beyond the old prefix, preservation of complete
reasoning and dissent, bounded multi-expert allocation, explicit omissions,
oversized-request refusal before dispatch, and legacy belief-only packets.
Preserve the failed development examination, repeat it as a diagnostic after
repair, and use fresh questions to check transfer. Source and interpretation
errors need their own repair; successful transport does not certify advice.
