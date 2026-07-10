# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 2.34.x  | Yes       |
| < 2.34  | No        |

## Reporting a Vulnerability

**Do not report security vulnerabilities via public GitHub issues.**

Email [nick@pueo.io](mailto:nick@pueo.io) with:

1. Description of the vulnerability
2. Steps to reproduce
3. Potential impact
4. Suggested fix (if any)

You should receive a response within 72 hours. Critical issues will be patched and released as soon as possible.

## Security Measures

Deepr includes:

- Input validation and request sanitization
- Prompt-injection detection/sanitization (`utils/prompt_security.PromptSanitizer`)
- SSRF protection on user-supplied URLs
- API key redaction in logs and error output
- Budget enforcement to prevent runaway spend (per-operation + daily/monthly caps, approval tiers)
- Dependency audit (`pip-audit`, blocking in CI) and SBOM generation
- Pre-commit hooks (ruff lint, debug statement detection)
- Comprehensive automated test suite with an enforced coverage gate (see [ROADMAP](ROADMAP.md) for current counts)

**Scope note:** Deepr orchestrates *hosted* model APIs; it does not train, fine-tune,
or serve model weights. Its security focus is therefore ingested/untrusted data and
agentic tool use (prompt injection, tool-abuse, trust boundaries), not model-internals
attacks (poisoning, weight extraction, etc.), which belong to the model providers. See
the "AI/agentic security" subsection of [ROADMAP](ROADMAP.md) for the planned hardening
and the explicit non-goals.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for technical details.
