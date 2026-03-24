# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 2.9.x   | Yes       |
| < 2.9   | No        |

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
- SSRF protection on user-supplied URLs
- API key redaction in logs and error output
- Budget enforcement to prevent runaway spend
- Pre-commit hooks (ruff lint, debug statement detection)
- 4300+ tests (Python 3.12)

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for technical details.
