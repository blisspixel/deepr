# Structured memory generation in the existing rehearsal

2026-10-25. Bounded representativeness repair; no new live authority.

The original Qwen development and its separately reviewed budget-guidance
validation both stopped at the 4096-token synopsis ceiling with incomplete
JSON. All earlier outcomes remain retained. The guidance was delivered but
did not establish complete study, briefing, maintenance or answer capacity.

The shipped native local study adapter requests `response_format=json_object`
and refuses a `length` termination, even if the returned bytes happen to form
valid JSON. The rehearsal dispatcher currently omits both controls for memory
generation. It also serves answer generation, where forcing JSON would change
the requested answer form. Numerical differences between a frozen rehearsal
policy and production defaults are separate experimental choices.

Use the existing native backend's response-format mapping for construction and
maintenance only. Record that effective option in the existing call receipt.
Answer requests retain their current options and prose-capable behavior. A
structured response ending at its context or output bound remains refused,
including a syntactically complete JSON prefix.

Retain the exact raw response, digest, stop reason, prompt, generation options
and known token counts before surfacing the refusal. The native request still
returned; its payload admission failed. Keep those facts separate in the call
record. Do not duplicate terminal accounting or turn known usage into unknown
merely because the structured result was refused. Existing parser and stage
admission remain in force, with no salvage or retry.

This changes the existing worker recipe, so its execution identity must change.
Historical runs keep their original identities and are not resumed or relabeled.
The native transport, source materialization, four arms, model admission,
accounting and workbook seams remain shared. There is no second evaluator,
provider surface, automatic model fallback or new policy flag.

Verify native JSON-format delivery for construction and maintenance, its
absence for answers, rejection of a valid JSON response stopped by length,
retention of raw output and known usage, and unchanged answer/word-limit and
call-limit handling. Structural tests establish request form and refusal,
not source support, useful advice or successful capacity.

No generation is authorized by this repair. A later production-derived
capacity proposal must identify every deliberate difference: output ceiling,
context reserve, source chunking, sampling and thinking controls. It must
justify the complete call count and phase/total bounds prospectively, preserve
all failed configurations, and receive independent review. Copying a larger
production ceiling alone is insufficient. No previous run's limits may change,
and S0 final capacity and S1 gates remain unmet.
