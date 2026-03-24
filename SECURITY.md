# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 2.9.x   | Yes       |
| < 2.9   | No        |

## Reporting a Vulnerability

**Do not open a public issue for security vulnerabilities.**

Please report security issues by emailing [nick@pueo.io](mailto:nick@pueo.io) with:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

You should receive an acknowledgment within 72 hours. Fixes for confirmed vulnerabilities will be released as patch versions.

## Security Measures

Deepr includes several security layers:

- **Input validation** on all CLI and API inputs
- **SSRF protection** for URL-based operations
- **API key redaction** in logs and error messages
- **Budget enforcement** to prevent runaway spend
- **Pre-commit hooks** running ruff lint and debug statement detection
- **4300+ tests** (Python 3.12) including security-focused test markers

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for technical security details.
