# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 2.9.x   | Yes       |
| < 2.9   | No        |

## Reporting a Vulnerability

**Do not report security vulnerabilities through public GitHub issues.**

Email [nick@pueo.io](mailto:nick@pueo.io) with:

- Description of the vulnerability
- Steps to reproduce
- Affected versions
- Any potential impact assessment

You should receive a response within 72 hours. If the issue is confirmed, a fix will be released as a patch version and credited in the changelog (unless you prefer to remain anonymous).

## Scope

Security-relevant areas of Deepr include:

- **API key handling** — Keys are stored in `.env` (gitignored) and redacted from logs and traces
- **Input validation** — All user input is validated before use in API calls or file operations
- **SSRF protection** — URL inputs are validated against allowlists
- **Cost controls** — Budget enforcement prevents runaway API spend
- **Web dashboard** — CORS, security headers, input sanitization
- **MCP server** — Tool authorization, budget propagation, trace isolation

## Hardening

- Run `deepr doctor` to verify your configuration
- Set `DEEPR_COST_TRACKING_STRICT=1` for fail-fast cost safety
- Use `--budget` flags to cap spend on all operations
- Review `docs/ARCHITECTURE.md` for the full security model
