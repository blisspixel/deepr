# Expert creation testing

Test expert creation without provider calls:

```bash
pytest tests/unit/test_cli/test_expert_commands.py -q
pytest tests/unit/test_experts/test_expert_profile.py -q
pytest tests/unit/test_experts/test_synthesis.py -q
```

Use temporary expert roots and mocked local/plan backends. Validate that:

- `expert make --local` creates the expected structured profile;
- source and belief state stays under the configured expert root;
- generated digests and memory cards are derived views;
- malformed or unverified input cannot write canonical beliefs;
- provider construction does not occur on a blocked metered path;
- cleanup affects only the isolated test root.

Do not use generic nonlocal `expert make`, `--learn`, API resume/refresh,
standalone metered chat, hosted vector stores, or paid gap filling as v2.36
acceptance tests. Those surfaces intentionally fail closed until they share the
durable per-call and parent-run accounting transaction.

Optional local Ollama dogfood must be explicit, `$0` inside Deepr, isolated from
normal expert state, and tolerant of a durable `busy`/waiting outcome.
