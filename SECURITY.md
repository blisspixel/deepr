# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 2.50.x  | Yes       |
| 2.49.x  | Yes       |
| < 2.49  | No        |

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
- Scheduled fleet heartbeat endpoints require public HTTPS, reject credentials
  and fragments, connect only to a prevalidated public address with environment
  proxies disabled, refuse redirects, and never log the secret-bearing target
- API key redaction in logs and error output
- Durable budget enforcement with per-operation and daily/monthly caps, append-only cost records,
  dispatch reservations, settlement checks, and a paid-dispatch freeze on ambiguous state
- Dependency audit (`pip-audit`, blocking in CI) and SBOM generation
- Pre-commit hooks (ruff lint, debug statement detection)
- Comprehensive automated test suite with an enforced coverage gate (see [ROADMAP](ROADMAP.md) for current counts)

**Scope note:** Deepr orchestrates bounded hosted model APIs, local Ollama, and
explicit plan-quota CLI backends. It does not train, fine-tune, or serve model
weights. Its security focus is ingested and untrusted data plus agentic tool use
(prompt injection, tool abuse, and trust boundaries), not model-internals attacks
(poisoning, weight extraction, and similar provider concerns). See the
"AI/agentic security" subsection of [ROADMAP](ROADMAP.md) for the planned
hardening and explicit non-goals.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for technical details.
